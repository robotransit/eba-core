# eck/critic.py
"""Critic subsystem (ADR-022–024).

Evaluates task outcomes and returns a typed CriticOutcome plus optional
PartialStructure for consumption by the confidence signal processor (ADR-025).

Design:
- When ExecutionResult.performed=False, the critic short-circuits immediately
  without calling the LLM. The refusal_reason is mapped deterministically to
  "deferred" (no valid proposal) or "rejected" (gate/kernel refusal).
  confidence.update() will be called but produces no change — rejected/
  deferred categories carry no confidence signal per ADR-021.
- When ExecutionResult.performed=True, the LLM evaluates result.outcome.
- LLM reports outcome quality (success/failure) + severity [0.0, 1.0]
  plus bounded structural fields (conflict_kind, conflict_footprint)
- Kernel derives category (success/partial/failure) from outcome + severity
- LLM never sees "partial" — category is kernel-controlled
- PartialStructure constructed by kernel iff derived category is "partial"
- All downstream confidence mechanics remain kernel authority
- CriticOutcome, PartialStructure, and ExecutionResult imported from
  eck.types (single source of truth)

Invariant:
  partial_structure is not None iff critic_outcome.category == "partial"

Refusal mapping (performed=False):
  refusal_reason == "no_valid_proposal"  → category "deferred"
  refusal_reason starts with "gate:"     → category "rejected"
  all other refusal reasons              → category "rejected"
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Literal, Optional

from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticCategory,
    CriticOutcome,
    ExecutionResult,
    PartialStructure,
    make_critic_outcome,
)

logger = logging.getLogger("eck-core")

# Severity floor below which a failure is promoted to partial (ADR-022).
# Configurable — default 0.5. Above this: failure category.
# Below this: partial category (both confidence directions permitted,
# no failure window triggered).
_DEFAULT_PARTIAL_THRESHOLD = 0.5

# Normalisation fallbacks for malformed or missing partial structure fields.
# These are the most conservative values — RESOLUTION_INSTABILITY maps to
# MovementClass.NEITHER (no confidence movement in either direction).
_FALLBACK_CONFLICT_KIND = ConflictKind.RESOLUTION_INSTABILITY
_FALLBACK_CONFLICT_FOOTPRINT = frozenset({ConflictLocus.LOCAL})

# Closed vocabulary maps for kernel normalisation of LLM string fields.
_CONFLICT_KIND_MAP: dict[str, ConflictKind] = {
    "evidence_conflict": ConflictKind.EVIDENCE_CONFLICT,
    "constraint_conflict": ConflictKind.CONSTRAINT_CONFLICT,
    "decomposition_conflict": ConflictKind.DECOMPOSITION_CONFLICT,
    "resolution_instability": ConflictKind.RESOLUTION_INSTABILITY,
}

_CONFLICT_LOCUS_MAP: dict[str, ConflictLocus] = {
    "factual": ConflictLocus.FACTUAL,
    "instruction": ConflictLocus.INSTRUCTION,
    "format": ConflictLocus.FORMAT,
    "consistency": ConflictLocus.CONSISTENCY,
    "local": ConflictLocus.LOCAL,
    "global": ConflictLocus.GLOBAL,
}


def _map_refusal_to_category(reason: str | None) -> Literal["rejected", "deferred"]:
    """
    Deterministically map an ExecutionResult refusal_reason to a
    CriticOutcome category.

    Mapping (ADR-042 / ADR-022):
      "no_valid_proposal"       → "deferred"  (no proposal produced)
      reason starts with "gate:" → "rejected"  (gate refused)
      all other reasons          → "rejected"  (kernel refused)

    Never raises — always returns a valid category string.
    """
    if reason == "no_valid_proposal":
        return "deferred"
    if reason and reason.startswith("gate:"):
        return "rejected"
    return "rejected"


def critic_evaluate(
    task_text: str,
    prediction: str,
    result: ExecutionResult,
    objective: str,
    llm_call: Callable[[str], str],
    enable_cross_validation: bool = True,
    verifier_callback: Optional[Callable[[str, str], bool]] = None,
    partial_threshold: float = _DEFAULT_PARTIAL_THRESHOLD,
) -> tuple[CriticOutcome, PartialStructure | None]:
    """
    Evaluate task result and return a typed CriticOutcome plus optional
    PartialStructure (ADR-022).

    When result.performed=False, the critic short-circuits immediately:
      - no LLM call is made
      - refusal_reason is mapped deterministically to "deferred" or "rejected"
      - severity is 0.0
      - partial_structure is None
      - confidence.update() will be called but produces no change — rejected/
        deferred categories carry no confidence signal per ADR-021

    When result.performed=True, the LLM evaluates result.outcome normally.
    The LLM reports outcome quality (success/failure), severity, and bounded
    structural fields. The kernel derives the final category and constructs
    the authoritative PartialStructure — the LLM never controls failure window
    suppression, confidence gate semantics, or movement class directly.

    Invariant: partial_structure is not None iff outcome.category == "partial"

    Cross-validation disagreement is determined at the level of derived
    category, not raw LLM outcome token. Two calls returning the same raw
    outcome ("failure") but with severities that derive to different categories
    (e.g. "partial" vs "failure") count as disagreement. This is intentional:
    category is the kernel-relevant abstraction, and disagreement at category
    level is what matters for confidence dynamics.

    On disagreement, severity is clamped to 1.0 but category is preserved from
    the first call (ADR-022 invariant). A would-be partial outcome stays partial
    even under disagreement — the severity escalation signals reduced confidence
    in the partial assessment without overriding the category. PartialStructure
    is taken from the first call when category is partial.

    Pessimistic fallback on any parse failure: failure category,
    severity=1.0, partial_structure=None (ADR-022 refusal-over-fabrication).

    Args:
        task_text: The task description.
        prediction: Predicted outcome.
        result: ExecutionResult from the execution boundary (ADR-042).
        objective: Overall goal.
        llm_call: Callable that takes a prompt and returns an LLM response.
        enable_cross_validation: If True, use dual critic calls for consensus.
        verifier_callback: Optional external verification hook.
        partial_threshold: Severity floor below which failure → partial category.

    Returns:
        Tuple of (CriticOutcome, PartialStructure | None).
        PartialStructure is not None iff category is "partial".
    """
    # ── Short-circuit on non-performed execution (ADR-042) ────────────────────
    # No LLM call, no partial structure, no confidence update path.
    # Category is derived deterministically from refusal_reason.
    if not result.performed:
        category: CriticCategory = _map_refusal_to_category(result.refusal_reason)
        feedback = result.refusal_reason or "Execution refused"
        logger.info(
            "Critic short-circuit — execution not performed",
            extra={
                "category": category,
                "refusal_reason": result.refusal_reason,
            },
        )
        return make_critic_outcome(
            category=category,
            severity=0.0,
            feedback=feedback,
        ), None

    # ── Performed path — LLM evaluation of result.outcome ────────────────────
    prompt = _build_prompt(task_text, prediction, result.outcome, objective)

    # First critic call
    raw1 = llm_call(prompt)
    outcome1, severity1, feedback1, raw_kind1, raw_footprint1 = _parse_critic_response(raw1)

    # Derive category from first call before any severity modification.
    category1: CriticCategory = _derive_category(outcome1, severity1, partial_threshold)

    if not enable_cross_validation:
        category = category1
        final_severity = _clamp(severity1)
        final_feedback = feedback1
        final_raw_kind = raw_kind1
        final_raw_footprint = raw_footprint1
    else:
        # Second critic call for consensus
        raw2 = llm_call(prompt)
        outcome2, severity2, feedback2, raw_kind2, raw_footprint2 = _parse_critic_response(raw2)

        category2: CriticCategory = _derive_category(outcome2, severity2, partial_threshold)

        if category1 != category2:
            logger.warning(
                "Critic disagreement detected",
                extra={
                    "outcome1": outcome1,
                    "outcome2": outcome2,
                    "severity1": severity1,
                    "severity2": severity2,
                    "category1": category1,
                    "category2": category2,
                },
            )
            category = category1
            final_severity = 1.0
            final_feedback = f"{feedback1} | Disagreement: {feedback2}"
            final_raw_kind = raw_kind1
            final_raw_footprint = raw_footprint1
        else:
            category = category1
            final_severity = _clamp((severity1 + severity2) / 2.0)
            final_feedback = f"{feedback1} | Consensus: {feedback2}"
            final_raw_kind = raw_kind1
            final_raw_footprint = raw_footprint1

    # Optional external verification hook — can only demote to failure (ADR-022)
    if verifier_callback is not None:
        if not verifier_callback(task_text, result.outcome):
            prior_category = category
            category = "failure"
            final_severity = 1.0
            final_feedback += " | External verification failed"
            logger.info(
                "External verifier demoted outcome to failure",
                extra={
                    "task_text": task_text[:80],
                    "prior_category": prior_category,
                },
            )

    # Construct PartialStructure iff derived category is "partial" (invariant)
    partial_structure: PartialStructure | None = None
    if category == "partial":
        partial_structure = _derive_partial_structure(final_raw_kind, final_raw_footprint)

    logger.info(
        "Critic outcome",
        extra={
            "category": category,
            "severity": final_severity,
            "cross_validation": enable_cross_validation,
            "partial_structure": {
                "conflict_kind": partial_structure.conflict_kind.name,
                "conflict_footprint": sorted([
                    locus.name for locus in partial_structure.conflict_footprint
                ]),
            } if partial_structure else None,
        },
    )

    return make_critic_outcome(
        category=category,
        severity=final_severity,
        feedback=final_feedback,
    ), partial_structure


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_prompt(
    task_text: str,
    prediction: str,
    outcome: str,
    objective: str,
) -> str:
    """
    Build the critic evaluation prompt.

    Accepts outcome string directly — called only on the performed path
    where result.outcome is the execution result string.
    """
    return f"""Evaluate the result against the task and objective.

Task: {task_text}
Prediction: {prediction}
Result: {outcome}
Objective: {objective}

Return ONLY valid JSON with exactly these fields:
{{
  "outcome": "success" or "failure",
  "severity": <float 0.0 to 1.0>,
  "feedback": "<brief explanation>",
  "conflict_kind": "resolution_instability" or "evidence_conflict" or "constraint_conflict" or "decomposition_conflict",
  "conflict_footprint": ["local", "global", "factual", "instruction", "format", "consistency"]
}}

severity meaning:
  0.0 = perfect alignment or trivial issue
  1.0 = complete failure or critical constraint violation
  Use values in between to indicate degree.

outcome meaning:
  "success" = result meaningfully advances the objective
  "failure" = result does not meet required constraints

conflict_kind meaning (select the best fit):
  "resolution_instability"   = inconsistent or unstable reasoning
  "evidence_conflict"        = conflicting evidence about the result
  "constraint_conflict"      = result violates a specific constraint
  "decomposition_conflict"   = task decomposition is internally inconsistent

conflict_footprint meaning (select all that apply):
  "local"       = conflict is localised to this task
  "global"      = conflict affects broader objective
  "factual"     = conflict involves factual accuracy
  "instruction" = conflict involves instruction adherence
  "format"      = conflict involves output format
  "consistency" = conflict involves internal consistency

Respond with valid JSON only. No other text.
"""


def _parse_critic_response(
    response: str,
) -> tuple[str, float, str, str | None, list[str] | None]:
    """
    Parse critic JSON response.

    Returns (outcome, severity, feedback, raw_conflict_kind, raw_conflict_footprint).
    Pessimistic fallback on any parse or input-shape failure — including
    non-string responses from the LLM.
    """
    if not isinstance(response, str):
        logger.warning(
            "Critic response non-string — pessimistic failure (ADR-022)",
            extra={"response_type": type(response).__name__},
        )
        return "failure", 1.0, "Parse failed — treated as failure", None, None

    try:
        data = json.loads(response.strip())

        outcome = str(data.get("outcome", "failure")).strip().lower()
        if outcome not in ("success", "failure"):
            logger.warning(
                "Critic returned unrecognised outcome — defaulting to failure",
                extra={"outcome": outcome},
            )
            outcome = "failure"

        raw_severity = data.get("severity", 1.0)
        try:
            severity = _clamp(float(raw_severity))
        except (TypeError, ValueError):
            logger.warning(
                "Critic severity unparseable — defaulting to 1.0",
                extra={"raw_severity": str(raw_severity)},
            )
            severity = 1.0

        feedback = str(data.get("feedback", "No feedback")).strip()
        if not feedback:
            feedback = "No feedback"

        raw_kind = data.get("conflict_kind", None)
        if raw_kind is not None:
            raw_kind = str(raw_kind).strip().lower()

        raw_footprint = data.get("conflict_footprint", None)
        if raw_footprint is not None and isinstance(raw_footprint, list):
            raw_footprint = [str(x).strip().lower() for x in raw_footprint]
        else:
            raw_footprint = None

        return outcome, severity, feedback, raw_kind, raw_footprint

    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Critic JSON parse failed — pessimistic failure (ADR-022)",
            extra={"response_preview": response[:80] if response else ""},
        )
        return "failure", 1.0, "Parse failed — treated as failure", None, None


def _derive_partial_structure(
    raw_kind: str | None,
    raw_footprint: list[str] | None,
) -> PartialStructure:
    """
    Construct authoritative PartialStructure from raw LLM string fields.

    Normalisation rules:
    - Unknown or missing conflict_kind → RESOLUTION_INSTABILITY (fallback)
    - Unknown footprint entries → dropped
    - Empty footprint after dropping unknowns → {LOCAL} (fallback)
    - Duplicates deduped via frozenset
    - collapse_status always "unresolved" (kernel-fixed)

    Never raises — always returns a valid PartialStructure.
    """
    if raw_kind is not None and raw_kind in _CONFLICT_KIND_MAP:
        conflict_kind = _CONFLICT_KIND_MAP[raw_kind]
    else:
        if raw_kind is not None:
            logger.warning(
                "Unknown conflict_kind — normalising to fallback",
                extra={
                    "raw_kind": raw_kind,
                    "fallback": _FALLBACK_CONFLICT_KIND.name,
                },
            )
        conflict_kind = _FALLBACK_CONFLICT_KIND

    conflict_footprint: frozenset[ConflictLocus]
    if raw_footprint:
        recognised = frozenset(
            _CONFLICT_LOCUS_MAP[entry]
            for entry in raw_footprint
            if entry in _CONFLICT_LOCUS_MAP
        )
        if recognised:
            conflict_footprint = recognised
        else:
            logger.warning(
                "No recognised conflict_footprint entries — normalising to fallback",
                extra={
                    "raw_footprint": raw_footprint,
                    "fallback": [l.name for l in _FALLBACK_CONFLICT_FOOTPRINT],
                },
            )
            conflict_footprint = _FALLBACK_CONFLICT_FOOTPRINT
    else:
        conflict_footprint = _FALLBACK_CONFLICT_FOOTPRINT

    return PartialStructure(
        collapse_status="unresolved",
        conflict_kind=conflict_kind,
        conflict_footprint=conflict_footprint,
    )


def _derive_category(
    outcome: str,
    severity: float,
    partial_threshold: float,
) -> Literal["success", "partial", "failure"]:
    """
    Derive ADR-022 category from LLM-reported outcome and severity.

    success  → "success"
    failure + severity < partial_threshold → "partial"
    failure + severity >= partial_threshold → "failure"
    """
    if outcome == "success":
        return "success"
    if severity < partial_threshold:
        return "partial"
    return "failure"


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a float to [lo, hi]."""
    return max(lo, min(hi, value))

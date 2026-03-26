# eck/critic.py
"""Critic subsystem (ADR-022–024).

Evaluates task outcomes and returns a typed CriticOutcome plus optional
PartialStructure for consumption by the confidence signal processor (ADR-025).

Design:
- LLM reports outcome quality (success/failure) + severity [0.0, 1.0]
  plus bounded structural fields (conflict_kind, conflict_footprint)
- Kernel derives category (success/partial/failure) from outcome + severity
- LLM never sees "partial" — category is kernel-controlled
- PartialStructure constructed by kernel iff derived category is "partial"
- All downstream confidence mechanics remain kernel authority
- CriticOutcome and PartialStructure imported from eck.types (single source)

Invariant:
  partial_structure is not None iff critic_outcome.category == "partial"
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
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


def critic_evaluate(
    task_text: str,
    prediction: str,
    result: str,
    objective: str,
    llm_call: Callable[[str], str],
    enable_cross_validation: bool = True,
    verifier_callback: Optional[Callable[[str, str], bool]] = None,
    partial_threshold: float = _DEFAULT_PARTIAL_THRESHOLD,
) -> tuple[CriticOutcome, PartialStructure | None]:
    """
    Evaluate task result and return a typed CriticOutcome plus optional
    PartialStructure (ADR-022).

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
        result: Actual execution outcome.
        objective: Overall goal.
        llm_call: Callable that takes a prompt and returns an LLM response.
        enable_cross_validation: If True, use dual critic calls for consensus.
        verifier_callback: Optional external verification hook.
        partial_threshold: Severity floor below which failure → partial category.

    Returns:
        Tuple of (CriticOutcome, PartialStructure | None).
        PartialStructure is not None iff category is "partial".
    """
    prompt = _build_prompt(task_text, prediction, result, objective)

    # First critic call
    raw1 = llm_call(prompt)
    outcome1, severity1, feedback1, raw_kind1, raw_footprint1 = _parse_critic_response(raw1)

    # Derive category from first call before any severity modification.
    # Category is derived here, not from raw outcome, so that disagreement
    # detection operates at the kernel-relevant abstraction level.
    category1 = _derive_category(outcome1, severity1, partial_threshold)

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

        # Derive category from second call for comparison.
        # Disagreement is at the derived-category level, not raw outcome level.
        # Example: both calls return "failure" but severity 0.3 vs 0.8 derives
        # to "partial" vs "failure" — this counts as disagreement.
        category2 = _derive_category(outcome2, severity2, partial_threshold)

        if category1 != category2:
            # Disagreement at derived-category level:
            # - severity clamped to 1.0 (signals reduced confidence)
            # - category preserved from first call (ADR-022 invariant)
            # - PartialStructure taken from first call if category is partial
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
            # Consensus: average severity, combine feedback, structure from first call
            category = category1
            final_severity = _clamp((severity1 + severity2) / 2.0)
            final_feedback = f"{feedback1} | Consensus: {feedback2}"
            final_raw_kind = raw_kind1
            final_raw_footprint = raw_footprint1

    # Optional external verification hook — can only demote to failure (ADR-022)
    if verifier_callback is not None:
        if not verifier_callback(task_text, result):
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
    result: str,
    objective: str,
) -> str:
    """
    Build the critic evaluation prompt.

    Asks for outcome quality (success/failure), severity, feedback, and
    bounded structural fields for partial outcome characterisation.
    Does not mention 'partial' — category derivation is kernel-controlled.
    Always requests conflict_kind and conflict_footprint — kernel uses them
    only when derived category is "partial".
    """
    return f"""Evaluate the result against the task and objective.

Task: {task_text}
Prediction: {prediction}
Result: {result}
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
    raw_conflict_kind and raw_conflict_footprint are raw strings/lists from the LLM
    — kernel normalisation happens in _derive_partial_structure().
    Pessimistic fallback on any parse failure: failure, severity=1.0, None structure.
    """
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

        # Extract raw structural fields — no validation here, normalised later
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
    # Normalise conflict_kind
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

    # Normalise conflict_footprint
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
) -> str:
    """
    Derive ADR-022 category from LLM-reported outcome and severity.

    success  → "success" (kernel gate: upward permitted)
    failure + severity < partial_threshold → "partial" (both directions, no failure window)
    failure + severity >= partial_threshold → "failure" (downward + failure window)
    """
    if outcome == "success":
        return "success"
    if severity < partial_threshold:
        return "partial"
    return "failure"


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a float to [lo, hi]."""
    return max(lo, min(hi, value))

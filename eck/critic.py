# eck/critic.py
"""Critic subsystem (ADR-022–024).

Evaluates task outcomes and returns a typed CriticOutcome for
consumption by the confidence signal processor (ADR-025).

Design:
- LLM reports outcome quality (success/failure) + severity [0.0, 1.0]
- Kernel derives category (success/partial/failure) from outcome + severity
- LLM never sees "partial" — category is kernel-controlled
- All downstream confidence mechanics remain kernel authority
- CriticOutcome is imported from eck.types (single source of truth)
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from eck.types import CriticOutcome, make_critic_outcome

logger = logging.getLogger("eck-core")

# Severity floor below which a failure is promoted to partial (ADR-022).
# Configurable — default 0.5. Above this: failure category.
# Below this: partial category (both confidence directions permitted,
# no failure window triggered).
_DEFAULT_PARTIAL_THRESHOLD = 0.5


def critic_evaluate(
    task_text: str,
    prediction: str,
    result: str,
    objective: str,
    llm_call: Callable[[str], str],
    enable_cross_validation: bool = True,
    verifier_callback: Optional[Callable[[str, str], bool]] = None,
    partial_threshold: float = _DEFAULT_PARTIAL_THRESHOLD,
) -> CriticOutcome:
    """
    Evaluate task result and return a typed CriticOutcome (ADR-022).

    The LLM reports outcome quality (success/failure) and severity.
    The kernel derives the final category — the LLM never controls
    failure window suppression or confidence gate semantics directly.

    Cross-validation disagreement maps to severity=1.0 within the
    first call's outcome category (ADR-022 invariant).

    Pessimistic fallback on any parse failure: failure category,
    severity=1.0 (ADR-022 refusal-over-fabrication posture).

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
        CriticOutcome with category, severity, feedback, and success flag.
    """
    prompt = _build_prompt(task_text, prediction, result, objective)

    # First critic call
    raw1 = llm_call(prompt)
    outcome1, severity1, feedback1 = _parse_critic_response(raw1)

    if not enable_cross_validation:
        category = _derive_category(outcome1, severity1, partial_threshold)
        final_severity = _clamp(severity1)
        final_feedback = feedback1
    else:
        # Second critic call for consensus
        raw2 = llm_call(prompt)
        outcome2, severity2, feedback2 = _parse_critic_response(raw2)

        if outcome1 != outcome2:
            # Disagreement: severity clamped to 1.0, category from first call (ADR-022)
            logger.warning(
                "Critic disagreement detected",
                extra={
                    "outcome1": outcome1,
                    "outcome2": outcome2,
                    "severity1": severity1,
                    "severity2": severity2,
                },
            )
            final_outcome = outcome1
            final_severity = 1.0
            final_feedback = f"{feedback1} | Disagreement: {feedback2}"
        else:
            # Consensus: average severity, combine feedback
            final_outcome = outcome1
            final_severity = _clamp((severity1 + severity2) / 2.0)
            final_feedback = f"{feedback1} | Consensus: {feedback2}"

        category = _derive_category(final_outcome, final_severity, partial_threshold)

    # Optional external verification hook — can only demote to failure (ADR-022)
    if verifier_callback is not None:
        if not verifier_callback(task_text, result):
            category = "failure"
            final_severity = 1.0
            final_feedback += " | External verification failed"
            logger.info(
                "External verifier demoted outcome to failure",
                extra={
                    "task_text": task_text[:80],
                    "prior_category": category,
                },
            )

    logger.info(
        "Critic outcome",
        extra={
            "category": category,
            "severity": final_severity,
            "cross_validation": enable_cross_validation,
        },
    )

    return make_critic_outcome(
        category=category,
        severity=final_severity,
        feedback=final_feedback,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_prompt(
    task_text: str,
    prediction: str,
    result: str,
    objective: str,
) -> str:
    """
    Build the critic evaluation prompt.

    Asks for outcome quality (success/failure) and severity only.
    Does not mention 'partial' — category derivation is kernel-controlled.
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
  "feedback": "<brief explanation>"
}}

severity meaning:
  0.0 = perfect alignment or trivial issue
  1.0 = complete failure or critical constraint violation
  Use values in between to indicate degree.

outcome meaning:
  "success" = result meaningfully advances the objective
  "failure" = result does not meet required constraints

Respond with valid JSON only. No other text.
"""


def _parse_critic_response(response: str) -> tuple[str, float, str]:
    """
    Parse critic JSON response.

    Returns (outcome, severity, feedback).
    Pessimistic fallback on any parse failure: failure, severity=1.0.
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

        return outcome, severity, feedback

    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Critic JSON parse failed — pessimistic failure (ADR-022)",
            extra={"response_preview": response[:80] if response else ""},
        )
        return "failure", 1.0, "Parse failed — treated as failure"


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

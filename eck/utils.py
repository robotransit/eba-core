# eck/utils.py
"""Utility functions for the Epistemic Control Kernel (ECK).

All functions are pure unless explicitly noted.
Logging is reserved for functions that are not pure (get_recommended_breadth).

NOTE:
get_recommended_breadth() and should_execute() are pre-gate utility functions
that predate the policy gate design (ADR-038). They remain here as a temporary
execution control surface pending full agent loop reconciliation with
AgentLoop/PolicyGate. They must not be treated as authoritative policy
decisions — that authority belongs exclusively to the policy gate.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from typing import Any, List

from .config import ECKConfig, PolicyMode

logger = logging.getLogger("eck-core")


# ── Identity ──────────────────────────────────────────────────────────────────

def generate_id() -> str:
    """Generate a unique task ID using UUID4."""
    return str(uuid.uuid4())


# ── Math utilities ────────────────────────────────────────────────────────────

def safe_mean(values: List[float]) -> float:
    """Compute mean safely, returning 0.0 if the list is empty."""
    return sum(values) / max(1, len(values))


def z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score, returning 0.0 if standard deviation is zero."""
    if std == 0:
        return 0.0
    return (value - mean) / std


# ── Parsing ───────────────────────────────────────────────────────────────────

def safe_parse_json_array(response: str) -> List[str]:
    """
    Safely parse a JSON array string from LLM output.

    Returns empty list on any failure.
    Logs a structured warning on parse failure.
    """
    try:
        parsed = json.loads(response.strip())
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        raise ValueError("Response is not a JSON array")
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(
            "Subtask JSON parse failed — no subtasks generated",
            extra={
                "error": str(e),
                "response_preview": response[:80] if response else "",
            },
        )
        return []


# ── Feasibility ───────────────────────────────────────────────────────────────

def is_numeric_feasible(
    prediction: Any,
    actual: Any,
) -> bool:
    """
    Determine if prediction and actual outcome are numeric-feasible.

    Checks in order:
    1. Both are numeric (int/float) → feasible
    2. Both are sequences of the same length → feasible
    3. String length heuristic fallback: difference <= 50 characters
       NOTE: This fallback is intentionally weak — it is a last-resort
       proxy for structural similarity, not a semantic measure.
       It will be replaced when a more principled feasibility signal
       is designed.
    """
    # Bool guard — isinstance(True, int) is True in Python
    if isinstance(prediction, bool) or isinstance(actual, bool):
        return False

    if isinstance(prediction, (int, float)) and isinstance(actual, (int, float)):
        return True

    if isinstance(prediction, (list, tuple)) and isinstance(actual, (list, tuple)):
        return len(prediction) == len(actual)

    try:
        pred_str = str(prediction)
        act_str = str(actual)
        if not pred_str or not act_str:
            return False
        return abs(len(pred_str) - len(act_str)) <= 50
    except Exception:
        return False


# ── Pre-gate execution utilities (temporary — pending ADR-038 wiring) ─────────
#
# get_recommended_breadth() and should_execute() are soft execution guidance
# utilities that predate the policy gate. They remain here pending full
# AgentLoop/PolicyGate reconciliation. Once the confidence signal is wired
# and PolicyGate is the sole execution authority (ADR-038), these functions
# will be retired.

def get_recommended_breadth(
    confidence: float,
    policy_mode: PolicyMode,
) -> str:
    """
    Map confidence and policy mode to a recommended breadth level.

    Returns one of: 'FULL', 'MODERATE', 'RESTRICTED', 'DEFERRED'

    Soft guidance only — not authoritative. The policy gate (ADR-038)
    is the sole authoritative execution boundary.
    """
    if policy_mode == PolicyMode.NORMAL:
        recommended = "FULL"
    elif confidence >= 0.8:
        recommended = "FULL"
    elif confidence >= 0.5:
        recommended = "MODERATE"
    elif confidence >= 0.3:
        recommended = "RESTRICTED"
    else:
        recommended = "DEFERRED"

    logger.info(
        "Breadth recommendation",
        extra={
            "recommended": recommended,
            "confidence": round(confidence, 4),
            "policy_mode": policy_mode.name,
        },
    )

    return recommended


def should_execute(policy_mode: PolicyMode, recommendation: str) -> bool:
    """
    Determine whether execution is permitted under the given policy mode
    and breadth recommendation.

    NOTE: This is a pre-gate soft enforcement rule, not authoritative policy.
    The policy gate (ADR-038) is the sole authoritative execution boundary.

    Current behaviour:
    - NORMAL / GUIDED: always permitted (no execution constraint applied)
    - ENFORCED: permitted unless recommendation is DEFERRED
    - HALT: never permitted

    GUIDED currently applies no execution constraint — this is a known
    gap pending effective_policy() integration and gate reconciliation.
    """
    if policy_mode == PolicyMode.HALT:
        return False

    if policy_mode == PolicyMode.ENFORCED:
        return recommendation != "DEFERRED"

    return True

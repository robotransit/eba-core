# eck/demo_policy_gate.py
"""
Demonstration childcare policy module for the Epistemic Control Kernel (ECK).

Implements the ADR-043 childcare-domain capability proof as a standalone
policy module satisfying the PolicyGate Protocol structurally.

This module is intentionally minimal but contains actual policy:
- out-of-domain evaluation fails closed per ADR-044
- required structured parameters are mandatory
- high-safety unbounded generation is refused
- child-facing transformation requests are refused even at high confidence
- failure window and baseline confidence handling remain aligned with
  DefaultPolicyGate when no childcare-semantic rule applies

Characteristics:
- no hidden state
- no side effects
- no external calls
- no execution authority
"""

from __future__ import annotations

from typing import Any

from .policy_gate import (
    ExecutionMode,
    PolicyCause,
    PolicyContext,
    PolicyDecision,
)


class DemoPolicyGate:
    """Deterministic childcare-domain policy module."""

    _REQUIRED_PARAMETER_KEYS = frozenset({"audience", "request_kind", "bounded"})

    def evaluate(
        self,
        proposed_action: Any,
        confidence: float,
        context: PolicyContext,
    ) -> PolicyDecision:
        """
        Evaluate the proposed action under childcare-domain policy rules.

        Evaluation order is load-bearing and follows ADR-043 exactly:
        1. out-of-domain check
        2. required schema validation
        3. childcare semantic rules
        4. failure window handling
        5. baseline confidence thresholds

        Args:
            proposed_action: Structured proposed action under evaluation.
            confidence: Current epistemic confidence in [0.0, 1.0].
            context: PolicyContext for the current cycle.

        Returns:
            PolicyDecision for the current cycle.
        """
        # Rule 1 — Out-of-domain fallback (ADR-044)
        if context.environment != "childcare":
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.DEFAULT,
                reason=(
                    "environment mismatch: expected childcare, "
                    f"got {context.environment!r}"
                ),
                rule_id="RULE_OUT_OF_DOMAIN",
            )

        parameters = getattr(proposed_action, "parameters", None)
        if not isinstance(parameters, dict):
            parameters = {}

        # Rule 2 — Missing required parameters (fail-closed)
        missing = sorted(self._REQUIRED_PARAMETER_KEYS - set(parameters.keys()))
        if missing:
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.DEFAULT,
                reason="missing required parameters: " + ", ".join(missing),
                rule_id="RULE_MISSING_PARAMETERS",
            )

        audience = parameters["audience"]
        request_kind = parameters["request_kind"]
        bounded = parameters["bounded"]
        action_type = getattr(proposed_action, "action_type", None)

        # Rule 3 — High safety level + unbounded generation
        # Note: safety_level None means "unspecified" and does not match "HIGH".
        if context.safety_level == "HIGH" and bounded is False:
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.SAFETY,
                reason="high safety level forbids unbounded generation",
                rule_id="RULE_HIGH_SAFETY_UNBOUNDED",
            )

        # Rule 4 — Directive transformation for child audience (core proof)
        if (
            action_type == "llm_query"
            and request_kind == "transform"
            and audience == "child"
        ):
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.SAFETY,
                reason="child-facing transformation requests are not permitted",
                rule_id="RULE_CHILD_TRANSFORM_REFUSED",
            )

        # Rule 5 — Failure window handling (inherited baseline safeguard)
        if context.failure_window_active:
            return PolicyDecision(
                mode=ExecutionMode.HALT,
                cause=PolicyCause.FAILURE_WINDOW,
                reason="Failure window active — immediate halt required",
                rule_id="RULE_001",
            )

        # Baseline confidence thresholds are the first place confidence is used.
        # Validation therefore occurs here, not earlier, to preserve the
        # ADR-043 load-bearing evaluation order and confidence-independence
        # of Rules 1–4.
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not (0.0 <= confidence <= 1.0)
        ):
            raise ValueError(
                f"Invalid confidence value: {confidence}. "
                "Must be int/float in [0.0, 1.0] and not bool."
            )

        # Rule 6 — Baseline confidence thresholds (inherited from DefaultPolicyGate)
        if confidence < 0.40:
            return PolicyDecision(
                mode=ExecutionMode.HALT,
                cause=PolicyCause.CONFIDENCE,
                reason=f"Confidence {confidence:.2f} below halt threshold 0.4",
                rule_id="RULE_002",
            )

        if confidence < 0.70:
            return PolicyDecision(
                mode=ExecutionMode.RETRY,
                cause=PolicyCause.CONFIDENCE,
                reason=(
                    f"Confidence {confidence:.2f} below retry threshold 0.7 "
                    "— awaiting stability"
                ),
                rule_id="RULE_003",
            )

        if confidence < 0.90:
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.CONFIDENCE,
                reason=(
                    f"Confidence {confidence:.2f} below degrade threshold 0.9 "
                    "— using safer fallback"
                ),
                rule_id="RULE_004",
            )

        return PolicyDecision(
            mode=ExecutionMode.EXECUTE,
            cause=PolicyCause.CONFIDENCE,
            reason=f"Confidence {confidence:.2f} sufficient for execution",
            rule_id="RULE_005",
        )

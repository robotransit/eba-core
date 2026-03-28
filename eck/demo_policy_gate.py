# eck/demo_policy_gate.py
"""
Demonstration policy module for the Epistemic Control Kernel (ECK).

Implements the ADR-043 reference policy as a standalone concrete
PolicyGate. This module is intentionally minimal, deterministic, and pure.

Characteristics:
- no hidden state
- no side effects
- no external calls
- no execution authority

Decision model:
- confidence >= 0.7 and failure_window_active == False -> EXECUTE
- confidence >= 0.7 and failure_window_active == True  -> DEGRADE
- confidence >= 0.5                                   -> DEGRADE
- confidence >= 0.3                                   -> RETRY
- otherwise                                           -> HALT
"""

from __future__ import annotations

from .policy_gate import (
    ExecutionMode,
    PolicyCause,
    PolicyContext,
    PolicyDecision,
    PolicyGate,
)


class DemoPolicyGate(PolicyGate):
    """Deterministic reference implementation of the PolicyGate contract."""

    def evaluate(
        self,
        proposed_action,
        confidence: float,
        context: PolicyContext,
    ) -> PolicyDecision:
        """
        Evaluate the policy decision for the current cycle.

        Args:
            proposed_action: Proposed action under consideration. Present for
                contract conformance; this demonstration policy does not inspect it.
            confidence: Current epistemic confidence value.
            context: PolicyContext carrying per-cycle control metadata.

        Returns:
            PolicyDecision for the current cycle.
        """
        if confidence >= 0.7:
            if not context.failure_window_active:
                return PolicyDecision(
                    mode=ExecutionMode.EXECUTE,
                    cause=PolicyCause.CONFIDENCE,
                    reason="confidence high",
                    rule_id="RULE_EXECUTE_CONF_HIGH",
                )
            else:
                return PolicyDecision(
                    mode=ExecutionMode.DEGRADE,
                    cause=PolicyCause.CONFIDENCE,
                    reason="failure window active — execute suppressed",
                    rule_id="RULE_DEGRADE_FAILURE_WINDOW",
                )

        elif confidence >= 0.5:
            return PolicyDecision(
                mode=ExecutionMode.DEGRADE,
                cause=PolicyCause.CONFIDENCE,
                reason="confidence moderate",
                rule_id="RULE_DEGRADE_CONF_MID",
            )

        elif confidence >= 0.3:
            return PolicyDecision(
                mode=ExecutionMode.RETRY,
                cause=PolicyCause.CONFIDENCE,
                reason="confidence low",
                rule_id="RULE_RETRY_CONF_LOW",
            )

        else:
            return PolicyDecision(
                mode=ExecutionMode.HALT,
                cause=PolicyCause.CONFIDENCE,
                reason="confidence below minimum threshold",
                rule_id="RULE_HALT_CONF_MIN",
            )

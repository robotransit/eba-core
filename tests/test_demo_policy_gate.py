# tests/test_demo_policy_gate.py
"""Tests for the ADR-043 demonstration policy module."""

from __future__ import annotations

import unittest

from eck.demo_policy_gate import DemoPolicyGate
from eck.policy_gate import (
    ExecutionMode,
    PolicyCause,
    PolicyContext,
)


class TestDemoPolicyGateThresholdBoundaries(unittest.TestCase):
    """Threshold boundary behavior for DemoPolicyGate."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()
        self.context = PolicyContext(failure_window_active=False)

    def test_execute_at_exact_execute_threshold(self) -> None:
        """confidence == 0.7 -> EXECUTE."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.7,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.EXECUTE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_EXECUTE_CONF_HIGH")
        self.assertEqual(decision.reason, "confidence high")

    def test_degrade_just_below_execute_threshold(self) -> None:
        """confidence just below 0.7 -> DEGRADE."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.699,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_DEGRADE_CONF_MID")
        self.assertEqual(decision.reason, "confidence moderate")

    def test_degrade_at_exact_degrade_threshold(self) -> None:
        """confidence == 0.5 -> DEGRADE."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.5,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_DEGRADE_CONF_MID")
        self.assertEqual(decision.reason, "confidence moderate")

    def test_retry_just_below_degrade_threshold(self) -> None:
        """confidence just below 0.5 -> RETRY."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.499,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.RETRY)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_RETRY_CONF_LOW")
        self.assertEqual(decision.reason, "confidence low")

    def test_retry_at_exact_retry_threshold(self) -> None:
        """confidence == 0.3 -> RETRY."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.3,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.RETRY)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_RETRY_CONF_LOW")
        self.assertEqual(decision.reason, "confidence low")

    def test_halt_just_below_retry_threshold(self) -> None:
        """confidence just below 0.3 -> HALT."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.299,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.HALT)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_HALT_CONF_MIN")
        self.assertEqual(
            decision.reason,
            "confidence below minimum threshold",
        )

    def test_halt_at_zero_confidence(self) -> None:
        """confidence == 0.0 -> HALT (true lower bound)."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.0,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.HALT)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_HALT_CONF_MIN")
        self.assertEqual(
            decision.reason,
            "confidence below minimum threshold",
        )


class TestDemoPolicyGateFailureWindowSuppression(unittest.TestCase):
    """Failure window suppression semantics for DemoPolicyGate."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_execute_allowed_at_threshold_without_failure_window(self) -> None:
        """confidence >= 0.7 with failure window inactive -> EXECUTE."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.7,
            context=PolicyContext(failure_window_active=False),
        )
        self.assertEqual(decision.mode, ExecutionMode.EXECUTE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_EXECUTE_CONF_HIGH")
        self.assertEqual(decision.reason, "confidence high")

    def test_execute_suppressed_at_threshold_with_failure_window(self) -> None:
        """confidence == 0.7 with failure window active -> DEGRADE."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.7,
            context=PolicyContext(failure_window_active=True),
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_DEGRADE_FAILURE_WINDOW")
        self.assertEqual(
            decision.reason,
            "failure window active — execute suppressed",
        )

    def test_high_confidence_still_degrades_with_failure_window(self) -> None:
        """confidence > 0.7 with failure window active -> DEGRADE."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.9,
            context=PolicyContext(failure_window_active=True),
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_DEGRADE_FAILURE_WINDOW")
        self.assertEqual(
            decision.reason,
            "failure window active — execute suppressed",
        )

    def test_midrange_degrade_unchanged_by_failure_window(self) -> None:
        """confidence in [0.5, 0.7) remains DEGRADE under failure window."""
        decision = self.gate.evaluate(
            proposed_action=None,
            confidence=0.6,
            context=PolicyContext(failure_window_active=True),
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_DEGRADE_CONF_MID")
        self.assertEqual(decision.reason, "confidence moderate")


class TestDemoPolicyGateDeterminism(unittest.TestCase):
    """Determinism and purity checks for DemoPolicyGate."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_identical_inputs_produce_identical_decisions(self) -> None:
        """Repeated identical inputs produce equal PolicyDecision outputs."""
        context = PolicyContext(failure_window_active=True)

        first = self.gate.evaluate(
            proposed_action=None,
            confidence=0.9,
            context=context,
        )
        second = self.gate.evaluate(
            proposed_action=None,
            confidence=0.9,
            context=context,
        )
        third = self.gate.evaluate(
            proposed_action=None,
            confidence=0.9,
            context=context,
        )

        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(first.mode, ExecutionMode.DEGRADE)
        self.assertEqual(first.rule_id, "RULE_DEGRADE_FAILURE_WINDOW")

    def test_proposed_action_is_not_inspected(self) -> None:
        """Decision depends only on confidence/context, not proposed_action."""
        context = PolicyContext(failure_window_active=False)

        with_action = self.gate.evaluate(
            proposed_action={"action_type": "something_else"},
            confidence=0.5,
            context=context,
        )
        without_action = self.gate.evaluate(
            proposed_action=None,
            confidence=0.5,
            context=context,
        )

        self.assertEqual(with_action, without_action)
        self.assertEqual(with_action.mode, ExecutionMode.DEGRADE)
        self.assertEqual(with_action.rule_id, "RULE_DEGRADE_CONF_MID")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from eck.policy_gate import (
    DefaultPolicyGate,
    ExecutionMode,
    PolicyCause,
    PolicyContext,
    PolicyDecision,
)


class TestDefaultPolicyGate(unittest.TestCase):
    """Test suite for DefaultPolicyGate (minimal default policy implementation)."""

    def setUp(self) -> None:
        self.gate = DefaultPolicyGate()
        self.context = PolicyContext(
            user_id="user123",
            safety_level="high",
            environment="banking",
            failure_window_active=False,
        )

    # ------------------------------------------------------------------
    # Confidence validation
    # ------------------------------------------------------------------
    def test_validate_confidence_valid(self) -> None:
        """Valid confidence values are accepted and return PolicyDecision."""
        decision = self.gate.evaluate(
            proposed_action="pay",
            confidence=0.5,
            context=self.context,
        )
        self.assertIsInstance(decision, PolicyDecision)

    def test_validate_confidence_invalid_type(self) -> None:
        """Invalid confidence type raises ValueError."""
        with self.assertRaises(ValueError):
            self.gate.evaluate("pay", "high", self.context)  # string

        with self.assertRaises(ValueError):
            self.gate.evaluate("pay", True, self.context)  # bool

        with self.assertRaises(ValueError):
            self.gate.evaluate("pay", None, self.context)  # None

    def test_validate_confidence_out_of_range(self) -> None:
        """Confidence outside [0.0, 1.0] raises ValueError."""
        with self.assertRaises(ValueError):
            self.gate.evaluate("pay", -0.1, self.context)

        with self.assertRaises(ValueError):
            self.gate.evaluate("pay", 1.1, self.context)

    # ------------------------------------------------------------------
    # Rule precedence, causes, and thresholds
    # ------------------------------------------------------------------
    def test_failure_window_precedence(self) -> None:
        """Failure window active forces HALT regardless of confidence."""
        context = PolicyContext(
            user_id="user123",
            safety_level="high",
            environment="banking",
            failure_window_active=True,
        )
        decision = self.gate.evaluate("transfer", 0.95, context)
        self.assertEqual(
            decision,
            PolicyDecision(
                mode=ExecutionMode.HALT,
                cause=PolicyCause.FAILURE_WINDOW,
                reason="Failure window active — immediate halt required",
                rule_id="RULE_001",
            ),
        )

    def test_low_confidence_halt(self) -> None:
        """Very low confidence forces HALT."""
        decision = self.gate.evaluate("transfer", 0.30, self.context)
        self.assertEqual(decision.mode, ExecutionMode.HALT)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_002")

    def test_moderate_confidence_retry(self) -> None:
        """Moderate uncertainty forces RETRY."""
        decision = self.gate.evaluate("transfer", 0.50, self.context)
        self.assertEqual(decision.mode, ExecutionMode.RETRY)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_003")

    def test_borderline_confidence_degrade(self) -> None:
        """Borderline confidence forces DEGRADE."""
        decision = self.gate.evaluate("transfer", 0.80, self.context)
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_004")

    def test_high_confidence_execute(self) -> None:
        """High confidence allows EXECUTE."""
        decision = self.gate.evaluate("transfer", 0.95, self.context)
        self.assertEqual(decision.mode, ExecutionMode.EXECUTE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_005")

    def test_threshold_boundaries(self) -> None:
        """Threshold boundaries map to the correct next-less-restrictive modes."""
        self.assertEqual(
            self.gate.evaluate("transfer", 0.40, self.context).mode,
            ExecutionMode.RETRY,
        )
        self.assertEqual(
            self.gate.evaluate("transfer", 0.70, self.context).mode,
            ExecutionMode.DEGRADE,
        )
        self.assertEqual(
            self.gate.evaluate("transfer", 0.90, self.context).mode,
            ExecutionMode.EXECUTE,
        )

    def test_monotonicity_lower_confidence_more_restrictive(self) -> None:
        """Lower confidence must not produce a more permissive mode."""
        decisions = []
        for conf in [0.95, 0.85, 0.65, 0.45, 0.35]:
            decisions.append(self.gate.evaluate("transfer", conf, self.context).mode)

        restrictiveness = {
            ExecutionMode.EXECUTE: 0,
            ExecutionMode.DEGRADE: 1,
            ExecutionMode.RETRY: 2,
            ExecutionMode.HALT: 3,
        }
        scores = [restrictiveness[mode] for mode in decisions]
        self.assertTrue(all(scores[i] <= scores[i + 1] for i in range(len(scores) - 1)))

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------
    def test_determinism_identical_inputs(self) -> None:
        """Identical inputs produce identical decisions."""
        decision1 = self.gate.evaluate("transfer", 0.50, self.context)
        decision2 = self.gate.evaluate("transfer", 0.50, self.context)
        self.assertEqual(decision1, decision2)

    # ------------------------------------------------------------------
    # proposed_action currently uninterpreted
    # ------------------------------------------------------------------
    def test_proposed_action_ignored(self) -> None:
        """proposed_action is accepted but ignored in default gate."""
        decision1 = self.gate.evaluate("transfer", 0.50, self.context)
        decision2 = self.gate.evaluate("login", 0.50, self.context)
        self.assertEqual(decision1, decision2)

    # ------------------------------------------------------------------
    # Rule ID / reason always present
    # ------------------------------------------------------------------
    def test_rule_id_always_present(self) -> None:
        """Every decision includes a non-empty rule_id."""
        decision = self.gate.evaluate("transfer", 0.50, self.context)
        self.assertTrue(decision.rule_id.strip() != "")

    def test_reason_always_present(self) -> None:
        """Every decision includes a non-empty reason."""
        decision = self.gate.evaluate("transfer", 0.50, self.context)
        self.assertTrue(decision.reason.strip() != "")


if __name__ == "__main__":
    unittest.main()

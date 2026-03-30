# tests/test_policy_gate.py
"""Tests for PolicyGate and DefaultPolicyGate."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from eck.policy_gate import (
    DefaultPolicyGate,
    ExecutionMode,
    PolicyCause,
    PolicyContext,
    PolicyDecision,
    PolicyGate,
)


# ── Telemetry helpers ─────────────────────────────────────────────────────────

_TELEMETRY_ARGS = dict(
    trace_id="trace-test",
    step_id="trace-test:step:0",
    deterministic_nonce=0,
)


def _get_telemetry_event(mock_logger: MagicMock) -> dict | None:
    """Extract the telemetry_event from the most recent logger.info call."""
    for call in reversed(mock_logger.info.call_args_list):
        kwargs = call.kwargs if call.kwargs else {}
        extra = kwargs.get("extra", {})
        if "telemetry_event" in extra:
            return extra["telemetry_event"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Test classes
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyGateProtocol(unittest.TestCase):
    """PolicyGate Protocol contract — structural typing verification."""

    def test_protocol_cannot_be_instantiated(self) -> None:
        """PolicyGate is a Protocol and cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            PolicyGate()

    def test_compliant_class_satisfies_protocol(self) -> None:
        """A class with the correct evaluate() signature satisfies PolicyGate."""
        class MinimalGate:
            def evaluate(self, proposed_action, confidence, context):
                return PolicyDecision(
                    mode=ExecutionMode.EXECUTE,
                    cause=PolicyCause.CONFIDENCE,
                    reason="test",
                    rule_id="RULE_TEST",
                )

        gate = MinimalGate()
        self.assertIsInstance(gate, PolicyGate)

    def test_non_compliant_class_does_not_satisfy_protocol(self) -> None:
        """A class without evaluate() does not satisfy the PolicyGate Protocol."""
        class NotAGate:
            pass

        self.assertNotIsInstance(NotAGate(), PolicyGate)

    def test_default_policy_gate_satisfies_protocol(self) -> None:
        """DefaultPolicyGate satisfies the PolicyGate Protocol structurally."""
        gate = DefaultPolicyGate()
        self.assertIsInstance(gate, PolicyGate)


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


class TestDefaultPolicyGateTelemetry(unittest.TestCase):
    """DefaultPolicyGate — policy.evaluate telemetry emission."""

    def setUp(self) -> None:
        self.gate = DefaultPolicyGate()
        self.context = PolicyContext(
            environment="banking",
            safety_level="high",
            failure_window_active=False,
        )

    def test_execute_path_emits_policy_evaluate(self) -> None:
        """High confidence emits policy.evaluate with EXECUTE mode."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.95, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "policy.evaluate")
        self.assertEqual(event["payload"]["mode"], "EXECUTE")
        self.assertEqual(event["payload"]["rule_id"], "RULE_005")
        self.assertEqual(event["payload"]["confidence"], 0.95)
        self.assertEqual(event["source"], "policy_gate")

    def test_halt_path_emits_policy_evaluate(self) -> None:
        """Low confidence emits policy.evaluate with HALT mode."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.30, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["payload"]["mode"], "HALT")
        self.assertEqual(event["payload"]["rule_id"], "RULE_002")

    def test_retry_path_emits_policy_evaluate(self) -> None:
        """Moderate confidence emits policy.evaluate with RETRY mode."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.50, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["payload"]["mode"], "RETRY")
        self.assertEqual(event["payload"]["rule_id"], "RULE_003")

    def test_degrade_path_emits_policy_evaluate(self) -> None:
        """Borderline confidence emits policy.evaluate with DEGRADE mode."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.80, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["payload"]["mode"], "DEGRADE")
        self.assertEqual(event["payload"]["rule_id"], "RULE_004")

    def test_failure_window_path_emits_policy_evaluate(self) -> None:
        """Failure window active emits policy.evaluate with HALT and FAILURE_WINDOW cause."""
        mock_logger = MagicMock()
        context = PolicyContext(failure_window_active=True)
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.95, context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["payload"]["mode"], "HALT")
        self.assertEqual(event["payload"]["cause"], "FAILURE_WINDOW")
        self.assertEqual(event["payload"]["rule_id"], "RULE_001")

    def test_payload_includes_required_fields(self) -> None:
        """policy.evaluate payload includes all MUST fields."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.95, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        for field in ("mode", "cause", "rule_id", "reason", "confidence"):
            self.assertIn(field, event["payload"])

    def test_payload_includes_context_fields(self) -> None:
        """policy.evaluate payload includes failure_window_active, environment, safety_level."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "transfer", 0.95, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertIn("failure_window_active", event["payload"])
        self.assertIn("environment", event["payload"])
        self.assertIn("safety_level", event["payload"])

    def test_action_type_included_when_present(self) -> None:
        """action_type included in payload when proposed_action has action_type attribute."""
        mock_logger = MagicMock()
        proposal = SimpleNamespace(action_type="llm_query")
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                proposal, 0.95, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["payload"]["action_type"], "llm_query")

    def test_action_type_absent_when_not_present(self) -> None:
        """action_type absent from payload when proposed_action has no action_type."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate(
                "plain_string_action", 0.95, self.context, **_TELEMETRY_ARGS
            )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertNotIn("action_type", event["payload"])

    def test_no_telemetry_args_does_not_emit(self) -> None:
        """Without telemetry args, no policy.evaluate event is emitted."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            self.gate.evaluate("transfer", 0.95, self.context)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNone(event)

    def test_decision_returned_unchanged_by_emit(self) -> None:
        """_emit() returns the PolicyDecision unchanged — telemetry is observability-only."""
        mock_logger = MagicMock()
        with patch("eck.policy_gate.logger", mock_logger):
            decision = self.gate.evaluate(
                "transfer", 0.95, self.context, **_TELEMETRY_ARGS
            )
        self.assertEqual(decision.mode, ExecutionMode.EXECUTE)
        self.assertEqual(decision.rule_id, "RULE_005")


if __name__ == "__main__":
    unittest.main()

# tests/test_demo_policy_gate.py
"""
Tests for the ADR-043 childcare-domain demonstration policy module.

Covers:
- ADR-043 semantic obligations
- ADR-044 out-of-domain compliance
- inherited baseline behavior
- confidence validation placement (load-bearing ordering proof)
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from eck.demo_policy_gate import DemoPolicyGate
from eck.policy_gate import (
    ExecutionMode,
    PolicyCause,
    PolicyContext,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _proposal(
    action_type: str = "llm_query",
    *,
    audience: str = "adult",
    request_kind: str = "inform",
    bounded: bool = True,
) -> SimpleNamespace:
    """Minimal well-formed childcare proposal. Defaults avoid all semantic rules."""
    return SimpleNamespace(
        action_type=action_type,
        parameters={
            "audience": audience,
            "request_kind": request_kind,
            "bounded": bounded,
        },
    )


def _context(
    environment: str | None = "childcare",
    safety_level: str | None = None,
    failure_window_active: bool = False,
) -> PolicyContext:
    """Minimal PolicyContext. Defaults to a clean childcare context."""
    return PolicyContext(
        environment=environment,
        safety_level=safety_level,
        failure_window_active=failure_window_active,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test classes
# ─────────────────────────────────────────────────────────────────────────────

class TestDemoPolicyGateOutOfDomain(unittest.TestCase):
    """ADR-044 out-of-domain compliance."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_non_childcare_environment_returns_degrade(self) -> None:
        """Non-childcare environment → DEGRADE."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence=0.95,
            context=_context(environment="banking"),
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.DEFAULT)
        self.assertEqual(decision.rule_id, "RULE_OUT_OF_DOMAIN")

    def test_none_environment_returns_out_of_domain(self) -> None:
        """None environment → RULE_OUT_OF_DOMAIN."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence=0.95,
            context=_context(environment=None),
        )
        self.assertEqual(decision.rule_id, "RULE_OUT_OF_DOMAIN")

    def test_out_of_domain_reason_identifies_mismatch(self) -> None:
        """Out-of-domain reason explicitly identifies the environment mismatch."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence=0.95,
            context=_context(environment="medical"),
        )
        self.assertIn("childcare", decision.reason)
        self.assertIn("medical", decision.reason)

    def test_out_of_domain_is_confidence_independent(self) -> None:
        """RULE_OUT_OF_DOMAIN fires regardless of confidence value."""
        for confidence in (0.0, 0.5, 0.95, 1.0):
            with self.subTest(confidence=confidence):
                decision = self.gate.evaluate(
                    proposed_action=_proposal(),
                    confidence=confidence,
                    context=_context(environment="banking"),
                )
                self.assertEqual(decision.rule_id, "RULE_OUT_OF_DOMAIN")

    def test_out_of_domain_fires_with_invalid_confidence(self) -> None:
        """RULE_OUT_OF_DOMAIN fires even when confidence is invalid — does not raise."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence="not_a_float",
            context=_context(environment="banking"),
        )
        self.assertEqual(decision.rule_id, "RULE_OUT_OF_DOMAIN")


class TestDemoPolicyGateSchemaEnforcement(unittest.TestCase):
    """Required parameter schema — fail-closed semantics."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_missing_audience_returns_missing_parameters(self) -> None:
        """Missing audience → RULE_MISSING_PARAMETERS."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={"request_kind": "inform", "bounded": True},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.DEFAULT)

    def test_missing_request_kind_returns_missing_parameters(self) -> None:
        """Missing request_kind → RULE_MISSING_PARAMETERS."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={"audience": "child", "bounded": True},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")

    def test_missing_bounded_returns_missing_parameters(self) -> None:
        """Missing bounded → RULE_MISSING_PARAMETERS."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={"audience": "child", "request_kind": "inform"},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")

    def test_all_fields_missing_returns_missing_parameters(self) -> None:
        """Empty parameters dict → RULE_MISSING_PARAMETERS."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")

    def test_non_dict_parameters_treated_as_missing(self) -> None:
        """Non-dict parameters → RULE_MISSING_PARAMETERS (normalised to empty dict)."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters=["audience", "child"],
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")

    def test_missing_parameters_reason_identifies_missing_fields(self) -> None:
        """RULE_MISSING_PARAMETERS reason identifies which fields are missing."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={"audience": "child"},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertIn("bounded", decision.reason)
        self.assertIn("request_kind", decision.reason)

    def test_missing_parameters_no_fallback_to_baseline(self) -> None:
        """RULE_MISSING_PARAMETERS never falls through to confidence thresholds."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence=0.95,
            context=_context(),
        )
        self.assertNotEqual(decision.rule_id, "RULE_005")
        self.assertNotEqual(decision.mode, ExecutionMode.EXECUTE)

    def test_missing_parameters_fires_with_invalid_confidence(self) -> None:
        """RULE_MISSING_PARAMETERS fires even when confidence is invalid."""
        proposal = SimpleNamespace(
            action_type="llm_query",
            parameters={},
        )
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence="bad",
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")


class TestDemoPolicyGateSemanticRules(unittest.TestCase):
    """ADR-043 childcare semantic rules — the capability proof."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    # ------------------------------------------------------------------
    # Rule 3 — High safety + unbounded generation
    # ------------------------------------------------------------------
    def test_high_safety_unbounded_returns_degrade(self) -> None:
        """safety_level=='HIGH' AND bounded==False → RULE_HIGH_SAFETY_UNBOUNDED."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(bounded=False),
            confidence=0.95,
            context=_context(safety_level="HIGH"),
        )
        self.assertEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.SAFETY)

    def test_high_safety_unbounded_is_confidence_independent(self) -> None:
        """RULE_HIGH_SAFETY_UNBOUNDED fires regardless of confidence."""
        for confidence in (0.0, 0.5, 0.95, 1.0):
            with self.subTest(confidence=confidence):
                decision = self.gate.evaluate(
                    proposed_action=_proposal(bounded=False),
                    confidence=confidence,
                    context=_context(safety_level="HIGH"),
                )
                self.assertEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")

    def test_none_safety_level_does_not_trigger_rule3(self) -> None:
        """safety_level=None does not match 'HIGH' — rule does not fire."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(bounded=False),
            confidence=0.95,
            context=_context(safety_level=None),
        )
        self.assertNotEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")

    def test_bounded_true_does_not_trigger_rule3(self) -> None:
        """bounded==True does not trigger RULE_HIGH_SAFETY_UNBOUNDED."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(bounded=True),
            confidence=0.95,
            context=_context(safety_level="HIGH"),
        )
        self.assertNotEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")

    def test_high_safety_unbounded_fires_with_invalid_confidence(self) -> None:
        """RULE_HIGH_SAFETY_UNBOUNDED fires even when confidence is invalid."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(bounded=False),
            confidence="bad",
            context=_context(safety_level="HIGH"),
        )
        self.assertEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")

    # ------------------------------------------------------------------
    # Rule 4 — Child-facing transformation refusal (load-bearing proof)
    # ------------------------------------------------------------------
    def test_child_transform_refused_at_high_confidence(self) -> None:
        """Core proof: child transform refused even at confidence >= 0.9."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="transform"),
            confidence=0.95,
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.SAFETY)

    def test_child_transform_refused_reason_is_not_confidence_derived(self) -> None:
        """Refusal reason makes no reference to confidence magnitude."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="transform"),
            confidence=0.95,
            context=_context(),
        )
        self.assertNotIn("0.95", decision.reason)
        self.assertNotIn("confidence", decision.reason.lower())

    def test_child_transform_refused_is_confidence_independent(self) -> None:
        """RULE_CHILD_TRANSFORM_REFUSED fires regardless of confidence."""
        for confidence in (0.0, 0.5, 0.95, 1.0):
            with self.subTest(confidence=confidence):
                decision = self.gate.evaluate(
                    proposed_action=_proposal(
                        audience="child", request_kind="transform"
                    ),
                    confidence=confidence,
                    context=_context(),
                )
                self.assertEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_adult_audience_does_not_trigger_rule4(self) -> None:
        """audience='adult' does not trigger RULE_CHILD_TRANSFORM_REFUSED."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="adult", request_kind="transform"),
            confidence=0.95,
            context=_context(),
        )
        self.assertNotEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_inform_request_kind_does_not_trigger_rule4(self) -> None:
        """request_kind='inform' does not trigger RULE_CHILD_TRANSFORM_REFUSED."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="inform"),
            confidence=0.95,
            context=_context(),
        )
        self.assertNotEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_non_llm_query_action_type_does_not_trigger_rule4(self) -> None:
        """action_type != 'llm_query' does not trigger RULE_CHILD_TRANSFORM_REFUSED."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(
                action_type="file_write",
                audience="child",
                request_kind="transform",
            ),
            confidence=0.95,
            context=_context(),
        )
        self.assertNotEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_child_transform_refused_fires_with_invalid_confidence(self) -> None:
        """RULE_CHILD_TRANSFORM_REFUSED fires even when confidence is invalid."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="transform"),
            confidence="bad",
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_semantic_rule_takes_precedence_over_failure_window(self) -> None:
        """Semantic rule fires even when failure_window_active is True."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="transform"),
            confidence=0.95,
            context=_context(failure_window_active=True),
        )
        self.assertEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")


class TestDemoPolicyGateFailureWindow(unittest.TestCase):
    """Failure window handling — inherited baseline safeguard."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_failure_window_returns_halt(self) -> None:
        """Failure window active → HALT when no semantic rule fires."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence=0.95,
            context=_context(failure_window_active=True),
        )
        self.assertEqual(decision.mode, ExecutionMode.HALT)
        self.assertEqual(decision.cause, PolicyCause.FAILURE_WINDOW)
        self.assertEqual(decision.rule_id, "RULE_001")

    def test_failure_window_does_not_preempt_rule3(self) -> None:
        """RULE_HIGH_SAFETY_UNBOUNDED takes precedence over failure window."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(bounded=False),
            confidence=0.95,
            context=_context(safety_level="HIGH", failure_window_active=True),
        )
        self.assertEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")

    def test_failure_window_does_not_preempt_rule4(self) -> None:
        """RULE_CHILD_TRANSFORM_REFUSED takes precedence over failure window."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="transform"),
            confidence=0.95,
            context=_context(failure_window_active=True),
        )
        self.assertEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_failure_window_reason_matches_default_gate(self) -> None:
        """Failure window reason is consistent with DefaultPolicyGate."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence=0.95,
            context=_context(failure_window_active=True),
        )
        self.assertEqual(
            decision.reason,
            "Failure window active — immediate halt required",
        )


class TestDemoPolicyGateBaselineThresholds(unittest.TestCase):
    """Baseline confidence thresholds — inherited from DefaultPolicyGate."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()
        self.proposal = _proposal()
        self.context = _context()

    def test_below_halt_threshold(self) -> None:
        """confidence < 0.40 → RULE_002, HALT."""
        decision = self.gate.evaluate(
            proposed_action=self.proposal,
            confidence=0.39,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.HALT)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_002")

    def test_below_retry_threshold(self) -> None:
        """confidence < 0.70 → RULE_003, RETRY."""
        decision = self.gate.evaluate(
            proposed_action=self.proposal,
            confidence=0.60,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.RETRY)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_003")

    def test_below_degrade_threshold(self) -> None:
        """confidence < 0.90 → RULE_004, DEGRADE."""
        decision = self.gate.evaluate(
            proposed_action=self.proposal,
            confidence=0.80,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.DEGRADE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_004")

    def test_at_execute_threshold(self) -> None:
        """confidence >= 0.90 → RULE_005, EXECUTE."""
        decision = self.gate.evaluate(
            proposed_action=self.proposal,
            confidence=0.95,
            context=self.context,
        )
        self.assertEqual(decision.mode, ExecutionMode.EXECUTE)
        self.assertEqual(decision.cause, PolicyCause.CONFIDENCE)
        self.assertEqual(decision.rule_id, "RULE_005")

    def test_exact_threshold_boundaries(self) -> None:
        """Exact threshold values map to the correct modes and rule IDs."""
        cases = [
            (0.40, ExecutionMode.RETRY, "RULE_003"),
            (0.70, ExecutionMode.DEGRADE, "RULE_004"),
            (0.90, ExecutionMode.EXECUTE, "RULE_005"),
        ]
        for confidence, expected_mode, expected_rule_id in cases:
            with self.subTest(confidence=confidence):
                decision = self.gate.evaluate(
                    proposed_action=self.proposal,
                    confidence=confidence,
                    context=self.context,
                )
                self.assertEqual(decision.mode, expected_mode)
                self.assertEqual(decision.rule_id, expected_rule_id)


class TestDemoPolicyGateDeterminism(unittest.TestCase):
    """Determinism — identical inputs produce identical outputs."""

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_semantic_rule_is_deterministic(self) -> None:
        """Repeated calls with identical inputs produce equal PolicyDecision."""
        proposal = _proposal(audience="child", request_kind="transform")
        context = _context()

        results = [
            self.gate.evaluate(
                proposed_action=proposal,
                confidence=0.95,
                context=context,
            )
            for _ in range(3)
        ]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_baseline_is_deterministic(self) -> None:
        """Baseline path repeated calls produce equal PolicyDecision."""
        proposal = _proposal()
        context = _context()

        results = [
            self.gate.evaluate(
                proposed_action=proposal,
                confidence=0.95,
                context=context,
            )
            for _ in range(3)
        ]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])


class TestDemoPolicyGateConfidenceValidationOrder(unittest.TestCase):
    """Confidence validation placement — load-bearing ordering proof.

    Proves that invalid confidence does not raise when Rules 1-4 fire,
    and does raise only when evaluation reaches the baseline stage.
    """

    def setUp(self) -> None:
        self.gate = DemoPolicyGate()

    def test_invalid_confidence_does_not_raise_when_rule1_fires(self) -> None:
        """RULE_OUT_OF_DOMAIN fires with invalid confidence — no ValueError."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(),
            confidence="not_a_float",
            context=_context(environment="banking"),
        )
        self.assertEqual(decision.rule_id, "RULE_OUT_OF_DOMAIN")

    def test_invalid_confidence_does_not_raise_when_rule2_fires(self) -> None:
        """RULE_MISSING_PARAMETERS fires with invalid confidence — no ValueError."""
        proposal = SimpleNamespace(action_type="llm_query", parameters={})
        decision = self.gate.evaluate(
            proposed_action=proposal,
            confidence="not_a_float",
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_MISSING_PARAMETERS")

    def test_invalid_confidence_does_not_raise_when_rule3_fires(self) -> None:
        """RULE_HIGH_SAFETY_UNBOUNDED fires with invalid confidence — no ValueError."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(bounded=False),
            confidence="not_a_float",
            context=_context(safety_level="HIGH"),
        )
        self.assertEqual(decision.rule_id, "RULE_HIGH_SAFETY_UNBOUNDED")

    def test_invalid_confidence_does_not_raise_when_rule4_fires(self) -> None:
        """RULE_CHILD_TRANSFORM_REFUSED fires with invalid confidence — no ValueError."""
        decision = self.gate.evaluate(
            proposed_action=_proposal(audience="child", request_kind="transform"),
            confidence="not_a_float",
            context=_context(),
        )
        self.assertEqual(decision.rule_id, "RULE_CHILD_TRANSFORM_REFUSED")

    def test_invalid_confidence_raises_only_at_baseline_stage(self) -> None:
        """ValueError raised only when evaluation reaches baseline confidence stage."""
        with self.assertRaises(ValueError):
            self.gate.evaluate(
                proposed_action=_proposal(),
                confidence="not_a_float",
                context=_context(),
            )

    def test_bool_confidence_raises_at_baseline_stage(self) -> None:
        """Bool confidence raises ValueError at baseline stage."""
        with self.assertRaises(ValueError):
            self.gate.evaluate(
                proposed_action=_proposal(),
                confidence=True,
                context=_context(),
            )


if __name__ == "__main__":
    unittest.main()

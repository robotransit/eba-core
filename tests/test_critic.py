# tests/test_critic.py
"""Invariant tests for critic subsystem (ADR-022–024)."""

from __future__ import annotations

import unittest

from eck.critic import critic_evaluate
from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
    ExecutionResult,
)


def _performed(outcome: str = "outcome") -> ExecutionResult:
    """Convenience constructor for a performed ExecutionResult."""
    return ExecutionResult(performed=True, outcome=outcome, refusal_reason=None)


def _refused(refusal_reason: str) -> ExecutionResult:
    """Convenience constructor for a refused ExecutionResult."""
    return ExecutionResult(performed=False, outcome="", refusal_reason=refusal_reason)


class TestCriticShortCircuit(unittest.TestCase):
    """Short-circuit path — performed=False bypasses LLM entirely (ADR-042)."""

    def _no_call_llm(self, prompt: str) -> str:
        """LLM callable that must never be called."""
        self.fail("LLM must not be called when performed=False")

    # ------------------------------------------------------------------
    # no_valid_proposal → deferred
    # ------------------------------------------------------------------
    def test_no_valid_proposal_returns_deferred(self) -> None:
        """performed=False with no_valid_proposal → category='deferred'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.category, "deferred")

    def test_no_valid_proposal_severity_zero(self) -> None:
        """performed=False with no_valid_proposal → severity=0.0."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertAlmostEqual(result.severity, 0.0)

    def test_no_valid_proposal_partial_structure_none(self) -> None:
        """performed=False with no_valid_proposal → partial_structure is None."""
        _, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertIsNone(partial)

    def test_no_valid_proposal_success_false(self) -> None:
        """performed=False with no_valid_proposal → success=False."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertFalse(result.success)

    def test_no_valid_proposal_feedback_is_refusal_reason(self) -> None:
        """performed=False with no_valid_proposal → feedback carries refusal_reason."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertIn("no_valid_proposal", result.feedback)

    # ------------------------------------------------------------------
    # gate:* → rejected
    # ------------------------------------------------------------------
    def test_gate_halt_returns_rejected(self) -> None:
        """performed=False with gate:HALT → category='rejected'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("gate:HALT"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.category, "rejected")
        self.assertIsNone(partial)

    def test_gate_retry_returns_rejected(self) -> None:
        """performed=False with gate:RETRY → category='rejected'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("gate:RETRY"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.category, "rejected")
        self.assertIsNone(partial)

    def test_gate_degrade_returns_rejected(self) -> None:
        """performed=False with gate:DEGRADE → category='rejected'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("gate:DEGRADE"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.category, "rejected")
        self.assertIsNone(partial)

    def test_gate_refusal_severity_zero(self) -> None:
        """performed=False with gate refusal → severity=0.0."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("gate:HALT"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertAlmostEqual(result.severity, 0.0)

    def test_gate_refusal_success_false(self) -> None:
        """performed=False with gate refusal → success=False."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("gate:HALT"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertFalse(result.success)

    # ------------------------------------------------------------------
    # Kernel refusal → rejected
    # ------------------------------------------------------------------
    def test_kernel_whitelist_refusal_returns_rejected(self) -> None:
        """performed=False with kernel refusal → category='rejected'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("action_type_not_whitelisted"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.category, "rejected")
        self.assertIsNone(partial)

    def test_kernel_missing_params_refusal_returns_rejected(self) -> None:
        """performed=False with missing params refusal → category='rejected'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("missing_required_parameters:prompt"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.category, "rejected")
        self.assertIsNone(partial)

    # ------------------------------------------------------------------
    # Cross-validation still short-circuits on performed=False
    # ------------------------------------------------------------------
    def test_short_circuit_with_cross_validation_enabled(self) -> None:
        """Cross-validation enabled does not prevent short-circuit on performed=False."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
            enable_cross_validation=True,
        )
        self.assertEqual(result.category, "deferred")
        self.assertIsNone(partial)

    # ------------------------------------------------------------------
    # Return type contract on short-circuit path
    # ------------------------------------------------------------------
    def test_short_circuit_returns_critic_outcome_instance(self) -> None:
        """Short-circuit path returns a CriticOutcome instance."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertIsInstance(result, CriticOutcome)

    def test_short_circuit_success_field_derived_from_category(self) -> None:
        """success field is always derived from category on short-circuit path."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=self._no_call_llm,
        )
        self.assertEqual(result.success, result.category == "success")


class TestCriticEvaluateSingleCall(unittest.TestCase):
    """Single-call (no cross-validation) critic behaviour — performed=True path."""

    def _llm(self, response: str):
        """Return a fixed-response LLM callable."""
        def llm(prompt: str) -> str:
            return response
        return llm

    # ------------------------------------------------------------------
    # Return type contract
    # ------------------------------------------------------------------
    def test_returns_tuple_of_critic_outcome_and_partial_structure(self) -> None:
        """critic_evaluate returns (CriticOutcome, PartialStructure | None)."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2, "feedback": "good"}'),
            enable_cross_validation=False,
        )
        self.assertIsInstance(result, CriticOutcome)
        self.assertIsNone(partial)

    def test_success_field_derived_from_category(self) -> None:
        """success field is always derived from category, never set independently."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2, "feedback": "good"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.success, result.category == "success")

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------
    def test_success_outcome_category(self) -> None:
        """Valid success JSON returns category='success'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2, "feedback": "good"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "success")
        self.assertTrue(result.success)
        self.assertIsNone(partial)

    def test_success_severity_preserved(self) -> None:
        """Severity from LLM is preserved on success path."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.3, "feedback": "ok"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 0.3)

    def test_success_feedback_preserved(self) -> None:
        """Feedback string from LLM is preserved on success path."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2, "feedback": "looks good"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.feedback, "looks good")

    # ------------------------------------------------------------------
    # Failure path and partial derivation
    # ------------------------------------------------------------------
    def test_high_severity_failure_returns_failure_category(self) -> None:
        """Failure with severity >= partial_threshold returns category='failure'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.8, "feedback": "bad"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertFalse(result.success)
        self.assertIsNone(partial)

    def test_low_severity_failure_returns_partial_category(self) -> None:
        """Failure with severity < partial_threshold returns category='partial'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.2, "feedback": "minor"}'),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertFalse(result.success)
        self.assertIsNotNone(partial)

    def test_severity_at_partial_threshold_returns_failure(self) -> None:
        """Failure with severity exactly at threshold returns category='failure'."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.5, "feedback": "borderline"}'),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "failure")
        self.assertIsNone(partial)

    def test_custom_partial_threshold(self) -> None:
        """partial_threshold parameter controls the partial/failure boundary."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.6, "feedback": "mid"}'),
            enable_cross_validation=False,
            partial_threshold=0.7,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)

    # ------------------------------------------------------------------
    # Pessimistic fallback (ADR-022)
    # ------------------------------------------------------------------
    def test_malformed_json_returns_failure(self) -> None:
        """Malformed JSON returns failure category."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm("not json at all"),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertFalse(result.success)
        self.assertIsNone(partial)

    def test_malformed_json_returns_severity_one(self) -> None:
        """Malformed JSON returns severity=1.0 (pessimistic fallback)."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm("not json at all"),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_malformed_json_feedback_is_non_empty_string(self) -> None:
        """Malformed JSON fallback produces non-empty feedback string."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm("not json at all"),
            enable_cross_validation=False,
        )
        self.assertIsInstance(result.feedback, str)
        self.assertTrue(result.feedback.strip())

    def test_empty_string_response_pessimistic_failure(self) -> None:
        """Empty string response returns pessimistic failure."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm(""),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertIsNone(partial)

    def test_non_string_llm_response_pessimistic_failure(self) -> None:
        """Non-string LLM response returns pessimistic failure."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=lambda prompt: None,
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertIsNone(partial)

    def test_unrecognised_outcome_value_returns_failure(self) -> None:
        """Unrecognised outcome value in JSON returns failure category."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "maybe", "severity": 0.5, "feedback": "unsure"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")

    def test_missing_outcome_key_returns_failure(self) -> None:
        """Missing outcome key in JSON defaults to failure."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"severity": 0.5, "feedback": "no outcome key"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")

    def test_missing_feedback_key_uses_default(self) -> None:
        """Missing feedback key uses default 'No feedback' string."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.feedback, "No feedback")

    def test_unparseable_severity_defaults_to_one(self) -> None:
        """Unparseable severity value defaults to 1.0."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": "bad", "feedback": "x"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_severity_clamped_above_one(self) -> None:
        """Severity above 1.0 in JSON is clamped to 1.0."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 1.5, "feedback": "x"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_severity_clamped_below_zero(self) -> None:
        """Severity below 0.0 in JSON is clamped to 0.0."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": -0.5, "feedback": "x"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 0.0)


class TestPartialStructureDerivation(unittest.TestCase):
    """PartialStructure derivation — kernel normalisation and invariants."""

    def _llm_partial(
        self,
        conflict_kind: str = "evidence_conflict",
        footprint: list[str] | None = None,
        severity: float = 0.2,
    ):
        """Return LLM callable producing a partial-triggering response."""
        fp = footprint if footprint is not None else ["local", "factual"]
        def llm(prompt: str) -> str:
            import json
            return json.dumps({
                "outcome": "failure",
                "severity": severity,
                "feedback": "partial outcome",
                "conflict_kind": conflict_kind,
                "conflict_footprint": fp,
            })
        return llm

    def test_partial_with_valid_structure_constructs_partial_structure(self) -> None:
        """Valid conflict_kind and footprint produce correct PartialStructure."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(
                conflict_kind="evidence_conflict",
                footprint=["local", "factual"],
            ),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_kind, ConflictKind.EVIDENCE_CONFLICT)
        self.assertIn(ConflictLocus.LOCAL, partial.conflict_footprint)
        self.assertIn(ConflictLocus.FACTUAL, partial.conflict_footprint)
        self.assertEqual(partial.collapse_status, "unresolved")

    def test_partial_missing_conflict_kind_normalises_to_fallback(self) -> None:
        """Missing conflict_kind normalises to RESOLUTION_INSTABILITY."""
        def llm(prompt: str) -> str:
            return '{"outcome": "failure", "severity": 0.2, "feedback": "x", "conflict_footprint": ["local"]}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_kind, ConflictKind.RESOLUTION_INSTABILITY)

    def test_partial_unknown_conflict_kind_normalises_to_fallback(self) -> None:
        """Unknown conflict_kind string normalises to RESOLUTION_INSTABILITY."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(conflict_kind="invented_kind"),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_kind, ConflictKind.RESOLUTION_INSTABILITY)

    def test_partial_empty_footprint_normalises_to_local(self) -> None:
        """Empty conflict_footprint normalises to {LOCAL}."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(footprint=[]),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_footprint, frozenset({ConflictLocus.LOCAL}))

    def test_partial_unknown_footprint_entries_dropped(self) -> None:
        """Unknown footprint entries are dropped; known entries preserved."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(footprint=["local", "invented_locus", "factual"]),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertIn(ConflictLocus.LOCAL, partial.conflict_footprint)
        self.assertIn(ConflictLocus.FACTUAL, partial.conflict_footprint)
        self.assertEqual(len(partial.conflict_footprint), 2)

    def test_partial_all_unknown_footprint_entries_normalises_to_local(self) -> None:
        """All unknown footprint entries → {LOCAL} fallback."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(footprint=["invented_a", "invented_b"]),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_footprint, frozenset({ConflictLocus.LOCAL}))

    def test_partial_non_list_footprint_normalises_to_local(self) -> None:
        """Non-list conflict_footprint (e.g. string) normalises to {LOCAL}."""
        def llm(prompt: str) -> str:
            return '{"outcome": "failure", "severity": 0.2, "feedback": "x", "conflict_kind": "evidence_conflict", "conflict_footprint": "local"}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_footprint, frozenset({ConflictLocus.LOCAL}))

    def test_partial_collapse_status_always_unresolved(self) -> None:
        """collapse_status is always 'unresolved' regardless of LLM output."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertIsNotNone(partial)
        self.assertEqual(partial.collapse_status, "unresolved")

    def test_partial_structure_is_frozenset(self) -> None:
        """conflict_footprint is a frozenset."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._llm_partial(),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertIsNotNone(partial)
        self.assertIsInstance(partial.conflict_footprint, frozenset)

    def test_success_with_structure_fields_returns_none_partial_structure(self) -> None:
        """Success outcome ignores structure fields — partial_structure is None."""
        def llm(prompt: str) -> str:
            return '{"outcome": "success", "severity": 0.1, "feedback": "good", "conflict_kind": "evidence_conflict", "conflict_footprint": ["local"]}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "success")
        self.assertIsNone(partial)

    def test_failure_with_structure_fields_returns_none_partial_structure(self) -> None:
        """High-severity failure ignores structure fields — partial_structure is None."""
        def llm(prompt: str) -> str:
            return '{"outcome": "failure", "severity": 0.9, "feedback": "bad", "conflict_kind": "evidence_conflict", "conflict_footprint": ["local"]}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertIsNone(partial)


class TestCriticCrossValidation(unittest.TestCase):
    """Cross-validation consensus and disagreement semantics (ADR-022)."""

    # ------------------------------------------------------------------
    # Consensus paths
    # ------------------------------------------------------------------
    def test_consensus_success_returns_success(self) -> None:
        """Both critics agree on success → success category."""
        def llm(prompt: str) -> str:
            return '{"outcome": "success", "severity": 0.2, "feedback": "good"}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertEqual(result.category, "success")
        self.assertTrue(result.success)
        self.assertIsNone(partial)

    def test_consensus_failure_returns_failure(self) -> None:
        """Both critics agree on failure → failure category (high severity)."""
        def llm(prompt: str) -> str:
            return '{"outcome": "failure", "severity": 0.8, "feedback": "bad"}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertEqual(result.category, "failure")
        self.assertIsNone(partial)

    def test_consensus_averages_severity(self) -> None:
        """Consensus path averages severity across both calls."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "failure", "severity": 0.6, "feedback": "a"}'
            return '{"outcome": "failure", "severity": 0.8, "feedback": "b"}'

        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertAlmostEqual(result.severity, 0.7)

    def test_consensus_feedback_contains_both(self) -> None:
        """Consensus feedback string contains content from both calls."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "success", "severity": 0.2, "feedback": "first"}'
            return '{"outcome": "success", "severity": 0.2, "feedback": "second"}'

        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertIn("first", result.feedback)
        self.assertIn("second", result.feedback)

    def test_consensus_on_partial_averages_severity_and_preserves_structure(self) -> None:
        """Both calls derive to partial: severity averaged, first-call structure retained."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "failure", "severity": 0.2, "feedback": "minor a", "conflict_kind": "evidence_conflict", "conflict_footprint": ["local", "factual"]}'
            return '{"outcome": "failure", "severity": 0.3, "feedback": "minor b", "conflict_kind": "constraint_conflict", "conflict_footprint": ["global"]}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertAlmostEqual(result.severity, 0.25)
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_kind, ConflictKind.EVIDENCE_CONFLICT)
        self.assertIn(ConflictLocus.LOCAL, partial.conflict_footprint)
        self.assertIn(ConflictLocus.FACTUAL, partial.conflict_footprint)

    def test_both_calls_are_made(self) -> None:
        """Cross-validation always invokes LLM exactly twice."""
        call_count = {"n": 0}

        def llm(prompt: str) -> str:
            call_count["n"] += 1
            return '{"outcome": "success", "severity": 0.2, "feedback": "ok"}'

        critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertEqual(call_count["n"], 2)

    def test_single_call_mode_invokes_llm_once(self) -> None:
        """No cross-validation invokes LLM exactly once."""
        call_count = {"n": 0}

        def llm(prompt: str) -> str:
            call_count["n"] += 1
            return '{"outcome": "success", "severity": 0.2, "feedback": "ok"}'

        critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
        )
        self.assertEqual(call_count["n"], 1)

    # ------------------------------------------------------------------
    # Disagreement path (ADR-022)
    # ------------------------------------------------------------------
    def test_disagreement_severity_clamped_to_one(self) -> None:
        """Disagreement clamps severity to 1.0 (ADR-022 invariant)."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "success", "severity": 0.2, "feedback": "yes"}'
            return '{"outcome": "failure", "severity": 0.4, "feedback": "no"}'

        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_disagreement_category_from_first_call(self) -> None:
        """Disagreement uses category from first call (ADR-022 invariant)."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "success", "severity": 0.2, "feedback": "yes"}'
            return '{"outcome": "failure", "severity": 0.8, "feedback": "no"}'

        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertEqual(result.category, "success")

    def test_disagreement_on_partial_preserves_partial_category_and_structure(self) -> None:
        """Disagreement at derived-category level preserves partial category and
        first-call PartialStructure."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "failure", "severity": 0.2, "feedback": "minor", "conflict_kind": "evidence_conflict", "conflict_footprint": ["local", "consistency"]}'
            return '{"outcome": "failure", "severity": 0.8, "feedback": "major"}'

        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertIsNotNone(partial)
        self.assertEqual(partial.conflict_kind, ConflictKind.EVIDENCE_CONFLICT)
        self.assertIn(ConflictLocus.LOCAL, partial.conflict_footprint)
        self.assertIn(ConflictLocus.CONSISTENCY, partial.conflict_footprint)

    def test_disagreement_logged_as_warning(self) -> None:
        """Disagreement emits a warning log entry."""
        import logging
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "success", "severity": 0.2, "feedback": "yes"}'
            return '{"outcome": "failure", "severity": 0.8, "feedback": "no"}'

        with self.assertLogs("eck-core", level=logging.WARNING) as cm:
            critic_evaluate(
                task_text="task",
                prediction="pred",
                result=_performed(),
                objective="obj",
                llm_call=llm,
                enable_cross_validation=True,
            )
        self.assertTrue(
            any("Critic disagreement detected" in msg for msg in cm.output)
        )

    def test_disagreement_feedback_contains_both(self) -> None:
        """Disagreement feedback contains content from both calls."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "success", "severity": 0.2, "feedback": "positive"}'
            return '{"outcome": "failure", "severity": 0.8, "feedback": "negative"}'

        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertIn("positive", result.feedback)
        self.assertIn("negative", result.feedback)

    # ------------------------------------------------------------------
    # Both calls malformed (ADR-022 pessimistic fallback)
    # ------------------------------------------------------------------
    def test_both_calls_malformed_returns_pessimistic_failure(self) -> None:
        """Both malformed calls return pessimistic failure, no disagreement warning."""
        import logging
        call_count = {"n": 0}

        def llm(prompt: str) -> str:
            call_count["n"] += 1
            return "nonsense"

        with self.assertLogs("eck-core", level=logging.WARNING) as cm:
            result, partial = critic_evaluate(
                task_text="task",
                prediction="pred",
                result=_performed(),
                objective="obj",
                llm_call=llm,
                enable_cross_validation=True,
            )

        self.assertEqual(call_count["n"], 2)
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertIsNone(partial)
        self.assertFalse(
            any("Critic disagreement detected" in msg for msg in cm.output)
        )


class TestVerifierCallback(unittest.TestCase):
    """External verifier callback can only demote, never promote (ADR-022)."""

    def _good_llm(self, prompt: str) -> str:
        return '{"outcome": "success", "severity": 0.2, "feedback": "good"}'

    def _partial_llm(self, prompt: str) -> str:
        return '{"outcome": "failure", "severity": 0.2, "feedback": "minor", "conflict_kind": "evidence_conflict", "conflict_footprint": ["local"]}'

    def test_verifier_false_demotes_success_to_failure(self) -> None:
        """Verifier returning False demotes success to failure, partial_structure=None."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=lambda t, r: False,
        )
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertFalse(result.success)
        self.assertIsNone(partial)

    def test_verifier_false_demotes_partial_to_failure(self) -> None:
        """Verifier returning False demotes partial to failure, partial_structure=None."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._partial_llm,
            enable_cross_validation=False,
            partial_threshold=0.5,
            verifier_callback=lambda t, r: False,
        )
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertIsNone(partial)

    def test_verifier_false_appends_to_feedback(self) -> None:
        """Verifier returning False appends verification failure to feedback."""
        result, _ = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=lambda t, r: False,
        )
        self.assertIn("External verification failed", result.feedback)

    def test_verifier_true_does_not_alter_outcome(self) -> None:
        """Verifier returning True does not alter the critic outcome."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=lambda t, r: True,
        )
        self.assertEqual(result.category, "success")
        self.assertTrue(result.success)
        self.assertIsNone(partial)

    def test_verifier_none_does_not_alter_outcome(self) -> None:
        """No verifier callback does not alter the critic outcome."""
        result, partial = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=None,
        )
        self.assertEqual(result.category, "success")
        self.assertIsNone(partial)

    def test_verifier_not_called_on_short_circuit(self) -> None:
        """Verifier callback is not invoked when performed=False."""
        verifier_calls = {"n": 0}

        def verifier(task: str, outcome: str) -> bool:
            verifier_calls["n"] += 1
            return False

        critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=lambda p: self.fail("LLM must not be called"),
            enable_cross_validation=False,
            verifier_callback=verifier,
        )
        self.assertEqual(verifier_calls["n"], 0)


class TestDeterminism(unittest.TestCase):
    """Identical inputs produce identical outputs."""

    def test_deterministic_replay_performed(self) -> None:
        """Identical performed inputs produce identical (CriticOutcome, PartialStructure)."""
        def llm(prompt: str) -> str:
            return '{"outcome": "failure", "severity": 0.2, "feedback": "minor", "conflict_kind": "evidence_conflict", "conflict_footprint": ["local", "factual"]}'

        result1, partial1 = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        result2, partial2 = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_performed(),
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result1, result2)
        self.assertEqual(partial1, partial2)

    def test_deterministic_replay_refused(self) -> None:
        """Identical refused inputs produce identical CriticOutcome."""
        result1, partial1 = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=lambda p: (_ for _ in ()).throw(AssertionError("must not call")),
            enable_cross_validation=False,
        )
        result2, partial2 = critic_evaluate(
            task_text="task",
            prediction="pred",
            result=_refused("no_valid_proposal"),
            objective="obj",
            llm_call=lambda p: (_ for _ in ()).throw(AssertionError("must not call")),
            enable_cross_validation=False,
        )
        self.assertEqual(result1, result2)
        self.assertIsNone(partial1)
        self.assertIsNone(partial2)


if __name__ == "__main__":
    unittest.main()

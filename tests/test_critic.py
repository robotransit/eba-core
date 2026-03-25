# tests/test_critic.py
"""Invariant tests for critic subsystem (ADR-022–024)."""

from __future__ import annotations

import unittest

from eck.critic import critic_evaluate
from eck.types import CriticOutcome, make_critic_outcome


class TestCriticEvaluateSingleCall(unittest.TestCase):
    """Single-call (no cross-validation) critic behaviour."""

    def _llm(self, response: str):
        """Return a fixed-response LLM callable."""
        def llm(prompt: str) -> str:
            return response
        return llm

    # ------------------------------------------------------------------
    # Return type contract
    # ------------------------------------------------------------------
    def test_returns_critic_outcome_instance(self) -> None:
        """critic_evaluate returns a CriticOutcome instance."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2, "feedback": "good"}'),
            enable_cross_validation=False,
        )
        self.assertIsInstance(result, CriticOutcome)

    def test_success_field_derived_from_category(self) -> None:
        """success field is always derived from category, never set independently."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
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
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2, "feedback": "good"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "success")
        self.assertTrue(result.success)

    def test_success_severity_preserved(self) -> None:
        """Severity from LLM is preserved on success path."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.3, "feedback": "ok"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 0.3)

    def test_success_feedback_preserved(self) -> None:
        """Feedback string from LLM is preserved on success path."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
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
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.8, "feedback": "bad"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertFalse(result.success)

    def test_low_severity_failure_returns_partial_category(self) -> None:
        """Failure with severity < partial_threshold returns category='partial'."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.2, "feedback": "minor"}'),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "partial")
        self.assertFalse(result.success)

    def test_severity_at_partial_threshold_returns_failure(self) -> None:
        """Failure with severity exactly at threshold returns category='failure'."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.5, "feedback": "borderline"}'),
            enable_cross_validation=False,
            partial_threshold=0.5,
        )
        self.assertEqual(result.category, "failure")

    def test_custom_partial_threshold(self) -> None:
        """partial_threshold parameter controls the partial/failure boundary."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 0.6, "feedback": "mid"}'),
            enable_cross_validation=False,
            partial_threshold=0.7,
        )
        self.assertEqual(result.category, "partial")

    # ------------------------------------------------------------------
    # Pessimistic fallback (ADR-022)
    # ------------------------------------------------------------------
    def test_malformed_json_returns_failure(self) -> None:
        """Malformed JSON returns failure category."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm("not json at all"),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertFalse(result.success)

    def test_malformed_json_returns_severity_one(self) -> None:
        """Malformed JSON returns severity=1.0 (pessimistic fallback)."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm("not json at all"),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_malformed_json_feedback_is_non_empty_string(self) -> None:
        """Malformed JSON fallback produces non-empty feedback string."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm("not json at all"),
            enable_cross_validation=False,
        )
        self.assertIsInstance(result.feedback, str)
        self.assertTrue(result.feedback.strip())

    def test_empty_string_response_pessimistic_failure(self) -> None:
        """Empty string response returns pessimistic failure."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm(""),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)

    def test_unrecognised_outcome_value_returns_failure(self) -> None:
        """Unrecognised outcome value in JSON returns failure category."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "maybe", "severity": 0.5, "feedback": "unsure"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")

    def test_missing_outcome_key_returns_failure(self) -> None:
        """Missing outcome key in JSON defaults to failure."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"severity": 0.5, "feedback": "no outcome key"}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.category, "failure")

    def test_missing_feedback_key_uses_default(self) -> None:
        """Missing feedback key uses default 'No feedback' string."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": 0.2}'),
            enable_cross_validation=False,
        )
        self.assertEqual(result.feedback, "No feedback")

    def test_unparseable_severity_defaults_to_one(self) -> None:
        """Unparseable severity value defaults to 1.0."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": "bad", "feedback": "x"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_severity_clamped_above_one(self) -> None:
        """Severity above 1.0 in JSON is clamped to 1.0."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "failure", "severity": 1.5, "feedback": "x"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 1.0)

    def test_severity_clamped_below_zero(self) -> None:
        """Severity below 0.0 in JSON is clamped to 0.0."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._llm('{"outcome": "success", "severity": -0.5, "feedback": "x"}'),
            enable_cross_validation=False,
        )
        self.assertAlmostEqual(result.severity, 0.0)


class TestCriticCrossValidation(unittest.TestCase):
    """Cross-validation consensus and disagreement semantics (ADR-022)."""

    # ------------------------------------------------------------------
    # Consensus paths
    # ------------------------------------------------------------------
    def test_consensus_success_returns_success(self) -> None:
        """Both critics agree on success → success category."""
        def llm(prompt: str) -> str:
            return '{"outcome": "success", "severity": 0.2, "feedback": "good"}'

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertEqual(result.category, "success")
        self.assertTrue(result.success)

    def test_consensus_failure_returns_failure(self) -> None:
        """Both critics agree on failure → failure category (high severity)."""
        def llm(prompt: str) -> str:
            return '{"outcome": "failure", "severity": 0.8, "feedback": "bad"}'

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertEqual(result.category, "failure")

    def test_consensus_averages_severity(self) -> None:
        """Consensus path averages severity across both calls."""
        calls = {"n": 0}

        def llm(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"outcome": "failure", "severity": 0.6, "feedback": "a"}'
            return '{"outcome": "failure", "severity": 0.8, "feedback": "b"}'

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
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

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        self.assertIn("first", result.feedback)
        self.assertIn("second", result.feedback)

    def test_both_calls_are_made(self) -> None:
        """Cross-validation always invokes LLM exactly twice."""
        call_count = {"n": 0}

        def llm(prompt: str) -> str:
            call_count["n"] += 1
            return '{"outcome": "success", "severity": 0.2, "feedback": "ok"}'

        critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
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
            result="outcome",
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

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
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

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=llm,
            enable_cross_validation=True,
        )
        # First call was success — category must be success despite disagreement
        self.assertEqual(result.category, "success")

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
                result="outcome",
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

        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
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
            result = critic_evaluate(
                task_text="task",
                prediction="pred",
                result="outcome",
                objective="obj",
                llm_call=llm,
                enable_cross_validation=True,
            )

        self.assertEqual(call_count["n"], 2)
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertFalse(
            any("Critic disagreement detected" in msg for msg in cm.output)
        )


class TestVerifierCallback(unittest.TestCase):
    """External verifier callback can only demote, never promote (ADR-022)."""

    def _good_llm(self, prompt: str) -> str:
        return '{"outcome": "success", "severity": 0.2, "feedback": "good"}'

    def test_verifier_false_demotes_to_failure(self) -> None:
        """Verifier returning False demotes outcome to failure."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=lambda t, r: False,
        )
        self.assertEqual(result.category, "failure")
        self.assertAlmostEqual(result.severity, 1.0)
        self.assertFalse(result.success)

    def test_verifier_false_appends_to_feedback(self) -> None:
        """Verifier returning False appends verification failure to feedback."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=lambda t, r: False,
        )
        self.assertIn("External verification failed", result.feedback)

    def test_verifier_true_does_not_alter_outcome(self) -> None:
        """Verifier returning True does not alter the critic outcome."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=lambda t, r: True,
        )
        self.assertEqual(result.category, "success")
        self.assertTrue(result.success)

    def test_verifier_none_does_not_alter_outcome(self) -> None:
        """No verifier callback does not alter the critic outcome."""
        result = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=self._good_llm,
            enable_cross_validation=False,
            verifier_callback=None,
        )
        self.assertEqual(result.category, "success")


class TestDeterminism(unittest.TestCase):
    """Identical inputs produce identical outputs."""

    def test_deterministic_replay(self) -> None:
        """Identical inputs produce identical CriticOutcome."""
        def llm(prompt: str) -> str:
            return '{"outcome": "success", "severity": 0.3, "feedback": "ok"}'

        result1 = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
        )
        result2 = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=llm,
            enable_cross_validation=False,
        )
        self.assertEqual(result1, result2)


if __name__ == "__main__":
    unittest.main()

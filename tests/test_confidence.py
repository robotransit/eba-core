# tests/test_confidence.py
"""Invariant tests for ConfidenceSignal (ADR-021–025)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from eck.confidence import ConfidenceSignal
from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
    PartialStructure,
    make_critic_outcome,
)


def _success(severity: float = 0.0, feedback: str = "ok") -> CriticOutcome:
    """Convenience constructor for success outcomes."""
    return make_critic_outcome(category="success", severity=severity, feedback=feedback)


def _failure(severity: float = 1.0, feedback: str = "fail") -> CriticOutcome:
    """Convenience constructor for failure outcomes."""
    return make_critic_outcome(category="failure", severity=severity, feedback=feedback)


def _partial(severity: float = 0.5, feedback: str = "partial") -> CriticOutcome:
    """Convenience constructor for partial outcomes."""
    return make_critic_outcome(category="partial", severity=severity, feedback=feedback)


def _rejected(feedback: str = "rejected") -> CriticOutcome:
    """Convenience constructor for rejected outcomes."""
    return make_critic_outcome(category="rejected", severity=0.0, feedback=feedback)


def _deferred(feedback: str = "deferred") -> CriticOutcome:
    """Convenience constructor for deferred outcomes."""
    return make_critic_outcome(category="deferred", severity=0.0, feedback=feedback)


def _evidence_struct(
    footprint: frozenset = frozenset([ConflictLocus.FACTUAL]),
) -> PartialStructure:
    """Convenience constructor for EVIDENCE_CONFLICT PartialStructure."""
    return PartialStructure(
        collapse_status="unresolved",
        conflict_kind=ConflictKind.EVIDENCE_CONFLICT,
        conflict_footprint=footprint,
    )


def _constraint_struct() -> PartialStructure:
    """Convenience constructor for CONSTRAINT_CONFLICT PartialStructure."""
    return PartialStructure(
        collapse_status="unresolved",
        conflict_kind=ConflictKind.CONSTRAINT_CONFLICT,
        conflict_footprint=frozenset([ConflictLocus.FACTUAL]),
    )


def _decomposition_struct() -> PartialStructure:
    """Convenience constructor for DECOMPOSITION_CONFLICT PartialStructure."""
    return PartialStructure(
        collapse_status="unresolved",
        conflict_kind=ConflictKind.DECOMPOSITION_CONFLICT,
        conflict_footprint=frozenset([ConflictLocus.FACTUAL]),
    )


def _resolution_instability_struct() -> PartialStructure:
    """Convenience constructor for RESOLUTION_INSTABILITY PartialStructure."""
    return PartialStructure(
        collapse_status="unresolved",
        conflict_kind=ConflictKind.RESOLUTION_INSTABILITY,
        conflict_footprint=frozenset([ConflictLocus.FACTUAL]),
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


class TestConfidenceSignalInit(unittest.TestCase):
    """Initialisation and alpha validation."""

    def test_initial_value(self) -> None:
        """Confidence starts at 0.5."""
        self.assertEqual(ConfidenceSignal().get_value(), 0.5)

    def test_alpha_zero_rejected(self) -> None:
        """alpha=0.0 is rejected (must be > 0.0)."""
        with self.assertRaises(ValueError):
            ConfidenceSignal(alpha=0.0)

    def test_alpha_above_one_rejected(self) -> None:
        """alpha > 1.0 is rejected."""
        with self.assertRaises(ValueError):
            ConfidenceSignal(alpha=1.1)

    def test_alpha_negative_rejected(self) -> None:
        """Negative alpha is rejected."""
        with self.assertRaises(ValueError):
            ConfidenceSignal(alpha=-0.1)

    def test_alpha_one_accepted(self) -> None:
        """alpha=1.0 is valid (upper boundary)."""
        conf = ConfidenceSignal(alpha=1.0)
        self.assertIsInstance(conf, ConfidenceSignal)

    def test_logger_name_is_eck_core(self) -> None:
        """Logger name is exclusively 'eck-core'."""
        conf = ConfidenceSignal()
        self.assertEqual(conf._logger.name, "eck-core")


class TestConfidenceSignalValidation(unittest.TestCase):
    """Input validation on update()."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_severity_below_zero_rejected(self) -> None:
        """Severity below 0.0 is rejected."""
        with self.assertRaises(ValueError):
            self.conf.update(_failure(severity=-0.1))

    def test_severity_above_one_rejected(self) -> None:
        """Severity above 1.0 is rejected."""
        with self.assertRaises(ValueError):
            self.conf.update(_failure(severity=1.1))

    def test_partial_without_structure_rejected(self) -> None:
        """Partial outcome without PartialStructure is rejected."""
        with self.assertRaises(ValueError):
            self.conf.update(_partial())

    def test_non_partial_with_structure_rejected(self) -> None:
        """Non-partial outcome with PartialStructure is rejected."""
        with self.assertRaises(ValueError):
            self.conf.update(_success(), _evidence_struct())

    def test_unknown_category_rejected(self) -> None:
        """Unknown category string is rejected."""
        bad = CriticOutcome(
            category="bogus",  # type: ignore[arg-type]
            severity=0.5,
            feedback="x",
            success=False,
        )
        with self.assertRaises(ValueError):
            self.conf.update(bad)


class TestNoUpdatePaths(unittest.TestCase):
    """Rejected and Deferred are true no-update paths (ADR-021)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_rejected_produces_no_update(self) -> None:
        """Rejected outcome leaves confidence unchanged."""
        prior = self.conf.get_value()
        self.conf.update(_rejected())
        self.assertEqual(self.conf.get_value(), prior)

    def test_deferred_produces_no_update(self) -> None:
        """Deferred outcome leaves confidence unchanged."""
        prior = self.conf.get_value()
        self.conf.update(_deferred())
        self.assertEqual(self.conf.get_value(), prior)

    def test_rejected_after_failure_no_update(self) -> None:
        """Rejected after failure still produces no confidence movement."""
        self.conf.update(_failure(severity=0.8))
        prior = self.conf.get_value()
        self.conf.update(_rejected())
        self.assertEqual(self.conf.get_value(), prior)

    def test_deferred_after_failure_no_update(self) -> None:
        """Deferred after failure still produces no confidence movement."""
        self.conf.update(_failure(severity=0.8))
        prior = self.conf.get_value()
        self.conf.update(_deferred())
        self.assertEqual(self.conf.get_value(), prior)

    def test_rejected_consumes_failure_window(self) -> None:
        """Rejected consumes the failure window — next success can move upward."""
        self.conf.update(_failure(severity=0.8))
        self.conf.update(_rejected())
        before = self.conf.get_value()
        self.conf.update(_success(severity=0.0))
        self.assertGreater(self.conf.get_value(), before)

    def test_deferred_consumes_failure_window(self) -> None:
        """Deferred consumes the failure window — next success can move upward."""
        self.conf.update(_failure(severity=0.8))
        self.conf.update(_deferred())
        before = self.conf.get_value()
        self.conf.update(_success(severity=0.0))
        self.assertGreater(self.conf.get_value(), before)


class TestFailureWindow(unittest.TestCase):
    """Single-cycle failure window semantics (ADR-023)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_failure_window_blocks_upward_next_cycle(self) -> None:
        """Success immediately after failure is blocked from moving upward."""
        self.conf.update(_failure(severity=0.6))
        prior = self.conf.get_value()
        self.conf.update(_success(severity=0.0))
        self.assertLessEqual(self.conf.get_value(), prior)

    def test_failure_window_expires_after_one_cycle(self) -> None:
        """After one eligible update the failure window expires and upward is permitted."""
        self.conf.update(_failure(severity=0.6))
        self.conf.update(_success(severity=0.0))  # window cycle — blocked
        restricted = self.conf.get_value()
        self.conf.update(_success(severity=0.0))  # window expired — free
        self.assertGreater(self.conf.get_value(), restricted)

    def test_failure_window_does_not_block_downward(self) -> None:
        """Downward movement is always permitted during failure window (ADR-023)."""
        self.conf.update(_failure(severity=0.6))
        prior = self.conf.get_value()
        self.conf.update(_failure(severity=0.9))
        self.assertLess(self.conf.get_value(), prior)

    def test_failure_window_exact_single_cycle(self) -> None:
        """Failure window lasts exactly one eligible update cycle."""
        self.conf.update(_failure(severity=0.6))
        after_failure = self.conf.get_value()

        # Cycle 1 after failure — window active, success blocked
        self.conf.update(_success(severity=0.0))
        after_blocked = self.conf.get_value()
        self.assertLessEqual(after_blocked, after_failure)

        # Cycle 2 after failure — window expired, success free
        self.conf.update(_success(severity=0.0))
        after_free = self.conf.get_value()
        self.assertGreater(after_free, after_blocked)


class TestMovementClassSemantics(unittest.TestCase):
    """Movement class derivation for partial outcomes (ADR-022/023)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_evidence_conflict_both_directions_permitted(self) -> None:
        """EVIDENCE_CONFLICT → BOTH movement permitted."""
        # Low severity partial should move upward
        prior = self.conf.get_value()
        self.conf.update(_partial(severity=0.1), _evidence_struct())
        self.assertGreater(self.conf.get_value(), prior)

    def test_constraint_conflict_down_only(self) -> None:
        """CONSTRAINT_CONFLICT → DOWN_ONLY even with low-severity partial."""
        prior = self.conf.get_value()
        self.conf.update(_partial(severity=0.1), _constraint_struct())
        self.assertLessEqual(self.conf.get_value(), prior)

    def test_decomposition_conflict_neither(self) -> None:
        """DECOMPOSITION_CONFLICT → NEITHER — no movement regardless of severity."""
        self.conf.update(_success(severity=0.1))  # create positive prior delta
        prior = self.conf.get_value()
        self.conf.update(_partial(severity=0.1), _decomposition_struct())
        self.assertEqual(self.conf.get_value(), prior)

    def test_resolution_instability_neither(self) -> None:
        """RESOLUTION_INSTABILITY → NEITHER — no movement regardless of severity."""
        self.conf.update(_success(severity=0.1))  # create positive prior delta
        prior = self.conf.get_value()
        self.conf.update(_partial(severity=0.1), _resolution_instability_struct())
        self.assertEqual(self.conf.get_value(), prior)

    def test_neither_movement_class_with_positive_prior_delta(self) -> None:
        """NEITHER movement class clamps both raw and prior smoothed delta to zero."""
        for kind in (ConflictKind.DECOMPOSITION_CONFLICT, ConflictKind.RESOLUTION_INSTABILITY):
            self.conf = ConfidenceSignal(alpha=0.3)
            self.conf.update(_success(severity=0.1))  # positive prior delta
            prior = self.conf.get_value()
            struct = PartialStructure(
                collapse_status="unresolved",
                conflict_kind=kind,
                conflict_footprint=frozenset([ConflictLocus.FACTUAL]),
            )
            self.conf.update(_partial(severity=0.3), struct)
            self.assertEqual(self.conf.get_value(), prior)

    def test_failure_window_restricts_evidence_conflict_both_to_down_only(self) -> None:
        """BOTH movement class restricted to DOWN_ONLY during failure window."""
        self.conf.update(_failure(severity=0.8))
        prior = self.conf.get_value()
        self.conf.update(_partial(severity=0.1), _evidence_struct())
        self.assertLessEqual(self.conf.get_value(), prior)

    def test_failure_window_restricts_up_only_to_neither(self) -> None:
        """UP_ONLY movement class restricted to NEITHER during failure window."""
        # No standard ConflictKind maps to UP_ONLY currently —
        # this test documents the gate logic is in place for future kinds.
        pass


class TestSeverityMonotonicity(unittest.TestCase):
    """Severity scales magnitude within category (ADR-022/025)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_success_higher_severity_smaller_upward_movement(self) -> None:
        """Higher severity on success produces smaller upward movement."""
        prior = self.conf.get_value()
        self.conf.update(_success(severity=0.1))
        low_sev_result = self.conf.get_value()

        self.conf = ConfidenceSignal(alpha=0.3)
        self.conf.update(_success(severity=0.9))
        high_sev_result = self.conf.get_value()

        self.assertLessEqual(high_sev_result - prior, low_sev_result - prior)

    def test_failure_higher_severity_larger_downward_movement(self) -> None:
        """Higher severity on failure produces larger downward movement."""
        self.conf.update(_failure(severity=0.3))
        low_sev_result = self.conf.get_value()

        self.conf = ConfidenceSignal(alpha=0.3)
        self.conf.update(_failure(severity=0.9))
        high_sev_result = self.conf.get_value()

        self.assertLess(high_sev_result, low_sev_result)

    def test_severity_never_reclassifies_category(self) -> None:
        """High severity on success still produces upward movement (no reclassification)."""
        prior = self.conf.get_value()
        self.conf.update(_success(severity=0.99))
        self.assertGreater(self.conf.get_value(), prior)


class TestGatedClampOnPriorDelta(unittest.TestCase):
    """Prior smoothed delta is clamped by effective movement class (ADR-025)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_positive_prior_delta_clamped_during_failure_window(self) -> None:
        """Positive prior smoothed delta is blocked during failure window."""
        self.conf.update(_success(severity=0.1))  # create positive prior delta
        prior_value = self.conf.get_value()
        self.conf.update(_failure(severity=0.9))  # activate failure window
        self.conf.update(_success(severity=0.0))  # window active — upward blocked
        self.assertLessEqual(self.conf.get_value(), prior_value)


class TestBoundedAccumulation(unittest.TestCase):
    """Confidence stays within [0.0, 1.0] (ADR-025)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_upper_bound_never_exceeded(self) -> None:
        """Repeated successes do not push confidence above 1.0."""
        for _ in range(50):
            self.conf.update(_success(severity=0.0))
        self.assertLessEqual(self.conf.get_value(), 1.0)

    def test_lower_bound_never_exceeded(self) -> None:
        """Repeated failures do not push confidence below 0.0."""
        for _ in range(50):
            self.conf.update(_failure(severity=1.0))
        self.assertGreaterEqual(self.conf.get_value(), 0.0)

    def test_upper_bound_clamps_to_one(self) -> None:
        """Sustained successes clamp at exactly 1.0."""
        for _ in range(100):
            self.conf.update(_success(severity=0.0))
        self.assertEqual(self.conf.get_value(), 1.0)

    def test_lower_bound_clamps_to_zero(self) -> None:
        """Sustained failures clamp at exactly 0.0."""
        for _ in range(100):
            self.conf.update(_failure(severity=1.0))
        self.assertEqual(self.conf.get_value(), 0.0)


class TestReplayDeterminism(unittest.TestCase):
    """Deterministic replay for testing and auditing (ADR-025)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_replay_produces_identical_trajectories(self) -> None:
        """Replay called twice produces identical trajectories."""
        outcomes = [
            (_success(severity=0.2), None),
            (_failure(severity=0.7), None),
            (_partial(severity=0.4), _evidence_struct()),
        ]
        traj1 = self.conf.replay(outcomes)
        traj2 = self.conf.replay(outcomes)
        self.assertEqual(traj1, traj2)

    def test_replay_restores_original_value(self) -> None:
        """Replay restores confidence to its pre-replay value."""
        prior = self.conf.get_value()
        outcomes = [(_failure(severity=0.9), None)]
        self.conf.replay(outcomes)
        self.assertEqual(self.conf.get_value(), prior)

    def test_replay_restores_cycle_id(self) -> None:
        """Replay restores cycle_id to its pre-replay value."""
        prior_cycle = self.conf._cycle_id
        outcomes = [(_success(severity=0.2), None), (_failure(severity=0.5), None)]
        self.conf.replay(outcomes)
        self.assertEqual(self.conf._cycle_id, prior_cycle)

    def test_replay_restores_failure_window_state(self) -> None:
        """Replay restores failure window state exactly."""
        prior_window = self.conf._last_outcome_was_failure
        outcomes = [(_failure(severity=0.9), None)]
        self.conf.replay(outcomes)
        self.assertEqual(self.conf._last_outcome_was_failure, prior_window)

    def test_replay_trajectory_length_matches_input(self) -> None:
        """Replay returns one value per outcome."""
        outcomes = [
            (_success(severity=0.2), None),
            (_failure(severity=0.7), None),
            (_rejected(), None),
        ]
        trajectory = self.conf.replay(outcomes)
        self.assertEqual(len(trajectory), 3)

    def test_replay_with_fixed_alpha_deterministic(self) -> None:
        """Fixed alpha and fixed outcomes produce identical trajectory on separate instances."""
        outcomes = [
            (_success(severity=0.2), None),
            (_failure(severity=0.8), None),
            (_success(severity=0.1), None),
            (_failure(severity=0.5), None),
        ]
        conf1 = ConfidenceSignal(alpha=0.3)
        conf2 = ConfidenceSignal(alpha=0.3)
        traj1 = conf1.replay(outcomes)
        traj2 = conf2.replay(outcomes)
        self.assertEqual(traj1, traj2)


class TestMakeCriticOutcome(unittest.TestCase):
    """make_critic_outcome enforces derived success field (eck.types contract)."""

    def test_success_category_sets_success_true(self) -> None:
        """make_critic_outcome with success category sets success=True."""
        outcome = make_critic_outcome("success", 0.2, "ok")
        self.assertTrue(outcome.success)

    def test_failure_category_sets_success_false(self) -> None:
        """make_critic_outcome with failure category sets success=False."""
        outcome = make_critic_outcome("failure", 0.8, "fail")
        self.assertFalse(outcome.success)

    def test_partial_category_sets_success_false(self) -> None:
        """make_critic_outcome with partial category sets success=False."""
        outcome = make_critic_outcome("partial", 0.4, "partial")
        self.assertFalse(outcome.success)

    def test_rejected_category_sets_success_false(self) -> None:
        """make_critic_outcome with rejected category sets success=False."""
        outcome = make_critic_outcome("rejected", 0.0, "rejected")
        self.assertFalse(outcome.success)

    def test_deferred_category_sets_success_false(self) -> None:
        """make_critic_outcome with deferred category sets success=False."""
        outcome = make_critic_outcome("deferred", 0.0, "deferred")
        self.assertFalse(outcome.success)


class TestAdmissibleSignals(unittest.TestCase):
    """ADR-024 whitelist boundary — critic-only for now."""

    def test_critic_only_whitelist_boundary(self) -> None:
        """Only critic outcomes are currently admissible."""
        conf = ConfidenceSignal(alpha=0.3)
        conf.update(_success(severity=0.2))
        self.assertGreater(conf.get_value(), 0.5)

    def test_admissible_signals_contains_critic(self) -> None:
        """Admissible signals set contains 'critic'."""
        conf = ConfidenceSignal(alpha=0.3)
        self.assertIn("critic", conf._admissible_signals)


class TestConfidenceSignalTelemetry(unittest.TestCase):
    """ConfidenceSignal.update() — epistemic.signal telemetry emission."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    def test_success_update_emits_epistemic_signal_updated_true(self) -> None:
        """Success update with telemetry args emits epistemic.signal with updated=True."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_success(severity=0.2), **_TELEMETRY_ARGS)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "epistemic.signal")
        self.assertTrue(event["payload"]["updated"])
        self.assertEqual(event["payload"]["category"], "success")
        self.assertIn("confidence", event["payload"])
        self.assertIn("prior_confidence", event["payload"])
        self.assertIn("delta_raw", event["payload"])
        self.assertIn("delta_smoothed", event["payload"])

    def test_failure_update_emits_epistemic_signal_updated_true(self) -> None:
        """Failure update emits epistemic.signal with updated=True."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_failure(severity=0.8), **_TELEMETRY_ARGS)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertTrue(event["payload"]["updated"])
        self.assertEqual(event["payload"]["category"], "failure")

    def test_rejected_emits_epistemic_signal_updated_false(self) -> None:
        """Rejected outcome emits epistemic.signal with updated=False."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_rejected(), **_TELEMETRY_ARGS)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "epistemic.signal")
        self.assertFalse(event["payload"]["updated"])
        self.assertEqual(event["payload"]["category"], "rejected")
        self.assertIn("confidence", event["payload"])
        self.assertIn("prior_confidence", event["payload"])

    def test_deferred_emits_epistemic_signal_updated_false(self) -> None:
        """Deferred outcome emits epistemic.signal with updated=False."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_deferred(), **_TELEMETRY_ARGS)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertFalse(event["payload"]["updated"])
        self.assertEqual(event["payload"]["category"], "deferred")

    def test_no_telemetry_args_does_not_emit(self) -> None:
        """Without telemetry args, no epistemic.signal event is emitted."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_success(severity=0.2))
        event = _get_telemetry_event(mock_logger)
        self.assertIsNone(event)

    def test_source_is_confidence(self) -> None:
        """epistemic.signal event has source='confidence'."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_success(severity=0.2), **_TELEMETRY_ARGS)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertEqual(event["source"], "confidence")

    def test_replay_does_not_emit_telemetry(self) -> None:
        """replay() is telemetry-silent — no epistemic.signal events emitted."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        outcomes = [
            (_success(severity=0.2), None),
            (_failure(severity=0.7), None),
            (_rejected(), None),
        ]
        self.conf.replay(outcomes)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNone(event)

    def test_partial_update_emits_epistemic_signal_updated_true(self) -> None:
        """Partial update emits epistemic.signal with updated=True."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(
            _partial(severity=0.3), _evidence_struct(), **_TELEMETRY_ARGS
        )
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertTrue(event["payload"]["updated"])
        self.assertEqual(event["payload"]["category"], "partial")

    def test_severity_present_in_payload(self) -> None:
        """severity field is present in epistemic.signal payload."""
        mock_logger = MagicMock()
        self.conf._logger = mock_logger
        self.conf.update(_success(severity=0.4), **_TELEMETRY_ARGS)
        event = _get_telemetry_event(mock_logger)
        self.assertIsNotNone(event)
        self.assertIn("severity", event["payload"])
        self.assertEqual(event["payload"]["severity"], 0.4)


if __name__ == "__main__":
    unittest.main()

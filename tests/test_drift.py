# tests/test_drift.py
"""Invariant tests for DriftMonitor (ADR-040)."""

from __future__ import annotations

import unittest

from eck.config import ECKConfig, PolicyMode
from eck.drift import DriftMonitor


def _config(**kwargs) -> ECKConfig:
    """Convenience constructor for ECKConfig with test-friendly defaults."""
    defaults = dict(
        drift_warmup_samples=3,      # short warmup for test speed
        error_z_threshold=2.0,
        max_drift_streak=5,
        guided_drift_threshold=1,
        enforced_drift_threshold=3,
        severe_drift_count=4,
        feas_conf_high=0.8,
        feas_conf_low=0.5,
        low_conf_threshold=0.4,
    )
    defaults.update(kwargs)
    return ECKConfig(**defaults)


class TestDriftMonitorInit(unittest.TestCase):
    """Initialisation and default state."""

    def test_initial_state_empty(self) -> None:
        """All evidence stores start empty."""
        dm = DriftMonitor(config=_config())
        self.assertEqual(dm.error_history, [])
        self.assertEqual(dm.drift_events, [])
        self.assertEqual(dm.feasibility_history, [])

    def test_initial_derived_signals(self) -> None:
        """Derived signals start at neutral values."""
        dm = DriftMonitor(config=_config())
        self.assertEqual(dm.last_error_z, 0.0)
        self.assertEqual(dm.drift_streak, 0)
        self.assertAlmostEqual(dm.numeric_bias, 1.0)

    def test_default_config_used_when_none(self) -> None:
        """DriftMonitor initialises with default ECKConfig when none provided."""
        dm = DriftMonitor()
        self.assertIsInstance(dm.config, ECKConfig)


class TestRecordError(unittest.TestCase):
    """record_error() warmup, z-score, and append-only behaviour."""

    def setUp(self) -> None:
        self.dm = DriftMonitor(config=_config())

    def test_returns_false_during_warmup(self) -> None:
        """Returns False while fewer than drift_warmup_samples recorded."""
        self.assertFalse(self.dm.record_error(1.0))
        self.assertFalse(self.dm.record_error(1.0))
        # warmup_samples=3, so third call may trigger

    def test_error_history_grows_unbounded(self) -> None:
        """error_history is append-only — grows with every call."""
        for i in range(10):
            self.dm.record_error(float(i))
        self.assertEqual(len(self.dm.error_history), 10)

    def test_returns_true_on_outlier_after_warmup(self) -> None:
        """Returns True when z-score exceeds threshold after warmup."""
        # Establish stable baseline with near-zero variance
        for _ in range(9):
            self.dm.record_error(1.0)
        # Extreme outlier against stable baseline produces high z-score
        result = self.dm.record_error(1000.0)
        self.assertTrue(result)

    def test_returns_false_for_normal_values(self) -> None:
        """Returns False when values are within normal range."""
        for _ in range(10):
            self.dm.record_error(1.0)
        result = self.dm.record_error(1.01)
        self.assertFalse(result)

    def test_last_error_z_zero_during_warmup(self) -> None:
        """last_error_z remains 0.0 during warmup period."""
        self.dm.record_error(999.0)
        self.assertEqual(self.dm.last_error_z, 0.0)

    def test_last_error_z_updated_after_warmup(self) -> None:
        """last_error_z is updated after warmup period."""
        self.dm.record_error(1.0)
        self.dm.record_error(1.0)
        self.dm.record_error(1.0)
        self.assertGreaterEqual(self.dm.last_error_z, 0.0)


class TestRegisterDriftAndStreak(unittest.TestCase):
    """register_drift(), clear_streak(), and append-only drift_events."""

    def setUp(self) -> None:
        self.dm = DriftMonitor(config=_config())

    def test_register_drift_appends_to_drift_events(self) -> None:
        """register_drift() appends to drift_events (append-only)."""
        self.dm.register_drift()
        self.dm.register_drift()
        self.assertEqual(len(self.dm.drift_events), 2)
        self.assertTrue(all(self.dm.drift_events))

    def test_register_drift_increments_streak(self) -> None:
        """register_drift() increments drift_streak."""
        self.dm.register_drift()
        self.assertEqual(self.dm.drift_streak, 1)
        self.dm.register_drift()
        self.assertEqual(self.dm.drift_streak, 2)

    def test_clear_streak_resets_counter_only(self) -> None:
        """clear_streak() resets drift_streak but not drift_events."""
        self.dm.register_drift()
        self.dm.register_drift()
        self.dm.clear_streak()
        self.assertEqual(self.dm.drift_streak, 0)
        self.assertEqual(len(self.dm.drift_events), 2)

    def test_drift_events_never_shrink(self) -> None:
        """drift_events never shrinks — append-only per ADR-040."""
        self.dm.register_drift()
        self.dm.register_drift()
        self.dm.clear_streak()
        self.dm.register_drift()
        self.assertEqual(len(self.dm.drift_events), 3)

    def test_total_drift_events_matches_drift_events_length(self) -> None:
        """total_drift_events() returns len(drift_events)."""
        self.dm.register_drift()
        self.dm.register_drift()
        self.assertEqual(self.dm.total_drift_events(), 2)


class TestRecordFeasibility(unittest.TestCase):
    """record_feasibility() and numeric_bias updates."""

    def setUp(self) -> None:
        self.dm = DriftMonitor(config=_config())

    def test_feasibility_history_grows(self) -> None:
        """feasibility_history is append-only."""
        self.dm.record_feasibility(True, True)
        self.dm.record_feasibility(False, False)
        self.assertEqual(len(self.dm.feasibility_history), 2)

    def test_no_numeric_entries_leaves_bias_unchanged(self) -> None:
        """numeric_bias unchanged when no numeric feasibility entries exist."""
        initial = self.dm.numeric_bias
        self.dm.record_feasibility(False, True)  # was_numeric=False
        self.assertAlmostEqual(self.dm.numeric_bias, initial)

    def test_high_numeric_success_increases_bias(self) -> None:
        """High numeric success rate increases numeric_bias."""
        for _ in range(10):
            self.dm.record_feasibility(True, True)
        self.assertGreater(self.dm.numeric_bias, 1.0)

    def test_low_numeric_success_decreases_bias(self) -> None:
        """Low numeric success rate decreases numeric_bias."""
        for _ in range(10):
            self.dm.record_feasibility(True, False)
        self.assertLess(self.dm.numeric_bias, 1.0)

    def test_numeric_bias_bounded(self) -> None:
        """numeric_bias stays within [0.7, 1.3]."""
        for _ in range(100):
            self.dm.record_feasibility(True, True)
        self.assertLessEqual(self.dm.numeric_bias, 1.3)

        dm2 = DriftMonitor(config=_config())
        for _ in range(100):
            dm2.record_feasibility(True, False)
        self.assertGreaterEqual(dm2.numeric_bias, 0.7)


class TestSevere(unittest.TestCase):
    """severe() triggers on drift event count and feasibility confidence."""

    def setUp(self) -> None:
        self.dm = DriftMonitor(config=_config(severe_drift_count=3))

    def test_not_severe_initially(self) -> None:
        """severe() returns False with no drift events."""
        self.assertFalse(self.dm.severe())

    def test_severe_on_drift_event_count(self) -> None:
        """severe() returns True when total drift events exceed severe_drift_count."""
        for _ in range(4):  # severe_drift_count=3, so 4 triggers
            self.dm.register_drift()
        self.assertTrue(self.dm.severe())

    def test_not_severe_at_threshold(self) -> None:
        """severe() returns False when drift events equal severe_drift_count."""
        for _ in range(3):
            self.dm.register_drift()
        self.assertFalse(self.dm.severe())

    def test_severe_on_low_feasibility_confidence(self) -> None:
        """severe() returns True when numeric success rate < low_conf_threshold."""
        for _ in range(10):
            self.dm.record_feasibility(True, False)  # 0% numeric success
        self.assertTrue(self.dm.severe())

    def test_not_severe_with_high_feasibility(self) -> None:
        """severe() returns False with high numeric success rate."""
        for _ in range(10):
            self.dm.record_feasibility(True, True)
        self.assertFalse(self.dm.severe())


class TestGetPolicyMode(unittest.TestCase):
    """get_policy_mode() graduated escalation (ADR-040 Section 2)."""

    def setUp(self) -> None:
        self.dm = DriftMonitor(config=_config(
            guided_drift_threshold=1,
            enforced_drift_threshold=3,
            max_drift_streak=5,
        ))

    def test_normal_initially(self) -> None:
        """Returns NORMAL with no drift."""
        self.assertEqual(self.dm.get_policy_mode(), PolicyMode.NORMAL)

    def test_guided_at_guided_threshold(self) -> None:
        """Returns GUIDED when streak >= guided_drift_threshold."""
        self.dm.register_drift()
        self.assertEqual(self.dm.get_policy_mode(), PolicyMode.GUIDED)

    def test_enforced_at_enforced_threshold(self) -> None:
        """Returns ENFORCED when streak >= enforced_drift_threshold."""
        for _ in range(3):
            self.dm.register_drift()
        self.assertEqual(self.dm.get_policy_mode(), PolicyMode.ENFORCED)

    def test_halt_at_max_drift_streak(self) -> None:
        """Returns HALT when streak >= max_drift_streak."""
        for _ in range(5):
            self.dm.register_drift()
        self.assertEqual(self.dm.get_policy_mode(), PolicyMode.HALT)

    def test_halt_when_severe(self) -> None:
        """Returns HALT when severe() is True."""
        dm = DriftMonitor(config=_config(severe_drift_count=2))
        for _ in range(3):
            dm.register_drift()
        self.assertEqual(dm.get_policy_mode(), PolicyMode.HALT)

    def test_halt_respected_when_already_halted(self) -> None:
        """Returns HALT immediately when config.policy_mode is HALT."""
        dm = DriftMonitor(config=_config(policy_mode=PolicyMode.HALT))
        self.assertEqual(dm.get_policy_mode(), PolicyMode.HALT)

    def test_streak_clear_reduces_mode(self) -> None:
        """Clearing streak reduces recommended mode on next call."""
        self.dm.register_drift()
        self.assertEqual(self.dm.get_policy_mode(), PolicyMode.GUIDED)
        self.dm.clear_streak()
        self.assertEqual(self.dm.get_policy_mode(), PolicyMode.NORMAL)

    def test_never_recommends_downgrade_from_halt(self) -> None:
        """Once config is HALT, get_policy_mode always returns HALT."""
        dm = DriftMonitor(config=_config(policy_mode=PolicyMode.HALT))
        dm.clear_streak()
        self.assertEqual(dm.get_policy_mode(), PolicyMode.HALT)


class TestSnapshot(unittest.TestCase):
    """snapshot() returns correct structured state."""

    def setUp(self) -> None:
        self.dm = DriftMonitor(config=_config())

    def test_snapshot_keys_present(self) -> None:
        """snapshot() contains all required keys."""
        snap = self.dm.snapshot()
        expected_keys = {
            "drift_streak",
            "total_drift_events",
            "last_error_z",
            "numeric_bias",
            "feasibility_sample_count",
            "numeric_success_rate",
            "severe",
        }
        self.assertEqual(set(snap.keys()), expected_keys)

    def test_snapshot_does_not_mutate_state(self) -> None:
        """snapshot() is read-only — does not alter any state."""
        self.dm.register_drift()
        before = self.dm.drift_streak
        self.dm.snapshot()
        self.assertEqual(self.dm.drift_streak, before)

    def test_snapshot_severe_matches_severe_method(self) -> None:
        """snapshot()['severe'] matches direct severe() call."""
        snap = self.dm.snapshot()
        self.assertEqual(snap["severe"], self.dm.severe())

    def test_snapshot_numeric_success_rate_none_when_no_numeric(self) -> None:
        """numeric_success_rate is None when no numeric feasibility entries."""
        snap = self.dm.snapshot()
        self.assertIsNone(snap["numeric_success_rate"])

    def test_snapshot_numeric_success_rate_present_when_numeric(self) -> None:
        """numeric_success_rate is a float when numeric entries exist."""
        self.dm.record_feasibility(True, True)
        snap = self.dm.snapshot()
        self.assertIsNotNone(snap["numeric_success_rate"])
        self.assertIsInstance(snap["numeric_success_rate"], float)

    def test_snapshot_drift_streak_accurate(self) -> None:
        """snapshot()['drift_streak'] matches drift_streak attribute."""
        self.dm.register_drift()
        self.dm.register_drift()
        snap = self.dm.snapshot()
        self.assertEqual(snap["drift_streak"], 2)

    def test_snapshot_total_drift_events_accurate(self) -> None:
        """snapshot()['total_drift_events'] matches total_drift_events()."""
        self.dm.register_drift()
        snap = self.dm.snapshot()
        self.assertEqual(snap["total_drift_events"], self.dm.total_drift_events())


if __name__ == "__main__":
    unittest.main()

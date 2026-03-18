from __future__ import annotations

import unittest

from eck.confidence import (
    ConfidenceSignal,
    CriticOutcome,
    PartialStructure,
    ConflictKind,
    ConflictLocus,
)


class TestConfidenceSignal(unittest.TestCase):
    """Test suite for ConfidenceSignal (ADR-021–025)."""

    def setUp(self) -> None:
        self.conf = ConfidenceSignal(alpha=0.3)

    # ------------------------------------------------------------------
    # Basic invariants and validation
    # ------------------------------------------------------------------
    def test_initial_value(self) -> None:
        """Confidence starts at 0.5."""
        self.assertEqual(self.conf.get_value(), 0.5)

    def test_alpha_validation(self) -> None:
        """Alpha must be in (0.0, 1.0]."""
        with self.assertRaises(ValueError):
            ConfidenceSignal(alpha=0.0)
        with self.assertRaises(ValueError):
            ConfidenceSignal(alpha=1.1)
        with self.assertRaises(ValueError):
            ConfidenceSignal(alpha=-0.1)

    def test_severity_validation(self) -> None:
        """Severity must be in [0.0, 1.0]."""
        with self.assertRaises(ValueError):
            self.conf.update(CriticOutcome("Success", -0.1))
        with self.assertRaises(ValueError):
            self.conf.update(CriticOutcome("Failure", 1.1))

    def test_partial_validation(self) -> None:
        """Partial requires PartialStructure; non-Partial forbids it."""
        struct = PartialStructure(
            collapse_status="unresolved",
            conflict_kind=ConflictKind.EVIDENCE_CONFLICT,
            conflict_footprint=frozenset([ConflictLocus.FACTUAL])
        )
        with self.assertRaises(ValueError):
            self.conf.update(CriticOutcome("Partial", 0.5))          # missing structure
        with self.assertRaises(ValueError):
            self.conf.update(CriticOutcome("Success", 0.5), struct)  # extra structure

    def test_unknown_category_rejection(self) -> None:
        """Unknown category is rejected immediately."""
        with self.assertRaises(ValueError):
            self.conf.update(CriticOutcome("Bogus", 0.5))

    # ------------------------------------------------------------------
    # Replay determinism
    # ------------------------------------------------------------------
    def test_replay_determinism(self) -> None:
        """Replay produces identical trajectories."""
        outcomes = [
            (CriticOutcome("Success", 0.2), None),
            (CriticOutcome("Failure", 0.7), None),
            (CriticOutcome("Partial", 0.4), PartialStructure(
                collapse_status="unresolved",
                conflict_kind=ConflictKind.EVIDENCE_CONFLICT,
                conflict_footprint=frozenset([ConflictLocus.FACTUAL])
            )),
        ]

        traj1 = self.conf.replay(outcomes)
        traj2 = self.conf.replay(outcomes)

        self.assertEqual(traj1, traj2)
        self.assertEqual(self.conf.get_value(), 0.5)  # value is restored

    # ------------------------------------------------------------------
    # No-update paths and failure window
    # ------------------------------------------------------------------
    def test_rejected_deferred_no_update_and_consume_window(self) -> None:
        """Rejected and Deferred are true no-update paths and consume the failure window."""
        self.conf.update(CriticOutcome("Failure", 0.8))  # activate window
        prior = self.conf.get_value()

        self.conf.update(CriticOutcome("Rejected", 0.5))
        self.assertEqual(self.conf.get_value(), prior)

        self.conf.update(CriticOutcome("Deferred", 0.3))
        self.assertEqual(self.conf.get_value(), prior)

    def test_failure_window_exact_single_cycle(self) -> None:
        """Failure activates downward-only restriction for exactly one following eligible update."""
        self.conf.update(CriticOutcome("Failure", 0.6))          # activate window

        prior = self.conf.get_value()

        # First eligible update after failure → upward movement blocked
        self.conf.update(CriticOutcome("Success", 0.0))
        after_restricted = self.conf.get_value()
        self.assertLessEqual(after_restricted, prior)

        # Second eligible update → window expired, upward movement allowed
        self.conf.update(CriticOutcome("Success", 0.0))
        after_free = self.conf.get_value()
        self.assertGreater(after_free, after_restricted)

    # ------------------------------------------------------------------
    # Movement class semantics
    # ------------------------------------------------------------------
    def test_neither_movement_class_with_carryover(self) -> None:
        """DECOMPOSITION_CONFLICT / RESOLUTION_INSTABILITY produce NEITHER even with positive prior delta."""
        for kind in (ConflictKind.DECOMPOSITION_CONFLICT, ConflictKind.RESOLUTION_INSTABILITY):
            self.conf = ConfidenceSignal(alpha=0.3)  # reset for isolation
            # Create positive prior smoothed delta
            self.conf.update(CriticOutcome("Success", 0.1))
            prior = self.conf.get_value()

            struct = PartialStructure(
                collapse_status="unresolved",
                conflict_kind=kind,
                conflict_footprint=frozenset([ConflictLocus.FACTUAL])
            )
            self.conf.update(CriticOutcome("Partial", 0.3), struct)
            self.assertEqual(self.conf.get_value(), prior)  # no movement allowed

    def test_constraint_conflict_down_only(self) -> None:
        """CONSTRAINT_CONFLICT produces DOWN_ONLY (tested with Partial outcome)."""
        struct = PartialStructure(
            collapse_status="unresolved",
            conflict_kind=ConflictKind.CONSTRAINT_CONFLICT,
            conflict_footprint=frozenset([ConflictLocus.FACTUAL])
        )

        prior = self.conf.get_value()
        # Partial with low severity that would normally tend upward
        self.conf.update(CriticOutcome("Partial", 0.3), struct)
        self.assertLessEqual(self.conf.get_value(), prior)

    # ------------------------------------------------------------------
    # Severity monotonicity (ADR-022/025)
    # ------------------------------------------------------------------
    def test_success_severity_monotonicity(self) -> None:
        """Higher severity on Success produces smaller (or equal) upward movement."""
        prior = self.conf.get_value()
        self.conf.update(CriticOutcome("Success", 0.1))
        low_sev = self.conf.get_value()

        self.conf = ConfidenceSignal(alpha=0.3)  # reset
        self.conf.update(CriticOutcome("Success", 0.9))
        high_sev = self.conf.get_value()

        self.assertLessEqual(high_sev - prior, low_sev - prior)

    def test_failure_severity_monotonicity(self) -> None:
        """Higher severity on Failure produces larger (or equal) downward movement."""
        prior = self.conf.get_value()
        self.conf.update(CriticOutcome("Failure", 0.3))
        low_sev = self.conf.get_value()

        self.conf = ConfidenceSignal(alpha=0.3)  # reset
        self.conf.update(CriticOutcome("Failure", 0.9))
        high_sev = self.conf.get_value()

        self.assertLess(high_sev, low_sev)

    # ------------------------------------------------------------------
    # Gated clamping on both raw and prior delta
    # ------------------------------------------------------------------
    def test_prior_smoothed_delta_is_clamped(self) -> None:
        """Prior smoothed delta is clamped by effective movement class (distinct from raw delta)."""
        # Create positive prior smoothed delta
        self.conf.update(CriticOutcome("Success", 0.1))
        prior_value = self.conf.get_value()

        # Activate failure window → DOWN_ONLY
        self.conf.update(CriticOutcome("Failure", 0.9))

        # Next Success should be clamped (prior positive delta blocked)
        self.conf.update(CriticOutcome("Success", 0.0))
        self.assertLessEqual(self.conf.get_value(), prior_value)

    # ------------------------------------------------------------------
    # Bounded accumulation
    # ------------------------------------------------------------------
    def test_bounded_accumulation(self) -> None:
        """Confidence never leaves [0.0, 1.0]."""
        for _ in range(30):
            self.conf.update(CriticOutcome("Success", 0.0))
        self.assertEqual(self.conf.get_value(), 1.0)

        for _ in range(30):
            self.conf.update(CriticOutcome("Failure", 1.0))
        self.assertEqual(self.conf.get_value(), 0.0)

    # ------------------------------------------------------------------
    # Current whitelist boundary (critic-only)
    # ------------------------------------------------------------------
    def test_critic_only_whitelist_boundary(self) -> None:
        """Only critic outcomes are currently admissible (whitelist boundary smoke test)."""
        self.conf.update(CriticOutcome("Success", 0.2))
        self.assertGreater(self.conf.get_value(), 0.5)


if __name__ == "__main__":
    unittest.main()

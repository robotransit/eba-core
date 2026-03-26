# tests/test_utils.py
"""Tests for ECK utility functions."""

from __future__ import annotations

import logging
import unittest

from eck.config import PolicyMode
from eck.utils import get_recommended_breadth, is_numeric_feasible, should_execute


class TestGetRecommendedBreadth(unittest.TestCase):
    """get_recommended_breadth() maps confidence and policy mode to breadth."""

    def test_normal_mode_always_full(self) -> None:
        """NORMAL mode always returns FULL regardless of confidence."""
        self.assertEqual(get_recommended_breadth(0.9, PolicyMode.NORMAL), "FULL")
        self.assertEqual(get_recommended_breadth(0.5, PolicyMode.NORMAL), "FULL")
        self.assertEqual(get_recommended_breadth(0.2, PolicyMode.NORMAL), "FULL")

    def test_guided_mode_full(self) -> None:
        """GUIDED mode returns FULL at confidence >= 0.8."""
        self.assertEqual(get_recommended_breadth(0.9, PolicyMode.GUIDED), "FULL")
        self.assertEqual(get_recommended_breadth(0.8, PolicyMode.GUIDED), "FULL")

    def test_guided_mode_moderate(self) -> None:
        """GUIDED mode returns MODERATE at confidence >= 0.5 and < 0.8."""
        self.assertEqual(get_recommended_breadth(0.6, PolicyMode.GUIDED), "MODERATE")
        self.assertEqual(get_recommended_breadth(0.5, PolicyMode.GUIDED), "MODERATE")
        self.assertEqual(get_recommended_breadth(0.799, PolicyMode.GUIDED), "MODERATE")

    def test_guided_mode_restricted(self) -> None:
        """GUIDED mode returns RESTRICTED at confidence >= 0.3 and < 0.5."""
        self.assertEqual(get_recommended_breadth(0.4, PolicyMode.GUIDED), "RESTRICTED")
        self.assertEqual(get_recommended_breadth(0.3, PolicyMode.GUIDED), "RESTRICTED")
        self.assertEqual(get_recommended_breadth(0.499, PolicyMode.GUIDED), "RESTRICTED")

    def test_guided_mode_deferred(self) -> None:
        """GUIDED mode returns DEFERRED at confidence < 0.3."""
        self.assertEqual(get_recommended_breadth(0.2, PolicyMode.GUIDED), "DEFERRED")
        self.assertEqual(get_recommended_breadth(0.299, PolicyMode.GUIDED), "DEFERRED")

    def test_enforced_mode_full_range(self) -> None:
        """ENFORCED mode uses full confidence mapping."""
        self.assertEqual(get_recommended_breadth(0.9, PolicyMode.ENFORCED), "FULL")
        self.assertEqual(get_recommended_breadth(0.6, PolicyMode.ENFORCED), "MODERATE")
        self.assertEqual(get_recommended_breadth(0.4, PolicyMode.ENFORCED), "RESTRICTED")
        self.assertEqual(get_recommended_breadth(0.2, PolicyMode.ENFORCED), "DEFERRED")

    def test_logging_observability(self) -> None:
        """get_recommended_breadth logs a structured INFO entry."""
        with self.assertLogs("eck-core", level="INFO") as cm:
            get_recommended_breadth(0.7, PolicyMode.GUIDED)
        self.assertTrue(any("Breadth recommendation" in m for m in cm.output))


class TestShouldExecute(unittest.TestCase):
    """should_execute() enforces policy mode and breadth recommendation."""

    def test_halt_never_executes(self) -> None:
        """HALT mode always returns False regardless of recommendation."""
        self.assertFalse(should_execute(PolicyMode.HALT, "FULL"))
        self.assertFalse(should_execute(PolicyMode.HALT, "MODERATE"))
        self.assertFalse(should_execute(PolicyMode.HALT, "RESTRICTED"))
        self.assertFalse(should_execute(PolicyMode.HALT, "DEFERRED"))

    def test_enforced_deferred_blocked(self) -> None:
        """ENFORCED mode blocks execution when recommendation is DEFERRED."""
        self.assertFalse(should_execute(PolicyMode.ENFORCED, "DEFERRED"))

    def test_enforced_non_deferred_permitted(self) -> None:
        """ENFORCED mode permits execution for non-DEFERRED recommendations."""
        self.assertTrue(should_execute(PolicyMode.ENFORCED, "FULL"))
        self.assertTrue(should_execute(PolicyMode.ENFORCED, "MODERATE"))
        self.assertTrue(should_execute(PolicyMode.ENFORCED, "RESTRICTED"))

    def test_normal_always_permitted(self) -> None:
        """NORMAL mode always permits execution."""
        self.assertTrue(should_execute(PolicyMode.NORMAL, "FULL"))
        self.assertTrue(should_execute(PolicyMode.NORMAL, "DEFERRED"))

    def test_guided_always_permitted(self) -> None:
        """GUIDED mode always permits execution — known gap pending gate wiring."""
        self.assertTrue(should_execute(PolicyMode.GUIDED, "FULL"))
        self.assertTrue(should_execute(PolicyMode.GUIDED, "DEFERRED"))


class TestIsNumericFeasible(unittest.TestCase):
    """is_numeric_feasible() structural similarity checks."""

    def test_both_numeric_is_feasible(self) -> None:
        """Two numeric values are always feasible."""
        self.assertTrue(is_numeric_feasible(1, 2))
        self.assertTrue(is_numeric_feasible(1.5, 2.5))
        self.assertTrue(is_numeric_feasible(0, 0))

    def test_bool_not_feasible(self) -> None:
        """Booleans are not treated as numeric despite isinstance(True, int)."""
        self.assertFalse(is_numeric_feasible(True, 1))
        self.assertFalse(is_numeric_feasible(1, False))
        self.assertFalse(is_numeric_feasible(True, False))

    def test_same_length_lists_feasible(self) -> None:
        """Lists of equal length are feasible."""
        self.assertTrue(is_numeric_feasible([1, 2, 3], [4, 5, 6]))

    def test_different_length_lists_not_feasible(self) -> None:
        """Lists of different length are not feasible."""
        self.assertFalse(is_numeric_feasible([1, 2], [1, 2, 3]))

    def test_same_length_tuples_feasible(self) -> None:
        """Tuples of equal length are feasible."""
        self.assertTrue(is_numeric_feasible((1, 2), (3, 4)))

    def test_string_heuristic_within_threshold(self) -> None:
        """Strings within 50 characters of each other are feasible."""
        self.assertTrue(is_numeric_feasible("hello", "world"))

    def test_string_heuristic_exceeds_threshold(self) -> None:
        """Strings more than 50 characters apart are not feasible."""
        self.assertFalse(is_numeric_feasible("x", "x" * 60))

    def test_empty_string_not_feasible(self) -> None:
        """Empty string prediction or actual is not feasible."""
        self.assertFalse(is_numeric_feasible("", "something"))
        self.assertFalse(is_numeric_feasible("something", ""))


if __name__ == "__main__":
    unittest.main()



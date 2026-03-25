# tests/test_queue.py
"""Tests for TaskQueue (deterministic ordering, overflow, boundary behaviour)."""

from __future__ import annotations

import unittest

from eck.queue import QueueFullError, TaskQueue


class TestTaskQueue(unittest.TestCase):
    """TaskQueue contract tests."""

    def setUp(self) -> None:
        self.queue = TaskQueue(max_size=3)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def test_initial_length_is_zero(self) -> None:
        """New queue is empty."""
        self.assertEqual(len(self.queue), 0)

    def test_max_size_zero_raises(self) -> None:
        """max_size < 1 raises ValueError."""
        with self.assertRaises(ValueError):
            TaskQueue(max_size=0)

    # ------------------------------------------------------------------
    # Push and overflow
    # ------------------------------------------------------------------
    def test_push_raises_on_overflow(self) -> None:
        """push() raises QueueFullError when at capacity — no silent drop."""
        self.queue.push({"id": "t1", "text": "first"})
        self.queue.push({"id": "t2", "text": "second"})
        self.queue.push({"id": "t3", "text": "third"})
        with self.assertRaises(QueueFullError):
            self.queue.push({"id": "t4", "text": "fourth"})

    def test_overflow_does_not_alter_queue(self) -> None:
        """Failed push leaves queue unchanged."""
        self.queue.push({"id": "t1", "text": "first"})
        self.queue.push({"id": "t2", "text": "second"})
        self.queue.push({"id": "t3", "text": "third"})
        try:
            self.queue.push({"id": "t4", "text": "fourth"})
        except QueueFullError:
            pass
        self.assertEqual(len(self.queue), 3)
        self.assertEqual(
            [t["text"] for t in self.queue.as_list()],
            ["first", "second", "third"],
        )

    # ------------------------------------------------------------------
    # FIFO order
    # ------------------------------------------------------------------
    def test_fifo_order(self) -> None:
        """Tasks are returned in FIFO order."""
        self.queue.push({"id": "t1", "text": "first"})
        self.queue.push({"id": "t2", "text": "second"})
        self.queue.push({"id": "t3", "text": "third"})
        self.assertEqual(self.queue.pop()["text"], "first")
        self.assertEqual(self.queue.pop()["text"], "second")
        self.assertEqual(self.queue.pop()["text"], "third")

    def test_pop_empty_returns_none(self) -> None:
        """pop() on empty queue returns None."""
        self.assertIsNone(self.queue.pop())

    # ------------------------------------------------------------------
    # is_empty
    # ------------------------------------------------------------------
    def test_is_empty_true_when_empty(self) -> None:
        """is_empty() returns True on empty queue."""
        self.assertTrue(self.queue.is_empty())

    def test_is_empty_false_when_non_empty(self) -> None:
        """is_empty() returns False when queue has tasks."""
        self.queue.push({"id": "t1", "text": "first"})
        self.assertFalse(self.queue.is_empty())

    # ------------------------------------------------------------------
    # as_list
    # ------------------------------------------------------------------
    def test_as_list_returns_copy(self) -> None:
        """as_list() returns a copy — mutating it does not affect queue."""
        self.queue.push({"id": "t1", "text": "first"})
        lst = self.queue.as_list()
        lst.append({"id": "t2", "text": "second"})
        self.assertEqual(len(self.queue), 1)

    def test_as_list_correct_contents(self) -> None:
        """as_list() returns all tasks in order."""
        self.queue.push({"id": "t1", "text": "first"})
        self.queue.push({"id": "t2", "text": "second"})
        self.assertEqual(
            self.queue.as_list(),
            [{"id": "t1", "text": "first"}, {"id": "t2", "text": "second"}],
        )

    # ------------------------------------------------------------------
    # clear() absent (ADR-040)
    # ------------------------------------------------------------------
    def test_clear_does_not_exist(self) -> None:
        """clear() must not exist — removed per ADR-040 epoch semantics."""
        self.assertFalse(hasattr(self.queue, "clear"))

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------
    def test_repr_shows_count_and_max(self) -> None:
        """__repr__ shows current count and max_size."""
        self.queue.push({"id": "t1", "text": "first"})
        self.assertEqual(str(self.queue), "TaskQueue(1/3 tasks)")


if __name__ == "__main__":
    unittest.main()

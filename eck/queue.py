# eck/queue.py
"""Bounded task queue for the Epistemic Control Kernel (ECK).

Design notes:
- push() raises QueueFullError on overflow rather than silently dropping tasks.
  Silent task loss would corrupt the goal completion predicate (ADR-041) by
  making a non-empty queue appear exhausted.
- clear() is intentionally absent. Queue state is not reset mid-epoch.
  If a supervised restart is required, that is an external operation defining
  a new kernel execution epoch (ADR-040 Section 4).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Optional

logger = logging.getLogger("eck-core")


class QueueFullError(Exception):
    """Raised when push() is called on a full TaskQueue."""


class TaskQueue:
    """
    Bounded task queue using deque for efficient operations.

    Raises QueueFullError on overflow — never silently drops tasks.
    Silent task loss would make a non-exhausted queue appear empty,
    corrupting the goal completion predicate (ADR-041).
    """

    def __init__(self, max_size: int = 50) -> None:
        """
        Initialize with a maximum size limit.

        Args:
            max_size: Maximum number of tasks allowed (default 50).
        """
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        self.queue: deque[dict[str, Any]] = deque()
        self.max_size = max_size

    def push(self, task: dict[str, Any]) -> None:
        """
        Add a task to the end of the queue.

        Raises QueueFullError if the queue is at capacity rather than
        silently dropping the task. The caller is responsible for
        handling overflow — typically by logging and skipping subtask
        generation for the current cycle.
        """
        if len(self.queue) >= self.max_size:
            logger.warning(
                "TaskQueue full — task rejected",
                extra={
                    "queue_size": len(self.queue),
                    "max_size": self.max_size,
                    "task_preview": str(task)[:80],
                },
            )
            raise QueueFullError(
                f"TaskQueue at capacity ({self.max_size}). Task rejected."
            )
        self.queue.append(task)

    def pop(self) -> Optional[dict[str, Any]]:
        """Remove and return the oldest task, or None if empty."""
        return self.queue.popleft() if self.queue else None

    def is_empty(self) -> bool:
        """Return True if the queue contains no tasks."""
        return len(self.queue) == 0

    def as_list(self) -> list[dict[str, Any]]:
        """
        Return a snapshot of all pending tasks as a list.

        Used by the goal completion predicate (ADR-041) to inspect
        whether the queue is naturally exhausted.
        Returns a copy — does not modify queue state.
        """
        return list(self.queue)

    def __len__(self) -> int:
        """Current number of tasks in queue."""
        return len(self.queue)

    def __repr__(self) -> str:
        return f"TaskQueue({len(self)}/{self.max_size} tasks)"

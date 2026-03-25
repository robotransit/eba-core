# eck/task.py
"""Task lifecycle state taxonomy for the Epistemic Control Kernel (ECK).

TaskState is the canonical set of observable lifecycle states for a task.
Causes and interpretations are handled elsewhere (critic, drift, policy).

NOTE:
TaskState is currently unused — the task lifecycle recording capability
was removed from agent.py during v0.2.0 reconciliation when the mutable
WorldModel interface was replaced with the read-only MemoryRetrieval
contract (ADR-026–030).

TaskState is preserved here for the v0.2.0 audit/observability layer,
which will reintroduce structured task lifecycle recording without
reintroducing mutable memory semantics. It must not be reactivated
by importing into agent.py until that layer is formally designed.
"""

from __future__ import annotations

from enum import Enum


class TaskState(Enum):
    """
    Canonical lifecycle states for a task within ECK.

    States describe observable task progression and outcomes.
    Causes and interpretations are handled elsewhere (critic, drift, policy).
    """
    CREATED          = "created"
    PREDICTED        = "predicted"
    EXECUTED         = "executed"
    SUCCEEDED        = "succeeded"
    FAILED           = "failed"
    REJECTED_BY_CRITIC = "rejected_by_critic"
    DEFERRED         = "deferred"

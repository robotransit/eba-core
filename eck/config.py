# eck/config.py
"""Central configuration for the Epistemic Control Kernel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class PolicyMode(Enum):
    """
    NORMAL:   full agent operation (default)
    GUIDED:   advisory mode (recommendations only, no enforcement)
    ENFORCED: hard enforcement active (agent may block actions)
    HALT:     no further task generation or execution (irreversible until manual reset)
    """
    NORMAL = "normal"
    GUIDED = "guided"
    ENFORCED = "enforced"
    HALT = "halt"


@dataclass(frozen=True)
class ECKConfig:
    """
    Central configuration for the Epistemic Control Kernel (ECK).

    All thresholds, limits, and policy overrides are defined here.
    This is a frozen dataclass — use dataclasses.replace() to produce
    updated instances rather than mutating in place.

    Consumers MUST use effective_policy() for policy-aware parameter
    resolution. Direct access to _guided_* fields is not policy-aware.
    """

    # ── Agent loop ────────────────────────────────────────────────────
    max_iterations: int = 100
    max_queue_size: int = 50
    guard_interval: int = 5

    # ── Drift monitoring ──────────────────────────────────────────────
    semantic_drift_threshold: float = 0.7
    error_z_threshold: float = 3.0
    max_drift_streak: int = 3

    # Number of error samples required before z-score signal activates.
    # During warmup, record_error() always returns False.
    drift_warmup_samples: int = 10

    # Total drift event count above which severe() returns True.
    severe_drift_count: int = 3

    # Consecutive drift streak length triggering GUIDED mode recommendation.
    guided_drift_threshold: int = 1

    # Consecutive drift streak length triggering ENFORCED mode recommendation.
    enforced_drift_threshold: int = 2

    # ── Feasibility and confidence ────────────────────────────────────
    feas_conf_high: float = 0.8
    feas_conf_low: float = 0.5
    low_conf_threshold: float = 0.4
    task_similarity_threshold: float = 0.75

    # ── Confidence signal processor (ADR-021–025) ─────────────────────
    # alpha: EWMA smoothing factor for ConfidenceSignal.
    # Must be in (0.0, 1.0]. Higher = faster adaptation to recent evidence.
    confidence_alpha: float = 0.3

    # ── Policy mode ───────────────────────────────────────────────────
    policy_mode: PolicyMode = PolicyMode.NORMAL

    # ── Policy effect parameters (resolved via effective_policy()) ────
    _guided_max_subtasks: int = 2
    _guided_critic_strictness: float = 0.9
    _guided_prediction_bias_delta: float = -0.2

    # ── Critic (ADR-022) ──────────────────────────────────────────────
    # Severity floor below which a failure is promoted to partial category.
    # Must be in [0.0, 1.0]. Above this: failure. Below this: partial.
    # Conceptually distinct from goal_completion_threshold and
    # execution thresholds — do not implicitly couple.
    partial_threshold: float = 0.5

    # ── Goal completion (ADR-041) ─────────────────────────────────────
    # Minimum confidence required for the kernel to declare goal completion.
    # Applies alongside task_success and no_required_work_remaining predicates.
    # Conceptually distinct from DefaultPolicyGate execution threshold (0.90)
    # even if they share a default value — do not implicitly couple (ADR-041).
    goal_completion_threshold: float = 0.9

    # ── Memory retrieval (ADR-026–030) ────────────────────────────────
    enable_memory_retrieval: bool = False
    memory_retrieval_limit: int = 5

    # ── Optional embeddings/cosine similarity (ADR-032) ───────────────
    # Default: False (core stdlib heuristic only).
    # When True and sentence-transformers extras are installed, model
    # loading occurs at ECKAgent construction. If disabled, extras are
    # missing, or load fails, behavior falls back silently to core path.
    enable_embeddings: bool = False

    def effective_policy(self) -> Mapping[str, object]:
        """
        Resolve effective parameters based on current policy mode.

        Returns an immutable mapping with the following possible keys:

        NORMAL:
          (empty — no overrides)

        GUIDED:
          - max_subtasks: int
          - critic_strictness: float
          - prediction_bias_delta: float

        ENFORCED:
          - max_subtasks: int (restricted to 1)
          - critic_strictness: float (maximum strictness)

        HALT:
          - halt: bool (always True)

        This is a read-only view — do not attempt to modify it.
        """
        if self.policy_mode == PolicyMode.NORMAL:
            return MappingProxyType({})

        if self.policy_mode == PolicyMode.GUIDED:
            return MappingProxyType({
                "max_subtasks": self._guided_max_subtasks,
                "critic_strictness": self._guided_critic_strictness,
                "prediction_bias_delta": self._guided_prediction_bias_delta,
            })

        if self.policy_mode == PolicyMode.ENFORCED:
            return MappingProxyType({
                "max_subtasks": 1,
                "critic_strictness": 1.0,
            })

        if self.policy_mode == PolicyMode.HALT:
            return MappingProxyType({"halt": True})

        raise ValueError(f"Unknown policy mode: {self.policy_mode}")

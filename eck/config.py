# eck/config.py
"""Central configuration for the Epistemic Control Kernel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping
from types import MappingProxyType


class PolicyMode(Enum):
    """
    NORMAL: full agent operation (default)
    GUIDED: advisory mode (recommendations only, no enforcement)
    ENFORCED: hard enforcement allowed (agent may block actions)
    HALT: no further task generation or execution (irreversible until manual reset)
    """
    NORMAL = "normal"
    GUIDED = "guided"
    ENFORCED = "enforced"
    HALT = "halt"


@dataclass(frozen=True)
class ECKConfig:
    """
    Central configuration for ECK (Epistemic Control Kernel).
    All thresholds, limits, and policy overrides are defined here.

    Consumers **must** use effective_policy(); direct access to _guided_* fields is not policy-aware.
    """

    # Public fields
    max_iterations: int = 100
    max_queue_size: int = 50
    semantic_drift_threshold: float = 0.7
    error_z_threshold: float = 3.0
    max_drift_streak: int = 3
    guard_interval: int = 5
    feas_conf_high: float = 0.8
    feas_conf_low: float = 0.5
    low_conf_threshold: float = 0.4
    task_similarity_threshold: float = 0.75

    # Policy mode
    policy_mode: PolicyMode = PolicyMode.NORMAL

    # Private: policy effect parameters (resolved via effective_policy())
    _guided_max_subtasks: int = 2
    _guided_critic_strictness: float = 0.9
    _guided_prediction_bias_delta: float = -0.2

    # Memory influence (retrieval for prediction context)
    enable_memory_retrieval: bool = False
    memory_retrieval_limit: int = 5
    memory_similarity_threshold: float = 0.6
    prefer_negative_memory: bool = True  # Bias toward failed outcomes

    # Optional embeddings/cosine similarity (ADR-032)
    # Default: False (core stdlib heuristic only).
    # When True and sentence-transformers extras are installed, model loading occurs at ECKAgent construction.
    # If disabled, extras are missing, or load fails, behavior falls back silently to the core path.
    enable_embeddings: bool = False


    def effective_policy(self) -> Mapping[str, object]:
        """
        Resolve effective parameters based on current policy mode.

        Returns an immutable mapping view with the following possible keys (all optional):

        - max_subtasks: int — maximum subtasks to generate per step
        - critic_strictness: float — higher values = stricter success threshold
        - prediction_bias_delta: float — signed bias adjustment to predictions
        - halt: bool — if True, agent should stop immediately

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

        if self.policy_mode == PolicyMode.HALT:
            return MappingProxyType({"halt": True})

        raise ValueError(f"Unknown policy mode: {self.policy_mode}")

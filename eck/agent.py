# eck/agent.py
"""Framework-agnostic core of the Epistemic Control Kernel (ECK)."""

import logging
from typing import Callable, Any
from dataclasses import replace

from .queue import TaskQueue
from .memory import MemoryRetrieval
from .drift import DriftMonitor
from .utils import (
    generate_id,
    is_numeric_feasible,
    get_recommended_breadth,
    should_execute,
)
from .config import ECKConfig, PolicyMode
from .prompts import (
    format_prompt,
    INITIAL_TASK_PROMPT_TEMPLATE,
)
from .critic import critic_evaluate
from .prediction import generate_prediction
from .task_generation import generate_subtasks
from .execution import execute_task

logger = logging.getLogger("eck-core")


# Policy ordering for safe, irreversible upgrades
_POLICY_ORDER = {
    PolicyMode.NORMAL: 0,
    PolicyMode.GUIDED: 1,
    PolicyMode.ENFORCED: 2,
    PolicyMode.HALT: 3,
}


class ECKAgent:
    """
    Framework-agnostic core of the Epistemic Control Kernel (ECK).

    Orchestrates task queue, memory, drift monitoring,
    and LLM-mediated prediction, execution, and evaluation.
    """

    def __init__(
        self,
        objective: str,
        llm_call: Callable[[str], str],
        config: ECKConfig = None,
    ):
        self.objective = objective
        self.llm = llm_call
        self.config = config or ECKConfig()

        # Current active policy mode (derived from config)
        self.current_policy_mode: PolicyMode = self.config.policy_mode

        # Current confidence (placeholder — future: rolling signal)
        # NOTE: Replace with ConfidenceSignal(alpha=self.config.confidence_alpha)
        # when ADR-021–025 wiring is complete.
        self.current_confidence: float = 0.5

        self.queue = TaskQueue(max_size=self.config.max_queue_size)

        # Memory retrieval (current contract — ADR-026–030)
        self.memory = MemoryRetrieval(enabled=self.config.enable_memory_retrieval)

        # NOTE:
        # Task lifecycle recording is currently absent.
        # This must be addressed via the v0.2.0 audit/observability layer,
        # not by reintroducing mutable memory semantics.

        self.drift = DriftMonitor(config=self.config)

        self.cycles: int = 0

        # ── Optional embeddings wiring (ADR-032) ─────────────────────────────────────
        # Model loading happens once at construction, gated by config.
        # Failure is completely silent and atomic.
        self._enable_embeddings: bool = self.config.enable_embeddings
        self._embedding_model: Any | None = None

        if self._enable_embeddings:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                # Silent atomic fallback
                self._embedding_model = None
        # ─────────────────────────────────────────────────────────────────────────────

    def seed(self, initial_task: str = None) -> None:
        """Seed the agent with an initial task (or generate one)."""
        if initial_task is None:
            prompt = format_prompt(
                INITIAL_TASK_PROMPT_TEMPLATE,
                objective=self.objective,
            )
            initial_task = self.llm(prompt).strip()

        task_id = generate_id()
        self.queue.push({"id": task_id, "text": initial_task})

        logger.info(
            "Agent seeded",
            extra={
                "task_id": task_id,
                "initial_task": initial_task,
            },
        )

    def step(self) -> bool:
        """Execute one full control cycle."""

        # ── Policy escalation (irreversible upgrades only) ────────────
        recommended_mode = self.drift.get_policy_mode()
        if _POLICY_ORDER[recommended_mode] > _POLICY_ORDER[self.current_policy_mode]:
            previous_policy_mode = self.current_policy_mode
            self.current_policy_mode = recommended_mode
            self.config = replace(self.config, policy_mode=recommended_mode)
            self.drift.config = self.config

            logger.info(
                "Policy upgrade",
                extra={
                    "previous_policy_mode": previous_policy_mode.name,
                    "new_policy_mode": self.current_policy_mode.name,
                    "drift_streak": self.drift.drift_streak,
                    "total_drift_events": self.drift.total_drift_events(),
                },
            )

        if self.current_policy_mode == PolicyMode.HALT:
            logger.critical(
                "Policy mode HALT — stopping agent",
                extra={"drift_snapshot": self.drift.snapshot()},
            )
            return False

        task = self.queue.pop()
        if not task:
            logger.info("Task queue empty — nothing to do")
            return False

        task_id = task["id"]
        task_text = task["text"]

        # 1. Prediction
        # NOTE (ADR-032):
        # embedding_model is passed to prediction.py which propagates it
        # to MemoryRetrieval for optional cosine retrieval.
        prediction = generate_prediction(
            task_text=task_text,
            objective=self.objective,
            llm_call=self.llm,
            memory=self.memory,
            config=self.config,
            embedding_model=self._embedding_model,
        )

        # 2. Execution (policy-gated)
        recommended_breadth = get_recommended_breadth(
            confidence=self.current_confidence,
            policy_mode=self.current_policy_mode,
        )

        if should_execute(self.current_policy_mode, recommended_breadth):
            outcome = execute_task(task_text, self.llm)
        else:
            logger.info(
                "Execution skipped",
                extra={
                    "task_id": task_id,
                    "policy_mode": self.current_policy_mode.name,
                    "recommendation": recommended_breadth,
                    "confidence": self.current_confidence,
                },
            )
            outcome = ""

        # 3. Critic (ADR-022)
        # NOTE:
        # critic_outcome.severity feeds DriftMonitor as the error signal
        # until the confidence signal processor (ADR-021–025) is wired —
        # at which point critic_outcome will be passed directly to
        # ConfidenceSignalProcessor.update() instead.
        critic_outcome = critic_evaluate(
            task_text=task_text,
            prediction=prediction,
            result=outcome,
            objective=self.objective,
            llm_call=self.llm,
            partial_threshold=self.config.partial_threshold,
        )
        success = critic_outcome.success
        feedback = critic_outcome.feedback
        error = critic_outcome.severity

        logger.info(
            "Critic evaluated",
            extra={
                "task_id": task_id,
                "category": critic_outcome.category,
                "severity": critic_outcome.severity,
                "success": critic_outcome.success,
            },
        )

        # 4. Drift tracking (append-only, no reset — ADR-040)
        perceptual_drift = self.drift.record_error(error)
        feasible = is_numeric_feasible(prediction, outcome)
        self.drift.record_feasibility(feasible, success)

        if perceptual_drift:
            self.drift.register_drift()
        else:
            self.drift.clear_streak()

        # ADR-040 observability: agent loop is canonical logging point
        drift_snap = self.drift.snapshot()
        logger.info(
            "Drift state updated",
            extra={
                "task_id": task_id,
                "perceptual_drift": perceptual_drift,
                **drift_snap,
            },
        )

        # Drift streak halt
        if self.drift.drift_streak > self.config.max_drift_streak:
            logger.critical(
                "Repeated drift detected — halting agent",
                extra={
                    "task_id": task_id,
                    **drift_snap,
                },
            )
            return False

        # Severe instability halt (independent of streak — ADR-040)
        if self.drift.severe():
            logger.critical(
                "Severe instability detected — halting agent",
                extra={
                    "task_id": task_id,
                    **drift_snap,
                },
            )
            return False

        # 5. Goal check
        # TODO(ADR-041):
        # Replace with deterministic predicate:
        #   success AND queue naturally exhausted AND
        #   confidence >= config.goal_completion_threshold
        # GOAL_ACHIEVED_PROMPT and free-form LLM string matching
        # are non-compliant with ADR-033 and must be removed.
        # Requires: per-cycle subtask suppression flag,
        #           confidence signal wiring (ADR-021–025).

        # 6. Subtask generation (policy-gated)
        if should_execute(self.current_policy_mode, recommended_breadth):
            subtasks = generate_subtasks(
                current_task=task_text,
                objective=self.objective,
                llm_call=self.llm,
                max_subtasks=5,
            )

            for sub in subtasks:
                sub_id = generate_id()
                self.queue.push({"id": sub_id, "text": sub})

        self.cycles += 1

        # 7. Periodic guard
        if self.cycles % self.config.guard_interval == 0:
            snap = self.drift.snapshot()
            if snap["severe"]:
                logger.critical(
                    "Severe instability detected — halting agent",
                    extra={
                        "task_id": task_id,
                        **snap,
                    },
                )
                return False

        return True

    def run(self) -> None:
        """Run the agent until halt or max iterations."""
        logger.info(
            "ECK run starting",
            extra={"objective": self.objective},
        )
        while self.cycles < self.config.max_iterations:
            if not self.step():
                break
        logger.info(
            "ECK run completed",
            extra={"cycles": self.cycles},
        )

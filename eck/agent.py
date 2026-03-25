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
    GOAL_ACHIEVED_PROMPT,
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
        self.current_confidence: float = 0.5

        self.queue = TaskQueue(max_size=self.config.max_queue_size)

        # Memory retrieval (current contract)
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
        # Irreversible policy upgrades only
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
                    "recommended_mode": recommended_mode.name,
                    "new_policy_mode": self.current_policy_mode.name,
                    "drift_streak": self.drift.drift_streak,
                },
            )

        if self.current_policy_mode == PolicyMode.HALT:
            logger.critical("Policy mode HALT — stopping agent")
            return False

        task = self.queue.pop()
        if not task:
            logger.info("Task queue empty — nothing to do")
            return False

        task_id = task["id"]
        task_text = task["text"]

        # 1. Prediction
        # NOTE:
        # Forward integration seam (ADR-032).
        # prediction.py must be updated to accept and propagate `embedding_model`.
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
                    "policy_mode": self.current_policy_mode.name,
                    "recommendation": recommended_breadth,
                    "confidence": self.current_confidence,
                },
            )
            outcome = ""

        # 3. Critic
        success, feedback, error = critic_evaluate(
            task_text=task_text,
            prediction=prediction,
            result=outcome,
            objective=self.objective,
            llm_call=self.llm,
        )

        # 4. Drift tracking (append-only, no reset)
        perceptual_drift = self.drift.record_error(error)
        feasible = is_numeric_feasible(prediction, outcome)
        self.drift.record_feasibility(feasible, success)

        if perceptual_drift:
            self.drift.register_drift()
        else:
            self.drift.clear_streak()

        # ADR-040 observability: agent loop is canonical logging point for drift state
        logger.info(
            "Drift state updated",
            extra={
                "task_id": task_id,
                "perceptual_drift": perceptual_drift,
                "drift_streak": self.drift.drift_streak,
                "policy_mode": self.current_policy_mode.name,
                "feasible": feasible,
                "success": success,
            },
        )

        if self.drift.drift_streak > self.config.max_drift_streak:
            logger.critical(
                "Repeated drift detected — halting agent",
                extra={
                    "task_id": task_id,
                    "drift_streak": self.drift.drift_streak,
                    "max_drift_streak": self.config.max_drift_streak,
                    "policy_mode": self.current_policy_mode.name,
                },
            )
            return False

        # 5. Goal check
        # TODO(ADR-039/loop reconciliation):
        # Goal completion currently uses legacy free-form LLM string matching.
        # Replace with a deterministic or structured decision surface aligned with v0.2.0.
        goal_prompt = format_prompt(
            GOAL_ACHIEVED_PROMPT,
            objective=self.objective,
            result=outcome,
        )
        if "YES" in self.llm(goal_prompt).upper():
            logger.info("Goal achieved — stopping early")
            return False

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
            if self.drift.severe():
                logger.error(
                    "Severe instability detected — halting agent",
                    extra={
                        "task_id": task_id,
                        "drift_streak": self.drift.drift_streak,
                        "policy_mode": self.current_policy_mode.name,
                    },
                )
                return False

        return True

    def run(self) -> None:
        """Run the agent until halt or max iterations."""
        logger.info(f"Starting ECK run with objective: {self.objective}")
        while self.cycles < self.config.max_iterations:
            if not self.step():
                break
        logger.info(f"ECK run completed after {self.cycles} cycles")

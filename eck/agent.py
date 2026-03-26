# eck/agent.py
"""Framework-agnostic core of the Epistemic Control Kernel (ECK)."""

import logging
from typing import Callable, Any
from dataclasses import replace

from .queue import TaskQueue, QueueFullError
from .memory import MemoryRetrieval
from .drift import DriftMonitor
from .confidence import ConfidenceSignal
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

        # Confidence signal processor (ADR-021–025)
        self._confidence: ConfidenceSignal = ConfidenceSignal(
            alpha=self.config.confidence_alpha
        )

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
            try:  # pragma: no cover
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
            confidence=self._confidence.get_value(),
            policy_mode=self.current_policy_mode,
        )

        # Per-cycle suppression flag (ADR-041):
        # Captures whether the current policy state permits subtask generation.
        # Used in step 5 to distinguish natural queue exhaustion from
        # policy-suppressed emptiness — a queue empty due to suppression
        # is not a valid completion signal.
        subtasks_suppressed = not should_execute(
            self.current_policy_mode, recommended_breadth
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
                    "confidence": self._confidence.get_value(),
                },
            )
            outcome = ""

        # 3. Critic (ADR-022)
        # critic_evaluate returns (CriticOutcome, PartialStructure | None).
        # Invariant: partial_structure is not None iff category == "partial".
        critic_outcome, partial_structure = critic_evaluate(
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
                "partial_structure": {
                    "conflict_kind": partial_structure.conflict_kind.name,
                    "conflict_footprint": sorted([
                        locus.name for locus in partial_structure.conflict_footprint
                    ]),
                } if partial_structure else None,
            },
        )

        # Confidence update (ADR-021–025)
        # partial_structure is passed directly — confidence.py validates the
        # invariant that partial outcomes carry PartialStructure and non-partial
        # outcomes do not. No guard needed here.
        prior_confidence = self._confidence.get_value()
        new_confidence = self._confidence.update(critic_outcome, partial_structure)
        logger.info(
            "Confidence updated",
            extra={
                "task_id": task_id,
                "category": critic_outcome.category,
                "prior_confidence": round(prior_confidence, 4),
                "new_confidence": round(new_confidence, 4),
                "failure_window_active": self._confidence._last_outcome_was_failure,
            },
        )

        # 4. Drift tracking (append-only, no reset — ADR-040)
        # Observability only — enforcement is in the periodic guard (step 7).
        # drift_snap includes "severe" field — no separate severe-specific log needed.
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

        # 5. Goal completion predicate (ADR-041)
        # Three conditions must all be true:
        #   - current task succeeded (critic)
        #   - queue is naturally exhausted (not policy-suppressed)
        #   - confidence >= goal_completion_threshold
        current_confidence = self._confidence.get_value()
        if (
            success
            and self.queue.is_empty()
            and not subtasks_suppressed
            and current_confidence >= self.config.goal_completion_threshold
        ):
            logger.info(
                "Goal completion predicate satisfied — stopping agent",
                extra={
                    "task_id": task_id,
                    "confidence": round(current_confidence, 4),
                    "goal_completion_threshold": self.config.goal_completion_threshold,
                    "queue_size": len(self.queue),
                    "subtasks_suppressed": subtasks_suppressed,
                    "policy_mode": self.current_policy_mode.name,
                    "critic_category": critic_outcome.category,
                },
            )
            return False

        # 6. Subtask generation (policy-gated)
        if not subtasks_suppressed:
            subtasks = generate_subtasks(
                current_task=task_text,
                objective=self.objective,
                llm_call=self.llm,
                max_subtasks=5,
            )

            pushed = 0
            for sub in subtasks:
                sub_id = generate_id()
                try:
                    self.queue.push({"id": sub_id, "text": sub})
                    pushed += 1
                except QueueFullError:
                    logger.warning(
                        "Subtask dropped — queue at capacity",
                        extra={
                            "task_id": task_id,
                            "queue_size": len(self.queue),
                            "max_size": self.config.max_queue_size,
                        },
                    )
                    break

            logger.info(
                "Subtasks generated",
                extra={
                    "task_id": task_id,
                    "generated": len(subtasks),
                    "pushed": pushed,
                    "queue_size": len(self.queue),
                    "policy_mode": self.current_policy_mode.name,
                },
            )

        self.cycles += 1

        # 7. Periodic guard — single severe halt seam (ADR-040)
        # Default guard_interval=1 delivers per-cycle semantics.
        # Increase guard_interval to introduce a grace period (explicit opt-in).
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

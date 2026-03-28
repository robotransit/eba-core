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
from .execution import propose_execution, authorize_and_perform
from .policy_gate import DefaultPolicyGate, PolicyContext, ExecutionMode, PolicyGate
from .types import ExecutionResult

logger = logging.getLogger("eck-core")


# Policy ordering for safe, irreversible upgrades
_POLICY_ORDER = {
    PolicyMode.NORMAL: 0,
    PolicyMode.GUIDED: 1,
    PolicyMode.ENFORCED: 2,
    PolicyMode.HALT: 3,
}

# Categories that indicate execution did not occur — drift and feasibility
# tracking is skipped for these cycles. Recording drift against a non-executed
# cycle would conflate "execution failed" with "execution did not happen."
_NO_EXECUTION_CATEGORIES = frozenset({"rejected", "deferred"})


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
        config: ECKConfig | None = None,
        policy_gate: PolicyGate | None = None,
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

        # Policy gate (ADR-042) — DefaultPolicyGate if not provided.
        # Injected at construction for testability and domain-specific
        # gate implementations. Stored privately to prevent runtime
        # reassignment — consistent with agent_loop.py invariant.
        self._policy_gate: PolicyGate = policy_gate or DefaultPolicyGate()

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

        # 2. Execution — propose / gate / authorize+perform (ADR-042)
        #
        # Per-cycle suppression flag (ADR-041):
        # Captures whether the current policy state permits subtask generation.
        # Used in step 5 to distinguish natural queue exhaustion from
        # policy-suppressed emptiness — a queue empty due to suppression
        # is not a valid completion signal.
        #
        # NOTE: get_recommended_breadth and should_execute are pre-gate
        # utilities (ADR-038 pending full retirement). They continue to gate
        # subtask generation. The execution path now uses the policy gate
        # directly per ADR-042.
        recommended_breadth = get_recommended_breadth(
            confidence=self._confidence.get_value(),
            policy_mode=self.current_policy_mode,
        )
        subtasks_suppressed = not should_execute(
            self.current_policy_mode, recommended_breadth
        )

        # Step 2a: Propose (advisory — no effects)
        proposed = propose_execution(
            task_text=task_text,
            llm_call=self.llm,
            task_id=task_id,
        )

        # Step 2b: Handle no proposal — per-cycle no-op, not a halt
        if proposed is None:
            execution_result = ExecutionResult(
                performed=False,
                outcome="",
                refusal_reason="no_valid_proposal",
            )
            logger.info(
                "Execution deferred — no valid proposal",
                extra={
                    "task_id": task_id,
                    "policy_mode": self.current_policy_mode.name,
                },
            )
        else:
            # Step 2c: Gate check (may execution occur at all this cycle?)
            policy_context = PolicyContext(
                failure_window_active=self._confidence._last_outcome_was_failure,
            )
            gate_decision = self._policy_gate.evaluate(
                proposed_action=proposed,
                confidence=self._confidence.get_value(),
                context=policy_context,
            )

            # Step 2d: Kernel authorization and effect
            # Only when gate returns EXECUTE — preserves INV1 (ADR-042)
            if gate_decision.mode is ExecutionMode.EXECUTE:
                execution_result = authorize_and_perform(
                    proposed_action=proposed,
                    policy_mode=self.current_policy_mode,
                    llm_call=self.llm,
                )
            else:
                execution_result = ExecutionResult(
                    performed=False,
                    outcome="",
                    refusal_reason=f"gate: {gate_decision.mode.name}",
                )
                logger.info(
                    "Execution refused by gate",
                    extra={
                        "task_id": task_id,
                        "gate_mode": gate_decision.mode.name,
                        "gate_rule_id": gate_decision.rule_id,
                        "gate_reason": gate_decision.reason,
                        "confidence": self._confidence.get_value(),
                        "policy_mode": self.current_policy_mode.name,
                    },
                )

        # 3. Critic (ADR-022)
        # critic_evaluate accepts ExecutionResult directly.
        # performed=False → short-circuits to rejected/deferred category,
        # no LLM call, no confidence update path.
        # Invariant: partial_structure is not None iff category == "partial".
        critic_outcome, partial_structure = critic_evaluate(
            task_text=task_text,
            prediction=prediction,
            result=execution_result,
            objective=self.objective,
            llm_call=self.llm,
            partial_threshold=self.config.partial_threshold,
        )
        success = critic_outcome.success
        error = critic_outcome.severity

        logger.info(
            "Critic evaluated",
            extra={
                "task_id": task_id,
                "category": critic_outcome.category,
                "severity": critic_outcome.severity,
                "success": critic_outcome.success,
                "performed": execution_result.performed,
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
        # rejected/deferred categories produce no confidence update per ADR-021
        # — this is handled inside confidence.py.
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
        # Skipped for rejected/deferred cycles — execution did not occur and
        # recording drift against a non-executed cycle would conflate
        # "execution failed" with "execution did not happen."
        if critic_outcome.category not in _NO_EXECUTION_CATEGORIES:
            perceptual_drift = self.drift.record_error(error)
            feasible = is_numeric_feasible(prediction, execution_result.outcome)
            self.drift.record_feasibility(feasible, success)

            if perceptual_drift:
                self.drift.register_drift()
            else:
                self.drift.clear_streak()

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
        else:
            logger.info(
                "Drift/feasibility tracking skipped — execution not performed",
                extra={
                    "task_id": task_id,
                    "category": critic_outcome.category,
                    "performed": execution_result.performed,
                },
            )

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
        # Snapshot is taken fresh here — independent of whether the drift
        # block ran this cycle (skipped for rejected/deferred categories).
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

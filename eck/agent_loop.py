# eck/agent_loop.py
"""Minimal enforcement seam for policy gate decisions (ADR-039)."""

from __future__ import annotations

from typing import Any, Callable

from eck.policy_gate import PolicyGate, ExecutionMode, PolicyContext, PolicyDecision


class AgentLoop:
    """
    Minimal runtime enforcement point that invokes the policy gate exactly once
    per proposed action and enforces the resulting execution mode.

    This is **not** a full agent orchestrator — it is solely the enforcement seam.
    """

    def __init__(self, policy_gate: PolicyGate) -> None:
        # Store gate privately to prevent runtime reassignment (v0.2.0 invariant:
        # exactly one fixed policy gate per kernel instance; no hot-swapping).
        self._policy_gate: PolicyGate = policy_gate

    def step(
        self,
        proposed_action: Any,
        confidence: float,
        context: PolicyContext,
        execute_hook: Callable[[Any], Any] | None = None,
    ) -> tuple[PolicyDecision, Any | None]:
        """
        Single deterministic step: evaluate policy → enforce mode → optional execution.

        Args:
            proposed_action: The action proposed by the predictor (opaque).
            confidence: Current confidence value [0.0, 1.0].
            context: PolicyContext forwarded verbatim to the gate (loop does not inspect it).
            execute_hook: Optional callable that actually performs the action (for testability).

        Returns:
            Tuple of (full PolicyDecision from the gate, result_or_none).
            result is only non-None when mode is EXECUTE and execute_hook is provided.
            The full PolicyDecision is always returned for auditability and traceability.
        """
        # ── Single, mandatory policy gate evaluation ─────────────────────────────
        # Context is passed unchanged — gate may depend only on this explicit context.
        decision: PolicyDecision = self._policy_gate.evaluate(
            proposed_action=proposed_action,
            confidence=confidence,
            context=context,
        )

        mode = decision.mode

        # ── Enforce execution modes (no bypasses, no side-channels) ──────────────
        if mode is ExecutionMode.EXECUTE:
            if execute_hook is not None:
                # Execution authorized — perform via hook; bubble exceptions (no recovery here)
                result = execute_hook(proposed_action)
                return decision, result
            else:
                # Authorized but not performed (no hook provided)
                return decision, None

        # All other modes strictly prevent execution.
        # DEGRADE: no degraded path defined in this minimal seam → treated as no-execute.
        if mode is ExecutionMode.HALT:
            return decision, None

        if mode is ExecutionMode.RETRY:
            return decision, None

        if mode is ExecutionMode.DEGRADE:
            return decision, None

        # Defensive: unreachable if PolicyGate returns valid ExecutionMode
        raise ValueError(f"Unknown execution mode from gate: {mode}")

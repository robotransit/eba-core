# tests/test_agent_loop.py
"""Invariant-enforcing tests for the minimal AgentLoop enforcement seam (ADR-039)."""

from __future__ import annotations

import pytest
from typing import Any

from eck.agent_loop import AgentLoop
from eck.policy_gate import (
    PolicyGate,
    ExecutionMode,
    PolicyCause,
    PolicyContext,
    PolicyDecision,
)


class FakePolicyGate:
    """Minimal fake gate for deterministic test control."""

    def __init__(
        self,
        mode: ExecutionMode,
        cause: PolicyCause = PolicyCause.DEFAULT,
        rule_id: str = "test-rule",
        reason: str = "test-reason",
    ):
        self.mode = mode
        self.cause = cause
        self.rule_id = rule_id
        self.reason = reason
        self.call_count = 0
        self.last_args: tuple[Any, float] | None = None
        self.last_kwargs: dict[str, Any] | None = None

    def evaluate(
        self,
        proposed_action: Any,
        confidence: float,
        context: PolicyContext,
    ) -> PolicyDecision:
        self.call_count += 1
        self.last_args = (proposed_action, confidence)
        self.last_kwargs = {"context": context}
        return PolicyDecision(
            mode=self.mode,
            cause=self.cause,
            rule_id=self.rule_id,
            reason=self.reason,
        )


def test_step_invokes_policy_gate_exactly_once():
    gate = FakePolicyGate(ExecutionMode.EXECUTE)
    loop = AgentLoop(gate)

    loop.step(object(), 0.85, PolicyContext())

    assert gate.call_count == 1


def test_step_passes_proposed_action_confidence_and_context_to_gate():
    gate = FakePolicyGate(ExecutionMode.EXECUTE)
    loop = AgentLoop(gate)

    action = object()
    conf = 0.72
    ctx = PolicyContext()  # safe minimal context (all defaults)

    loop.step(action, conf, ctx)

    assert gate.last_args == (action, conf)
    assert gate.last_kwargs == {"context": ctx}


def test_step_execute_calls_hook_once_and_returns_result():
    gate = FakePolicyGate(ExecutionMode.EXECUTE)
    loop = AgentLoop(gate)

    action = object()
    calls: list[object] = []

    def hook(act: Any) -> str:
        calls.append(act)
        return "result-from-hook"

    decision, result = loop.step(action, 0.9, PolicyContext(), execute_hook=hook)

    assert len(calls) == 1
    assert calls[0] is action  # identity: exact same object forwarded
    assert result == "result-from-hook"
    assert decision.mode is ExecutionMode.EXECUTE


def test_step_execute_with_no_hook_returns_decision_and_none():
    gate = FakePolicyGate(ExecutionMode.EXECUTE)
    loop = AgentLoop(gate)

    decision, result = loop.step(object(), 0.8, PolicyContext())

    assert decision.mode is ExecutionMode.EXECUTE
    assert result is None


def test_step_halt_blocks_execution():
    gate = FakePolicyGate(ExecutionMode.HALT)
    loop = AgentLoop(gate)

    calls: list[Any] = []
    decision, result = loop.step(object(), 0.6, PolicyContext(), execute_hook=lambda a: calls.append(a))

    assert len(calls) == 0
    assert result is None
    assert decision.mode is ExecutionMode.HALT


def test_step_retry_blocks_execution():
    gate = FakePolicyGate(ExecutionMode.RETRY)
    loop = AgentLoop(gate)

    calls: list[Any] = []
    decision, result = loop.step(object(), 0.4, PolicyContext(), execute_hook=lambda a: calls.append(a))

    assert len(calls) == 0
    assert result is None
    assert decision.mode is ExecutionMode.RETRY


def test_step_degrade_blocks_execution():
    gate = FakePolicyGate(ExecutionMode.DEGRADE)
    loop = AgentLoop(gate)

    calls: list[Any] = []
    decision, result = loop.step(object(), 0.3, PolicyContext(), execute_hook=lambda a: calls.append(a))

    assert len(calls) == 0
    assert result is None
    assert decision.mode is ExecutionMode.DEGRADE


def test_step_returns_full_policy_decision_for_all_modes():
    cases = [
        (ExecutionMode.EXECUTE, PolicyCause.CONFIDENCE, "exec-rule"),
        (ExecutionMode.HALT, PolicyCause.FAILURE_WINDOW, "halt-rule"),
        (ExecutionMode.RETRY, PolicyCause.SAFETY, "retry-rule"),
        (ExecutionMode.DEGRADE, PolicyCause.DEFAULT, "degrade-rule"),
    ]

    for mode, cause, rule_id in cases:
        gate = FakePolicyGate(mode, cause=cause, rule_id=rule_id)
        loop = AgentLoop(gate)

        decision, _ = loop.step(object(), 0.5, PolicyContext())

        assert decision.mode is mode
        assert decision.cause is cause
        assert decision.rule_id == rule_id
        assert decision.reason == "test-reason"


def test_step_preserves_policy_decision_fields():
    gate = FakePolicyGate(
        ExecutionMode.EXECUTE,
        cause=PolicyCause.SAFETY,
        rule_id="specific-rule-42",
        reason="safety boundary violated"
    )
    loop = AgentLoop(gate)

    decision, _ = loop.step(object(), 0.1, PolicyContext(safety_level="high"))

    assert decision.cause is PolicyCause.SAFETY
    assert decision.rule_id == "specific-rule-42"
    assert decision.reason == "safety boundary violated"


def test_step_propagates_execute_hook_exceptions():
    gate = FakePolicyGate(ExecutionMode.EXECUTE)
    loop = AgentLoop(gate)

    def failing_hook(_: Any) -> None:
        raise RuntimeError("hook failed deliberately")

    with pytest.raises(RuntimeError, match="hook failed deliberately"):
        loop.step(object(), 0.95, PolicyContext(), execute_hook=failing_hook)


def test_step_raises_value_error_on_invalid_mode():
    class BrokenGate(PolicyGate):
        def evaluate(
            self,
            proposed_action: Any,
            confidence: float,
            context: PolicyContext,
        ) -> PolicyDecision:
            # Non-compliant: invalid mode type
            return PolicyDecision(
                mode="INVALID",  # type: ignore[arg-type]
                cause=PolicyCause.DEFAULT,
                rule_id="bad",
                reason="bug",
            )

    broken_gate = BrokenGate()
    loop = AgentLoop(broken_gate)

    with pytest.raises(ValueError, match="Unknown execution mode from gate: INVALID"):
        loop.step(object(), 0.7, PolicyContext())


def test_step_is_deterministic_on_repeated_identical_inputs():
    gate = FakePolicyGate(ExecutionMode.EXECUTE, cause=PolicyCause.CONFIDENCE)
    loop = AgentLoop(gate)

    action = object()
    conf = 0.88
    ctx = PolicyContext()

    decision1, result1 = loop.step(action, conf, ctx)
    decision2, result2 = loop.step(action, conf, ctx)

    assert decision1.mode is decision2.mode
    assert decision1.cause is decision2.cause
    assert decision1.rule_id == decision2.rule_id
    assert decision1.reason == decision2.reason
    assert result1 is result2 is None
    assert gate.call_count == 2

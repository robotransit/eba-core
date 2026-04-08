# tests/test_adversarial.py
"""Adversarial tests for ECK invariant edges.

Focused on the highest-consequence failure modes:
- Rejected/deferred cycles must not contaminate execution-derived state
- Policy gate refusal is a hard stop — authorize_and_perform must not be called
- No-proposal path is a true no-op at the execution boundary
- HALT is terminal before any seam is called — step() returns False immediately
- Goal completion does not fire under policy-suppressed queue emptiness
- Post-failure gate suppression: failure window blocks the immediately
  following execution attempt at the gate seam
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from typing import Any

from eck.agent import ECKAgent
from eck.config import ECKConfig, PolicyMode
from eck.policy_gate import (
    ExecutionMode,
    PolicyCause,
    PolicyDecision,
    PolicyGate,
)
from eck.types import (
    CriticOutcome,
    ExecutionResult,
    PartialStructure,
    ProposedAction,
    make_critic_outcome,
)


# ── Shared stubs ──────────────────────────────────────────────────────────────

def dummy_llm(prompt: str) -> str:
    return "NO"


def _agent(
    policy_mode: PolicyMode = PolicyMode.NORMAL,
    gate: PolicyGate | None = None,
    **config_kwargs: Any,
) -> ECKAgent:
    config = ECKConfig(policy_mode=policy_mode, **config_kwargs)
    return ECKAgent(
        objective="Test objective",
        llm_call=dummy_llm,
        config=config,
        policy_gate=gate,
    )


def _mock_proposal() -> ProposedAction:
    return ProposedAction(
        action_type="llm_query",
        parameters={"prompt": "do the thing"},
        task_text="task",
        task_id="test-task-id",
        provenance_id="test-provenance-id",
    )


def _result_performed() -> ExecutionResult:
    return ExecutionResult(performed=True, outcome="outcome", refusal_reason=None)


def _critic(
    category: str,
    severity: float = 0.0,
) -> tuple[CriticOutcome, PartialStructure | None]:
    return (
        make_critic_outcome(category=category, severity=severity, feedback=category),
        None,
    )


def _gate_decision(mode: ExecutionMode) -> PolicyDecision:
    return PolicyDecision(
        mode=mode,
        cause=PolicyCause.CONFIDENCE,
        reason="adversarial test",
        rule_id="TEST",
    )


def _snap(severe: bool = False) -> dict[str, Any]:
    return {
        "drift_streak": 0,
        "total_drift_events": 0,
        "last_error_z": 0.0,
        "numeric_bias": 0.0,
        "feasibility_sample_count": 0,
        "numeric_success_rate": None,
        "severe": severe,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGateRefusalIsHardStop(unittest.TestCase):
    """Policy gate refusal must prevent authorize_and_perform from being called."""

    def _assert_authorize_not_called(self, gate_mode: ExecutionMode) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_decision(gate_mode)
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution",
                          return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic("rejected")), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_not_called()

    def test_gate_retry_never_calls_authorize_and_perform(self) -> None:
        self._assert_authorize_not_called(ExecutionMode.RETRY)

    def test_gate_degrade_never_calls_authorize_and_perform(self) -> None:
        self._assert_authorize_not_called(ExecutionMode.DEGRADE)

    def test_gate_halt_never_calls_authorize_and_perform(self) -> None:
        self._assert_authorize_not_called(ExecutionMode.HALT)


class TestNoProposalIsExecutionNoOp(unittest.TestCase):
    """No-proposal path must not evaluate the gate or perform execution."""

    def test_no_proposal_skips_gate_and_execution(self) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic("deferred")), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        gate.evaluate.assert_not_called()
        mock_auth.assert_not_called()

    def test_no_proposal_critic_receives_non_executed_result(self) -> None:
        import eck.agent as agent_mod

        a = _agent()
        a.seed("task")
        received: dict[str, Any] = {}

        def capture_critic(**kwargs: Any) -> tuple[CriticOutcome, PartialStructure | None]:
            received["result"] = kwargs["result"]
            return _critic("deferred")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          side_effect=capture_critic), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertFalse(received["result"].performed)
        self.assertEqual(received["result"].refusal_reason, "no_valid_proposal")


class TestRejectedDeferredDoNotContaminateState(unittest.TestCase):
    """Rejected and deferred cycles must not update drift or feasibility state."""

    def _assert_no_drift_or_feasibility(self, category: str) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_decision(ExecutionMode.RETRY)
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution",
                          return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform"), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic(category)), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error") as mock_error, \
             patch.object(a.drift, "record_feasibility") as mock_feas, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_error.assert_not_called()
        mock_feas.assert_not_called()

    def test_rejected_cycle_skips_drift_and_feasibility(self) -> None:
        self._assert_no_drift_or_feasibility("rejected")

    def test_deferred_cycle_skips_drift_and_feasibility(self) -> None:
        self._assert_no_drift_or_feasibility("deferred")


class TestHaltIsPreStartTerminal(unittest.TestCase):
    """HALT mode must terminate before any execution seam is called."""

    def test_halt_returns_false_without_consuming_task(self) -> None:
        import eck.agent as agent_mod

        a = _agent(policy_mode=PolicyMode.HALT)
        a.seed("task")
        queue_size_before = len(a.queue)

        def raise_if_called(*_: Any, **__: Any) -> None:
            raise AssertionError("No seams should be called in HALT mode")

        with patch.object(agent_mod, "propose_execution", raise_if_called), \
             patch.object(agent_mod, "authorize_and_perform", raise_if_called), \
             patch.object(agent_mod, "generate_prediction", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called):
            result = a.step()

        self.assertIs(result, False)
        self.assertEqual(len(a.queue), queue_size_before)


class TestGoalCompletionUnderSuppression(unittest.TestCase):
    """Goal completion must not fire when queue emptiness is policy-induced.

    The critic is set to 'success' so that the only reason goal completion
    does not fire is suppression — not a failed cycle.
    """

    def test_goal_completion_does_not_trigger_under_suppressed_subtasks(self) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_decision(ExecutionMode.EXECUTE)
        a = _agent(gate=gate, goal_completion_threshold=0.0)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution",
                          return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth",
                          return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", return_value=False), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic("success", severity=0.1)), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "record_feasibility"), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            result = a.step()

        # Critic said success, confidence threshold is 0.0, queue is empty —
        # but suppression is active, so goal completion must not fire.
        self.assertIs(result, True)


class TestPostFailureGateSuppression(unittest.TestCase):
    """Failure window propagates into gate context on the immediately following cycle.

    This test is scoped to one seam only:
        confidence failure window → PolicyContext.failure_window_active → gate refusal

    Drift escalation, error recording, feasibility tracking, and subtask
    generation are held constant via explicit patches because they are
    orthogonal to this invariant. Both cycles use the same patch set for
    symmetry and to make the isolation claim literal.
    """

    def test_failure_window_propagates_to_gate_context_on_next_cycle(self) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.side_effect = [
            _gate_decision(ExecutionMode.EXECUTE),   # cycle 1: permit execution
            _gate_decision(ExecutionMode.RETRY),     # cycle 2: refuse — window active
        ]
        a = _agent(gate=gate, goal_completion_threshold=0.99)

        # Cycle 1: execution is permitted, critic returns failure.
        # This opens the confidence failure window.
        # Drift escalation, error recording, and feasibility tracking are
        # held constant — all orthogonal to this test.
        a.seed("task1")
        with patch.object(agent_mod, "propose_execution",
                          return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic("failure", severity=0.8)), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "get_policy_mode",
                          return_value=PolicyMode.NORMAL), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "record_feasibility"), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        # Failure window must now be open.
        self.assertTrue(a._confidence._last_outcome_was_failure)

        # Cycle 2: a new proposal exists.
        # All orthogonal mechanisms still held constant — symmetric with cycle 1.
        # The gate must receive failure_window_active=True
        # and execution must be refused before authorize_and_perform is called.
        a.seed("task2")
        with patch.object(agent_mod, "propose_execution",
                          return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic("rejected")), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "get_policy_mode",
                          return_value=PolicyMode.NORMAL), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "record_feasibility"), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        second_call_kwargs = gate.evaluate.call_args_list[1].kwargs
        self.assertTrue(second_call_kwargs["context"].failure_window_active)
        mock_auth.assert_not_called()


if __name__ == "__main__":
    unittest.main()

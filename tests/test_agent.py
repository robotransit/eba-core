# tests/test_agent.py
"""Tests for ECKAgent orchestration loop."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from eck.agent import ECKAgent
from eck.config import ECKConfig, PolicyMode
from eck.policy_gate import (
    DefaultPolicyGate,
    ExecutionMode,
    PolicyCause,
    PolicyContext,
    PolicyDecision,
    PolicyGate,
)
from eck.types import ExecutionResult, make_critic_outcome


# ── LLM stub ─────────────────────────────────────────────────────────────────

def dummy_llm(prompt: str) -> str:
    """Deterministic stub — always returns NO."""
    return "NO"


# ── ExecutionResult fixtures ──────────────────────────────────────────────────

def _result_performed(outcome: str = "outcome") -> ExecutionResult:
    """Performed ExecutionResult with a real outcome string."""
    return ExecutionResult(performed=True, outcome=outcome, refusal_reason=None)


def _result_refused(refusal_reason: str) -> ExecutionResult:
    """Refused ExecutionResult with a given refusal reason."""
    return ExecutionResult(performed=False, outcome="", refusal_reason=refusal_reason)


# ── Critic outcome fixtures ───────────────────────────────────────────────────

def _critic_success():
    """(CriticOutcome, None) for a successful evaluation."""
    return (make_critic_outcome(category="success", severity=0.1, feedback="ok"), None)


def _critic_failure():
    """(CriticOutcome, None) for a failed evaluation."""
    return (make_critic_outcome(category="failure", severity=0.8, feedback="fail"), None)


def _critic_deferred():
    """(CriticOutcome, None) for a deferred cycle (no valid proposal)."""
    return (make_critic_outcome(category="deferred", severity=0.0, feedback="no_valid_proposal"), None)


def _critic_rejected():
    """(CriticOutcome, None) for a rejected cycle (gate/kernel refusal)."""
    return (make_critic_outcome(category="rejected", severity=0.0, feedback="gate:RETRY"), None)


# ── Gate decision fixtures ────────────────────────────────────────────────────

def _gate_execute() -> PolicyDecision:
    """PolicyDecision authorizing execution."""
    return PolicyDecision(
        mode=ExecutionMode.EXECUTE,
        cause=PolicyCause.CONFIDENCE,
        reason="confidence sufficient",
        rule_id="RULE_005",
    )


def _gate_retry() -> PolicyDecision:
    """PolicyDecision refusing execution with RETRY."""
    return PolicyDecision(
        mode=ExecutionMode.RETRY,
        cause=PolicyCause.CONFIDENCE,
        reason="confidence too low",
        rule_id="RULE_003",
    )


def _gate_halt() -> PolicyDecision:
    """PolicyDecision refusing execution with HALT."""
    return PolicyDecision(
        mode=ExecutionMode.HALT,
        cause=PolicyCause.CONFIDENCE,
        reason="confidence below halt threshold",
        rule_id="RULE_002",
    )


def _gate_degrade() -> PolicyDecision:
    """PolicyDecision refusing execution with DEGRADE."""
    return PolicyDecision(
        mode=ExecutionMode.DEGRADE,
        cause=PolicyCause.CONFIDENCE,
        reason="borderline confidence",
        rule_id="RULE_004",
    )


# ── Mock ProposedAction ───────────────────────────────────────────────────────

def _mock_proposal():
    """Minimal mock ProposedAction for use in gate/execution tests."""
    from eck.types import ProposedAction
    return ProposedAction(
        action_type="llm_query",
        parameters={"prompt": "do the thing"},
        task_text="task",
        task_id="test-task-id",
        provenance_id="test-provenance-id",
    )


# ── Agent factory ─────────────────────────────────────────────────────────────

def _agent(
    policy_mode: PolicyMode = PolicyMode.NORMAL,
    gate: PolicyGate | None = None,
    **config_kwargs,
) -> ECKAgent:
    """Construct a test ECKAgent with an optional injected gate."""
    config = ECKConfig(policy_mode=policy_mode, **config_kwargs)
    return ECKAgent(
        objective="Test objective",
        llm_call=dummy_llm,
        config=config,
        policy_gate=gate,
    )


# ── Drift snapshot helper ─────────────────────────────────────────────────────

def _snap(severe: bool = False) -> dict:
    """Minimal drift snapshot for use in patch targets."""
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
# Test classes
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentHalt(unittest.TestCase):
    """HALT mode — step() returns False immediately."""

    def test_halt_at_start_stops_step(self) -> None:
        """HALT mode → step() returns False without calling any seams."""
        import eck.agent as agent_mod

        a = _agent(policy_mode=PolicyMode.HALT)

        def raise_if_called(*_, **__):
            raise AssertionError("No seams should be called in HALT mode")

        with patch.object(agent_mod, "propose_execution", raise_if_called), \
             patch.object(agent_mod, "authorize_and_perform", raise_if_called), \
             patch.object(agent_mod, "generate_prediction", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called):
            self.assertIs(a.step(), False)


class TestQueueEmpty(unittest.TestCase):
    """Empty queue — step() returns False without calling seams."""

    def test_queue_empty_step_returns_false(self) -> None:
        """Empty queue → step() returns False."""
        a = _agent()
        self.assertIs(a.step(), False)

    def test_queue_empty_no_seam_calls(self) -> None:
        """Empty queue → no prediction, critic, execution, or subtask calls."""
        import eck.agent as agent_mod

        a = _agent()

        def raise_if_called(*_, **__):
            raise AssertionError("No seams should be called when queue is empty")

        with patch.object(agent_mod, "generate_prediction", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate", raise_if_called), \
             patch.object(agent_mod, "propose_execution", raise_if_called), \
             patch.object(agent_mod, "authorize_and_perform", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called):
            self.assertIs(a.step(), False)


class TestExecutionBoundary(unittest.TestCase):
    """ADR-042 propose/gate/authorize sequence — the two-gate boundary."""

    # ------------------------------------------------------------------
    # No proposal path
    # ------------------------------------------------------------------
    def test_no_proposal_gate_not_called(self) -> None:
        """propose_execution returns None → gate is never evaluated."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "authorize_and_perform"), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        gate.evaluate.assert_not_called()

    def test_no_proposal_authorize_not_called(self) -> None:
        """propose_execution returns None → authorize_and_perform is never called."""
        import eck.agent as agent_mod

        a = _agent()
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_not_called()

    def test_no_proposal_produces_deferred_result(self) -> None:
        """propose_execution returns None → critic receives performed=False result."""
        import eck.agent as agent_mod

        a = _agent()
        a.seed("task")
        received = {}

        def capture_critic(**kwargs):
            received["result"] = kwargs["result"]
            return _critic_deferred()

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "authorize_and_perform"), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", side_effect=capture_critic), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertFalse(received["result"].performed)
        self.assertEqual(received["result"].refusal_reason, "no_valid_proposal")

    # ------------------------------------------------------------------
    # Gate refusal paths
    # ------------------------------------------------------------------
    def test_gate_retry_authorize_not_called(self) -> None:
        """Gate returns RETRY → authorize_and_perform is not called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_retry()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_rejected()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_not_called()

    def test_gate_halt_authorize_not_called(self) -> None:
        """Gate returns HALT → authorize_and_perform is not called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_halt()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_rejected()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_not_called()

    def test_gate_degrade_authorize_not_called(self) -> None:
        """Gate returns DEGRADE → authorize_and_perform is not called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_degrade()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform") as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_rejected()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_not_called()

    def test_gate_refusal_produces_refused_result(self) -> None:
        """Gate returns non-EXECUTE → critic receives performed=False result."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_retry()
        a = _agent(gate=gate)
        a.seed("task")
        received = {}

        def capture_critic(**kwargs):
            received["result"] = kwargs["result"]
            return _critic_rejected()

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform"), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", side_effect=capture_critic), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertFalse(received["result"].performed)
        self.assertIn("gate:", received["result"].refusal_reason)

    # ------------------------------------------------------------------
    # Gate EXECUTE path
    # ------------------------------------------------------------------
    def test_gate_execute_authorize_called_once(self) -> None:
        """Gate returns EXECUTE → authorize_and_perform is called exactly once."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()) as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_called_once()

    def test_gate_execute_authorize_called_with_correct_arguments(self) -> None:
        """Gate returns EXECUTE → authorize_and_perform receives correct arguments."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")
        proposal = _mock_proposal()

        with patch.object(agent_mod, "propose_execution", return_value=proposal), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()) as mock_auth, \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_auth.assert_called_once_with(
            proposed_action=proposal,
            policy_mode=a.current_policy_mode,
            llm_call=dummy_llm,
        )

    def test_gate_execute_result_passed_to_critic(self) -> None:
        """Gate returns EXECUTE → critic receives the ExecutionResult from authorize."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")
        received = {}
        expected_result = _result_performed("the outcome")

        def capture_critic(**kwargs):
            received["result"] = kwargs["result"]
            return _critic_success()

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=expected_result), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", side_effect=capture_critic), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertEqual(received["result"], expected_result)
        self.assertTrue(received["result"].performed)

    def test_gate_evaluated_with_proposal_and_correct_context(self) -> None:
        """Gate is called with the ProposedAction and correct PolicyContext."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")
        proposal = _mock_proposal()

        self.assertFalse(a._confidence._last_outcome_was_failure)

        with patch.object(agent_mod, "propose_execution", return_value=proposal), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        gate.evaluate.assert_called_once()
        call_kwargs = gate.evaluate.call_args.kwargs
        self.assertEqual(call_kwargs["proposed_action"], proposal)
        self.assertIsInstance(call_kwargs["context"], PolicyContext)
        self.assertEqual(call_kwargs["context"].failure_window_active, False)

    def test_gate_context_reflects_failure_window_active(self) -> None:
        """Gate PolicyContext carries failure_window_active=True when confidence
        signal has recorded a failure."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")
        a._confidence._last_outcome_was_failure = True

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        call_kwargs = gate.evaluate.call_args.kwargs
        self.assertTrue(call_kwargs["context"].failure_window_active)


class TestDriftBehavior(unittest.TestCase):
    """Drift and feasibility tracking semantics — execution-aware gating."""

    # ------------------------------------------------------------------
    # Rejected/deferred skip drift
    # ------------------------------------------------------------------
    def test_deferred_skips_record_error(self) -> None:
        """Deferred cycle → drift.record_error is not called."""
        import eck.agent as agent_mod

        a = _agent()
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error") as mock_record_error, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_record_error.assert_not_called()

    def test_deferred_skips_record_feasibility(self) -> None:
        """Deferred cycle → drift.record_feasibility is not called."""
        import eck.agent as agent_mod

        a = _agent()
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_feasibility") as mock_record_feas, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_record_feas.assert_not_called()

    def test_rejected_skips_record_error(self) -> None:
        """Rejected cycle → drift.record_error is not called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_retry()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform"), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_rejected()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error") as mock_record_error, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_record_error.assert_not_called()

    def test_rejected_skips_record_feasibility(self) -> None:
        """Rejected cycle → drift.record_feasibility is not called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_retry()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform"), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_rejected()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_feasibility") as mock_record_feas, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_record_feas.assert_not_called()

    # ------------------------------------------------------------------
    # Performed execution updates drift normally
    # ------------------------------------------------------------------
    def test_success_calls_record_error(self) -> None:
        """Successful execution → drift.record_error is called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False) as mock_record_error, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_record_error.assert_called_once()

    def test_success_calls_record_feasibility(self) -> None:
        """Successful execution → drift.record_feasibility is called."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "record_feasibility") as mock_feas, \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        mock_feas.assert_called_once()

    # ------------------------------------------------------------------
    # Drift streak halt
    # ------------------------------------------------------------------
    def test_drift_streak_halt_returns_false(self) -> None:
        """step() returns False when drift_streak exceeds max_drift_streak."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, max_drift_streak=2)
        a.seed("task")
        a.drift.drift_streak = 3

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_failure()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=True), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            result = a.step()

        self.assertIs(result, False)


class TestPeriodicGuard(unittest.TestCase):
    """Periodic severe instability guard — single seam (ADR-040)."""

    def test_severe_instability_halts_agent(self) -> None:
        """Periodic guard returns False when snapshot severe is True."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, guard_interval=1, goal_completion_threshold=0.99)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_failure()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap(severe=True)):
            result = a.step()

        self.assertIs(result, False)

    def test_non_severe_does_not_halt(self) -> None:
        """Periodic guard does not halt when snapshot severe is False."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, guard_interval=1, goal_completion_threshold=0.99)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_failure()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap(severe=False)):
            result = a.step()

        self.assertIs(result, True)

    def test_severe_halt_within_guard_interval_cycles(self) -> None:
        """Severe instability halts within at most guard_interval cycles."""
        import eck.agent as agent_mod

        guard_interval = 3
        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, guard_interval=guard_interval, goal_completion_threshold=0.99)

        halt_cycle = None
        for i in range(guard_interval + 1):
            a.seed(f"task_{i}")
            with patch.object(agent_mod, "propose_execution",
                              return_value=_mock_proposal()), \
                 patch.object(agent_mod, "authorize_and_perform",
                              return_value=_result_performed()), \
                 patch.object(agent_mod, "generate_prediction", return_value="pred"), \
                 patch.object(agent_mod, "critic_evaluate",
                              return_value=_critic_failure()), \
                 patch.object(agent_mod, "generate_subtasks", return_value=[]), \
                 patch.object(a.drift, "record_error", return_value=False), \
                 patch.object(a.drift, "snapshot", return_value=_snap(severe=True)):
                if not a.step():
                    halt_cycle = i + 1
                    break

        self.assertIsNotNone(halt_cycle, "Agent did not halt within guard_interval cycles")
        self.assertLessEqual(halt_cycle, guard_interval)

    def test_periodic_guard_fires_on_deferred_cycle(self) -> None:
        """Periodic guard still runs even when execution was deferred."""
        import eck.agent as agent_mod

        a = _agent(guard_interval=1, goal_completion_threshold=0.99)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap(severe=True)):
            result = a.step()

        self.assertIs(result, False)


class TestPolicyModeIrreversibility(unittest.TestCase):
    """Policy mode upgrades are irreversible — no downgrade permitted."""

    def test_policy_mode_upgrades_are_irreversible(self) -> None:
        """Policy mode advances through GUIDED → ENFORCED and does not retreat."""
        import eck.agent as agent_mod

        a = _agent(policy_mode=PolicyMode.NORMAL)
        self.assertEqual(a.current_policy_mode, PolicyMode.NORMAL)

        modes = iter([PolicyMode.GUIDED, PolicyMode.NORMAL, PolicyMode.ENFORCED])

        with patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "get_policy_mode", side_effect=modes), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("t1")
            a.step()
            self.assertEqual(a.current_policy_mode, PolicyMode.GUIDED)

            a.seed("t2")
            a.step()
            self.assertEqual(a.current_policy_mode, PolicyMode.GUIDED)

            a.seed("t3")
            a.step()
            self.assertEqual(a.current_policy_mode, PolicyMode.ENFORCED)

    def test_policy_mode_single_sourced_no_split_brain(self) -> None:
        """agent.current_policy_mode, config, and drift.config must never diverge."""
        import eck.agent as agent_mod

        a = _agent(policy_mode=PolicyMode.NORMAL)

        def assert_sync(expected: PolicyMode) -> None:
            self.assertEqual(a.current_policy_mode, expected)
            self.assertEqual(a.config.policy_mode, expected)
            self.assertEqual(a.drift.config.policy_mode, expected)

        assert_sync(PolicyMode.NORMAL)

        with patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):

            with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.GUIDED):
                a.seed("t1")
                a.step()
            assert_sync(PolicyMode.GUIDED)

            with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL):
                a.seed("t2")
                a.step()
            assert_sync(PolicyMode.GUIDED)

            with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.ENFORCED):
                a.seed("t3")
                a.step()
            assert_sync(PolicyMode.ENFORCED)


class TestGoalCompletion(unittest.TestCase):
    """ADR-041 deterministic goal completion predicate."""

    def test_goal_completion_predicate_satisfied(self) -> None:
        """Success + empty queue + threshold met → step() returns False."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, goal_completion_threshold=0.0)

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("x")
            result = a.step()

        self.assertIs(result, False)

    def test_goal_completion_not_satisfied_when_confidence_low(self) -> None:
        """Success + empty queue + threshold not met → step() returns True."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, goal_completion_threshold=0.99)

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("x")
            result = a.step()

        self.assertIs(result, True)

    def test_goal_completion_not_satisfied_when_subtasks_suppressed(self) -> None:
        """Success + suppressed subtasks → goal predicate not satisfied."""
        import eck.agent as agent_mod

        a = _agent(goal_completion_threshold=0.0)

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", return_value=False), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("x")
            result = a.step()

        self.assertIs(result, True)

    def test_goal_not_satisfied_for_deferred_cycle(self) -> None:
        """Deferred cycle cannot satisfy goal completion — success=False."""
        import eck.agent as agent_mod

        a = _agent(goal_completion_threshold=0.0)

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("x")
            result = a.step()

        self.assertIs(result, True)


class TestSubtaskGeneration(unittest.TestCase):
    """Subtask generation — gated by should_execute, logged correctly."""

    def test_subtasks_pushed_to_queue_when_execution_permitted(self) -> None:
        """Subtasks are pushed to queue when should_execute returns True."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, goal_completion_threshold=0.99)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=["sub1", "sub2"]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertEqual(len(a.queue), 2)

    def test_subtasks_not_generated_when_suppressed(self) -> None:
        """Subtask generation skipped when should_execute returns False."""
        import eck.agent as agent_mod

        a = _agent(goal_completion_threshold=0.99)
        a.seed("task")

        subtask_calls = {"n": 0}

        def count_subtasks(*_, **__):
            subtask_calls["n"] += 1
            return []

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", return_value=False), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", side_effect=count_subtasks), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertEqual(subtask_calls["n"], 0)

    def test_queue_full_error_during_subtask_push_is_handled(self) -> None:
        """QueueFullError during subtask push logs warning and breaks loop."""
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = _agent(gate=gate, goal_completion_threshold=0.99, max_queue_size=1)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks",
                          return_value=["sub1", "sub2", "sub3"]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            result = a.step()

        self.assertIs(result, True)


class TestSeedBehaviour(unittest.TestCase):
    """seed() — explicit task and LLM-generated task paths."""

    def test_seed_with_explicit_task_pushes_to_queue(self) -> None:
        """seed() with an explicit task pushes it to the queue."""
        a = _agent()
        a.seed("explicit task")
        self.assertEqual(len(a.queue), 1)

    def test_seed_without_task_calls_llm(self) -> None:
        """seed() with no task calls the LLM to generate one."""
        called = {"n": 0}

        def counting_llm(prompt: str) -> str:
            called["n"] += 1
            return "generated task"

        a = ECKAgent(
            objective="Test objective",
            llm_call=counting_llm,
            config=ECKConfig(),
        )
        a.seed()
        self.assertGreater(called["n"], 0)
        self.assertEqual(len(a.queue), 1)

    def test_seed_without_task_uses_llm_response(self) -> None:
        """seed() with no task uses the LLM response as the initial task."""
        a = ECKAgent(
            objective="Test objective",
            llm_call=lambda p: "  llm generated task  ",
            config=ECKConfig(),
        )
        a.seed()
        task = a.queue.pop()
        self.assertEqual(task["text"], "llm generated task")


class TestRunMethod(unittest.TestCase):
    """run() — iterates step() until halt or max_iterations."""

    def test_run_stops_when_step_returns_false(self) -> None:
        """run() stops when step() returns False."""
        import eck.agent as agent_mod

        a = _agent(goal_completion_threshold=0.0)

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a._policy_gate = gate

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("x")
            a.run()

        self.assertEqual(a.cycles, 0)

    def test_run_respects_max_iterations(self) -> None:
        """run() stops after max_iterations cycles."""
        import eck.agent as agent_mod

        a = _agent(goal_completion_threshold=0.99, max_iterations=2)

        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a._policy_gate = gate

        with patch.object(agent_mod, "propose_execution", return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=["sub"]), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.seed("x")
            a.run()

        self.assertLessEqual(a.cycles, 2)


class TestDefaultGateInjection(unittest.TestCase):
    """DefaultPolicyGate is used when no gate is provided at construction."""

    def test_default_gate_injected_when_none_provided(self) -> None:
        """ECKAgent uses DefaultPolicyGate when policy_gate=None."""
        a = ECKAgent(
            objective="test",
            llm_call=dummy_llm,
            config=ECKConfig(),
            policy_gate=None,
        )
        self.assertIsInstance(a._policy_gate, DefaultPolicyGate)

    def test_injected_gate_used_when_provided(self) -> None:
        """ECKAgent uses the injected gate when one is provided."""
        gate = MagicMock(spec=PolicyGate)
        gate.evaluate.return_value = _gate_execute()
        a = ECKAgent(
            objective="test",
            llm_call=dummy_llm,
            config=ECKConfig(),
            policy_gate=gate,
        )
        self.assertIs(a._policy_gate, gate)


class TestTaskLifecycle(unittest.TestCase):
    """Task lifecycle recording is absent pending v0.2.0 audit layer."""

    def test_task_lifecycle_recording_absent(self) -> None:
        from eck.memory import MemoryRetrieval
        memory = MemoryRetrieval(enabled=False)
        self.assertFalse(hasattr(memory, "record"))


if __name__ == "__main__":
    unittest.main()

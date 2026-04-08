# tests/test_adversarial_sequences.py
"""Multi-cycle adversarial sequence tests for ECK.

These tests verify progression invariants across multiple control cycles.
They differ from test_adversarial.py in scope and method:

  - test_adversarial.py:           single-seam, local invariant edges
  - test_adversarial_sequences.py: multi-cycle, subsystem interaction sequences

Design principle:
    Subsystems that define the sequence under test run real.
    Only machinery orthogonal to the sequence is patched.

Sequences covered:
  - Failure → blocked cycle → recovery
    (failure window opens, propagates into gate context, consumed on
    rejected cycle, confidence recovers on success)
  - Failure → partial → recovery
    (confidence trajectory across mixed outcomes with active failure window)
  - Policy mode escalation under drift stress
    (irreversible progression — retreat attempts are ignored)
  - HALT irreversibility
    (once halted, subsequent step() calls return False regardless of queue)
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
    ConflictKind,
    ConflictLocus,
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
        reason="sequence test",
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


def _run_cycle(
    a: ECKAgent,
    agent_mod: Any,
    *,
    gate_mode: ExecutionMode,
    critic_category: str,
    critic_severity: float = 0.0,
) -> bool:
    """
    Run one controlled executed cycle on agent a.

    Proposal, execution result, prediction, subtasks, and drift machinery
    are all patched as orthogonal. Confidence runs real. Gate behavior is
    controlled via gate_mode. Critic outcome is controlled via critic_category.

    Use this helper only for cycles where execution is performed.
    For refusal cycles, use _run_refusal_cycle so the distinction is visible.
    """
    gate = a._policy_gate
    if isinstance(gate, MagicMock):
        gate.evaluate.return_value = _gate_decision(gate_mode)

    with patch.object(agent_mod, "propose_execution",
                      return_value=_mock_proposal()), \
         patch.object(agent_mod, "authorize_and_perform",
                      return_value=_result_performed()), \
         patch.object(agent_mod, "generate_prediction", return_value="pred"), \
         patch.object(agent_mod, "critic_evaluate",
                      return_value=_critic(critic_category, critic_severity)), \
         patch.object(agent_mod, "generate_subtasks", return_value=[]), \
         patch.object(a.drift, "get_policy_mode",
                      return_value=PolicyMode.NORMAL), \
         patch.object(a.drift, "record_error", return_value=False), \
         patch.object(a.drift, "record_feasibility"), \
         patch.object(a.drift, "snapshot", return_value=_snap()):
        return a.step()


def _run_refusal_cycle(
    a: ECKAgent,
    agent_mod: Any,
    gate: MagicMock,
) -> tuple[bool, dict[str, Any], MagicMock]:
    """
    Run one controlled refusal cycle where the gate refuses execution.

    Returns a three-tuple:
        step_result       bool             — return value of a.step()
        gate_call_kwargs  dict[str, Any]   — kwargs passed to gate.evaluate
        mock_auth         MagicMock        — the authorize_and_perform mock,
                                            for the caller to assert not called

    Gate is set to RETRY. All drift machinery and orthogonal surfaces are
    patched. Confidence runs real — a rejected cycle consumes the failure
    window per the confidence.py contract (ADR-023).
    """
    gate.evaluate.return_value = _gate_decision(ExecutionMode.RETRY)

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
        result = a.step()

    gate_call_kwargs = gate.evaluate.call_args.kwargs
    return result, gate_call_kwargs, mock_auth


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFailureRecoverySequence(unittest.TestCase):
    """Failure window opens, propagates into gate context, then is consumed.

    Confidence runs real. Gate behavior is controlled per cycle.
    Drift machinery is patched as orthogonal.

    Sequence (aligned to confidence.py ADR-023 contract):
        Cycle 1: EXECUTE + failure  → failure window opens
        Cycle 2: gate refuses       → failure_window_active=True in gate context,
                                      execution blocked, confidence unchanged,
                                      window consumed and cleared by rejected path
        Cycle 3: EXECUTE + success  → confidence recovers from post-failure value
    """

    def test_failure_window_opens_blocks_then_clears(self) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        a = _agent(gate=gate, goal_completion_threshold=0.99)

        # Cycle 1: executed, critic returns failure → window opens
        a.seed("task1")
        _run_cycle(a, agent_mod,
                   gate_mode=ExecutionMode.EXECUTE,
                   critic_category="failure",
                   critic_severity=0.8)

        self.assertTrue(a._confidence._last_outcome_was_failure)
        confidence_after_failure = a._confidence.get_value()

        # Cycle 2: gate refuses — failure_window_active=True must reach the gate,
        # execution must be blocked, confidence must not change numerically.
        # Per ADR-023: the rejected path consumes and clears the failure window.
        a.seed("task2")
        _, gate_kwargs, mock_auth = _run_refusal_cycle(a, agent_mod, gate)

        self.assertTrue(gate_kwargs["context"].failure_window_active)
        mock_auth.assert_not_called()
        self.assertEqual(a._confidence.get_value(), confidence_after_failure)
        # Window is consumed and cleared by the rejected cycle (ADR-023)
        self.assertFalse(a._confidence._last_outcome_was_failure)

        # Cycle 3: gate permits, success → confidence recovers upward
        a.seed("task3")
        _run_cycle(a, agent_mod,
                   gate_mode=ExecutionMode.EXECUTE,
                   critic_category="success",
                   critic_severity=0.1)

        self.assertGreater(a._confidence.get_value(), confidence_after_failure)


class TestFailurePartialRecoverySequence(unittest.TestCase):
    """Confidence trajectory across failure → partial → success.

    Confidence runs real. Drift machinery is patched as orthogonal.

    Sequence:
        Cycle 1: failure  → confidence drops, window opens
        Cycle 2: partial  → failure window still active;
                            confidence must not move upward
                            (failure window restricts upward movement on partial
                            outcomes — locked semantic per ADR-021–025)
        Cycle 3: success  → confidence recovers upward
    """

    def test_confidence_trajectory_across_failure_partial_success(self) -> None:
        import eck.agent as agent_mod

        gate = MagicMock(spec=PolicyGate)
        a = _agent(gate=gate, goal_completion_threshold=0.99)

        confidence_initial = a._confidence.get_value()

        # Cycle 1: failure → confidence drops, window opens
        a.seed("task1")
        _run_cycle(a, agent_mod,
                   gate_mode=ExecutionMode.EXECUTE,
                   critic_category="failure",
                   critic_severity=0.8)

        confidence_after_failure = a._confidence.get_value()
        self.assertLess(confidence_after_failure, confidence_initial)
        self.assertTrue(a._confidence._last_outcome_was_failure)

        # Cycle 2: partial outcome with failure window still active.
        # Per ADR-021–025, the failure window restricts upward movement —
        # confidence must not increase from its post-failure value.
        partial_structure = PartialStructure(
            collapse_status="unresolved",
            conflict_kind=ConflictKind.EVIDENCE_CONFLICT,
            conflict_footprint=frozenset({ConflictLocus.LOCAL}),
        )
        gate.evaluate.return_value = _gate_decision(ExecutionMode.EXECUTE)
        a.seed("task2")
        with patch.object(agent_mod, "propose_execution",
                          return_value=_mock_proposal()), \
             patch.object(agent_mod, "authorize_and_perform",
                          return_value=_result_performed()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=(
                              make_critic_outcome(
                                  category="partial",
                                  severity=0.4,
                                  feedback="partial",
                              ),
                              partial_structure,
                          )), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "get_policy_mode",
                          return_value=PolicyMode.NORMAL), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "record_feasibility"), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        confidence_after_partial = a._confidence.get_value()
        self.assertLessEqual(confidence_after_partial, confidence_after_failure)

        # Cycle 3: success → confidence recovers upward
        a.seed("task3")
        _run_cycle(a, agent_mod,
                   gate_mode=ExecutionMode.EXECUTE,
                   critic_category="success",
                   critic_severity=0.1)

        self.assertGreater(a._confidence.get_value(), confidence_after_partial)


class TestPolicyModeEscalationSequence(unittest.TestCase):
    """Policy mode advances irreversibly — retreat attempts are ignored.

    Real policy mode state on the agent. Drift recommendations are controlled
    via patched get_policy_mode. Proposal/execution/critic surfaces are patched
    to make the sequence deterministic.

    Sequence:
        Cycle 1: recommend GUIDED    → mode advances to GUIDED
        Cycle 2: recommend GUIDED    → mode stays GUIDED
        Cycle 3: recommend NORMAL    → retreat ignored, mode stays GUIDED
        Cycle 4: recommend ENFORCED  → mode advances to ENFORCED
        Cycle 5: recommend NORMAL    → retreat ignored, mode stays ENFORCED
    """

    def test_policy_mode_never_retreats_once_advanced(self) -> None:
        import eck.agent as agent_mod

        a = _agent(policy_mode=PolicyMode.NORMAL, goal_completion_threshold=0.99)

        modes_seen: list[PolicyMode] = []

        policy_sequence = [
            PolicyMode.GUIDED,
            PolicyMode.GUIDED,
            PolicyMode.NORMAL,    # retreat attempt
            PolicyMode.ENFORCED,
            PolicyMode.NORMAL,    # retreat attempt
        ]

        for i, recommended_mode in enumerate(policy_sequence):
            a.seed(f"task{i}")
            with patch.object(agent_mod, "propose_execution", return_value=None), \
                 patch.object(agent_mod, "generate_prediction", return_value="pred"), \
                 patch.object(agent_mod, "critic_evaluate",
                              return_value=_critic("deferred")), \
                 patch.object(agent_mod, "generate_subtasks", return_value=[]), \
                 patch.object(a.drift, "get_policy_mode",
                              return_value=recommended_mode), \
                 patch.object(a.drift, "snapshot", return_value=_snap()):
                a.step()
            modes_seen.append(a.current_policy_mode)

        self.assertEqual(modes_seen[0], PolicyMode.GUIDED)
        self.assertEqual(modes_seen[1], PolicyMode.GUIDED)
        self.assertEqual(modes_seen[2], PolicyMode.GUIDED)    # retreat ignored
        self.assertEqual(modes_seen[3], PolicyMode.ENFORCED)
        self.assertEqual(modes_seen[4], PolicyMode.ENFORCED)  # retreat ignored


class TestHaltIrreversibility(unittest.TestCase):
    """Once the agent reaches HALT, subsequent step() calls return False.

    Drives agent to HALT via drift recommendation, then proves that seams
    are never reached on subsequent cycles regardless of queue contents.
    """

    def test_halt_is_irreversible_across_subsequent_steps(self) -> None:
        import eck.agent as agent_mod

        a = _agent(policy_mode=PolicyMode.NORMAL, goal_completion_threshold=0.99)

        # Drive to HALT
        a.seed("task1")
        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic("deferred")), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "get_policy_mode",
                          return_value=PolicyMode.HALT), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            result = a.step()

        self.assertIs(result, False)
        self.assertEqual(a.current_policy_mode, PolicyMode.HALT)

        # Subsequent cycles must return False immediately — no seam reached
        for i in range(3):
            a.seed(f"recovery_attempt_{i}")

            def raise_if_called(*_: Any, **__: Any) -> None:
                raise AssertionError("No seams should be called after HALT")

            with patch.object(agent_mod, "propose_execution", raise_if_called), \
                 patch.object(agent_mod, "authorize_and_perform", raise_if_called), \
                 patch.object(agent_mod, "generate_prediction", raise_if_called), \
                 patch.object(agent_mod, "critic_evaluate", raise_if_called), \
                 patch.object(agent_mod, "generate_subtasks", raise_if_called):
                result = a.step()

            self.assertIs(result, False)


if __name__ == "__main__":
    unittest.main()

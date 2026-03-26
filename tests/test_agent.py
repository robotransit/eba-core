# tests/test_agent.py
"""Tests for ECKAgent orchestration loop."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from eck.agent import ECKAgent
from eck.config import ECKConfig, PolicyMode
from eck.queue import QueueFullError
from eck.types import make_critic_outcome


def dummy_llm(prompt: str) -> str:
    """Deterministic stub — always returns NO."""
    return "NO"


def _make_critic_outcome_success():
    """Return a CriticOutcome representing a successful evaluation."""
    return make_critic_outcome(category="success", severity=0.1, feedback="ok")


def _make_critic_outcome_failure():
    """Return a CriticOutcome representing a failed evaluation."""
    return make_critic_outcome(category="failure", severity=0.8, feedback="fail")


class TestAgentHaltAndDeferred(unittest.TestCase):
    """Policy mode enforcement — HALT and ENFORCED/DEFERRED paths."""

    def test_halt_at_start_stops_step(self) -> None:
        """HALT mode → step() returns False immediately, no execution."""
        import eck.agent as agent_mod

        a = ECKAgent(
            objective="Test HALT",
            llm_call=dummy_llm,
            config=ECKConfig(policy_mode=PolicyMode.HALT),
        )

        def raise_if_called(*_, **__):
            raise AssertionError("No actions should be called in HALT")

        with patch.object(agent_mod, "execute_task", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called), \
             patch.object(agent_mod, "generate_prediction", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate", raise_if_called):
            self.assertIs(a.step(), False)

    def test_enforced_deferred_no_execution_no_subtasks(self) -> None:
        """ENFORCED + DEFERRED → no execution, no subtask generation."""
        import eck.agent as agent_mod

        config = ECKConfig(policy_mode=PolicyMode.ENFORCED)
        agent = ECKAgent(
            objective="Test agent loop",
            llm_call=dummy_llm,
            config=config,
        )
        agent.seed("Seed task")

        received = []

        def assert_deferred_and_false(policy_mode, breadth):
            received.append(breadth)
            return False

        def raise_if_called(*_, **__):
            raise AssertionError("Execution or subtask generation should not be called")

        with patch.object(agent.drift, "get_policy_mode", return_value=PolicyMode.ENFORCED), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", side_effect=assert_deferred_and_false), \
             patch.object(agent_mod, "execute_task", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"):
            result = agent.step()

        self.assertIs(result, True)
        self.assertEqual(len(agent.queue), 0)


class TestQueueEmptyBehaviour(unittest.TestCase):
    """Queue empty path — step returns False without calling seams."""

    def _agent(self) -> ECKAgent:
        return ECKAgent(
            objective="Test",
            llm_call=dummy_llm,
            config=ECKConfig(policy_mode=PolicyMode.ENFORCED),
        )

    def test_queue_empty_step_returns_false(self) -> None:
        """Empty queue → step() returns False."""
        agent = self._agent()
        self.assertIs(agent.step(), False)

    def test_queue_empty_no_seam_calls(self) -> None:
        """Empty queue → no prediction, critic, execution, or subtask calls."""
        import eck.agent as agent_mod

        agent = self._agent()

        def raise_if_called(*_, **__):
            raise AssertionError("No seams should be called when queue is empty")

        with patch.object(agent_mod, "generate_prediction", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate", raise_if_called), \
             patch.object(agent_mod, "execute_task", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called):
            self.assertIs(agent.step(), False)


class TestEnforcedFullExecution(unittest.TestCase):
    """ENFORCED + FULL breadth → execution and subtask generation permitted."""

    def test_enforced_full_execution_and_subtasks_allowed(self) -> None:
        import eck.agent as agent_mod

        config = ECKConfig(policy_mode=PolicyMode.ENFORCED)
        agent = ECKAgent(
            objective="Test agent loop",
            llm_call=dummy_llm,
            config=config,
        )
        agent.seed("Seed task")

        calls = []

        def allow(policy_mode, breadth):
            calls.append((policy_mode, breadth))
            return True

        executed = {"ok": False}

        def exec_task(*_, **__):
            executed["ok"] = True
            return "outcome"

        with patch.object(agent.drift, "get_policy_mode", return_value=PolicyMode.ENFORCED), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", side_effect=allow), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(agent_mod, "execute_task", side_effect=exec_task), \
             patch.object(agent_mod, "generate_subtasks", return_value=["sub"]):
            result = agent.step()

        self.assertIs(result, True)
        self.assertTrue(executed["ok"])

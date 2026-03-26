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


class TestPolicyModeIrreversibility(unittest.TestCase):
    """Policy mode upgrades are irreversible — no downgrade permitted."""

    def test_policy_mode_upgrades_are_irreversible(self) -> None:
        import eck.agent as agent_mod

        a = ECKAgent(
            objective="Test upgrades",
            llm_call=dummy_llm,
            config=ECKConfig(policy_mode=PolicyMode.NORMAL),
        )
        self.assertEqual(a.current_policy_mode, PolicyMode.NORMAL)

        modes = iter([PolicyMode.GUIDED, PolicyMode.NORMAL, PolicyMode.ENFORCED])

        with patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", return_value=False), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(a.drift, "get_policy_mode", side_effect=modes):

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

        a = ECKAgent(
            objective="Test policy sync",
            llm_call=dummy_llm,
            config=ECKConfig(policy_mode=PolicyMode.NORMAL),
        )

        def assert_sync(expected: PolicyMode) -> None:
            self.assertEqual(a.current_policy_mode, expected)
            self.assertEqual(a.config.policy_mode, expected)
            self.assertEqual(a.drift.config.policy_mode, expected)

        assert_sync(PolicyMode.NORMAL)

        with patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", return_value=False), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()):

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
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            goal_completion_threshold=0.0,
        )
        a = ECKAgent(objective="Test goal", llm_call=dummy_llm, config=config)

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "severe", return_value=False), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]):
            a.seed("x")
            result = a.step()

        self.assertIs(result, False)

    def test_goal_completion_not_satisfied_when_confidence_low(self) -> None:
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            goal_completion_threshold=0.99,
        )
        a = ECKAgent(objective="Test goal", llm_call=dummy_llm, config=config)

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "severe", return_value=False), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]):
            a.seed("x")
            result = a.step()

        self.assertIs(result, True)

    def test_goal_completion_not_satisfied_when_subtasks_suppressed(self) -> None:
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            goal_completion_threshold=0.0,
        )
        a = ECKAgent(objective="Test goal", llm_call=dummy_llm, config=config)

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="DEFERRED"), \
             patch.object(agent_mod, "should_execute", return_value=False), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()):
            a.seed("x")
            result = a.step()

        self.assertIs(result, True)


class TestDriftHalts(unittest.TestCase):
    """Drift-triggered halt paths — streak halt and severe instability via periodic guard."""

    def test_drift_streak_halt_returns_false(self) -> None:
        """step() returns False when drift_streak exceeds max_drift_streak."""
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            max_drift_streak=2,
        )
        a = ECKAgent(objective="Test drift halt", llm_call=dummy_llm, config=config)
        a.seed("task")
        a.drift.drift_streak = 3

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_failure()), \
             patch.object(a.drift, "record_error", return_value=True), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]):
            result = a.step()

        self.assertIs(result, False)

    def test_severe_instability_halt_returns_false(self) -> None:
        """step() returns False when periodic guard detects severe instability."""
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            guard_interval=1,
            goal_completion_threshold=0.99,
        )
        a = ECKAgent(objective="Test severe halt", llm_call=dummy_llm, config=config)
        a.seed("task")

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_failure()), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "snapshot",
                          return_value={
                              "drift_streak": 0,
                              "total_drift_events": 0,
                              "last_error_z": 0.0,
                              "numeric_bias": 1.0,
                              "feasibility_sample_count": 0,
                              "numeric_success_rate": None,
                              "severe": True,
                          }), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]):
            result = a.step()

        self.assertIs(result, False)

    def test_periodic_guard_severe_halts_agent(self) -> None:
        """Periodic guard returns False when snapshot severe is True."""
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            guard_interval=1,
            goal_completion_threshold=0.99,
        )
        a = ECKAgent(objective="Test periodic guard", llm_call=dummy_llm, config=config)
        a.seed("task")

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "severe", return_value=False), \
             patch.object(a.drift, "snapshot",
                          return_value={
                              "drift_streak": 0,
                              "total_drift_events": 0,
                              "last_error_z": 0.0,
                              "numeric_bias": 1.0,
                              "feasibility_sample_count": 0,
                              "numeric_success_rate": None,
                              "severe": True,
                          }), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]):
            result = a.step()

        self.assertIs(result, False)


class TestGuardIntervalInvariant(unittest.TestCase):
    """guard_interval bounds the maximum cycles before a severe halt."""

    def test_severe_halt_within_guard_interval_cycles(self) -> None:
        """Severe instability halts within at most guard_interval cycles."""
        import eck.agent as agent_mod

        guard_interval = 3
        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            guard_interval=guard_interval,
            goal_completion_threshold=0.99,
        )
        a = ECKAgent(objective="Test guard interval", llm_call=dummy_llm, config=config)

        halt_cycle = None
        for i in range(guard_interval + 1):
            a.seed(f"task_{i}")
            with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
                 patch.object(agent_mod, "generate_prediction", return_value="pred"), \
                 patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
                 patch.object(agent_mod, "should_execute", return_value=True), \
                 patch.object(agent_mod, "execute_task", return_value="outcome"), \
                 patch.object(agent_mod, "critic_evaluate",
                              return_value=_make_critic_outcome_failure()), \
                 patch.object(a.drift, "record_error", return_value=False), \
                 patch.object(a.drift, "snapshot",
                              return_value={
                                  "drift_streak": 0,
                                  "total_drift_events": 0,
                                  "last_error_z": 0.0,
                                  "numeric_bias": 1.0,
                                  "feasibility_sample_count": 0,
                                  "numeric_success_rate": None,
                                  "severe": True,
                              }), \
                 patch.object(agent_mod, "generate_subtasks", return_value=[]):
                if not a.step():
                    halt_cycle = i + 1
                    break

        self.assertIsNotNone(halt_cycle, "Agent did not halt within guard_interval cycles")
        self.assertLessEqual(halt_cycle, guard_interval)


class TestSubtaskGenerationLogging(unittest.TestCase):
    """Subtask generation logging path — step 6 completion log."""

    def test_subtask_generation_log_reached(self) -> None:
        """Step 6 subtask generation log fires when subtasks are generated."""
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            goal_completion_threshold=0.99,
            guard_interval=100,
        )
        a = ECKAgent(objective="Test subtask log", llm_call=dummy_llm, config=config)
        a.seed("task")

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "severe", return_value=False), \
             patch.object(agent_mod, "generate_subtasks",
                          return_value=["sub1", "sub2"]):
            result = a.step()

        self.assertIs(result, True)
        self.assertEqual(len(a.queue), 2)


class TestQueueFullErrorHandling(unittest.TestCase):
    """QueueFullError during subtask push is handled gracefully."""

    def test_queue_full_error_during_subtask_push_continues(self) -> None:
        """QueueFullError during subtask push logs warning and breaks loop."""
        import eck.agent as agent_mod

        config = ECKConfig(
            policy_mode=PolicyMode.NORMAL,
            max_queue_size=1,
            goal_completion_threshold=0.99,
        )
        a = ECKAgent(objective="Test queue full", llm_call=dummy_llm, config=config)
        a.seed("task")

        with patch.object(a.drift, "get_policy_mode", return_value=PolicyMode.NORMAL), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "get_recommended_breadth", return_value="FULL"), \
             patch.object(agent_mod, "should_execute", return_value=True), \
             patch.object(agent_mod, "execute_task", return_value="outcome"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_make_critic_outcome_success()), \
             patch.object(a.drift, "record_error", return_value=False), \
             patch.object(a.drift, "severe", return_value=False), \
             patch.object(agent_mod, "generate_subtasks",
                          return_value=["sub1", "sub2", "sub3"]):
            result = a.step()

        self.assertIs(result, True)


class TestTaskLifecycle(unittest.TestCase):
    """Task lifecycle recording is absent pending v0.2.0 audit layer."""

    def test_task_lifecycle_recording_absent(self) -> None:
        from eck.memory import MemoryRetrieval
        memory = MemoryRetrieval(enabled=False)
        self.assertFalse(hasattr(memory, "record"))


if __name__ == "__main__":
    unittest.main()

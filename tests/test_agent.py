import pytest

from eck.agent import ECKAgent
from eck.config import ECKConfig, PolicyMode
from eck.task import TaskState


def dummy_llm(prompt: str) -> str:
    """Deterministic stub for agent loop tests."""
    # Ensure goal check never returns YES
    return "NO"


@pytest.fixture
def agent():
    config = ECKConfig(policy_mode=PolicyMode.ENFORCED)
    return ECKAgent(
        objective="Test agent loop",
        llm_call=dummy_llm,
        config=config,
    )


def test_enforced_deferred_no_execution_no_subtasks(agent, monkeypatch):
    """ENFORCED + DEFERRED → no execution, no subtask generation."""
    import eck.agent as agent_mod

    agent.seed("Seed task")

    # Lock drift recommendation to ENFORCED (prevents upgrade before should_execute)
    monkeypatch.setattr(agent.drift, "get_policy_mode", lambda: PolicyMode.ENFORCED)

    # Force DEFERRED breadth
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "DEFERRED")

    received_breadth = []

    def assert_deferred_and_false(policy_mode, breadth):
        received_breadth.append(breadth)
        assert breadth == "DEFERRED"
        assert policy_mode == PolicyMode.ENFORCED
        return False

    monkeypatch.setattr(agent_mod, "should_execute", assert_deferred_and_false)

    def raise_if_called(*args, **kwargs):
        raise AssertionError("Execution or subtask generation should not be called")

    monkeypatch.setattr(agent_mod, "execute_task", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_subtasks", raise_if_called)

    assert agent.step() is True
    assert received_breadth == ["DEFERRED", "DEFERRED"]
    assert len(agent.queue) == 0


def test_halt_at_start_stops_step(monkeypatch):
    """HALT mode → step() returns False, no execution/generation."""
    import eck.agent as agent_mod

    halt_agent = ECKAgent(
        objective="Test HALT",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.HALT),
    )

    def raise_if_called(*args, **kwargs):
        raise AssertionError("No actions should be called in HALT")

    monkeypatch.setattr(agent_mod, "execute_task", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_subtasks", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_prediction", raise_if_called)
    monkeypatch.setattr(agent_mod, "critic_evaluate", raise_if_called)

    assert halt_agent.step() is False


def test_queue_empty_step_returns_false(agent):
    """Empty queue → step() returns False (no loop iterations)."""
    agent.queue.clear()
    assert len(agent.queue) == 0
    assert agent.step() is False


def test_queue_empty_no_seam_calls(agent, monkeypatch):
    """Queue empty → step() returns False and no LLM/seams are called."""
    import eck.agent as agent_mod

    agent.queue.clear()
    assert len(agent.queue) == 0

    def raise_if_called(*args, **kwargs):
        raise AssertionError("No seams should be called when queue is empty")

    monkeypatch.setattr(agent_mod, "generate_prediction", raise_if_called)
    monkeypatch.setattr(agent_mod, "critic_evaluate", raise_if_called)
    monkeypatch.setattr(agent_mod, "execute_task", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_subtasks", raise_if_called)

    assert agent.step() is False


def test_enforced_full_execution_and_subtasks_allowed(agent, monkeypatch):
    """ENFORCED + FULL → execution happens and subtasks are allowed."""
    import eck.agent as agent_mod

    agent.seed("Seed task")

    monkeypatch.setattr(agent.drift, "get_policy_mode", lambda: PolicyMode.ENFORCED)
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "FULL")

    should_execute_calls = []

    def assert_full_and_true(policy_mode, breadth):
        should_execute_calls.append((policy_mode, breadth))
        assert policy_mode == PolicyMode.ENFORCED
        assert breadth == "FULL"
        return True

    monkeypatch.setattr(agent_mod, "should_execute", assert_full_and_true)

    # Keep the rest deterministic / low-coupling
    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "", 0.0))

    executed = {"called": False}

    def mark_executed(*args, **kwargs):
        executed["called"] = True
        return "outcome"

    monkeypatch.setattr(agent_mod, "execute_task", mark_executed)

    subtasks_generated = {"called": False}

    def mark_subtasks(*args, **kwargs):
        subtasks_generated["called"] = True
        return ["sub1"]

    monkeypatch.setattr(agent_mod, "generate_subtasks", mark_subtasks)

    assert agent.step() is True

    assert executed["called"] is True
    assert subtasks_generated["called"] is True
    assert len(agent.queue) > 0

    assert should_execute_calls == [
        (PolicyMode.ENFORCED, "FULL"),
        (PolicyMode.ENFORCED, "FULL"),
    ]


def test_policy_mode_upgrades_are_irreversible(monkeypatch):
    """
    Irreversible upgrade rule:
    if drift recommends a higher mode, agent upgrades;
    if drift later recommends a lower mode, agent must NOT downgrade.
    Also asserts drift.config sync after upgrade.
    """
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test irreversible upgrades",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    # Initial sync check
    assert a.drift.config is a.config

    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "DEFERRED")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: False)
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "", 0.0))

    monkeypatch.setattr(a.drift, "record_error", lambda *a, **k: False)
    monkeypatch.setattr(a.drift, "record_feasibility", lambda *a, **k: None)
    monkeypatch.setattr(a.drift, "register_drift", lambda *a, **k: None)
    monkeypatch.setattr(a.drift, "clear_streak", lambda *a, **k: None)

    seq = iter([PolicyMode.GUIDED, PolicyMode.ENFORCED, PolicyMode.NORMAL])
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: next(seq))

    assert a.current_policy_mode == PolicyMode.NORMAL

    a.seed("t1")
    assert a.step() is True
    assert a.current_policy_mode == PolicyMode.GUIDED
    assert a.drift.config is a.config

    a.seed("t2")
    assert a.step() is True
    assert a.current_policy_mode == PolicyMode.ENFORCED
    assert a.drift.config is a.config

    a.seed("t3")
    assert a.step() is True
    assert a.current_policy_mode == PolicyMode.ENFORCED
    assert a.drift.config is a.config


def test_goal_check_yes_stops_step_early(monkeypatch):
    """If the goal-check prompt returns YES, step() stops early (returns False)."""
    import eck.agent as agent_mod

    seen = {"goal_check_prompt": False}

    def goal_yes_llm(prompt: str) -> str:
        # Match exact phrase from GOAL_ACHIEVED_PROMPT
        if 'Answer ONLY "YES" or "NO"' in prompt:
            seen["goal_check_prompt"] = True
            assert "Objective: Test objective" in prompt
            assert "Latest result: outcome" in prompt
            return "YES"
        return "NO"

    a = ECKAgent(
        objective="Test objective",
        llm_call=goal_yes_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    # Keep the step deterministic and avoid other early exits
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.NORMAL)
    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "FULL")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: True)
    monkeypatch.setattr(agent_mod, "execute_task", lambda *a, **k: "outcome")
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "ok", 0.0))
    monkeypatch.setattr(agent_mod, "generate_subtasks", lambda *a, **k: [])

    a.seed("Seed task")
    assert a.step() is False
    assert seen["goal_check_prompt"] is True


def test_task_lifecycle_recording_in_one_step(monkeypatch):
    """
    Single task_id emits lifecycle record() calls:
    CREATED (seed) → PREDICTED → EXECUTED → final.
    (WorldModel stores latest-only, so we spy on record() calls instead.)
    """
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test lifecycle",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    # Force deterministic success path
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.NORMAL)
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "FULL")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: True)
    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "prediction")
    monkeypatch.setattr(agent_mod, "execute_task", lambda *a, **k: "outcome")
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "good", 0.0))
    monkeypatch.setattr(agent_mod, "generate_subtasks", lambda *a, **k: [])

    # Spy on record() calls
    calls = []
    real_record = a.memory.record

    def record_spy(*, task_id, task_text, prediction, outcome, success, feedback, state, metadata=None):
        calls.append(
            {
                "task_id": task_id,
                "task_text": task_text,
                "prediction": prediction,
                "outcome": outcome,
                "success": success,
                "feedback": feedback,
                "state": state,
            }
        )
        return real_record(
            task_id=task_id,
            task_text=task_text,
            prediction=prediction,
            outcome=outcome,
            success=success,
            feedback=feedback,
            state=state,
            metadata=metadata,
        )

    monkeypatch.setattr(a.memory, "record", record_spy)

    task_text = "Test lifecycle task"
    a.seed(task_text)

    task_id = a.queue.as_list()[0]["id"]
    assert len(calls) == 1
    assert calls[0]["task_id"] == task_id
    assert calls[0]["state"] == TaskState.CREATED

    assert a.step() is True

    # After step(): +3 calls (PREDICTED, EXECUTED, final)
    assert [c["state"] for c in calls] == [
        TaskState.CREATED,
        TaskState.PREDICTED,
        TaskState.EXECUTED,
        TaskState.SUCCEEDED,
    ]

    final = calls[-1]
    assert final["task_id"] == task_id
    assert final["task_text"] == task_text
    assert final["prediction"] == "prediction"
    assert final["outcome"] == "outcome"
    assert final["success"] is True
    assert final["feedback"] == "good"

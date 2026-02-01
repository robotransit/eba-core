import pytest

from eck.agent import ECKAgent
from eck.config import ECKConfig, PolicyMode
from eck.task import TaskState


def dummy_llm(prompt: str) -> str:
    """Deterministic stub for agent loop tests."""
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

    monkeypatch.setattr(agent.drift, "get_policy_mode", lambda: PolicyMode.ENFORCED)
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "DEFERRED")

    received = []

    def assert_deferred_and_false(policy_mode, breadth):
        received.append(breadth)
        assert policy_mode == PolicyMode.ENFORCED
        assert breadth == "DEFERRED"
        return False

    monkeypatch.setattr(agent_mod, "should_execute", assert_deferred_and_false)

    def raise_if_called(*_, **__):
        raise AssertionError("Execution or subtask generation should not be called")

    monkeypatch.setattr(agent_mod, "execute_task", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_subtasks", raise_if_called)

    assert agent.step() is True
    assert received == ["DEFERRED", "DEFERRED"]
    assert len(agent.queue) == 0


def test_halt_at_start_stops_step(monkeypatch):
    """HALT mode → step() returns False, no execution/generation."""
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test HALT",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.HALT),
    )

    def raise_if_called(*_, **__):
        raise AssertionError("No actions should be called in HALT")

    monkeypatch.setattr(agent_mod, "execute_task", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_subtasks", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_prediction", raise_if_called)
    monkeypatch.setattr(agent_mod, "critic_evaluate", raise_if_called)

    assert a.step() is False


def test_queue_empty_step_returns_false(agent):
    agent.queue.clear()
    assert agent.step() is False


def test_queue_empty_no_seam_calls(agent, monkeypatch):
    import eck.agent as agent_mod

    agent.queue.clear()

    def raise_if_called(*_, **__):
        raise AssertionError("No seams should be called when queue is empty")

    monkeypatch.setattr(agent_mod, "generate_prediction", raise_if_called)
    monkeypatch.setattr(agent_mod, "critic_evaluate", raise_if_called)
    monkeypatch.setattr(agent_mod, "execute_task", raise_if_called)
    monkeypatch.setattr(agent_mod, "generate_subtasks", raise_if_called)

    assert agent.step() is False


def test_enforced_full_execution_and_subtasks_allowed(agent, monkeypatch):
    import eck.agent as agent_mod

    agent.seed("Seed task")

    monkeypatch.setattr(agent.drift, "get_policy_mode", lambda: PolicyMode.ENFORCED)
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "FULL")

    calls = []

    def allow(policy_mode, breadth):
        calls.append((policy_mode, breadth))
        return True

    monkeypatch.setattr(agent_mod, "should_execute", allow)
    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "", 0.0))

    executed = {"ok": False}

    def exec_task(*_, **__):
        executed["ok"] = True
        return "outcome"

    monkeypatch.setattr(agent_mod, "execute_task", exec_task)
    monkeypatch.setattr(agent_mod, "generate_subtasks", lambda *a, **k: ["sub"])

    assert agent.step() is True
    assert executed["ok"] is True
    assert calls == [(PolicyMode.ENFORCED, "FULL"), (PolicyMode.ENFORCED, "FULL")]


def test_policy_mode_upgrades_are_irreversible(monkeypatch):
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test upgrades",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    assert a.current_policy_mode == PolicyMode.NORMAL
    assert a.current_policy_mode == a.config.policy_mode
    assert a.current_policy_mode == a.drift.config.policy_mode

    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "DEFERRED")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: False)
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "", 0.0))

    seq = iter([PolicyMode.GUIDED, PolicyMode.NORMAL, PolicyMode.ENFORCED])
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: next(seq))

    a.seed("t1")
    a.step()
    assert a.current_policy_mode == PolicyMode.GUIDED

    a.seed("t2")
    a.step()
    assert a.current_policy_mode == PolicyMode.GUIDED  # no downgrade

    a.seed("t3")
    a.step()
    assert a.current_policy_mode == PolicyMode.ENFORCED


def test_policy_mode_single_sourced_no_split_brain(monkeypatch):
    """agent.current_policy_mode, config, and drift.config must never diverge."""
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test policy sync",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    def assert_sync(expected):
        assert a.current_policy_mode == expected
        assert a.config.policy_mode == expected
        assert a.drift.config.policy_mode == expected

    assert_sync(PolicyMode.NORMAL)

    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "DEFERRED")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: False)
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "", 0.0))

    # Upgrade to GUIDED
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.GUIDED)
    a.seed("t1")
    a.step()
    assert_sync(PolicyMode.GUIDED)

    # Downgrade attempt ignored
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.NORMAL)
    a.seed("t2")
    a.step()
    assert_sync(PolicyMode.GUIDED)

    # Upgrade to ENFORCED
    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.ENFORCED)
    a.seed("t3")
    a.step()
    assert_sync(PolicyMode.ENFORCED)


def test_goal_check_yes_stops_step_early(monkeypatch):
    import eck.agent as agent_mod

    seen = {"hit": False}

    def yes_llm(prompt: str) -> str:
        if 'Answer ONLY "YES" or "NO"' in prompt:
            seen["hit"] = True
            return "YES"
        return "NO"

    a = ECKAgent(
        objective="Test goal",
        llm_call=yes_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.NORMAL)
    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "pred")
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "FULL")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: True)
    monkeypatch.setattr(agent_mod, "execute_task", lambda *a, **k: "outcome")
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "ok", 0.0))
    monkeypatch.setattr(agent_mod, "generate_subtasks", lambda *a, **k: [])

    a.seed("x")
    assert a.step() is False
    assert seen["hit"] is True


def test_task_lifecycle_recording_in_one_step(monkeypatch):
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test lifecycle",
        llm_call=dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.NORMAL),
    )

    monkeypatch.setattr(a.drift, "get_policy_mode", lambda: PolicyMode.NORMAL)
    monkeypatch.setattr(agent_mod, "get_recommended_breadth", lambda *a, **k: "FULL")
    monkeypatch.setattr(agent_mod, "should_execute", lambda *a, **k: True)
    monkeypatch.setattr(agent_mod, "generate_prediction", lambda *a, **k: "prediction")
    monkeypatch.setattr(agent_mod, "execute_task", lambda *a, **k: "outcome")
    monkeypatch.setattr(agent_mod, "critic_evaluate", lambda *a, **k: (True, "good", 0.0))
    monkeypatch.setattr(agent_mod, "generate_subtasks", lambda *a, **k: [])

    calls = []
    real = a.memory.record

    def spy(**kw):
        calls.append(kw)
        return real(**kw)

    monkeypatch.setattr(a.memory, "record", spy)

    a.seed("task")
    assert calls[0]["state"] == TaskState.CREATED

    a.step()
    assert [c["state"] for c in calls] == [
        TaskState.CREATED,
        TaskState.PREDICTED,
        TaskState.EXECUTED,
        TaskState.SUCCEEDED,
    ]

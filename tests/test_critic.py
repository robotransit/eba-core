import pytest

from eck.critic import critic_evaluate


def test_critic_valid_json_returns_expected_tuple():
    def good_llm(prompt: str) -> str:
        return '{"success": true, "feedback": "good"}'

    success, feedback, error = critic_evaluate(
        task_text="task",
        prediction="pred",
        result="outcome",
        objective="obj",
        llm_call=good_llm,
        enable_cross_validation=False,
    )
    assert success is True
    assert feedback == "good"
    assert error == 0.0


def test_critic_malformed_json_returns_pessimistic_failure():
    def bad_llm(prompt: str) -> str:
        return "not json"

    success, feedback, error = critic_evaluate(
        task_text="task",
        prediction="pred",
        result="outcome",
        objective="obj",
        llm_call=bad_llm,
        enable_cross_validation=False,
    )
    assert success is False
    assert feedback == "Parse failed - treated as non-success"
    assert error == 1.0


def test_critic_cross_validation_disagreement_returns_failure(caplog):
    calls = {"n": 0}

    def disagree_llm(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"success": true, "feedback": "yes"}'
        return '{"success": false, "feedback": "no"}'

    with caplog.at_level("WARNING"):
        success, feedback, error = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=disagree_llm,
            enable_cross_validation=True,
        )

    assert success is False
    assert "Consensus:" in feedback
    assert error == 1.0
    assert any("Critic disagreement detected" in r.message for r in caplog.records)


def test_critic_cross_validation_both_malformed_is_pessimistic_no_disagreement_warning(caplog):
    """
    If cross-validation is enabled and BOTH critic calls are malformed/unparseable,
    the result must be deterministic pessimistic failure, and must NOT log a
    "Critic disagreement detected" warning (because both parses agree on failure).
    """

    def bad_llm(prompt: str) -> str:
        return "not json"

    with caplog.at_level("WARNING"):
        success, feedback, error = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=bad_llm,
            enable_cross_validation=True,
        )

    assert success is False
    assert feedback == "Parse failed - treated as non-success | Consensus: False"
    assert error == 1.0

    # This case should emit JSON-parse-failed warnings, but NOT disagreement warnings.
    assert not any("Critic disagreement detected" in r.message for r in caplog.records)

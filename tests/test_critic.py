import pytest

from eck.critic import critic_evaluate


def test_critic_valid_json_returns_expected_tuple():
    def good_llm(prompt: str) -> str:
        return '{"success": true, "feedback": "good"}'

    success, feedback, severity = critic_evaluate(
        task_text="task",
        prediction="pred",
        result="outcome",
        objective="obj",
        llm_call=good_llm,
        enable_cross_validation=False,
    )

    assert success is True
    assert feedback == "good"
    assert severity == 0.0


def test_critic_malformed_json_returns_pessimistic_failure():
    """
    Malformed or unparseable critic output must deterministically
    result in pessimistic failure (success=False, severity=1.0).
    """
    def bad_llm(prompt: str) -> str:
        return "not json"

    success, feedback, severity = critic_evaluate(
        task_text="task",
        prediction="pred",
        result="outcome",
        objective="obj",
        llm_call=bad_llm,
        enable_cross_validation=False,
    )

    assert success is False
    assert severity == 1.0
    assert isinstance(feedback, str)
    assert feedback.strip() != ""
    assert any(w in feedback.lower() for w in ["parse", "json", "fail", "invalid", "error"])


def test_critic_cross_validation_disagreement_returns_failure(caplog):
    """
    When cross-validation is enabled and the two critic calls disagree
    (valid but conflicting parses), the result must be failure with
    severity=1.0 and a logged disagreement warning.
    """
    calls = {"n": 0}

    def disagree_llm(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"success": true, "feedback": "yes"}'
        return '{"success": false, "feedback": "no"}'

    with caplog.at_level("WARNING"):
        success, feedback, severity = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=disagree_llm,
            enable_cross_validation=True,
        )

    assert success is False
    assert severity == 1.0
    assert isinstance(feedback, str)
    assert "Consensus:" in feedback
    assert any("Critic disagreement detected" in r.message for r in caplog.records)


def test_critic_pessimism_on_parse_failure_cross_validation(caplog):
    """
    When cross-validation is enabled and BOTH critic calls are malformed/unparseable,
    the result must be deterministic pessimistic failure (success=False, severity=1.0).
    No "Critic disagreement detected" warning is expected — disagreement logic
    only applies to valid but conflicting parses.
    """
    critic_calls = {"n": 0}

    def malformed_llm(prompt: str) -> str:
        critic_calls["n"] += 1
        return "nonsense output"

    with caplog.at_level("WARNING"):
        success, feedback, severity = critic_evaluate(
            task_text="task",
            prediction="pred",
            result="outcome",
            objective="obj",
            llm_call=malformed_llm,
            enable_cross_validation=True,
        )

    assert critic_calls["n"] == 2  # both critics called
    assert success is False
    assert severity == 1.0
    assert isinstance(feedback, str)
    assert feedback.strip() != ""
    assert any(w in feedback.lower() for w in ["parse", "json", "fail", "invalid", "error"])

    # This case should emit JSON-parse-failed warnings, but NOT disagreement warnings.
    assert not any("Critic disagreement detected" in r.message for r in caplog.records)
    

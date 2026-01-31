import pytest

from eck.prediction import build_prediction_context, generate_prediction
from eck.memory import WorldModel
from eck.config import ECKConfig


@pytest.fixture
def memory():
    return WorldModel()


def test_build_prediction_context_disabled_returns_empty(memory):
    cfg = ECKConfig(enable_memory_retrieval=False)
    out = build_prediction_context("task", "obj", memory, cfg)
    assert out == ""


def test_build_prediction_context_enabled_no_hits_returns_empty(monkeypatch, memory):
    cfg = ECKConfig(enable_memory_retrieval=True)

    monkeypatch.setattr(memory, "retrieve_similar", lambda **kwargs: [])
    out = build_prediction_context("task", "obj", memory, cfg)
    assert out == ""


def test_build_prediction_context_includes_entries(monkeypatch, memory):
    cfg = ECKConfig(
        enable_memory_retrieval=True,
        memory_similarity_threshold=0.1,
        memory_retrieval_limit=5,
        prefer_negative_memory=True,
    )

    monkeypatch.setattr(
        memory,
        "retrieve_similar",
        lambda **kwargs: [
            {
                "task": "Past task",
                "state": "executed",
                "outcome": "Past outcome",
                "success": False,
                "feedback": "Past feedback",
            }
        ],
    )

    out = build_prediction_context("task", "obj", memory, cfg)
    assert out.startswith("Relevant past outcomes:")
    assert "Past task" in out
    assert "Past outcome" in out
    assert "Success: False" in out
    # Optional high-signal check: feedback should appear if present
    assert "Past feedback" in out


def test_generate_prediction_normalizes_whitespace(memory):
    cfg = ECKConfig(enable_memory_retrieval=False)

    def llm(prompt: str) -> str:
        return "  a   b \n c\t\t d  "

    pred = generate_prediction("task", "obj", llm, memory, cfg)
    assert pred == "a b c d"


def test_generate_prediction_empty_becomes_placeholder(memory):
    cfg = ECKConfig(enable_memory_retrieval=False)

    def llm(prompt: str) -> str:
        return "   \n\t  "

    pred = generate_prediction("task", "obj", llm, memory, cfg)
    assert pred == "(no prediction generated)"


def test_generate_prediction_truncates_to_max_length(memory):
    cfg = ECKConfig(enable_memory_retrieval=False)

    def llm(prompt: str) -> str:
        return "x" * 500

    pred = generate_prediction("task", "obj", llm, memory, cfg, max_length=200)
    assert len(pred) <= 203  # 200 + "..."
    assert pred.endswith("...")


def test_generate_prediction_includes_memory_context_in_prompt(monkeypatch, memory):
    cfg = ECKConfig(enable_memory_retrieval=True)

    monkeypatch.setattr(memory, "retrieve_similar", lambda **kwargs: [{"task": "T", "outcome": "O"}])

    seen = {"prompt": None}

    def llm(prompt: str) -> str:
        seen["prompt"] = prompt
        return "ok"

    _ = generate_prediction("task", "obj", llm, memory, cfg)
    assert seen["prompt"] is not None
    assert "Relevant past outcomes:" in seen["prompt"]
    assert "Predict the expected outcome" in seen["prompt"]


def test_memory_retrieval_gating_disabled_no_calls(monkeypatch, memory):
    """When enable_memory_retrieval=False, no retrieval methods are called."""
    cfg = ECKConfig(enable_memory_retrieval=False)

    def raise_if_called(*args, **kwargs):
        raise AssertionError("Memory retrieval should not be called when disabled")

    monkeypatch.setattr(memory, "retrieve_similar", raise_if_called)

    # Test direct context builder
    _ = build_prediction_context("task", "obj", memory, cfg)

    def llm(prompt: str) -> str:
        return "ok"

    # Test public entrypoint (generate_prediction)
    _ = generate_prediction("task", "obj", llm, memory, cfg)

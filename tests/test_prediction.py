# tests/test_prediction.py
"""Tests for prediction subsystem (ADR-026–028, ADR-032)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from eck.config import ECKConfig
from eck.memory import MemoryRetrieval
from eck.prediction import build_prediction_context, generate_prediction


class TestBuildPredictionContext(unittest.TestCase):
    """build_prediction_context delegates to MemoryRetrieval contract."""

    def setUp(self) -> None:
        self.cfg_disabled = ECKConfig(enable_memory_retrieval=False)
        self.cfg_enabled = ECKConfig(enable_memory_retrieval=True)

    def test_disabled_returns_empty_string(self) -> None:
        """When memory retrieval is disabled, context is always empty."""
        memory = MemoryRetrieval(enabled=False)
        result = build_prediction_context("task", "obj", memory, self.cfg_disabled)
        self.assertEqual(result, "")

    def test_disabled_no_retrieval_calls(self) -> None:
        """When disabled, retrieve() is never called."""
        memory = MemoryRetrieval(enabled=False)
        with patch.object(memory, "retrieve") as mock_retrieve:
            build_prediction_context("task", "obj", memory, self.cfg_disabled)
            mock_retrieve.assert_not_called()

    def test_enabled_empty_result_returns_empty_string(self) -> None:
        """When enabled but retrieval returns None, context is empty."""
        memory = MemoryRetrieval(enabled=True)
        with patch.object(memory, "retrieve", return_value=None):
            result = build_prediction_context("task", "obj", memory, self.cfg_enabled)
            self.assertEqual(result, "")

    def test_enabled_with_result_returns_formatted_block(self) -> None:
        """When enabled and retrieval returns integration, formatted_block is returned."""
        from eck.memory import RetrievalIntegration
        memory = MemoryRetrieval(enabled=True)
        fake_integration = RetrievalIntegration(
            formatted_block="=== BEGIN MEMORY CONTEXT ===\nsome content\n=== END MEMORY CONTEXT ===",
            item_count=1,
            context_length=60,
        )
        with patch.object(memory, "retrieve", return_value=fake_integration):
            result = build_prediction_context("task", "obj", memory, self.cfg_enabled)
            self.assertEqual(result, fake_integration.formatted_block)

    def test_embedding_model_passed_to_retrieve(self) -> None:
        """embedding_model is forwarded to memory.retrieve()."""
        memory = MemoryRetrieval(enabled=True)
        fake_model = object()
        with patch.object(memory, "retrieve", return_value=None) as mock_retrieve:
            build_prediction_context("task", "obj", memory, self.cfg_enabled, embedding_model=fake_model)
            mock_retrieve.assert_called_once_with(
                user_input="task",
                embedding_model=fake_model,
            )

    def test_config_disabled_overrides_enabled_memory(self) -> None:
        """Config disabled flag takes priority — no retrieve() call even if memory is enabled."""
        memory = MemoryRetrieval(enabled=True)
        with patch.object(memory, "retrieve") as mock_retrieve:
            result = build_prediction_context("task", "obj", memory, self.cfg_disabled)
            mock_retrieve.assert_not_called()
            self.assertEqual(result, "")


class TestGeneratePrediction(unittest.TestCase):
    """generate_prediction is pure — formats prompt, calls LLM, normalises result."""

    def setUp(self) -> None:
        self.memory = MemoryRetrieval(enabled=False)
        self.cfg = ECKConfig(enable_memory_retrieval=False)

    def _llm(self, response: str):
        def llm(prompt: str) -> str:
            return response
        return llm

    def test_normalizes_internal_whitespace(self) -> None:
        """Whitespace normalisation collapses multiples and removes newlines."""
        pred = generate_prediction(
            "task", "obj", self._llm("  a   b \n c\t\t d  "), self.memory, self.cfg
        )
        self.assertEqual(pred, "a b c d")

    def test_empty_response_becomes_placeholder(self) -> None:
        """Empty or whitespace-only LLM response returns placeholder string."""
        pred = generate_prediction(
            "task", "obj", self._llm("   \n\t  "), self.memory, self.cfg
        )
        self.assertEqual(pred, "(no prediction generated)")

    def test_truncates_to_max_length(self) -> None:
        """Predictions exceeding max_length are truncated with ellipsis."""
        pred = generate_prediction(
            "task", "obj", self._llm("x" * 500), self.memory, self.cfg,
            max_length=200,
        )
        self.assertLessEqual(len(pred), 203)
        self.assertTrue(pred.endswith("..."))

    def test_returns_string(self) -> None:
        """generate_prediction always returns a string."""
        pred = generate_prediction(
            "task", "obj", self._llm("some output"), self.memory, self.cfg
        )
        self.assertIsInstance(pred, str)

    def test_memory_context_injected_into_prompt(self) -> None:
        """When memory returns content, it appears in the prompt sent to LLM."""
        from eck.memory import RetrievalIntegration
        memory = MemoryRetrieval(enabled=True)
        cfg = ECKConfig(enable_memory_retrieval=True)
        fake_integration = RetrievalIntegration(
            formatted_block="=== BEGIN MEMORY CONTEXT ===\nfake context\n=== END MEMORY CONTEXT ===",
            item_count=1,
            context_length=60,
        )
        seen = {"prompt": None}

        def llm(prompt: str) -> str:
            seen["prompt"] = prompt
            return "ok"

        with patch.object(memory, "retrieve", return_value=fake_integration):
            generate_prediction("task", "obj", llm, memory, cfg)

        self.assertIsNotNone(seen["prompt"])
        self.assertIn("fake context", seen["prompt"])
        self.assertIn("Predict the expected outcome", seen["prompt"])

    def test_disabled_memory_no_retrieval_calls(self) -> None:
        """When disabled, retrieve() is never called during generate_prediction."""
        memory = MemoryRetrieval(enabled=True)
        with patch.object(memory, "retrieve") as mock_retrieve:
            generate_prediction(
                "task", "obj", self._llm("ok"), memory, self.cfg
            )
            mock_retrieve.assert_not_called()

    def test_prompt_identity_disabled_vs_enabled_empty(self) -> None:
        """
        Prompt is bit-for-bit identical whether retrieval is disabled
        or enabled but returns no context (ADR-026/027 equivalence).
        """
        memory_enabled = MemoryRetrieval(enabled=True)
        memory_disabled = MemoryRetrieval(enabled=False)
        cfg_enabled = ECKConfig(enable_memory_retrieval=True)
        cfg_disabled = ECKConfig(enable_memory_retrieval=False)

        prompts = []

        def spy_llm(prompt: str) -> str:
            prompts.append(prompt)
            return "fixed"

        with patch.object(memory_enabled, "retrieve", return_value=None):
            generate_prediction("task", "obj", spy_llm, memory_enabled, cfg_enabled)

        generate_prediction("task", "obj", spy_llm, memory_disabled, cfg_disabled)

        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[0], prompts[1])


if __name__ == "__main__":
    unittest.main()

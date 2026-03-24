# tests/test_similarity.py
"""Invariant tests for Similarity subsystem fallback (ADRs 031–032)."""

import unittest
from datetime import datetime
from unittest.mock import patch
import types

from eck.similarity import retrieve_similar, retrieve_scored
from eck.memory import TaskRecord
from eck.agent import ECKAgent
from eck.config import ECKConfig


class TestSimilarityCore(unittest.TestCase):
    """Core similarity behavior (ADR-031)."""

    def setUp(self) -> None:
        self.tasks = [
            TaskRecord(task_id=1, description="Task A", created_at=datetime(2025, 1, 1), completed=False),
            TaskRecord(task_id=2, description="Task B", created_at=datetime(2025, 1, 3), completed=True),
            TaskRecord(task_id=3, description="Task C", created_at=datetime(2025, 1, 2), completed=False),
        ]

    def test_retrieve_similar_returns_newest_first(self) -> None:
        """Core path returns newest-first ordering."""
        result = retrieve_similar(self.tasks, None, limit=3)
        ids = [r.task_id for r in result]
        self.assertEqual(ids, [2, 3, 1])  # 2025-01-03, 2025-01-02, 2025-01-01

    def test_retrieve_scored_returns_deterministic_scores(self) -> None:
        """Core path returns deterministic normalized scores (1.0, 2/3, 1/3 for limit=3)."""
        result = retrieve_scored(self.tasks, None, limit=3)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0][1], 1.0)
        self.assertAlmostEqual(result[1][1], 2.0 / 3.0)
        self.assertAlmostEqual(result[2][1], 1.0 / 3.0)

    def test_limit_zero_returns_empty(self) -> None:
        """limit <= 0 returns empty list/tuples."""
        self.assertEqual(retrieve_similar(self.tasks, None, 0), [])
        self.assertEqual(retrieve_scored(self.tasks, None, 0), [])

    def test_query_embedding_is_ignored_in_core_path(self) -> None:
        """Core path ignores query_embedding (ADR-031 fallback invariant)."""
        result1 = retrieve_similar(self.tasks, None, limit=3)
        result2 = retrieve_similar(self.tasks, "some totally different value", limit=3)
        self.assertEqual(result1, result2)

        scored1 = retrieve_scored(self.tasks, None, limit=3)
        scored2 = retrieve_scored(self.tasks, "different", limit=3)
        self.assertEqual(scored1, scored2)


class TestAgentEmbeddingFallback(unittest.TestCase):
    """ADR-032 silent atomic fallback invariants at ECKAgent construction."""

    def test_enable_embeddings_false_leaves_model_none(self) -> None:
        """When enable_embeddings=False, _embedding_model is None."""
        config = ECKConfig(enable_embeddings=False)
        agent = ECKAgent(objective="test", llm_call=lambda x: "dummy", config=config)
        self.assertIsNone(agent._embedding_model)

    def test_missing_extras_triggers_silent_fallback(self) -> None:
        """Missing sentence-transformers package triggers silent fallback (no exception)."""
        config = ECKConfig(enable_embeddings=True)
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("No module named 'sentence_transformers'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            agent = ECKAgent(objective="test", llm_call=lambda x: "dummy", config=config)
            self.assertIsNone(agent._embedding_model)

    def test_model_load_failure_triggers_silent_fallback(self) -> None:
        """Model load failure triggers silent fallback (no exception)."""
        config = ECKConfig(enable_embeddings=True)
        fake_module = types.SimpleNamespace()
        fake_module.SentenceTransformer = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("load failed"))
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            agent = ECKAgent(objective="test", llm_call=lambda x: "dummy", config=config)
            self.assertIsNone(agent._embedding_model)

    def test_no_exception_on_fallback(self) -> None:
        """Fallback never raises to caller."""
        config = ECKConfig(enable_embeddings=True)
        fake_module = types.SimpleNamespace()
        fake_module.SentenceTransformer = lambda *a, **k: (_ for _ in ()).throw(Exception("load failed"))
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            try:
                agent = ECKAgent(objective="test", llm_call=lambda x: "dummy", config=config)
                self.assertIsNone(agent._embedding_model)
            except Exception as e:
                self.fail(f"Exception propagated on fallback: {e}")

    def test_no_partial_state_on_fallback(self) -> None:
        """On failure, state is cleanly None (no partial initialization)."""
        config = ECKConfig(enable_embeddings=True)
        fake_module = types.SimpleNamespace()
        fake_module.SentenceTransformer = lambda *a, **k: (_ for _ in ()).throw(Exception("load failed"))
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            agent = ECKAgent(objective="test", llm_call=lambda x: "dummy", config=config)
            self.assertIsNone(agent._embedding_model)


if __name__ == "__main__":
    unittest.main()

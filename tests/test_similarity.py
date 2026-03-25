# tests/test_similarity.py
"""Invariant tests for Similarity subsystem (ADRs 031–032)."""

from __future__ import annotations

import types
import unittest
from datetime import datetime
from unittest.mock import patch

from eck.agent import ECKAgent
from eck.config import ECKConfig
from eck.memory import TaskRecord
from eck.similarity import (
    _optional_retrieve_scored,
    _optional_retrieve_similar,
    retrieve_scored,
    retrieve_similar,
)


class TestSimilarityCore(unittest.TestCase):
    """Core similarity behavior — stdlib-only path (ADR-031)."""

    def setUp(self) -> None:
        self.tasks = [
            TaskRecord(task_id=1, description="Task A", created_at=datetime(2025, 1, 1), completed=False),
            TaskRecord(task_id=2, description="Task B", created_at=datetime(2025, 1, 3), completed=True),
            TaskRecord(task_id=3, description="Task C", created_at=datetime(2025, 1, 2), completed=False),
        ]

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------
    def test_retrieve_similar_returns_newest_first(self) -> None:
        """Core path returns newest-first ordering."""
        result = retrieve_similar(self.tasks, None, limit=3)
        ids = [r.task_id for r in result]
        self.assertEqual(ids, [2, 3, 1])  # 2025-01-03, 2025-01-02, 2025-01-01

    def test_retrieve_similar_limit_less_than_total(self) -> None:
        """limit=1 returns only the single most recent task."""
        result = retrieve_similar(self.tasks, None, limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].task_id, 2)  # newest

    def test_retrieve_similar_limit_two(self) -> None:
        """limit=2 returns top 2 most recent tasks."""
        result = retrieve_similar(self.tasks, None, limit=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].task_id, 2)
        self.assertEqual(result[1].task_id, 3)

    # ------------------------------------------------------------------
    # Scores
    # ------------------------------------------------------------------
    def test_retrieve_scored_returns_deterministic_scores(self) -> None:
        """Core path returns deterministic normalized scores (1.0, 2/3, 1/3 for limit=3)."""
        result = retrieve_scored(self.tasks, None, limit=3)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0][1], 1.0)
        self.assertAlmostEqual(result[1][1], 2.0 / 3.0)
        self.assertAlmostEqual(result[2][1], 1.0 / 3.0)

    def test_retrieve_scored_limit_two_scores(self) -> None:
        """limit=2 returns top 2 with correct scores."""
        result = retrieve_scored(self.tasks, None, limit=2)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0][1], 1.0)
        self.assertAlmostEqual(result[1][1], 0.5)

    def test_retrieve_scored_records_match_ordering(self) -> None:
        """Scored records are ordered newest-first consistent with retrieve_similar."""
        scored = retrieve_scored(self.tasks, None, limit=3)
        similar = retrieve_similar(self.tasks, None, limit=3)
        self.assertEqual([r for r, _ in scored], similar)

    # ------------------------------------------------------------------
    # Boundary: limit <= 0
    # ------------------------------------------------------------------
    def test_limit_zero_returns_empty(self) -> None:
        """limit=0 returns empty for both functions."""
        self.assertEqual(retrieve_similar(self.tasks, None, 0), [])
        self.assertEqual(retrieve_scored(self.tasks, None, 0), [])

    def test_limit_negative_returns_empty(self) -> None:
        """Negative limit returns empty for both functions."""
        self.assertEqual(retrieve_similar(self.tasks, None, -1), [])
        self.assertEqual(retrieve_scored(self.tasks, None, -1), [])

    # ------------------------------------------------------------------
    # Boundary: empty task list
    # ------------------------------------------------------------------
    def test_retrieve_similar_empty_tasks(self) -> None:
        """Empty task list returns empty list."""
        self.assertEqual(retrieve_similar([], None, limit=3), [])

    def test_retrieve_scored_empty_tasks(self) -> None:
        """Empty task list returns empty scored list."""
        self.assertEqual(retrieve_scored([], None, limit=3), [])

    # ------------------------------------------------------------------
    # query_embedding ignored in core path (ADR-031)
    # ------------------------------------------------------------------
    def test_query_embedding_ignored_in_retrieve_similar(self) -> None:
        """Core path ignores query_embedding in retrieve_similar."""
        result_none = retrieve_similar(self.tasks, None, limit=3)
        result_str = retrieve_similar(self.tasks, "some totally different value", limit=3)
        self.assertEqual(result_none, result_str)

    def test_query_embedding_ignored_in_retrieve_scored(self) -> None:
        """Core path ignores query_embedding in retrieve_scored."""
        scored_none = retrieve_scored(self.tasks, None, limit=3)
        scored_str = retrieve_scored(self.tasks, "different", limit=3)
        self.assertEqual(scored_none, scored_str)

    # ------------------------------------------------------------------
    # Tie-breaking: equal scores resolved reverse-chronologically (ADR-031)
    # ------------------------------------------------------------------
    def test_tie_breaking_reverse_chronological(self) -> None:
        """Equal-score ties are broken reverse-chronologically (ADR-031 invariant)."""
        tied_tasks = [
            TaskRecord(task_id=1, description="Same", created_at=datetime(2025, 1, 1), completed=False),
            TaskRecord(task_id=2, description="Same", created_at=datetime(2025, 1, 3), completed=False),
            TaskRecord(task_id=3, description="Same", created_at=datetime(2025, 1, 2), completed=False),
        ]
        result = retrieve_similar(tied_tasks, None, limit=3)
        ids = [r.task_id for r in result]
        self.assertEqual(ids, [2, 3, 1])  # newest first

    # ------------------------------------------------------------------
    # Determinism / replay
    # ------------------------------------------------------------------
    def test_retrieve_similar_deterministic_replay(self) -> None:
        """Identical inputs produce identical retrieve_similar output on replay."""
        result1 = retrieve_similar(self.tasks, None, limit=3)
        result2 = retrieve_similar(self.tasks, None, limit=3)
        self.assertEqual(result1, result2)

    def test_retrieve_scored_deterministic_replay(self) -> None:
        """Identical inputs produce identical retrieve_scored output on replay."""
        result1 = retrieve_scored(self.tasks, None, limit=3)
        result2 = retrieve_scored(self.tasks, None, limit=3)
        self.assertEqual(result1, result2)

    # ------------------------------------------------------------------
    # Advisory-only: pure output, no side-effects
    # ------------------------------------------------------------------
    def test_retrieve_similar_does_not_mutate_input(self) -> None:
        """retrieve_similar does not mutate the input task list."""
        original = list(self.tasks)
        retrieve_similar(self.tasks, None, limit=3)
        self.assertEqual(self.tasks, original)

    def test_retrieve_scored_does_not_mutate_input(self) -> None:
        """retrieve_scored does not mutate the input task list."""
        original = list(self.tasks)
        retrieve_scored(self.tasks, None, limit=3)
        self.assertEqual(self.tasks, original)


class TestOptionalPathFallback(unittest.TestCase):
    """ADR-032 fallback invariants at the similarity.py level."""

    def setUp(self) -> None:
        self.tasks = [
            TaskRecord(task_id=1, description="Task A", created_at=datetime(2025, 1, 1), completed=False),
            TaskRecord(task_id=2, description="Task B", created_at=datetime(2025, 1, 3), completed=True),
        ]

    # ------------------------------------------------------------------
    # None model falls back to core (no drift)
    # ------------------------------------------------------------------
    def test_optional_retrieve_similar_none_model_falls_back_to_core(self) -> None:
        """_optional_retrieve_similar with None model produces identical output to core path."""
        core_result = retrieve_similar(self.tasks, None, limit=2)
        optional_result = _optional_retrieve_similar(self.tasks, "query", 2, None)
        self.assertEqual(core_result, optional_result)

    def test_optional_retrieve_scored_none_model_falls_back_to_core(self) -> None:
        """_optional_retrieve_scored with None model produces identical output to core path."""
        core_result = retrieve_scored(self.tasks, None, limit=2)
        optional_result = _optional_retrieve_scored(self.tasks, "query", 2, None)
        self.assertEqual(core_result, optional_result)

    # ------------------------------------------------------------------
    # Encoding failure falls back silently (no exception, no drift)
    # ------------------------------------------------------------------
    def test_optional_retrieve_similar_encoding_failure_falls_back(self) -> None:
        """Encoding failure in _optional_retrieve_similar falls back to core output."""
        class FailingModel:
            def encode(self, *args, **kwargs):
                raise RuntimeError("encoding failed")

        core_result = retrieve_similar(self.tasks, None, limit=2)
        result = _optional_retrieve_similar(self.tasks, "query", 2, FailingModel())
        self.assertEqual(result, core_result)

    def test_optional_retrieve_scored_encoding_failure_falls_back(self) -> None:
        """Encoding failure in _optional_retrieve_scored falls back to core output."""
        class FailingModel:
            def encode(self, *args, **kwargs):
                raise RuntimeError("encoding failed")

        core_result = retrieve_scored(self.tasks, None, limit=2)
        result = _optional_retrieve_scored(self.tasks, "query", 2, FailingModel())
        self.assertEqual(result, core_result)

    def test_optional_retrieve_similar_no_exception_on_any_failure(self) -> None:
        """No exception propagates from _optional_retrieve_similar on any failure."""
        class AlwaysFailModel:
            def encode(self, *args, **kwargs):
                raise Exception("catastrophic failure")

        try:
            result = _optional_retrieve_similar(self.tasks, "query", 2, AlwaysFailModel())
            self.assertIsInstance(result, list)
        except Exception as e:
            self.fail(f"Exception propagated from _optional_retrieve_similar: {e}")

    def test_optional_retrieve_scored_no_exception_on_any_failure(self) -> None:
        """No exception propagates from _optional_retrieve_scored on any failure."""
        class AlwaysFailModel:
            def encode(self, *args, **kwargs):
                raise Exception("catastrophic failure")

        try:
            result = _optional_retrieve_scored(self.tasks, "query", 2, AlwaysFailModel())
            self.assertIsInstance(result, list)
        except Exception as e:
            self.fail(f"Exception propagated from _optional_retrieve_scored: {e}")

    # ------------------------------------------------------------------
    # No prompt drift on fallback vs direct core path (ADR-032)
    # ------------------------------------------------------------------
    def test_no_prompt_drift_similar_fallback_vs_core(self) -> None:
        """Fallback output of _optional_retrieve_similar is identical to direct core path."""
        class FailingModel:
            def encode(self, *args, **kwargs):
                raise RuntimeError("fail")

        core_result = retrieve_similar(self.tasks, None, limit=2)
        fallback_result = _optional_retrieve_similar(self.tasks, "query", 2, FailingModel())
        self.assertEqual(core_result, fallback_result)

    def test_no_prompt_drift_scored_fallback_vs_core(self) -> None:
        """Fallback output of _optional_retrieve_scored is identical to direct core path."""
        class FailingModel:
            def encode(self, *args, **kwargs):
                raise RuntimeError("fail")

        core_result = retrieve_scored(self.tasks, None, limit=2)
        fallback_result = _optional_retrieve_scored(self.tasks, "query", 2, FailingModel())
        self.assertEqual(core_result, fallback_result)

    # ------------------------------------------------------------------
    # limit=0 on optional path falls back cleanly
    # ------------------------------------------------------------------
    def test_optional_retrieve_similar_limit_zero(self) -> None:
        """_optional_retrieve_similar with limit=0 returns empty list."""
        class DummyModel:
            def encode(self, *args, **kwargs):
                return []

        result = _optional_retrieve_similar(self.tasks, "query", 0, DummyModel())
        self.assertEqual(result, [])

    def test_optional_retrieve_scored_limit_zero(self) -> None:
        """_optional_retrieve_scored with limit=0 returns empty list."""
        class DummyModel:
            def encode(self, *args, **kwargs):
                return []

        result = _optional_retrieve_scored(self.tasks, "query", 0, DummyModel())
        self.assertEqual(result, [])


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

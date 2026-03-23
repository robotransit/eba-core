from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from eck.memory import (
    MemoryRetrieval,
    RetrievalExecution,
    RetrievalQuery,
    TaskRecord,
    RetrievalIntegration,
)


class TestMemoryRetrieval(unittest.TestCase):
    """Test suite for MemoryRetrieval contract (ADR-026–030)."""

    def setUp(self) -> None:
        self.retrieval = MemoryRetrieval(enabled=True)
        self.disabled_retrieval = MemoryRetrieval(enabled=False)

    def _sample_task_record(self) -> TaskRecord:
        """Return a concrete TaskRecord for non-empty execution tests."""
        return TaskRecord(
            task_id=99,
            description="Test task",
            created_at=datetime(2025, 1, 1, 0, 0),
            completed=False,
            priority=0,
        )

    # ------------------------------------------------------------------
    # Proposal determinism
    # ------------------------------------------------------------------
    def test_proposal_determinism(self) -> None:
        """Identical user_input must produce identical RetrievalQuery."""
        q1 = self.retrieval.build_retrieval_query("hello world")
        q2 = self.retrieval.build_retrieval_query("hello world")
        self.assertEqual(q1.text, q2.text)

    def test_proposal_returns_identical_query_object_shape(self) -> None:
        """Proposal returns identical query objects (type and equality)."""
        q1 = self.retrieval.build_retrieval_query("test input")
        q2 = self.retrieval.build_retrieval_query("test input")
        self.assertIsInstance(q1, RetrievalQuery)
        self.assertEqual(q1, q2)

    def test_proposal_normalizes_whitespace_and_case(self) -> None:
        """Proposal normalizes whitespace and case."""
        q = self.retrieval.build_retrieval_query("  RePoRt  ")
        self.assertEqual(q.text, "report")

    # ------------------------------------------------------------------
    # Permission gating
    # ------------------------------------------------------------------
    def test_retrieval_permitted_reflects_enabled_flag(self) -> None:
        """retrieval_permitted() reflects the enabled flag."""
        self.assertTrue(self.retrieval.retrieval_permitted())
        self.assertFalse(self.disabled_retrieval.retrieval_permitted())

    def test_run_retrieval_raises_when_disabled(self) -> None:
        """_run_retrieval raises when called while retrieval is disabled."""
        query = self.disabled_retrieval.build_retrieval_query("report")
        with self.assertRaises(RuntimeError):
            self.disabled_retrieval._run_retrieval(query)

    # ------------------------------------------------------------------
    # Disabled isolation (zero activity)
    # ------------------------------------------------------------------
    def test_disabled_path_zero_retrieval_activity(self) -> None:
        """Disabled path performs zero retrieval activity (no execution, no log)."""
        with patch.object(self.disabled_retrieval, "_run_retrieval") as mock_exec:
            with patch.object(self.disabled_retrieval._logger, "info") as mock_log:
                result = self.disabled_retrieval.retrieve("test input")
                mock_exec.assert_not_called()
                mock_log.assert_not_called()
                self.assertIsNone(result)

    def test_disabled_path_returns_none(self) -> None:
        """Disabled path returns None."""
        result = self.disabled_retrieval.retrieve("test input")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Enabled + empty semantics
    # ------------------------------------------------------------------
    def test_enabled_empty_returns_none(self) -> None:
        """Enabled-empty path returns None."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            result = self.retrieval.retrieve("test input")
            self.assertIsNone(result)

    def test_enabled_empty_logs_exactly_once(self) -> None:
        """Enabled-empty path logs exactly once."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            with patch.object(self.retrieval._logger, "info") as mock_log:
                self.retrieval.retrieve("test input")
                mock_log.assert_called_once()

    def test_enabled_empty_log_fields(self) -> None:
        """Enabled-empty path logs correct metadata fields (no timestamp)."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            with patch.object(self.retrieval._logger, "info") as mock_log:
                self.retrieval.retrieve("test input")
                mock_log.assert_called_once()
                extra = mock_log.call_args[1]["extra"]
                self.assertEqual(extra["enabled"], True)
                self.assertEqual(extra["item_count"], 0)
                self.assertEqual(extra["context_length"], 0)
                self.assertIn("run_id", extra)
                self.assertEqual(extra["event_type"], "retrieval_attempt")
                self.assertNotIn("timestamp", extra)

    # ------------------------------------------------------------------
    # Prompt equivalence boundary
    # ------------------------------------------------------------------
    def test_prompt_equivalence_disabled_vs_enabled_empty(self) -> None:
        """Disabled and enabled-empty must yield the same integration result (None)."""
        disabled_result = self.disabled_retrieval.retrieve("test input")

        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            empty_result = self.retrieval.retrieve("test input")

        self.assertIsNone(disabled_result)
        self.assertIsNone(empty_result)
        self.assertEqual(disabled_result, empty_result)

    # ------------------------------------------------------------------
    # Exact-once observability on enabled path (including exceptions)
    # ------------------------------------------------------------------
    def test_logging_exact_once_enabled_path(self) -> None:
        """Enabled path logs exactly once (success or failure)."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            with patch.object(self.retrieval._logger, "info") as mock_log:
                self.retrieval.retrieve("test input")
                mock_log.assert_called_once()
                extra = mock_log.call_args[1]["extra"]
                self.assertEqual(extra["enabled"], True)
                self.assertEqual(extra["item_count"], 0)
                self.assertEqual(extra["context_length"], 0)
                self.assertIn("run_id", extra)
                self.assertEqual(extra["event_type"], "retrieval_attempt")

    def test_logging_exact_once_on_exception(self) -> None:
        """Enabled path logs exactly once even when execution raises."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.side_effect = RuntimeError("backend failure")
            with patch.object(self.retrieval._logger, "info") as mock_log:
                with self.assertRaises(RuntimeError):
                    self.retrieval.retrieve("test input")
                mock_log.assert_called_once()
                extra = mock_log.call_args[1]["extra"]
                self.assertEqual(extra["enabled"], True)
                self.assertEqual(extra["item_count"], 0)
                self.assertEqual(extra["context_length"], 0)
                self.assertIn("run_id", extra)
                self.assertEqual(extra["event_type"], "retrieval_attempt")

    # ------------------------------------------------------------------
    # Advisory-only posture (non-empty integration)
    # ------------------------------------------------------------------
    def test_non_empty_integration_returns_advisory_text(self) -> None:
        """Non-empty execution produces advisory RetrievalIntegration with text block."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=(self._sample_task_record(),))
            result = self.retrieval.retrieve("test input")
            self.assertIsInstance(result, RetrievalIntegration)
            self.assertIsInstance(result.formatted_block, str)
            self.assertTrue(result.formatted_block.startswith("=== BEGIN MEMORY CONTEXT ==="))
            self.assertGreater(result.item_count, 0)
            self.assertGreater(result.context_length, 0)

    # ------------------------------------------------------------------
    # Ordering (newest-first)
    # ------------------------------------------------------------------
    def test_run_retrieval_returns_newest_first(self) -> None:
        """_run_retrieval returns items sorted newest-first by created_at."""
        # Override mock model for controlled test
        self.retrieval._mock_world_model = (
            TaskRecord(task_id=1, description="Test", created_at=datetime(2025, 1, 1), completed=False, priority=0),
            TaskRecord(task_id=2, description="Test", created_at=datetime(2025, 1, 2), completed=False, priority=0),
            TaskRecord(task_id=3, description="Test", created_at=datetime(2025, 1, 3), completed=False, priority=0),
        )
        query = RetrievalQuery(text="test")
        execution = self.retrieval._run_retrieval(query)
        ids = tuple(r.task_id for r in execution.items)
        self.assertEqual(ids, (3, 2, 1))  # newest first

    # ------------------------------------------------------------------
    # Metadata-only logging (current keys)
    # ------------------------------------------------------------------
    def test_metadata_only_logging(self) -> None:
        """Log entries contain only expected metadata keys (no timestamp)."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            with patch.object(self.retrieval._logger, "info") as mock_log:
                self.retrieval.retrieve("test input")
                mock_log.assert_called_once()
                extra = mock_log.call_args[1]["extra"]
                expected_keys = {
                    "run_id",
                    "enabled",
                    "item_count",
                    "context_length",
                    "event_type",
                }
                self.assertEqual(set(extra.keys()), expected_keys)


if __name__ == "__main__":
    unittest.main()

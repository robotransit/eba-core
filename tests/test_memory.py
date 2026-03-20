from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from eck.memory import (
    MemoryRetrieval,
    RetrievalExecution,
    RetrievalQuery,
    TaskRecord,
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
    # Disable isolation
    # ------------------------------------------------------------------
    def test_disabled_path_no_execution_object(self) -> None:
        """Disabled path creates no RetrievalExecution object."""
        with patch.object(self.disabled_retrieval, "_run_retrieval") as mock_exec:
            result = self.disabled_retrieval.retrieve("test input")
            mock_exec.assert_not_called()
            self.assertIsNone(result)

    def test_disabled_path_returns_none(self) -> None:
        """Disabled path returns None."""
        result = self.disabled_retrieval.retrieve("test input")
        self.assertIsNone(result)

    def test_disabled_path_logs_exactly_once(self) -> None:
        """Disabled path logs exactly once."""
        with patch.object(self.disabled_retrieval._logger, "info") as mock_log:
            self.disabled_retrieval.retrieve("test input")
            mock_log.assert_called_once()

    def test_disabled_path_log_fields(self) -> None:
        """Disabled path logs correct metadata fields."""
        with patch.object(self.disabled_retrieval._logger, "info") as mock_log:
            self.disabled_retrieval.retrieve("test input")
            mock_log.assert_called_once()
            extra = mock_log.call_args[1]["extra"]
            self.assertEqual(extra["enabled"], False)
            self.assertEqual(extra["item_count"], 0)
            self.assertEqual(extra["context_length"], 0)
            self.assertIn("run_id", extra)
            self.assertIn("timestamp", extra)
            self.assertEqual(extra["event_type"], "retrieval_attempt")

    # ------------------------------------------------------------------
    # Enabled + empty semantics
    # ------------------------------------------------------------------
    def test_enabled_empty_returns_none(self) -> None:
        """Enabled-empty path returns None (integration returns None)."""
        result = self.retrieval.retrieve("test input")
        self.assertIsNone(result)

    def test_enabled_empty_logs_exactly_once(self) -> None:
        """Enabled-empty path logs exactly once."""
        with patch.object(self.retrieval._logger, "info") as mock_log:
            self.retrieval.retrieve("test input")
            mock_log.assert_called_once()

    def test_enabled_empty_log_fields(self) -> None:
        """Enabled-empty path logs correct metadata fields."""
        with patch.object(self.retrieval._logger, "info") as mock_log:
            self.retrieval.retrieve("test input")
            mock_log.assert_called_once()
            extra = mock_log.call_args[1]["extra"]
            self.assertEqual(extra["enabled"], True)
            self.assertEqual(extra["item_count"], 0)
            self.assertEqual(extra["context_length"], 0)
            self.assertIn("run_id", extra)
            self.assertIn("timestamp", extra)
            self.assertEqual(extra["event_type"], "retrieval_attempt")

    def test_enabled_empty_executes_internally(self) -> None:
        """Enabled-empty path creates real RetrievalExecution internally."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            result = self.retrieval.retrieve("test input")
            mock_exec.assert_called_once()
            self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Prompt equivalence boundary
    # ------------------------------------------------------------------
    def test_prompt_equivalence_disabled_vs_enabled_empty(self) -> None:
        """Disabled and enabled-empty must yield the same integration result."""
        disabled_result = self.disabled_retrieval.retrieve("test input")
        empty_result = self.retrieval.retrieve("test input")
        self.assertEqual(disabled_result, empty_result)

    # ------------------------------------------------------------------
    # Exact-once observability on exception path
    # ------------------------------------------------------------------
    def test_logging_exact_once_on_exception(self) -> None:
        """Enabled path logs exactly once even when integration raises."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=(self._sample_task_record(),))
            with patch.object(self.retrieval._logger, "info") as mock_log:
                with self.assertRaises(NotImplementedError):
                    self.retrieval.retrieve("test input")
                mock_log.assert_called_once()
                extra = mock_log.call_args[1]["extra"]
                self.assertEqual(extra["enabled"], True)
                self.assertEqual(extra["item_count"], 1)
                self.assertEqual(extra["context_length"], 0)
                self.assertIn("run_id", extra)
                self.assertEqual(extra["event_type"], "retrieval_attempt")

    # ------------------------------------------------------------------
    # Metadata-only logging
    # ------------------------------------------------------------------
    def test_metadata_only_logging(self) -> None:
        """Log entries contain only expected metadata keys."""
        with patch.object(self.retrieval._logger, "info") as mock_log:
            self.retrieval.retrieve("test input")
            mock_log.assert_called_once()
            extra = mock_log.call_args[1]["extra"]
            expected_keys = {
                "run_id",
                "timestamp",
                "enabled",
                "item_count",
                "context_length",
                "event_type",
            }
            self.assertEqual(set(extra.keys()), expected_keys)

    # ------------------------------------------------------------------
    # Non-empty integration deferred honestly
    # ------------------------------------------------------------------
    def test_non_empty_integration_raises_not_implemented(self) -> None:
        """Non-empty execution raises NotImplementedError in integration."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=(self._sample_task_record(),))
            with self.assertRaises(NotImplementedError):
                self.retrieval.retrieve("test input")

    # ------------------------------------------------------------------
    # Direct method tests for contract breadth
    # ------------------------------------------------------------------
    def test_integrate_retrieval_none_returns_none(self) -> None:
        """integrate_retrieval(None) returns None."""
        result = self.retrieval.integrate_retrieval(None)
        self.assertIsNone(result)

    def test_integrate_retrieval_empty_execution_returns_none(self) -> None:
        """integrate_retrieval(empty execution) returns None."""
        empty_exec = RetrievalExecution(items=())
        result = self.retrieval.integrate_retrieval(empty_exec)
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Query behavior
    # ------------------------------------------------------------------
    def test_empty_query_returns_empty_execution(self) -> None:
        """Empty query returns empty execution."""
        query = self.retrieval.build_retrieval_query("   ")
        execution = self.retrieval._run_retrieval(query)
        self.assertEqual(len(execution.items), 0)

    def test_query_matching_returns_expected_items(self) -> None:
        """Query matching returns expected items."""
        query = self.retrieval.build_retrieval_query("report")
        execution = self.retrieval._run_retrieval(query)
        self.assertEqual(len(execution.items), 1)
        self.assertIn("report", execution.items[0].description.lower())

    def test_query_no_match_returns_empty(self) -> None:
        """No-match query returns empty execution."""
        query = self.retrieval.build_retrieval_query("nonexistent")
        execution = self.retrieval._run_retrieval(query)
        self.assertEqual(len(execution.items), 0)

    def test_retrieval_preserves_order(self) -> None:
        """Retrieval preserves append-only order."""
        query = self.retrieval.build_retrieval_query("e")
        execution = self.retrieval._run_retrieval(query)
        ids = [record.task_id for record in execution.items]
        expected_ids = [
            record.task_id
            for record in self.retrieval._mock_world_model
            if "e" in record.description.lower()
        ]
        self.assertEqual(ids, expected_ids)


if __name__ == "__main__":
    unittest.main()
    

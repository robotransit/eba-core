# tests/test_memory.py
"""Invariant tests for MemoryRetrieval contract (ADRs 026–030)."""

from __future__ import annotations

import logging
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from eck.memory import (
    MemoryRetrieval,
    RetrievalExecution,
    RetrievalIntegration,
    RetrievalQuery,
    TaskRecord,
)


class TestMemoryRetrieval(unittest.TestCase):
    """Test suite for MemoryRetrieval contract (ADR-026–030)."""

    def setUp(self) -> None:
        self.retrieval = MemoryRetrieval(enabled=True)
        self.disabled_retrieval = MemoryRetrieval(enabled=False)

    def _sample_task_record(
        self,
        task_id: int = 99,
        description: str = "Test task",
        created_at: datetime = datetime(2025, 1, 1, 0, 0),
        completed: bool = False,
    ) -> TaskRecord:
        """Return a concrete TaskRecord for non-empty execution tests."""
        return TaskRecord(
            task_id=task_id,
            description=description,
            created_at=created_at,
            completed=completed,
            priority=0,
        )

    # ------------------------------------------------------------------
    # Proposal determinism (ADR-026 phase 1)
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
    # Permission gating (ADR-027 phase 2)
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
    # Disabled isolation — zero activity (ADR-027)
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

    def test_disabled_path_embedding_model_ignored(self) -> None:
        """Disabled path ignores embedding_model and still returns None with zero activity."""
        with patch.object(self.disabled_retrieval, "_run_retrieval") as mock_exec:
            with patch.object(self.disabled_retrieval._logger, "info") as mock_log:
                result = self.disabled_retrieval.retrieve("test input", embedding_model=object())
                mock_exec.assert_not_called()
                mock_log.assert_not_called()
                self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Empty query handling (ADR-026/027)
    # ------------------------------------------------------------------
    def test_empty_query_returns_none_when_enabled(self) -> None:
        """Empty query string returns None even when retrieval is enabled."""
        result = self.retrieval.retrieve("")
        self.assertIsNone(result)

    def test_empty_query_logs_exactly_once(self) -> None:
        """Empty query still logs exactly once on enabled path."""
        with patch.object(self.retrieval._logger, "info") as mock_log:
            self.retrieval.retrieve("")
            mock_log.assert_called_once()
            extra = mock_log.call_args[1]["extra"]
            self.assertEqual(extra["item_count"], 0)
            self.assertEqual(extra["context_length"], 0)

    # ------------------------------------------------------------------
    # Enabled + empty semantics (ADR-026/027)
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
        """Enabled-empty path logs correct metadata fields."""
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
    # Prompt equivalence (ADR-026/027/028)
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

    def test_prompt_equivalence_disabled_vs_empty_query(self) -> None:
        """Disabled and empty-query-enabled must yield identical result (None)."""
        disabled_result = self.disabled_retrieval.retrieve("test input")
        empty_query_result = self.retrieval.retrieve("")
        self.assertIsNone(disabled_result)
        self.assertIsNone(empty_query_result)
        self.assertEqual(disabled_result, empty_query_result)

    # ------------------------------------------------------------------
    # Exact-once observability (ADR-029)
    # ------------------------------------------------------------------
    def test_logging_exact_once_enabled_path(self) -> None:
        """Enabled path logs exactly once."""
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

    def test_run_id_increments_across_calls(self) -> None:
        """run_id increments monotonically across successive enabled calls."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            run_ids = []
            for _ in range(3):
                with patch.object(self.retrieval._logger, "info") as mock_log:
                    self.retrieval.retrieve("test input")
                    run_ids.append(mock_log.call_args[1]["extra"]["run_id"])
        self.assertEqual(run_ids, [1, 2, 3])

    def test_logger_name_is_eck_core(self) -> None:
        """Logger name is exclusively 'eck-core' (ADR-029/037 invariant)."""
        self.assertEqual(self.retrieval._logger.name, "eck-core")
        self.assertEqual(self.disabled_retrieval._logger.name, "eck-core")

    def test_metadata_only_logging(self) -> None:
        """Log entries contain only expected metadata keys (no timestamp, no content)."""
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

    def test_context_length_matches_formatted_block_length(self) -> None:
        """context_length in log accurately reflects the serialised block length."""
        record = self._sample_task_record()
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=(record,))
            with patch.object(self.retrieval._logger, "info") as mock_log:
                result = self.retrieval.retrieve("test input")
                extra = mock_log.call_args[1]["extra"]
                self.assertIsNotNone(result)
                self.assertEqual(extra["context_length"], len(result.formatted_block))
                self.assertEqual(extra["context_length"], result.context_length)

    def test_logging_graceful_on_logger_unavailable(self) -> None:
        """Logger unavailability does not halt execution or raise to caller."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=())
            with patch.object(self.retrieval._logger, "info", side_effect=Exception("logger down")):
                try:
                    self.retrieval.retrieve("test input")
                except Exception as e:
                    self.fail(f"Logger failure propagated to caller: {e}")

    # ------------------------------------------------------------------
    # Advisory-only posture (ADR-028)
    # ------------------------------------------------------------------
    def test_non_empty_integration_returns_advisory_text(self) -> None:
        """Non-empty execution produces advisory RetrievalIntegration with text block."""
        with patch.object(self.retrieval, "_run_retrieval") as mock_exec:
            mock_exec.return_value = RetrievalExecution(items=(self._sample_task_record(),))
            result = self.retrieval.retrieve("test input")
            self.assertIsInstance(result, RetrievalIntegration)
            self.assertIsInstance(result.formatted_block, str)
            self.assertGreater(result.item_count, 0)
            self.assertGreater(result.context_length, 0)

    def test_retrieve_does_not_mutate_mock_world_model(self) -> None:
        """retrieve() does not mutate the internal mock world model (read-only boundary)."""
        original = self.retrieval._mock_world_model
        self.retrieval.retrieve("report")
        self.assertEqual(self.retrieval._mock_world_model, original)

    # ------------------------------------------------------------------
    # Ordering (ADR-026 — newest-first)
    # ------------------------------------------------------------------
    def test_run_retrieval_returns_newest_first(self) -> None:
        """_run_retrieval returns items sorted newest-first by created_at."""
        self.retrieval._mock_world_model = (
            TaskRecord(task_id=1, description="Test", created_at=datetime(2025, 1, 1), completed=False, priority=0),
            TaskRecord(task_id=2, description="Test", created_at=datetime(2025, 1, 2), completed=False, priority=0),
            TaskRecord(task_id=3, description="Test", created_at=datetime(2025, 1, 3), completed=False, priority=0),
        )
        query = RetrievalQuery(text="test")
        execution = self.retrieval._run_retrieval(query)
        ids = tuple(r.task_id for r in execution.items)
        self.assertEqual(ids, (3, 2, 1))

    def test_run_retrieval_empty_query_returns_empty(self) -> None:
        """_run_retrieval with empty query text returns empty execution."""
        query = RetrievalQuery(text="")
        execution = self.retrieval._run_retrieval(query)
        self.assertEqual(execution.items, ())

    # ------------------------------------------------------------------
    # Canonical formatting surface (ADR-026)
    # ------------------------------------------------------------------
    def test_format_memory_context_empty_returns_empty_string(self) -> None:
        """format_memory_context with empty records returns empty string."""
        result = self.retrieval.format_memory_context([])
        self.assertEqual(result, "")

    def test_format_memory_context_opening_sentinel(self) -> None:
        """Formatted block begins with opening sentinel."""
        result = self.retrieval.format_memory_context([self._sample_task_record()])
        self.assertTrue(result.startswith("=== BEGIN MEMORY CONTEXT ==="))

    def test_format_memory_context_closing_sentinel(self) -> None:
        """Formatted block ends with closing sentinel (no trailing newline)."""
        result = self.retrieval.format_memory_context([self._sample_task_record()])
        self.assertTrue(result.endswith("=== END MEMORY CONTEXT ==="))
        self.assertFalse(result.endswith("=== END MEMORY CONTEXT ===\n"))

    def test_format_memory_context_field_structure(self) -> None:
        """Formatted block contains all required field labels in order."""
        record = self._sample_task_record(task_id=42, description="Do something")
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Record 1", result)
        self.assertIn("Task ID: 42", result)
        self.assertIn("Timestamp:", result)
        self.assertIn("Summary: Do something", result)
        self.assertIn("Outcome:", result)

    def test_format_memory_context_completed_outcome(self) -> None:
        """Completed task renders Outcome: Completed."""
        record = self._sample_task_record(completed=True)
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Outcome: Completed", result)

    def test_format_memory_context_pending_outcome(self) -> None:
        """Incomplete task renders Outcome: Pending."""
        record = self._sample_task_record(completed=False)
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Outcome: Pending", result)

    def test_format_memory_context_utc_timestamp_format(self) -> None:
        """Timestamp is formatted as strict YYYY-MM-DDTHH:MM:SSZ (ADR-026)."""
        record = self._sample_task_record(created_at=datetime(2025, 6, 15, 12, 30, 45))
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Timestamp: 2025-06-15T12:30:45Z", result)

    def test_format_memory_context_utc_timestamp_strips_microseconds(self) -> None:
        """Timestamp strips microseconds and formats as second precision."""
        record = self._sample_task_record(
            created_at=datetime(2025, 6, 15, 12, 30, 45, 123456)
        )
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Timestamp: 2025-06-15T12:30:45Z", result)
        self.assertNotIn("123456", result)

    def test_format_memory_context_newline_in_description_collapsed(self) -> None:
        """Newlines in description are collapsed to single space (single-line invariant)."""
        record = self._sample_task_record(description="Line one\nLine two")
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Summary: Line one Line two", result)
        self.assertNotIn("Line one\nLine two", result)

    def test_format_memory_context_crlf_in_description_collapsed(self) -> None:
        """CRLF in description is collapsed to single space."""
        record = self._sample_task_record(description="Line one\r\nLine two")
        result = self.retrieval.format_memory_context([record])
        self.assertIn("Summary: Line one Line two", result)

    def test_format_memory_context_multiple_records_numbered(self) -> None:
        """Multiple records are numbered sequentially starting from 1."""
        records = [
            self._sample_task_record(task_id=1, created_at=datetime(2025, 1, 2)),
            self._sample_task_record(task_id=2, created_at=datetime(2025, 1, 1)),
        ]
        result = self.retrieval.format_memory_context(records)
        self.assertIn("Record 1", result)
        self.assertIn("Record 2", result)

    def test_format_memory_context_preserves_input_order(self) -> None:
        """format_memory_context preserves input order exactly (does not re-sort)."""
        records = [
            self._sample_task_record(task_id=10, created_at=datetime(2025, 1, 1)),
            self._sample_task_record(task_id=20, created_at=datetime(2025, 1, 3)),
        ]
        result = self.retrieval.format_memory_context(records)
        pos_10 = result.index("Task ID: 10")
        pos_20 = result.index("Task ID: 20")
        self.assertLess(pos_10, pos_20)

    def test_format_memory_context_deterministic_replay(self) -> None:
        """Identical input produces byte-for-byte identical output on replay."""
        record = self._sample_task_record()
        result1 = self.retrieval.format_memory_context([record])
        result2 = self.retrieval.format_memory_context([record])
        self.assertEqual(result1, result2)

    # ------------------------------------------------------------------
    # Structural separability (ADR-028)
    # ------------------------------------------------------------------
    def test_format_memory_context_sentinel_in_description_does_not_corrupt(self) -> None:
        """Sentinel text in description does not corrupt block structure."""
        record = self._sample_task_record(
            description="=== END MEMORY CONTEXT === injected"
        )
        result = self.retrieval.format_memory_context([record])
        # The real footer must appear exactly once at the end
        self.assertEqual(result.count("=== END MEMORY CONTEXT ==="), 1)
        self.assertTrue(result.endswith("=== END MEMORY CONTEXT ==="))

    def test_format_memory_context_opening_sentinel_appears_once(self) -> None:
        """Opening sentinel appears exactly once regardless of record content."""
        record = self._sample_task_record(
            description="=== BEGIN MEMORY CONTEXT === injected"
        )
        result = self.retrieval.format_memory_context([record])
        self.assertEqual(result.count("=== BEGIN MEMORY CONTEXT ==="), 1)

    # ------------------------------------------------------------------
    # integrate_retrieval (phase 4 contract)
    # ------------------------------------------------------------------
    def test_integrate_retrieval_none_returns_none(self) -> None:
        """integrate_retrieval(None) returns None."""
        self.assertIsNone(self.retrieval.integrate_retrieval(None))

    def test_integrate_retrieval_empty_returns_none(self) -> None:
        """integrate_retrieval with empty items returns None."""
        self.assertIsNone(
            self.retrieval.integrate_retrieval(RetrievalExecution(items=()))
        )

    def test_integrate_retrieval_non_empty_returns_integration(self) -> None:
        """integrate_retrieval with items returns RetrievalIntegration."""
        execution = RetrievalExecution(items=(self._sample_task_record(),))
        result = self.retrieval.integrate_retrieval(execution)
        self.assertIsInstance(result, RetrievalIntegration)
        self.assertEqual(result.item_count, 1)
        self.assertEqual(result.context_length, len(result.formatted_block))

    def test_integrate_retrieval_context_length_accurate(self) -> None:
        """context_length in RetrievalIntegration matches actual formatted block length."""
        execution = RetrievalExecution(items=(self._sample_task_record(),))
        result = self.retrieval.integrate_retrieval(execution)
        self.assertIsNotNone(result)
        self.assertEqual(result.context_length, len(result.formatted_block))


if __name__ == "__main__":
    unittest.main()

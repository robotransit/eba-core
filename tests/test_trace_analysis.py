"""Basic tests for the Trace Analysis Service (v0.4.0).
Focuses exclusively on structural invariants:
- Deep-copy isolation (both directions)
- Invalid trace_id skipping
- Severity normalisation
- summarise_trace / render_trace behaviour
"""
import unittest
from eck.trace_analysis import TraceAnalyzer


class TestTraceAnalysis(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = TraceAnalyzer()

    def test_ingest_deep_copy_isolation(self) -> None:
        """Mutating original event after ingest must not affect stored state."""
        event = {"trace_id": "t1", "event_type": "step", "severity": "INFO"}
        self.analyzer.ingest([event])
        event["severity"] = "MUTATED"
        summary = self.analyzer.summarise_trace("t1")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["severity_counts"], {"INFO": 1})

    def test_get_trace_returns_deep_copy(self) -> None:
        """Mutating returned dict must not affect internal state."""
        self.analyzer.ingest([{"trace_id": "t1", "event_type": "step", "severity": "INFO"}])
        events = self.analyzer.get_trace("t1")
        events[0]["severity"] = "MUTATED"
        summary = self.analyzer.summarise_trace("t1")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["severity_counts"], {"INFO": 1})

    def test_invalid_trace_id_skipped(self) -> None:
        """Non-string, None, missing, empty, or whitespace-only trace_id events are silently skipped."""
        events = [
            {"event_type": "step"},
            {"trace_id": None, "event_type": "step"},
            {"trace_id": 123, "event_type": "step"},
            {"trace_id": "", "event_type": "step"},
            {"trace_id": "   ", "event_type": "step"},
        ]
        self.analyzer.ingest(events)
        self.assertEqual(self.analyzer.list_traces(), [])

    def test_severity_normalisation(self) -> None:
        """Missing, None, or empty severity normalises to UNKNOWN."""
        events = [
            {"trace_id": "t1", "event_type": "step"},
            {"trace_id": "t1", "event_type": "step", "severity": None},
            {"trace_id": "t1", "event_type": "step", "severity": ""},
        ]
        self.analyzer.ingest(events)
        summary = self.analyzer.summarise_trace("t1")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["severity_counts"], {"UNKNOWN": 3})

    def test_summarise_trace_unknown_trace_returns_none(self) -> None:
        self.assertIsNone(self.analyzer.summarise_trace("nonexistent"))

    def test_summarise_trace_key_set(self) -> None:
        """summarise_trace must return exactly the committed minimal key set."""
        self.analyzer.ingest([{"trace_id": "t1", "event_type": "step", "severity": "INFO"}])
        summary = self.analyzer.summarise_trace("t1")
        self.assertIsNotNone(summary)
        self.assertEqual(set(summary.keys()), {"trace_id", "event_count", "event_types", "severity_counts"})

    def test_render_trace_unknown_trace(self) -> None:
        output = self.analyzer.render_trace("nonexistent")
        self.assertIn("nonexistent", output)
        self.assertIn("no events", output.lower())

    def test_summarise_and_render_missing_severity_handling_differ(self) -> None:
        """summarise_trace normalises missing severity to UNKNOWN; render_trace shows <missing>."""
        self.analyzer.ingest([{"trace_id": "t1", "event_type": "step"}])
        summary = self.analyzer.summarise_trace("t1")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["severity_counts"], {"UNKNOWN": 1})
        rendered = self.analyzer.render_trace("t1")
        self.assertIn("<missing>", rendered)

    def test_list_traces_is_sorted(self) -> None:
        self.analyzer.ingest([
            {"trace_id": "z-trace"},
            {"trace_id": "a-trace"},
            {"trace_id": "m-trace"},
        ])
        self.assertEqual(self.analyzer.list_traces(), ["a-trace", "m-trace", "z-trace"])

    def test_filter_by_event_type(self) -> None:
        self.analyzer.ingest([
            {"trace_id": "t1", "event_type": "step"},
            {"trace_id": "t1", "event_type": "critic"},
            {"trace_id": "t2", "event_type": "step"},
        ])
        self.assertEqual(len(self.analyzer.filter_by_event_type("step")), 2)
        self.assertEqual(len(self.analyzer.filter_by_event_type("step", "t1")), 1)


if __name__ == "__main__":
    unittest.main()

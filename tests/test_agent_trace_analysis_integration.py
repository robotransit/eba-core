# tests/test_agent_trace_analysis_integration.py
"""Integration tests locking the one-way seam between ECKAgent and TraceAnalyzer.

These tests verify two properties only:
1. The agent loop correctly delivers step.start and step.end events to the
   analyzer when one is injected.
2. The presence or absence of a TraceAnalyzer has zero effect on agent
   control outcomes.

No assertions are made on analyzer-driven behaviour — there must not be any.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from eck.agent import ECKAgent
from eck.config import ECKConfig
from eck.trace_analysis import TraceAnalyzer
from eck.types import make_critic_outcome


# ── Shared stubs (mirrors test_agent.py conventions) ─────────────────────────

def dummy_llm(prompt: str) -> str:
    return "NO"


def _critic_deferred():
    return (make_critic_outcome(category="deferred", severity=0.0, feedback="no_valid_proposal"), None)


def _snap(severe: bool = False) -> dict:
    return {
        "drift_streak": 0,
        "total_drift_events": 0,
        "last_error_z": 0.0,
        "numeric_bias": 0.0,
        "feasibility_sample_count": 0,
        "numeric_success_rate": None,
        "severe": severe,
    }


def _agent(trace_analyzer: TraceAnalyzer | None = None) -> ECKAgent:
    return ECKAgent(
        objective="Test objective",
        llm_call=dummy_llm,
        config=ECKConfig(),
        trace_analyzer=trace_analyzer,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test classes
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentAnalyzerSeam(unittest.TestCase):
    """The agent loop delivers events to the analyzer — seam lock."""

    def test_step_delivers_step_start_and_step_end_to_analyzer(self) -> None:
        """After one step, the analyzer contains both step.start and step.end."""
        import eck.agent as agent_mod

        analyzer = TraceAnalyzer()
        a = _agent(trace_analyzer=analyzer)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        traces = analyzer.list_traces()
        self.assertEqual(len(traces), 1)

        events = analyzer.get_trace(traces[0])
        event_types = [e["event_type"] for e in events]
        self.assertIn("step.start", event_types)
        self.assertIn("step.end", event_types)

    def test_analyzer_trace_id_matches_agent_trace_id(self) -> None:
        """Events in the analyzer carry the same trace_id as the agent."""
        import eck.agent as agent_mod

        analyzer = TraceAnalyzer()
        a = _agent(trace_analyzer=analyzer)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        self.assertIn(a._trace_id, analyzer.list_traces())

    def test_analyzer_events_are_plain_dicts(self) -> None:
        """Events stored in the analyzer are plain dicts — no live kernel objects."""
        import eck.agent as agent_mod

        analyzer = TraceAnalyzer()
        a = _agent(trace_analyzer=analyzer)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            a.step()

        for event in analyzer.get_trace(a._trace_id):
            self.assertIsInstance(event, dict)


class TestAnalyzerBehavioralEquivalence(unittest.TestCase):
    """Analyzer presence must not alter agent control outcomes."""

    def _run_step(self, trace_analyzer: TraceAnalyzer | None) -> bool:
        import eck.agent as agent_mod

        a = _agent(trace_analyzer=trace_analyzer)
        a.seed("task")

        with patch.object(agent_mod, "propose_execution", return_value=None), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate", return_value=_critic_deferred()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(a.drift, "snapshot", return_value=_snap()):
            return a.step()

    def test_step_return_value_identical_with_and_without_analyzer(self) -> None:
        """step() returns the same value regardless of analyzer presence."""
        result_without = self._run_step(trace_analyzer=None)
        result_with = self._run_step(trace_analyzer=TraceAnalyzer())
        self.assertEqual(result_without, result_with)

    def test_no_analyzer_does_not_raise(self) -> None:
        """Agent runs without error when no analyzer is provided."""
        result = self._run_step(trace_analyzer=None)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()

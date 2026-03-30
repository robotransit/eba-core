# tests/test_telemetry_wiring.py
"""
Trace-coherence integration tests for the ECK telemetry wiring (ADR-045).

These tests verify that the live agent loop produces coherent per-step
traces — correct event sequence, consistent identifiers across all events
in a cycle, correct nonce progression, correct trace scoping across runs,
and replay silence.

These are integration tests, not unit tests for individual emitters.
The instrumented components — propose_execution, DefaultPolicyGate.evaluate,
authorize_and_perform, ConfidenceSignal.update — run for real. Only the
lower seams they depend on are patched: generate_prediction, critic_evaluate,
generate_subtasks, drift methods, and the LLM callable.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from eck.agent import ECKAgent
from eck.confidence import ConfidenceSignal
from eck.config import ECKConfig, PolicyMode
from eck.types import make_critic_outcome


# ── LLM stubs ─────────────────────────────────────────────────────────────────

def _llm_wiring(prompt: str) -> str:
    """
    LLM stub for wiring tests.

    propose_execution sends a prompt containing 'Respond with ONLY valid JSON'.
    authorize_and_perform passes the extracted prompt parameter value directly.
    All other callers (generate_prediction etc.) are patched out at the seam level.
    """
    if "Respond with ONLY valid JSON" in prompt:
        return json.dumps({
            "action_type": "llm_query",
            "parameters": {"prompt": "do the thing"},
        })
    return "outcome string"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _critic_success():
    """(CriticOutcome, None) for a successful evaluation."""
    return (make_critic_outcome(category="success", severity=0.1, feedback="ok"), None)


def _snap(severe: bool = False) -> dict:
    """Minimal drift snapshot."""
    return {
        "drift_streak": 0,
        "total_drift_events": 0,
        "last_error_z": 0.0,
        "numeric_bias": 0.0,
        "feasibility_sample_count": 0,
        "numeric_success_rate": None,
        "severe": severe,
    }


def _agent(goal_completion_threshold: float = 0.99) -> ECKAgent:
    """
    Construct a test ECKAgent using the real DefaultPolicyGate.

    Confidence is seeded to 0.95 so DefaultPolicyGate returns EXECUTE.
    goal_completion_threshold is high by default to prevent early exit
    in multi-step tests.
    """
    config = ECKConfig(
        policy_mode=PolicyMode.NORMAL,
        goal_completion_threshold=goal_completion_threshold,
    )
    agent = ECKAgent(
        objective="Test objective",
        llm_call=_llm_wiring,
        config=config,
    )
    # Seed confidence above DefaultPolicyGate.DEGRADE_THRESHOLD (0.90)
    # so the gate returns EXECUTE on the first cycle.
    agent._confidence._value = 0.95
    return agent


# ── Telemetry collection helpers ──────────────────────────────────────────────

def _collect_telemetry_events(mock_logger: MagicMock) -> list[dict]:
    """Extract all telemetry_event dicts from all logger.info calls.

    Harvests INFO-level calls only — sufficient for the canonical success
    paths exercised in this file, which emit all telemetry at INFO severity.
    Extend to warning/error call_args_list if ERROR-severity paths are added.
    """
    events = []
    for call in mock_logger.info.call_args_list:
        kwargs = call.kwargs if call.kwargs else {}
        extra = kwargs.get("extra", {})
        if "telemetry_event" in extra:
            events.append(extra["telemetry_event"])
    return events


def _run_canonical_step(agent: ECKAgent) -> tuple[list[dict], MagicMock]:
    """
    Drive one canonical successful step() with real instrumented components.

    Real components (telemetry wiring verified):
      - propose_execution(...)
      - DefaultPolicyGate.evaluate(...)
      - authorize_and_perform(...)
      - ConfidenceSignal.update(...)

    Patched lower seams:
      - generate_prediction — returns a fixed string
      - critic_evaluate — returns success
      - generate_subtasks — returns empty list
      - drift.record_error — returns False
      - drift.snapshot — returns non-severe snapshot

    Logger patching:
      - eck.agent.logger patched to mock_logger
      - eck.policy_gate.logger patched to mock_logger
      - eck.execution.logger patched to mock_logger
      - agent._confidence._logger set to mock_logger (instance attribute —
        module-level patch does not reach the stored instance reference)

    Returns (events, mock_logger).
    """
    import eck.agent as agent_mod

    mock_logger = MagicMock()
    agent._confidence._logger = mock_logger

    with patch("eck.agent.logger", mock_logger), \
         patch("eck.policy_gate.logger", mock_logger), \
         patch("eck.execution.logger", mock_logger), \
         patch.object(agent_mod, "generate_prediction", return_value="pred"), \
         patch.object(agent_mod, "critic_evaluate", return_value=_critic_success()), \
         patch.object(agent_mod, "generate_subtasks", return_value=[]), \
         patch.object(agent.drift, "record_error", return_value=False), \
         patch.object(agent.drift, "snapshot", return_value=_snap(severe=False)):
        agent.step()

    return _collect_telemetry_events(mock_logger), mock_logger


# ─────────────────────────────────────────────────────────────────────────────
# Test classes
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleStepTraceCoherence(unittest.TestCase):
    """Single canonical step produces a coherent six-event trace."""

    def setUp(self) -> None:
        self.agent = _agent()
        self.agent.seed("task")
        self.events, _ = _run_canonical_step(self.agent)

    def test_exactly_six_telemetry_events_emitted(self) -> None:
        """Exactly six telemetry events are emitted for a canonical step."""
        self.assertEqual(len(self.events), 6)

    def test_event_sequence_is_correct(self) -> None:
        """Six events are emitted in the canonical ADR-045 order."""
        event_types = [e["event_type"] for e in self.events]
        self.assertEqual(event_types, [
            "step.start",
            "action.proposed",
            "policy.evaluate",
            "action.executed",
            "epistemic.signal",
            "step.end",
        ])

    def test_all_events_share_trace_id(self) -> None:
        """All six events carry the same trace_id."""
        trace_ids = {e["trace_id"] for e in self.events}
        self.assertEqual(len(trace_ids), 1)

    def test_all_events_share_step_id(self) -> None:
        """All six events carry the same step_id."""
        step_ids = {e["step_id"] for e in self.events}
        self.assertEqual(len(step_ids), 1)

    def test_all_events_share_deterministic_nonce(self) -> None:
        """All six events carry the same deterministic_nonce."""
        nonces = {e["deterministic_nonce"] for e in self.events}
        self.assertEqual(len(nonces), 1)

    def test_first_step_uses_nonce_zero(self) -> None:
        """First step uses deterministic_nonce=0."""
        self.assertEqual(self.events[0]["deterministic_nonce"], 0)

    def test_step_id_encodes_trace_id_and_nonce(self) -> None:
        """step_id is derived from trace_id and nonce in canonical form."""
        trace_id = self.events[0]["trace_id"]
        nonce = self.events[0]["deterministic_nonce"]
        step_id = self.events[0]["step_id"]
        self.assertEqual(step_id, f"{trace_id}:step:{nonce}")

    def test_action_proposed_has_proposal_present_true(self) -> None:
        """action.proposed event carries proposal_present=True on success path."""
        proposed = next(
            e for e in self.events if e["event_type"] == "action.proposed"
        )
        self.assertTrue(proposed["payload"]["proposal_present"])

    def test_policy_evaluate_has_execute_mode(self) -> None:
        """policy.evaluate event carries mode=EXECUTE on success path."""
        evaluated = next(
            e for e in self.events if e["event_type"] == "policy.evaluate"
        )
        self.assertEqual(evaluated["payload"]["mode"], "EXECUTE")

    def test_action_executed_has_performed_true(self) -> None:
        """action.executed event carries performed=True on success path."""
        executed = next(
            e for e in self.events if e["event_type"] == "action.executed"
        )
        self.assertTrue(executed["payload"]["performed"])

    def test_epistemic_signal_has_updated_true(self) -> None:
        """epistemic.signal event carries updated=True on success path."""
        signal = next(
            e for e in self.events if e["event_type"] == "epistemic.signal"
        )
        self.assertTrue(signal["payload"]["updated"])


class TestStepBoundaryClosure(unittest.TestCase):
    """Every step.start has exactly one corresponding step.end."""

    def test_single_step_has_matched_start_and_end(self) -> None:
        """One step.start and one step.end with matching identifiers."""
        agent = _agent()
        agent.seed("task")
        events, _ = _run_canonical_step(agent)

        starts = [e for e in events if e["event_type"] == "step.start"]
        ends = [e for e in events if e["event_type"] == "step.end"]

        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)
        self.assertEqual(starts[0]["trace_id"], ends[0]["trace_id"])
        self.assertEqual(starts[0]["step_id"], ends[0]["step_id"])
        self.assertEqual(
            starts[0]["deterministic_nonce"],
            ends[0]["deterministic_nonce"],
        )

    def test_two_steps_produce_two_matched_pairs(self) -> None:
        """Two steps produce two start/end pairs, each internally consistent."""
        import eck.agent as agent_mod

        agent = _agent()
        mock_logger = MagicMock()
        agent._confidence._logger = mock_logger

        for i in range(2):
            # Reset confidence above DEGRADE_THRESHOLD before each step —
            # ensures DefaultPolicyGate returns EXECUTE on every cycle
            # regardless of confidence carry-through from the prior update.
            # These tests verify trace coherence, not confidence trajectory.
            agent._confidence._value = 0.95
            agent.seed(f"task_{i}")
            with patch("eck.agent.logger", mock_logger), \
                 patch("eck.policy_gate.logger", mock_logger), \
                 patch("eck.execution.logger", mock_logger), \
                 patch.object(agent_mod, "generate_prediction",
                              return_value="pred"), \
                 patch.object(agent_mod, "critic_evaluate",
                              return_value=_critic_success()), \
                 patch.object(agent_mod, "generate_subtasks", return_value=[]), \
                 patch.object(agent.drift, "record_error", return_value=False), \
                 patch.object(agent.drift, "snapshot",
                              return_value=_snap(severe=False)):
                agent.step()

        events = _collect_telemetry_events(mock_logger)
        starts = [e for e in events if e["event_type"] == "step.start"]
        ends = [e for e in events if e["event_type"] == "step.end"]

        self.assertEqual(len(starts), 2)
        self.assertEqual(len(ends), 2)

        for start, end in zip(starts, ends):
            self.assertEqual(start["trace_id"], end["trace_id"])
            self.assertEqual(start["step_id"], end["step_id"])
            self.assertEqual(
                start["deterministic_nonce"],
                end["deterministic_nonce"],
            )


class TestNonceProgression(unittest.TestCase):
    """deterministic_nonce increments correctly across steps."""

    def _run_two_steps(self) -> list[dict]:
        """Run two canonical steps and return all telemetry events."""
        import eck.agent as agent_mod

        agent = _agent()
        mock_logger = MagicMock()
        agent._confidence._logger = mock_logger

        for i in range(2):
            # Reset confidence above DEGRADE_THRESHOLD before each step —
            # ensures DefaultPolicyGate returns EXECUTE on every cycle
            # regardless of confidence carry-through from the prior update.
            # These tests verify nonce progression, not confidence trajectory.
            agent._confidence._value = 0.95
            agent.seed(f"task_{i}")
            with patch("eck.agent.logger", mock_logger), \
                 patch("eck.policy_gate.logger", mock_logger), \
                 patch("eck.execution.logger", mock_logger), \
                 patch.object(agent_mod, "generate_prediction",
                              return_value="pred"), \
                 patch.object(agent_mod, "critic_evaluate",
                              return_value=_critic_success()), \
                 patch.object(agent_mod, "generate_subtasks", return_value=[]), \
                 patch.object(agent.drift, "record_error", return_value=False), \
                 patch.object(agent.drift, "snapshot",
                              return_value=_snap(severe=False)):
                agent.step()

        return _collect_telemetry_events(mock_logger)

    def test_first_step_uses_nonce_zero(self) -> None:
        """First step's step.start carries deterministic_nonce=0."""
        events = self._run_two_steps()
        starts = [e for e in events if e["event_type"] == "step.start"]
        self.assertEqual(starts[0]["deterministic_nonce"], 0)

    def test_second_step_uses_nonce_one(self) -> None:
        """Second step's step.start carries deterministic_nonce=1."""
        events = self._run_two_steps()
        starts = [e for e in events if e["event_type"] == "step.start"]
        self.assertEqual(starts[1]["deterministic_nonce"], 1)

    def test_all_events_in_first_step_use_nonce_zero(self) -> None:
        """All six events in the first step carry deterministic_nonce=0."""
        events = self._run_two_steps()
        step_one_events = [e for e in events if e["deterministic_nonce"] == 0]
        self.assertEqual(len(step_one_events), 6)

    def test_all_events_in_second_step_use_nonce_one(self) -> None:
        """All six events in the second step carry deterministic_nonce=1."""
        events = self._run_two_steps()
        step_two_events = [e for e in events if e["deterministic_nonce"] == 1]
        self.assertEqual(len(step_two_events), 6)


class TestTraceScopingAcrossRuns(unittest.TestCase):
    """run() refreshes trace_id — events from separate runs carry distinct trace_ids."""

    def test_two_runs_produce_distinct_trace_ids(self) -> None:
        """Events from run 1 and run 2 carry different trace_ids.

        A fresh agent is constructed for each run to isolate trace scoping
        behavior from cumulative agent state effects.
        """
        import eck.agent as agent_mod

        run_trace_ids = []

        for _ in range(2):
            agent = _agent(goal_completion_threshold=0.0)
            agent.seed("task")
            mock_logger = MagicMock()
            agent._confidence._logger = mock_logger

            with patch("eck.agent.logger", mock_logger), \
                 patch("eck.policy_gate.logger", mock_logger), \
                 patch("eck.execution.logger", mock_logger), \
                 patch.object(agent_mod, "generate_prediction",
                              return_value="pred"), \
                 patch.object(agent_mod, "critic_evaluate",
                              return_value=_critic_success()), \
                 patch.object(agent_mod, "generate_subtasks", return_value=[]), \
                 patch.object(agent.drift, "record_error", return_value=False), \
                 patch.object(agent.drift, "snapshot",
                              return_value=_snap(severe=False)):
                agent.run()

            events = _collect_telemetry_events(mock_logger)
            trace_ids = {e["trace_id"] for e in events}
            self.assertEqual(
                len(trace_ids), 1,
                "All events within a run must share one trace_id",
            )
            run_trace_ids.append(trace_ids.pop())

        self.assertNotEqual(
            run_trace_ids[0],
            run_trace_ids[1],
            "Separate runs must produce distinct trace_ids",
        )

    def test_all_events_within_run_share_trace_id(self) -> None:
        """All telemetry events within a single minimal run share the same trace_id."""
        import eck.agent as agent_mod

        # Single task, goal_completion_threshold=0.0 — one step, one run,
        # minimal surface to prove trace_id sharing.
        agent = _agent(goal_completion_threshold=0.0)
        mock_logger = MagicMock()
        agent._confidence._logger = mock_logger
        agent.seed("task")

        with patch("eck.agent.logger", mock_logger), \
             patch("eck.policy_gate.logger", mock_logger), \
             patch("eck.execution.logger", mock_logger), \
             patch.object(agent_mod, "generate_prediction", return_value="pred"), \
             patch.object(agent_mod, "critic_evaluate",
                          return_value=_critic_success()), \
             patch.object(agent_mod, "generate_subtasks", return_value=[]), \
             patch.object(agent.drift, "record_error", return_value=False), \
             patch.object(agent.drift, "snapshot",
                          return_value=_snap(severe=False)):
            agent.run()

        events = _collect_telemetry_events(mock_logger)
        trace_ids = {e["trace_id"] for e in events}
        self.assertEqual(len(trace_ids), 1)


class TestReplaySilence(unittest.TestCase):
    """ConfidenceSignal.replay() emits no epistemic.signal events."""

    def test_replay_produces_no_epistemic_signal_events(self) -> None:
        """replay() is telemetry-silent — no epistemic.signal events emitted."""
        conf = ConfidenceSignal(alpha=0.3)
        mock_logger = MagicMock()
        conf._logger = mock_logger

        outcomes = [
            (make_critic_outcome("success", 0.2, "ok"), None),
            (make_critic_outcome("failure", 0.7, "fail"), None),
            (make_critic_outcome("deferred", 0.0, "deferred"), None),
        ]
        conf.replay(outcomes)

        events = _collect_telemetry_events(mock_logger)
        epistemic_events = [
            e for e in events if e["event_type"] == "epistemic.signal"
        ]
        self.assertEqual(len(epistemic_events), 0)

    def test_replay_produces_no_telemetry_events_at_all(self) -> None:
        """replay() produces no telemetry events of any kind."""
        conf = ConfidenceSignal(alpha=0.3)
        mock_logger = MagicMock()
        conf._logger = mock_logger

        outcomes = [
            (make_critic_outcome("success", 0.2, "ok"), None),
            (make_critic_outcome("failure", 0.8, "fail"), None),
        ]
        conf.replay(outcomes)

        events = _collect_telemetry_events(mock_logger)
        self.assertEqual(len(events), 0)

    def test_live_update_emits_but_replay_does_not(self) -> None:
        """Live update() with telemetry args emits; replay() does not."""
        conf = ConfidenceSignal(alpha=0.3)
        mock_logger = MagicMock()
        conf._logger = mock_logger

        conf.update(
            make_critic_outcome("success", 0.2, "ok"),
            trace_id="trace-test",
            step_id="trace-test:step:0",
            deterministic_nonce=0,
        )
        live_events = _collect_telemetry_events(mock_logger)
        self.assertEqual(len(live_events), 1)
        self.assertEqual(live_events[0]["event_type"], "epistemic.signal")

        mock_logger.reset_mock()
        outcomes = [
            (make_critic_outcome("success", 0.2, "ok"), None),
            (make_critic_outcome("failure", 0.7, "fail"), None),
        ]
        conf.replay(outcomes)
        replay_events = _collect_telemetry_events(mock_logger)
        self.assertEqual(len(replay_events), 0)


if __name__ == "__main__":
    unittest.main()

"""TraceHarness — high-level entry point for v0.5.0 empirical work.

Convenience wrapper for live collection and replay.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from eck.agent import ECKAgent
from eck.policy_gate import PolicyGate

from .trace_recorder import TraceRecorder
from .trace_store import TraceStore
from .trace_types import RunTrace


class TraceHarness:
    """High-level harness for trace collection and replay."""

    def __init__(
        self,
        objective: str,
        llm_call: Callable[[str], str],
        policy_gate: PolicyGate | None = None,
        store: Optional[TraceStore] = None,
    ):
        self.objective = objective
        self.llm_call = llm_call
        self.policy_gate = policy_gate
        self.store = store or TraceStore()

        self.recorder = TraceRecorder()
        self.agent = ECKAgent(
            objective=objective,
            llm_call=llm_call,
            policy_gate=policy_gate,
            trace_analyzer=self.recorder,
        )

    def run(self, max_steps: int = 50, seed_task: str | None = None) -> RunTrace:
        """Run the agent and collect a full trace."""
        self.recorder.start_run(trace_id=self.agent._trace_id, objective=self.objective)

        if seed_task:
            self.agent.seed(seed_task)
        else:
            self.agent.seed()

        for _ in range(max_steps):
            continued = self.agent.step()
            if not continued:
                break

        trace = self.recorder.finalize()
        return trace

    def save_last_run(self, filename: str | None = None) -> Path:
        """Save the last run to disk."""
        if not self.recorder.current_run:
            raise ValueError("No run to save")
        return self.store.save_run(self.recorder.current_run, filename)

    def load_run(self, filename: str | Path) -> Optional[RunTrace]:
        """Load a previously saved run."""
        return self.store.load_run(filename)

"""TraceRecorder for v0.5.0 harness.

Observational only. Builds StepTrace/RunTrace from telemetry events.
Follows the one-way ingest pattern from Trace Analysis Service (ADR-045).
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from .trace_types import Event, StepTrace, RunTrace


class TraceRecorder:
    """Builds structured traces from telemetry events.

    Purely observational. No control authority.
    """

    def __init__(self):
        self.current_run: Optional[RunTrace] = None
        self.current_step: Optional[StepTrace] = None
        self._active_trace_id: Optional[str] = None

    def start_run(self, trace_id: str, objective: str) -> None:
        """Start a new run trace."""
        self.current_run = RunTrace(trace_id=trace_id, objective=objective)
        self._active_trace_id = trace_id

    def ingest(self, events: List[Dict[str, Any]]) -> None:
        """Ingest plain-dict events (matches TraceAnalyzer pattern)."""
        for raw in events:
            if not isinstance(raw, dict):
                continue

            event = Event(
                event_type=raw.get("event_type", ""),
                version=raw.get("version", "1.0"),
                timestamp=raw.get("timestamp", time.time()),
                trace_id=raw.get("trace_id", ""),
                step_id=raw.get("step_id", ""),
                deterministic_nonce=raw.get("deterministic_nonce", 0),
                severity=raw.get("severity", "INFO"),
                source=raw.get("source", ""),
                payload=raw.get("payload", {}),
            )

            self._process_event(event)

    def _process_event(self, event: Event) -> None:
        """Route event to current step/run."""
        if not self.current_run:
            self.start_run(event.trace_id, "Unknown objective")

        # Start new step if needed
        if not self.current_step or self.current_step.step_id != event.step_id:
            if self.current_step:
                self.current_step.finalize()
                self.current_run.add_step(self.current_step)

            self.current_step = StepTrace(
                step_id=event.step_id,
                trace_id=event.trace_id
            )

        self.current_step.events.append(event)

    def finalize(self) -> Optional[RunTrace]:
        """Finalize current step and run."""
        if self.current_step:
            self.current_step.finalize()
            if self.current_run:
                self.current_run.add_step(self.current_step)
            self.current_step = None

        if self.current_run:
            self.current_run.finalize()

        return self.current_run

    def clear(self) -> None:
        """Reset for a new run."""
        self.current_run = None
        self.current_step = None
        self._active_trace_id = None

"""
Trace Analysis Service — minimal read-only implementation.

NO-CONTROL-AUTHORITY INVARIANT (load-bearing)
- This module is strictly read-only.
- It must never influence policy, confidence, execution, or any other control surface.
- Information flow is one-way only: raw telemetry event dicts are ingested here and
  analysed/rendered for operator visibility only.
- No output from this module may be treated as an instruction, policy input, or
  execution control signal.

STRUCTURAL GUARDS
- Zero imports from any eck.* module.
- Operates only on plain list[dict] raw event payloads.
- ingest() immediately deep-copies every accepted incoming event to prevent
  aliasing and mutation.
- Events without a trace_id are silently skipped.
- Public outputs are plain data only: dict, list, str, or None.
- Returned event dicts are defensive deep copies so callers cannot mutate
  analyzer state.
"""

from copy import deepcopy
from typing import Any


# Minimal first version only.
# Advanced analysis and richer rendering are intentionally deferred.
class TraceAnalyzer:
    # Returns plain data only. Must never be consumed by control surfaces.
    def __init__(self) -> None:
        self._traces: dict[str, list[dict[str, Any]]] = {}

    # Returns plain data only. Must never be consumed by control surfaces.
    def ingest(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            trace_id = event.get("trace_id")
            if not isinstance(trace_id, str):
                continue

            if trace_id not in self._traces:
                self._traces[trace_id] = []

            self._traces[trace_id].append(deepcopy(event))

    # Returns plain data only. Must never be consumed by control surfaces.
    def list_traces(self) -> list[str]:
        return sorted(self._traces.keys())

    # Returns plain data only. Must never be consumed by control surfaces.
    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        events = self._traces.get(trace_id, [])
        return [deepcopy(event) for event in events]

    # Returns plain data only. Must never be consumed by control surfaces.
    def filter_by_event_type(
        self,
        event_type: str,
        trace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if trace_id is not None:
            events = self._traces.get(trace_id, [])
            return [
                deepcopy(event)
                for event in events
                if event.get("event_type") == event_type
            ]

        result: list[dict[str, Any]] = []
        for events in self._traces.values():
            for event in events:
                if event.get("event_type") == event_type:
                    result.append(deepcopy(event))
        return result

    # Returns plain data only. Must never be consumed by control surfaces.
    def summarise_trace(self, trace_id: str) -> dict[str, Any] | None:
        events = self._traces.get(trace_id)
        if not events:
            return None

        event_types: list[str] = []
        seen_event_types: set[str] = set()
        severity_counts: dict[str, int] = {}

        for event in events:
            event_type = event.get("event_type")
            if isinstance(event_type, str) and event_type not in seen_event_types:
                seen_event_types.add(event_type)
                event_types.append(event_type)

            # Treat missing or empty severity as "UNKNOWN" (falsy values are meaningless here)
            severity = event.get("severity") or "UNKNOWN"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        return {
            "trace_id": trace_id,
            "event_count": len(events),
            "event_types": event_types,
            "severity_counts": severity_counts,
        }

    # Returns plain data only. Must never be consumed by control surfaces.
    def render_trace(self, trace_id: str) -> str:
        events = self._traces.get(trace_id, [])

        lines: list[str] = [f"trace_id={trace_id}"]
        for event in events:
            event_type = event.get("event_type", "<missing>")
            severity = event.get("severity", "<missing>")
            lines.append(f"{event_type} {severity}")

        return "\n".join(lines)

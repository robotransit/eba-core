"""TraceStore for v0.5.0 harness.

Simple append-only storage for RunTrace / StepTrace (JSONL format).
Replay-safe and schema-aligned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from .trace_types import RunTrace, StepTrace


class TraceStore:
    """Append-only store for traces (JSONL)."""

    def __init__(self, base_dir: str | Path = "traces"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, run: RunTrace, filename: str | None = None) -> Path:
        """Save a full run as JSONL."""
        if filename is None:
            filename = f"run_{run.trace_id}.jsonl"

        path = self.base_dir / filename

        with open(path, "w", encoding="utf-8") as f:
            # Write run metadata as first line
            f.write(json.dumps({
                "type": "run_metadata",
                "trace_id": run.trace_id,
                "objective": run.objective,
                "total_steps": run.total_steps,
                "halted": run.halted,
                "final_policy_mode": run.final_policy_mode,
            }) + "\n")

            # Write each step
            for step in run.steps:
                step_dict = {
                    "type": "step",
                    "step_id": step.step_id,
                    "events": [e.to_dict() for e in step.events],
                    "proposed_action": step.proposed_action,
                    "policy_decision": step.policy_decision,
                    "execution_result": step.execution_result,
                    "critic_outcome": step.critic_outcome,
                    "confidence_before": step.confidence_before,
                    "confidence_after": step.confidence_after,
                    "policy_mode": step.policy_mode,
                    "outcome_category": step.outcome_category,
                }
                f.write(json.dumps(step_dict) + "\n")

        return path

    def load_run(self, filename: str | Path) -> Optional[RunTrace]:
        """Load a run from JSONL."""
        path = Path(filename)
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return None

        # First line is run metadata
        metadata = json.loads(lines[0])
        run = RunTrace(
            trace_id=metadata["trace_id"],
            objective=metadata.get("objective", "")
        )

        # Remaining lines are steps
        for line in lines[1:]:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("type") != "step":
                continue

            step = StepTrace(
                step_id=data["step_id"],
                trace_id=run.trace_id
            )

            # Reconstruct events
            for e_dict in data.get("events", []):
                step.events.append(Event(
                    event_type=e_dict["event_type"],
                    version=e_dict.get("version", "1.0"),
                    timestamp=e_dict["timestamp"],
                    trace_id=e_dict["trace_id"],
                    step_id=e_dict["step_id"],
                    deterministic_nonce=e_dict["deterministic_nonce"],
                    severity=e_dict["severity"],
                    source=e_dict["source"],
                    payload=e_dict["payload"],
                ))

            step.proposed_action = data.get("proposed_action")
            step.policy_decision = data.get("policy_decision")
            step.execution_result = data.get("execution_result")
            step.critic_outcome = data.get("critic_outcome")
            step.confidence_before = data.get("confidence_before")
            step.confidence_after = data.get("confidence_after")
            step.policy_mode = data.get("policy_mode")
            step.outcome_category = data.get("outcome_category")

            run.add_step(step)

        run.finalize()
        return run

    def list_traces(self) -> List[str]:
        """List available trace files."""
        return [f.name for f in self.base_dir.glob("run_*.jsonl")]

"""Core trace data models for ECK v0.5.0 empirical work.

Aligned to telemetry.schema.json (ADR-045).
Purely observational / analytical structures — never imported into control path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Event:
    """Canonical telemetry event (matches telemetry.schema.json)."""
    event_type: str                    # From enum: step.start, policy.evaluate, etc.
    version: str                       # e.g. "1.0"
    timestamp: float                   # Wall-clock time (seconds since epoch)
    trace_id: str
    step_id: str
    deterministic_nonce: int
    severity: str                      # DEBUG, INFO, WARNING, ERROR
    source: str
    payload: Dict[str, Any]            # Event-specific data

    def to_dict(self) -> Dict[str, Any]:
        """Serialize back to schema-compliant dict."""
        return {
            "event_type": self.event_type,
            "version": self.version,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "step_id": self.step_id,
            "deterministic_nonce": self.deterministic_nonce,
            "severity": self.severity,
            "source": self.source,
            "payload": self.payload,
        }


@dataclass
class StepTrace:
    """Complete record of one control cycle."""
    step_id: str
    trace_id: str

    events: List[Event] = field(default_factory=list)

    # Enriched fields for analysis
    proposed_action: Optional[Dict[str, Any]] = None
    policy_decision: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    critic_outcome: Optional[Dict[str, Any]] = None
    partial_structure: Optional[Dict[str, Any]] = None

    confidence_before: Optional[float] = None
    confidence_after: Optional[float] = None
    confidence_delta: Optional[float] = None

    policy_mode: Optional[str] = None
    outcome_category: Optional[str] = None

    task_id: Optional[str] = None
    task_text: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> None:
        """Populate derived fields from events (call after collection)."""
        if not self.events:
            return

        for ev in self.events:
            p = ev.payload or {}

            if ev.event_type == "step.start":
                self.task_id = p.get("task_id")
                self.task_text = p.get("task_text")
                self.policy_mode = p.get("policy_mode")
                self.confidence_before = p.get("current_confidence")

            elif ev.event_type in ("action.proposed", "propose_execution"):
                self.proposed_action = p.get("proposed_action") or p

            elif ev.event_type in ("policy.evaluate", "policy.decision"):
                self.policy_decision = p
                if "mode" in p:
                    self.policy_mode = p.get("mode")

            elif ev.event_type in ("action.executed", "authorize_and_perform"):
                self.execution_result = p.get("execution_result") or p

            elif ev.event_type in ("critic.evaluate", "critic_outcome"):
                self.critic_outcome = p
                self.partial_structure = p.get("partial_structure")

            elif ev.event_type == "epistemic.signal":
                if self.confidence_after is None:
                    self.confidence_after = p.get("confidence")

        if self.confidence_before is not None and self.confidence_after is not None:
            self.confidence_delta = self.confidence_after - self.confidence_before

        if self.outcome_category is None and self.policy_decision:
            mode = str(self.policy_decision.get("mode", "")).upper()
            if mode in ("EXECUTE", "AUTHORIZED"):
                self.outcome_category = "executed"
            elif mode in ("RETRY", "GUIDED", "ENFORCED"):
                self.outcome_category = "deferred_or_guided"
            elif mode == "HALT":
                self.outcome_category = "halted"


@dataclass
class RunTrace:
    """Complete record of one agent run."""
    trace_id: str
    objective: str

    steps: List[StepTrace] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)

    start_time: Optional[float] = None
    end_time: Optional[float] = None
    total_steps: int = 0
    halted: bool = False
    final_policy_mode: Optional[str] = None

    def add_step(self, step: StepTrace) -> None:
        self.steps.append(step)
        self.total_steps = len(self.steps)
        if step.policy_mode:
            self.final_policy_mode = step.policy_mode
        if step.outcome_category == "halted":
            self.halted = True

    def finalize(self) -> None:
        for step in self.steps:
            step.finalize()
        self.total_steps = len(self.steps)
        if self.steps:
            self.final_policy_mode = self.steps[-1].policy_mode

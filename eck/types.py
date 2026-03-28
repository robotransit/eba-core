# eck/types.py
"""
Shared kernel types for the Epistemic Control Kernel (ECK).

This module is the single source of truth for types that cross
subsystem boundaries. No behavioural logic lives here — only
type definitions and their invariants.

Current inhabitants:
  - CriticOutcome: primary epistemic signal from critic → confidence
  - PartialStructure: structural enrichment for Partial outcomes
  - make_critic_outcome: canonical constructor enforcing derived fields
  - ProposedAction: structured, advisory action proposal (ADR-042)
  - ExecutionResult: structured execution boundary output (ADR-042)

ADR references:
  - ADR-022: Failure vs Non-Failure Classification (category taxonomy)
  - ADR-024: Minimal Input Signal Set (admissible signals)
  - ADR-025: Confidence Update Mechanics (EWMA consumer)
  - ADR-042: Propose/Authorize/Perform Execution Boundary
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, NamedTuple


# ── Critic outcome taxonomy (ADR-022) ─────────────────────────────────────────

class CriticOutcome(NamedTuple):
    """
    Primary epistemic signal produced by the critic and consumed by the
    confidence signal processor.

    category: locked ADR-022 taxonomy (lowercase, kernel-canonical)
        "success"  — result met constraints; upward confidence permitted
        "partial"  — low-severity failure; both directions permitted,
                     no failure window triggered
        "failure"  — hard constraint violation; downward + failure window
        "rejected" — execution was refused by gate or kernel authorization;
                     no confidence update (ADR-021)
        "deferred" — no valid proposal was produced this cycle;
                     no confidence update (ADR-021)

    severity: float [0.0, 1.0]
        Scales the magnitude of confidence delta within the category.
        Never reclassifies the category (ADR-022 invariant).
        0.0 = trivial / perfect alignment
        1.0 = maximal impact within category

    feedback: human-readable explanation from critic (advisory only)

    success: derived convenience bool — True only when category == "success"
        Never set directly — use make_critic_outcome() to construct.
    """
    category: Literal["success", "partial", "failure", "rejected", "deferred"]
    severity: float
    feedback: str
    success: bool


def make_critic_outcome(
    category: Literal["success", "partial", "failure", "rejected", "deferred"],
    severity: float,
    feedback: str,
) -> CriticOutcome:
    """
    Canonical constructor for CriticOutcome.

    Derives the success field from category — never set directly.
    Use this instead of constructing CriticOutcome directly to ensure
    the success field is always consistent with category.
    """
    return CriticOutcome(
        category=category,
        severity=severity,
        feedback=feedback,
        success=(category == "success"),
    )


# ── Partial outcome structural enrichment ─────────────────────────────────────

class ConflictKind(Enum):
    """Coarse classification of what kind of conflict produced a Partial outcome."""
    EVIDENCE_CONFLICT = "evidence_conflict"
    CONSTRAINT_CONFLICT = "constraint_conflict"
    DECOMPOSITION_CONFLICT = "decomposition_conflict"
    RESOLUTION_INSTABILITY = "resolution_instability"


class ConflictLocus(Enum):
    """Where in the reasoning the conflict is located."""
    FACTUAL = "factual"
    INSTRUCTION = "instruction"
    FORMAT = "format"
    CONSISTENCY = "consistency"
    LOCAL = "local"
    GLOBAL = "global"


class PartialStructure(NamedTuple):
    """
    Structural enrichment for Partial outcomes.

    Required by confidence.py when category == "partial" to determine
    the MovementClass (which confidence directions are permitted).

    collapse_status: always "unresolved" in v0.2.0 — reserved for
        future resolution tracking.
    conflict_kind: drives MovementClass mapping in confidence.py
    conflict_footprint: set of ConflictLocus values indicating
        where the conflict manifests
    """
    collapse_status: Literal["unresolved"]
    conflict_kind: ConflictKind
    conflict_footprint: frozenset[ConflictLocus]


# ── Execution boundary types (ADR-042) ────────────────────────────────────────

@dataclass(frozen=True)
class ProposedAction:
    """
    Structured, typed, kernel-inspectable action proposal (ADR-042).

    Advisory only — carries no authority. Produced by propose_execution()
    and consumed by authorize_and_perform() and PolicyGate.evaluate().

    Crosses subsystem boundaries:
        execution.py, policy_gate.py, agent.py, tests, observability

    Invariants (enforced at construction):
        - immutable (frozen dataclass)
        - action_type must be a non-empty string
        - task_id must be a non-empty string
        - provenance_id must be a non-empty string
        - parameters must be a dict (may be empty)
        - task_text must be a string

    Compliant proposals must not contain executable code or callable
    objects; this is enforced by proposal construction, not recursively
    by this type.

    In compliant implementations, ProposedAction MUST be constructed via
    propose_execution() and not constructed directly in other code paths.
    """
    action_type: str
    parameters: dict[str, object]
    task_text: str
    task_id: str
    provenance_id: str

    def __post_init__(self) -> None:
        if not self.action_type or not self.action_type.strip():
            raise ValueError(
                "ProposedAction.action_type must be a non-empty string"
            )
        if not isinstance(self.parameters, dict):
            raise ValueError(
                "ProposedAction.parameters must be a dict (may be empty)"
            )
        if not isinstance(self.task_text, str):
            raise ValueError(
                "ProposedAction.task_text must be a string"
            )
        if not self.task_id or not self.task_id.strip():
            raise ValueError(
                "ProposedAction.task_id must be a non-empty string"
            )
        if not self.provenance_id or not self.provenance_id.strip():
            raise ValueError(
                "ProposedAction.provenance_id must be a non-empty string"
            )


@dataclass(frozen=True)
class ExecutionResult:
    """
    Structured output of the execution boundary (ADR-042).

    Produced by authorize_and_perform() and consumed by agent.py,
    critic.py, and observability layer.

    Crosses subsystem boundaries:
        execution.py, agent.py, critic.py, tests, observability

    Invariants (enforced at construction):
        performed=True  → refusal_reason is None
                          outcome is a string carrying the execution result
        performed=False → outcome is empty string ("")
                          refusal_reason is a non-empty string

    A split-brain ExecutionResult (e.g. performed=True with a
    refusal_reason, or performed=False with a non-empty outcome) is
    a construction error and will raise ValueError.
    """
    performed: bool
    outcome: str
    refusal_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, str):
            raise ValueError(
                "ExecutionResult.outcome must be a string"
            )
        if self.refusal_reason is not None and not isinstance(self.refusal_reason, str):
            raise ValueError(
                "ExecutionResult.refusal_reason must be a string or None"
            )
        if self.performed:
            if self.refusal_reason is not None:
                raise ValueError(
                    "ExecutionResult.refusal_reason must be None when "
                    f"performed=True, got: {self.refusal_reason!r}"
                )
        else:
            if self.outcome != "":
                raise ValueError(
                    "ExecutionResult.outcome must be empty string when "
                    f"performed=False, got: {self.outcome!r}"
                )
            if not self.refusal_reason:
                raise ValueError(
                    "ExecutionResult.refusal_reason must be a non-empty "
                    "string when performed=False"
                )

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

ADR references:
  - ADR-022: Failure vs Non-Failure Classification (category taxonomy)
  - ADR-024: Minimal Input Signal Set (admissible signals)
  - ADR-025: Confidence Update Mechanics (EWMA consumer)
"""

from __future__ import annotations

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
        "rejected" — no execution occurred; no confidence update (ADR-021)
        "deferred" — cycle deferred before critic; no confidence update

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

# tests/test_properties.py
"""Property-based tests for ECK invariants using Hypothesis.

Each property in this file corresponds to a formally stated architectural
invariant. Properties are kept narrowly scoped: one subsystem, one guarantee.

Current properties:
    - ConfidenceSignal boundedness (ADR-025)
      For all valid sequences of critic outcomes, every confidence value
      in the resulting trajectory is within [0.0, 1.0].

Pending (separate commits):
    - HALT absorption
    - Gate execution exclusivity
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import composite, DrawFn

from eck.confidence import ConfidenceSignal, _KIND_TO_MOVEMENT_CLASS
from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
    PartialStructure,
    make_critic_outcome,
)


# ── Coverage assertion ────────────────────────────────────────────────────────

def test_conflict_kind_mapping_covers_full_enum() -> None:
    """
    The confidence module's _KIND_TO_MOVEMENT_CLASS must cover every member
    of ConflictKind. If a new ConflictKind is added without a corresponding
    mapping entry, this test fails loudly before any property test runs.
    """
    assert set(ConflictKind) == set(_KIND_TO_MOVEMENT_CLASS), (
        f"ConflictKind members not in _KIND_TO_MOVEMENT_CLASS: "
        f"{set(ConflictKind) - set(_KIND_TO_MOVEMENT_CLASS)}"
    )


# ── Strategies ────────────────────────────────────────────────────────────────

# Non-partial categories — paired with PartialStructure=None
_NON_PARTIAL_CATEGORIES = ["success", "failure", "rejected", "deferred"]

# All ConflictLocus members for footprint generation
_ALL_LOCI = list(ConflictLocus)


@composite
def valid_partial_structure(draw: DrawFn) -> PartialStructure:
    """Draw a valid PartialStructure with all required fields."""
    conflict_kind = draw(st.sampled_from(list(ConflictKind)))
    # Footprint must be non-empty (frozenset of at least one ConflictLocus)
    footprint = draw(
        st.frozensets(st.sampled_from(_ALL_LOCI), min_size=1)
    )
    return PartialStructure(
        collapse_status="unresolved",
        conflict_kind=conflict_kind,
        conflict_footprint=footprint,
    )


@composite
def valid_critic_outcome_with_structure(
    draw: DrawFn,
) -> tuple[CriticOutcome, PartialStructure | None]:
    """
    Draw a valid (CriticOutcome, PartialStructure | None) pair that satisfies
    the confidence signal contract:
        - partial category  → PartialStructure is present
        - all other categories → PartialStructure is None
        - severity ∈ [0.0, 1.0]
    """
    is_partial = draw(st.booleans())

    if is_partial:
        category = "partial"
        structure: PartialStructure | None = draw(valid_partial_structure())
    else:
        category = draw(st.sampled_from(_NON_PARTIAL_CATEGORIES))
        structure = None

    severity = draw(
        st.floats(
            min_value=0.0,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    outcome = make_critic_outcome(
        category=category,
        severity=severity,
        feedback=category,
    )
    return outcome, structure


# ── Properties ────────────────────────────────────────────────────────────────

@pytest.mark.property
@given(
    sequence=st.lists(
        valid_critic_outcome_with_structure(),
        min_size=1,
        max_size=50,
    )
)
@settings(max_examples=500)
def test_confidence_always_bounded(
    sequence: list[tuple[CriticOutcome, PartialStructure | None]],
) -> None:
    """
    ADR-025 bounded accumulation invariant:

        For all valid sequences of critic outcomes, every confidence value
        in the resulting trajectory is within [0.0, 1.0].

    This property tests the ConfidenceSignal directly via replay(), which
    runs the full update sequence without affecting live state. No agent
    loop, no mocks, no cross-subsystem coupling.
    """
    signal = ConfidenceSignal()
    trajectory = signal.replay(sequence)

    for i, value in enumerate(trajectory):
        assert 0.0 <= value <= 1.0, (
            f"Confidence out of bounds at step {i}: {value!r} "
            f"(sequence length {len(sequence)})"
        )

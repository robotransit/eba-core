# tests/test_properties.py
"""Property-based tests for ECK invariants using Hypothesis.

Each property in this file corresponds to a formally stated architectural
invariant. Properties are kept narrowly scoped: one subsystem, one guarantee.

Current properties:
    - ConfidenceSignal boundedness (ADR-025)
      For all valid sequences of critic outcomes, every confidence value
      in the resulting trajectory is within [0.0, 1.0].
    - HALT absorption
      For all subsequent step() attempts on an agent already in HALT,
      step() returns False and no execution seam is reached.

Pending (separate commits):
    - Gate execution exclusivity
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import composite, DrawFn
from unittest.mock import patch

from eck.agent import ECKAgent
from eck.confidence import ConfidenceSignal, _KIND_TO_MOVEMENT_CLASS
from eck.config import ECKConfig, PolicyMode
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


# ── Shared stubs ──────────────────────────────────────────────────────────────

def _dummy_llm(prompt: str) -> str:
    return "NO"


# ── Strategies ────────────────────────────────────────────────────────────────

# Non-partial categories — paired with PartialStructure=None
_NON_PARTIAL_CATEGORIES = ["success", "failure", "rejected", "deferred"]

# All ConflictLocus members for footprint generation
_ALL_LOCI = list(ConflictLocus)


@composite
def valid_partial_structure(draw: DrawFn) -> PartialStructure:
    """Draw a valid PartialStructure with all required fields."""
    conflict_kind = draw(st.sampled_from(list(ConflictKind)))
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


@pytest.mark.property
@given(
    task_texts=st.lists(
        st.text(min_size=1, max_size=50),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=200)
def test_halt_is_absorbing(task_texts: list[str]) -> None:
    """
    HALT absorption invariant:

        For all subsequent step() attempts on an agent already in HALT,
        step() returns False and no execution seam is reached.

    The agent is constructed directly in PolicyMode.HALT. This property
    tests absorption, not acquisition — the path into HALT is covered by
    the sequence tests.

    task_texts drives the number and content of subsequent step() attempts.
    Each text is seeded as a task before the corresponding step() call,
    giving Hypothesis control over how many attempts are made (1–10) and
    what is in the queue, without affecting the HALT outcome.
    """
    import eck.agent as agent_mod

    a = ECKAgent(
        objective="Test objective",
        llm_call=_dummy_llm,
        config=ECKConfig(policy_mode=PolicyMode.HALT),
    )

    def raise_if_called(*_: object, **__: object) -> object:
        raise AssertionError("No execution seam should be called in HALT mode")

    for task_text in task_texts:
        a.seed(task_text)
        with patch.object(agent_mod, "propose_execution", raise_if_called), \
             patch.object(agent_mod, "authorize_and_perform", raise_if_called), \
             patch.object(agent_mod, "generate_prediction", raise_if_called), \
             patch.object(agent_mod, "critic_evaluate", raise_if_called), \
             patch.object(agent_mod, "generate_subtasks", raise_if_called):
            result = a.step()

        assert result is False, (
            f"step() returned {result!r} in HALT mode "
            f"(task_text={task_text!r})"
        )

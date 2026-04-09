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
    - Gate execution exclusivity
      For all non-EXECUTE gate decisions, authorize_and_perform is never
      called, and the gate is evaluated exactly once.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import composite, DrawFn
from unittest.mock import patch, MagicMock

from eck.agent import ECKAgent
from eck.confidence import ConfidenceSignal, _KIND_TO_MOVEMENT_CLASS
from eck.config import ECKConfig, PolicyMode
from eck.policy_gate import (
    ExecutionMode,
    PolicyCause,
    PolicyDecision,
    PolicyGate,
)
from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
    PartialStructure,
    ProposedAction,
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


def _mock_proposal() -> ProposedAction:
    return ProposedAction(
        action_type="llm_query",
        parameters={"prompt": "do the thing"},
        task_text="task",
        task_id="test-task-id",
        provenance_id="test-provenance-id",
    )


def _gate_decision(mode: ExecutionMode) -> PolicyDecision:
    return PolicyDecision(
        mode=mode,
        cause=PolicyCause.CONFIDENCE,
        reason="property test",
        rule_id="TEST",
    )


def _snap() -> dict[str, object]:
    return {
        "drift_streak": 0,
        "total_drift_events": 0,
        "last_error_z": 0.0,
        "numeric_bias": 0.0,
        "feasibility_sample_count": 0,
        "numeric_success_rate": None,
        "severe": False,
    }


# ── Strategies ────────────────────────────────────────────────────────────────

# Non-partial categories — paired with PartialStructure=None
_NON_PARTIAL_CATEGORIES = ["success", "failure", "rejected", "deferred"]

# All ConflictLocus members for footprint generation
_ALL_LOCI = list(ConflictLocus)

# Non-EXECUTE gate modes — the three refusal outcomes
_NON_EXECUTE_MODES = [ExecutionMode.RETRY, ExecutionMode.DEGRADE, ExecutionMode.HALT]


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


@pytest.mark.property
@given(
    gate_mode=st.sampled_from(_NON_EXECUTE_MODES),
)
@settings(max_examples=100)
def test_gate_non_execute_never_calls_authorize(
    gate_mode: ExecutionMode,
) -> None:
    """
    Gate execution exclusivity invariant:

        Given a proposal exists and the gate returns a non-EXECUTE decision,
        authorize_and_perform is never called and the gate is evaluated
        exactly once.

    This property is narrowly scoped to the gate-refusal seam. The
    no-proposal path (a distinct pre-gate short-circuit) is covered
    deterministically in test_adversarial.py.

    gate_mode is drawn from {RETRY, DEGRADE, HALT} — the three non-EXECUTE
    outcomes. propose_execution always returns a valid proposal so the gate
    is always reached. All orthogonal machinery is patched.
    """
    import eck.agent as agent_mod

    gate = MagicMock(spec=PolicyGate)
    gate.evaluate.return_value = _gate_decision(gate_mode)

    a = ECKAgent(
        objective="Test objective",
        llm_call=_dummy_llm,
        config=ECKConfig(),
        policy_gate=gate,
    )
    a.seed("task")

    def raise_if_called(*_: object, **__: object) -> object:
        raise AssertionError(
            f"authorize_and_perform must not be called when gate={gate_mode.name}"
        )

    with patch.object(agent_mod, "propose_execution",
                      return_value=_mock_proposal()), \
         patch.object(agent_mod, "authorize_and_perform",
                      side_effect=raise_if_called), \
         patch.object(agent_mod, "generate_prediction", return_value="pred"), \
         patch.object(agent_mod, "critic_evaluate",
                      return_value=(
                          make_critic_outcome(
                              category="rejected",
                              severity=0.0,
                              feedback="rejected",
                          ),
                          None,
                      )), \
         patch.object(agent_mod, "generate_subtasks", return_value=[]), \
         patch.object(a.drift, "get_policy_mode",
                      return_value=PolicyMode.NORMAL), \
         patch.object(a.drift, "record_error", return_value=False), \
         patch.object(a.drift, "record_feasibility"), \
         patch.object(a.drift, "snapshot", return_value=_snap()):
        a.step()

    # Gate must have been evaluated exactly once
    gate.evaluate.assert_called_once()

    # Gate must not have returned EXECUTE
    decision = gate.evaluate.return_value
    assert decision.mode is not ExecutionMode.EXECUTE, (
        f"Gate returned EXECUTE in a non-EXECUTE property test — "
        f"strategy is broken"
    )

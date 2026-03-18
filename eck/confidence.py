from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import NamedTuple, Optional, Literal


class CriticOutcome(NamedTuple):
    """Locked critic outcome taxonomy per ADR-022.

    This is the canonical set of categories. No other values are permitted.
    Severity is always in [0.0, 1.0] and acts only as a magnitude scaler.
    """
    category: Literal["Success", "Failure", "Partial", "Rejected", "Deferred"]
    severity: float   # 0.0 ≤ severity ≤ 1.0 (enforced)


class ConflictKind(Enum):
    EVIDENCE_CONFLICT = "evidence_conflict"
    CONSTRAINT_CONFLICT = "constraint_conflict"
    DECOMPOSITION_CONFLICT = "decomposition_conflict"
    RESOLUTION_INSTABILITY = "resolution_instability"


class ConflictLocus(Enum):
    FACTUAL = "factual"
    INSTRUCTION = "instruction"
    FORMAT = "format"
    CONSISTENCY = "consistency"
    LOCAL = "local"
    GLOBAL = "global"


class PartialStructure(NamedTuple):
    """Locked structural enrichment for Partial outcomes (interface required)."""
    collapse_status: Literal["unresolved"]
    conflict_kind: ConflictKind
    conflict_footprint: frozenset[ConflictLocus]


class MovementClass(Enum):
    BOTH = "both"
    UP_ONLY = "up_only"
    DOWN_ONLY = "down_only"
    NEITHER = "neither"


_KIND_TO_MOVEMENT_CLASS = {
    ConflictKind.EVIDENCE_CONFLICT: MovementClass.BOTH,
    ConflictKind.CONSTRAINT_CONFLICT: MovementClass.DOWN_ONLY,
    ConflictKind.DECOMPOSITION_CONFLICT: MovementClass.NEITHER,
    ConflictKind.RESOLUTION_INSTABILITY: MovementClass.NEITHER,
}


class ConfidenceSignal:
    """Core confidence update mechanism with EWMA smoothing.

    This file implements the staged increments for ADR-021–025:
    - Core state model, raw delta, gated EWMA, bounded accumulation
    - Critic outcome taxonomy + severity scaling
    - Permission gates + single-cycle failure window
    - Whitelist of admissible input signals (critic-only for now; optional signals
      are downward-only and fully disableable with zero phantom influence)

    Still deferred:
    - Final observability richness / precise clamp attribution (beyond current minimal level)
    - Full optional-signal surface and integration

    All invariants preserved (stdlib-only, advisory-only confidence, no silent coupling,
    exact logger "eck-core").
    """

    def __init__(self, alpha: float = 0.3) -> None:
        """Initialize with per-instance smoothing factor used for replay determinism.

        alpha must be in (0.0, 1.0] per ADR-025 semantics.
        """
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"alpha must be in (0.0, 1.0], got {alpha}")

        self._value: float = 0.5
        self._alpha: float = alpha
        self._last_smoothed_delta: float = 0.0
        self._last_outcome_was_failure: bool = False
        self._cycle_id: int = 0
        self._logger = logging.getLogger("eck-core")

        # ADR-024 whitelist boundary (critic-only for now)
        self._admissible_signals: set[str] = {"critic"}

    def _compute_raw_delta(self, outcome: CriticOutcome) -> float:
        """Compute raw directional delta from critic outcome (ADR-022/025)."""
        if outcome.category == "Success":
            return 0.35 - (0.25 * outcome.severity)

        if outcome.category == "Failure":
            return -outcome.severity

        if outcome.category == "Partial":
            return self._compute_partial_raw_delta(outcome.severity)

        if outcome.category in ("Rejected", "Deferred"):
            return 0.0

        raise ValueError(f"Unknown critic outcome category: {outcome.category}")

    def _compute_partial_raw_delta(self, severity: float) -> float:
        """Severity-based bidirectional but downward-biased raw delta for Partial."""
        if severity <= 0.5:
            return (0.5 - severity) * 0.5
        else:
            return -(severity - 0.5) * 1.2

    def _derive_base_and_effective_class(
        self,
        outcome: CriticOutcome,
        partial_structure: Optional[PartialStructure],
        prior_failure_window_active: bool
    ) -> tuple[MovementClass, MovementClass]:
        """Derive base_class and effective_class."""
        if outcome.category == "Partial":
            if partial_structure is None:
                raise ValueError("Partial outcome must be accompanied by PartialStructure")
            base_class = _KIND_TO_MOVEMENT_CLASS[partial_structure.conflict_kind]
        else:
            if partial_structure is not None:
                raise ValueError("PartialStructure is only valid for Partial outcomes")
            base_class = MovementClass.BOTH

        effective_class = base_class

        # Single-cycle failure window restriction
        if prior_failure_window_active:
            if base_class is MovementClass.BOTH:
                effective_class = MovementClass.DOWN_ONLY
            elif base_class is MovementClass.UP_ONLY:
                effective_class = MovementClass.NEITHER

        return base_class, effective_class

    def _apply_gated_clamp(self, delta: float, movement_class: MovementClass) -> float:
        """Clamp delta according to movement class."""
        if movement_class is MovementClass.BOTH:
            return delta
        if movement_class is MovementClass.UP_ONLY:
            return max(0.0, delta)
        if movement_class is MovementClass.DOWN_ONLY:
            return min(0.0, delta)
        if movement_class is MovementClass.NEITHER:
            return 0.0
        raise ValueError("unreachable movement class")

    def update(self, outcome: CriticOutcome, partial_structure: Optional[PartialStructure] = None) -> float:
        """Core update entrypoint with EWMA smoothing."""
        # 0. Airtight validation — BEFORE ANY mutation
        # (category admissibility rejection happens in _compute_raw_delta(); this is accepted deferred hardening)
        if outcome.category == "Partial":
            if partial_structure is None:
                raise ValueError("Partial outcome must be accompanied by PartialStructure")
        else:
            if partial_structure is not None:
                raise ValueError("PartialStructure is only valid for Partial outcomes")

        if not (0.0 <= outcome.severity <= 1.0):
            raise ValueError(f"Severity must be in [0.0, 1.0], got {outcome.severity}")

        # Now safe to mutate
        self._cycle_id += 1
        prior_value = self._value
        prior_smoothed_delta = self._last_smoothed_delta
        prior_failure_window_active = self._last_outcome_was_failure

        # 1. True no-update path for Rejected / Deferred
        if outcome.category in ("Rejected", "Deferred"):
            if prior_failure_window_active:
                self._last_outcome_was_failure = False
            self._logger.info("confidence.update", extra={
                "cycle_id": self._cycle_id,
                "timestamp": datetime.now().isoformat(),
                "category": outcome.category,
                "severity": outcome.severity,
                "prior_value": prior_value,
                "action": "no_update",
                "failure_window_consumed": prior_failure_window_active,
                "final_value": self._value
            })
            return self._value

        # 2. Compute raw delta
        delta_raw = self._compute_raw_delta(outcome)

        # 3. Derive base and effective movement class
        base_class, effective_class = self._derive_base_and_effective_class(
            outcome, partial_structure, prior_failure_window_active
        )

        # 4. Apply gated clamp to both raw delta and prior smoothed delta
        permitted_raw = self._apply_gated_clamp(delta_raw, effective_class)
        permitted_prior = self._apply_gated_clamp(prior_smoothed_delta, effective_class)

        # 5. Gated EWMA smoothing
        delta_smoothed = self._alpha * permitted_raw + (1 - self._alpha) * permitted_prior
        self._last_smoothed_delta = delta_smoothed

        # 6. Bounded accumulation
        self._value = max(0.0, min(1.0, self._value + delta_smoothed))

        # 7. Update failure-window state
        self._last_outcome_was_failure = (outcome.category == "Failure")

        # Structured logging (minimal but accurate)
        if permitted_raw != delta_raw or permitted_prior != prior_smoothed_delta:
            if prior_failure_window_active and effective_class != base_class:
                clamp_reason = "failure_window_clamped"
            elif effective_class is MovementClass.DOWN_ONLY:
                clamp_reason = "movement_class_down_only_clamped"
            elif effective_class is MovementClass.NEITHER:
                clamp_reason = "movement_class_neither_clamped"
            else:
                clamp_reason = "movement_class_clamped"
        else:
            clamp_reason = "no_clamp"

        self._logger.info("confidence.update", extra={
            "cycle_id": self._cycle_id,
            "timestamp": datetime.now().isoformat(),
            "category": outcome.category,
            "severity": outcome.severity,
            "prior_value": prior_value,
            "base_class": base_class.name,
            "effective_class": effective_class.name,
            "delta_raw": delta_raw,
            "permitted_raw": permitted_raw,
            "permitted_prior": permitted_prior,
            "delta_smoothed": delta_smoothed,
            "final_value": self._value,
            "clamp_reason": clamp_reason,
            "partial_structure": {
                "conflict_kind": partial_structure.conflict_kind.name if partial_structure else None,
                "conflict_footprint": sorted([locus.name for locus in partial_structure.conflict_footprint]) if partial_structure else None
            } if partial_structure else None,
            "admissible_signals": sorted(self._admissible_signals)   # deterministic order
        })

        return self._value

    def get_value(self) -> float:
        """Return current confidence value."""
        return self._value

    def replay(self, outcomes: list[tuple[CriticOutcome, Optional[PartialStructure]]]) -> list[float]:
        """Deterministic replay for testing and auditing."""
        original_value = self._value
        original_last_delta = self._last_smoothed_delta
        original_last_failure = self._last_outcome_was_failure
        original_cycle_id = self._cycle_id

        trajectory: list[float] = []
        for outcome, structure in outcomes:
            self.update(outcome, structure)
            trajectory.append(self._value)

        # Restore original state
        self._value = original_value
        self._last_smoothed_delta = original_last_delta
        self._last_outcome_was_failure = original_last_failure
        self._cycle_id = original_cycle_id
        return trajectory
      

# eck/confidence.py
"""Confidence signal processor (ADR-021–025).

Implements the staged increments for the ECK confidence system:
- Core state model, raw delta, gated EWMA, bounded accumulation
- Critic outcome taxonomy + severity scaling (ADR-022)
- Permission gates + single-cycle failure window (ADR-023)
- Whitelist of admissible input signals (ADR-024)
- EWMA update mechanics (ADR-025)

CriticOutcome, PartialStructure, ConflictKind, and ConflictLocus
are imported from eck.types (single source of truth).

Still deferred:
- Final observability richness / precise clamp attribution
- Full optional-signal surface and integration
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from eck.telemetry import emit_event
from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
    PartialStructure,
)

logger = logging.getLogger("eck-core")


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

# Severity scaling constants for partial delta computation.
# Low-severity partial (≤ 0.5): small upward nudge, scaled by distance from midpoint.
# High-severity partial (> 0.5): downward push, scaled more aggressively.
_PARTIAL_UPWARD_SCALE = 0.5
_PARTIAL_DOWNWARD_SCALE = 1.2
_PARTIAL_MIDPOINT = 0.5


class ConfidenceSignal:
    """Core confidence update mechanism with EWMA smoothing (ADR-021–025).

    Consumes CriticOutcome from eck.types. All category comparisons
    use lowercase canonical values per eck.types contract.
    """

    def __init__(self, alpha: float = 0.3) -> None:
        """Initialize with per-instance smoothing factor.

        alpha must be in (0.0, 1.0] per ADR-025 semantics.
        Higher alpha = faster adaptation to recent evidence.
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

    def update(
        self,
        outcome: CriticOutcome,
        partial_structure: Optional[PartialStructure] = None,
        *,
        trace_id: str | None = None,
        step_id: str | None = None,
        deterministic_nonce: int | None = None,
    ) -> float:
        """Core update entrypoint with EWMA smoothing (ADR-025).

        Returns the new confidence value after applying the update.
        No update occurs for rejected/deferred outcomes (ADR-021).

        Telemetry args (trace_id, step_id, deterministic_nonce) are optional.
        When all three are supplied, an epistemic.signal event is emitted.
        When any are None, telemetry is silently skipped.
        replay() calls update() without telemetry args — no phantom events.
        """
        # Airtight validation — before any mutation
        if outcome.category == "partial":
            if partial_structure is None:
                raise ValueError("Partial outcome must be accompanied by PartialStructure")
        else:
            if partial_structure is not None:
                raise ValueError("PartialStructure is only valid for partial outcomes")

        if not (0.0 <= outcome.severity <= 1.0):
            raise ValueError(f"Severity must be in [0.0, 1.0], got {outcome.severity}")

        # Safe to mutate from here
        self._cycle_id += 1
        prior_value = self._value
        prior_smoothed_delta = self._last_smoothed_delta
        prior_failure_window_active = self._last_outcome_was_failure

        def _emit_epistemic(
            *,
            updated: bool,
            extra: dict[str, Any] | None = None,
        ) -> None:
            """Emit epistemic.signal telemetry if telemetry context is present."""
            if (
                trace_id is None
                or step_id is None
                or deterministic_nonce is None
            ):
                return
            payload: dict[str, Any] = {
                "confidence": self._value,
                "category": outcome.category,
                "updated": updated,
                "severity": outcome.severity,
                "prior_confidence": prior_value,
            }
            if extra:
                payload.update(extra)
            emit_event(
                "epistemic.signal",
                trace_id=trace_id,
                step_id=step_id,
                deterministic_nonce=deterministic_nonce,
                severity="INFO",
                source="confidence",
                payload=payload,
                logger=self._logger,
            )

        # True no-update path for rejected / deferred (ADR-021)
        if outcome.category in ("rejected", "deferred"):
            if prior_failure_window_active:
                # Consume the failure window — clear both the window flag and
                # the negative momentum carried by _last_smoothed_delta.
                # No new evidence was produced, so the downward carry from the
                # prior failure should not persist past window consumption.
                self._last_outcome_was_failure = False
                self._last_smoothed_delta = 0.0
            self._logger.info("confidence.update", extra={
                "cycle_id": self._cycle_id,
                "category": outcome.category,
                "severity": outcome.severity,
                "prior_value": prior_value,
                "action": "no_update",
                "failure_window_consumed": prior_failure_window_active,
                "final_value": self._value,
            })
            _emit_epistemic(updated=False)
            return self._value

        # 1. Compute raw delta
        delta_raw = self._compute_raw_delta(outcome)

        # 2. Derive base and effective movement class (ADR-023)
        base_class, effective_class = self._derive_base_and_effective_class(
            outcome, partial_structure, prior_failure_window_active
        )

        # 3. Apply gated clamp to both raw delta and prior smoothed delta
        permitted_raw = self._apply_gated_clamp(delta_raw, effective_class)
        permitted_prior = self._apply_gated_clamp(prior_smoothed_delta, effective_class)

        # 4. Gated EWMA smoothing (ADR-025)
        delta_smoothed = (
            self._alpha * permitted_raw
            + (1 - self._alpha) * permitted_prior
        )
        self._last_smoothed_delta = delta_smoothed

        # 5. Bounded accumulation (ADR-025)
        self._value = max(0.0, min(1.0, self._value + delta_smoothed))

        # 6. Update failure window state (ADR-023)
        self._last_outcome_was_failure = (outcome.category == "failure")

        # 7. Determine clamp reason for observability
        if permitted_raw != delta_raw or permitted_prior != prior_smoothed_delta:
            if prior_failure_window_active and effective_class != base_class:
                clamp_reason = "failure_window_clamped"
            elif effective_class is MovementClass.DOWN_ONLY:
                clamp_reason = "movement_class_down_only_clamped"
            elif effective_class is MovementClass.NEITHER:
                clamp_reason = "movement_class_neither_clamped"
            else:
                clamp_reason = "movement_class_clamped"  # pragma: no cover
        else:
            clamp_reason = "no_clamp"

        self._logger.info("confidence.update", extra={
            "cycle_id": self._cycle_id,
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
                "conflict_kind": partial_structure.conflict_kind.name,
                "conflict_footprint": sorted([
                    locus.name for locus in partial_structure.conflict_footprint
                ]),
            } if partial_structure else None,
            "admissible_signals": sorted(self._admissible_signals),
        })

        _emit_epistemic(
            updated=True,
            extra={
                "delta_raw": delta_raw,
                "delta_smoothed": delta_smoothed,
            },
        )

        return self._value

    def get_value(self) -> float:
        """Return current confidence value."""
        return self._value

    def replay(
        self,
        outcomes: list[tuple[CriticOutcome, Optional[PartialStructure]]],
    ) -> list[float]:
        """Deterministic replay for testing and auditing (ADR-025).

        Runs the update sequence against the provided outcomes and returns
        the confidence trajectory, then restores original state exactly.
        Logging is suppressed during replay to avoid phantom log entries.
        Telemetry is suppressed during replay — update() is called without
        telemetry args so no epistemic.signal events are emitted for
        synthetic replay trajectories.
        """
        original_value = self._value
        original_last_delta = self._last_smoothed_delta
        original_last_failure = self._last_outcome_was_failure
        original_cycle_id = self._cycle_id

        trajectory: list[float] = []

        # Suppress logging during replay
        with _suppress_logger(self._logger):
            for outcome, structure in outcomes:
                self.update(outcome, structure)
                trajectory.append(self._value)

        # Restore original state exactly
        self._value = original_value
        self._last_smoothed_delta = original_last_delta
        self._last_outcome_was_failure = original_last_failure
        self._cycle_id = original_cycle_id

        return trajectory


# ── Logging suppression context manager for replay ───────────────────────────

class _suppress_logger:
    """Temporarily raise logger level to suppress output during replay."""

    def __init__(self, log: logging.Logger) -> None:
        self._logger = log
        self._original_level = log.level

    def __enter__(self) -> None:
        self._logger.setLevel(logging.CRITICAL + 1)

    def __exit__(self, *_: object) -> None:
        self._logger.setLevel(self._original_level)

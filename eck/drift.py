# eck/drift.py
"""Drift monitoring subsystem (ADR-040).

Tracks perceptual error outliers, drift streaks, and numeric feasibility
signals. Provides policy escalation recommendations to the agent loop.

Design principles (ADR-040):
- Drift history is append-only — no silent truncation or reset
- DriftMonitor accumulates evidence; it does not log (agent loop is the
  canonical logging point per ADR-040 Section 5)
- Recovery is external — DriftMonitor never resets itself
- get_policy_mode() provides graduated escalation:
    NORMAL → GUIDED → ENFORCED → HALT
"""

from __future__ import annotations

import statistics
from typing import Any, List, Optional, Tuple

from .config import ECKConfig, PolicyMode
from .utils import safe_mean, z_score


class DriftMonitor:
    """
    Append-only drift evidence accumulator and policy escalation advisor.

    All history lists grow without bound for the lifetime of the kernel
    execution epoch (ADR-040). No internal reset is permitted.

    The agent loop is responsible for:
    - Logging drift state after each update (ADR-040 Section 5)
    - Enforcing escalation decisions returned by get_policy_mode()
    - Treating this instance as append-only evidence (ADR-040 Section 3)
    """

    def __init__(self, config: ECKConfig | None = None) -> None:
        self.config = config or ECKConfig()

        # ── Append-only evidence stores (ADR-040) ─────────────────────
        # None of these may be truncated, reset, or bounded during a
        # kernel execution epoch.
        self.error_history: List[float] = []
        self.drift_events: List[bool] = []        # True per registered drift event
        self.feasibility_history: List[Tuple[bool, bool]] = []  # (was_numeric, success)

        # ── Derived signals (computed from evidence above) ────────────
        self.last_error_z: float = 0.0
        self.drift_streak: int = 0
        self.numeric_bias: float = 1.0

    # ── Evidence recording ────────────────────────────────────────────

    def record_error(self, error: float) -> bool:
        """
        Record a new perceptual error and return True if it is a z-score outlier.

        Requires at least config.drift_warmup_samples samples before
        producing a signal — returns False during warmup period.
        Advisory-only: does not alter policy directly.
        """
        self.error_history.append(error)

        if len(self.error_history) < self.config.drift_warmup_samples:
            self.last_error_z = 0.0
            return False

        recent = self.error_history[-self.config.drift_warmup_samples:]
        mean = statistics.mean(recent)
        std = statistics.pstdev(recent) or 1e-8
        z = abs(z_score(error, mean, std))
        self.last_error_z = z

        return z > self.config.error_z_threshold

    def record_feasibility(self, was_numeric: bool, success: bool) -> None:
        """
        Record a feasibility observation and update numeric bias signal.

        numeric_bias reflects recent numeric task success rate and feeds
        into severe() as an additional instability signal.
        """
        self.feasibility_history.append((was_numeric, success))

        numeric_successes = [s for f, s in self.feasibility_history if f]
        if not numeric_successes:
            return

        conf = safe_mean([float(x) for x in numeric_successes])
        if conf > self.config.feas_conf_high:
            self.numeric_bias = min(1.3, self.numeric_bias * 1.1)
        elif conf < self.config.feas_conf_low:
            self.numeric_bias = max(0.7, self.numeric_bias * 0.9)

    def register_drift(self) -> None:
        """
        Record a confirmed drift event and increment streak counter.

        Appends to drift_events (append-only per ADR-040).
        """
        self.drift_events.append(True)
        self.drift_streak += 1

    def clear_streak(self) -> None:
        """
        Reset the consecutive drift streak counter on a non-drift cycle.

        NOTE: This resets only the streak counter — a derived signal.
        The underlying drift_events history is never modified (ADR-040).
        A streak reset does not erase the evidence that prior drifts occurred.
        """
        self.drift_streak = 0

    # ── Severity and escalation ───────────────────────────────────────

    def severe(self) -> bool:
        """
        Return True if conditions warrant immediate HALT.

        Triggers on:
        - Total drift event count exceeds config.severe_drift_count
        - Numeric feasibility confidence falls below low_conf_threshold
        """
        if len(self.drift_events) > self.config.severe_drift_count:
            return True

        numeric_successes = [s for f, s in self.feasibility_history if f]
        if numeric_successes and safe_mean([float(x) for x in numeric_successes]) < self.config.low_conf_threshold:
            return True

        return False

    def get_policy_mode(self) -> PolicyMode:
        """
        Recommend a policy mode based on current drift evidence.

        Graduated escalation (ADR-040 Section 2):
            NORMAL   — no significant drift signals
            GUIDED   — moderate drift streak (>= guided_drift_threshold)
            ENFORCED — sustained drift streak (>= enforced_drift_threshold)
            HALT     — severe instability or streak >= max_drift_streak

        Never recommends a downgrade — the agent loop enforces irreversibility.
        If already at HALT, returns HALT immediately (no re-evaluation needed).
        """
        # Respect already-escalated policy (never downgrade)
        if self.config.policy_mode == PolicyMode.HALT:
            return PolicyMode.HALT

        # HALT conditions (highest priority)
        if (
            self.severe()
            or self.drift_streak >= self.config.max_drift_streak
            or self.last_error_z >= self.config.error_z_threshold
        ):
            return PolicyMode.HALT

        # ENFORCED: sustained drift streak approaching max
        if self.drift_streak >= self.config.enforced_drift_threshold:
            return PolicyMode.ENFORCED

        # GUIDED: moderate drift streak
        if self.drift_streak >= self.config.guided_drift_threshold:
            return PolicyMode.GUIDED

        return PolicyMode.NORMAL

    # ── Audit surface ─────────────────────────────────────────────────

    def total_drift_events(self) -> int:
        """Return the total number of drift events recorded (audit surface)."""
        return len(self.drift_events)

    def snapshot(self) -> dict[str, Any]:
        """
        Return a read-only snapshot of current drift state for logging.

        Intended for use by the agent loop as the canonical logging point
        (ADR-040 Section 5). Does not modify any state.
        """
        numeric_successes = [s for f, s in self.feasibility_history if f]
        return {
            "drift_streak": self.drift_streak,
            "total_drift_events": len(self.drift_events),
            "last_error_z": self.last_error_z,
            "numeric_bias": self.numeric_bias,
            "feasibility_sample_count": len(self.feasibility_history),
            "numeric_success_rate": safe_mean([float(x) for x in numeric_successes]) if numeric_successes else None,
            "severe": self.severe(),
        }

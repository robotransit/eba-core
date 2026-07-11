"""Tests for calibration utilities (v0.5.0)."""

import pytest
from eck.telemetry.calibration import compute_calibration
from eck.telemetry.trace_types import RunTrace, StepTrace, Event


def create_test_trace(outcome_categories, confidences):
    """Helper to create synthetic traces for testing."""
    trace = RunTrace(trace_id="test-trace", objective="Test objective")
    for i, (outcome, conf) in enumerate(zip(outcome_categories, confidences)):
        step = StepTrace(step_id=f"step-{i}", trace_id="test-trace")
        step.events.append(Event(
            event_type="epistemic.signal",
            version="1.0",
            timestamp=0.0,
            trace_id="test-trace",
            step_id=f"step-{i}",
            deterministic_nonce=i,
            severity="INFO",
            source="confidence",
            payload={"confidence": conf, "category": outcome, "updated": True}
        ))
        step.confidence_after = conf
        step.outcome_category = outcome
        step.finalize()
        trace.add_step(step)
    trace.finalize()
    return trace


def test_compute_calibration_basic():
    """Basic calibration computation test."""
    trace = create_test_trace(
        ["executed", "executed", "rejected", "executed"],
        [0.9, 0.8, 0.6, 0.4]
    )

    result = compute_calibration([trace], n_bins=5)

    assert len(result.bins) == 6
    assert result.ece >= 0.0
    assert sum(result.counts) == 4


def test_over_under_confidence_detection():
    """Test detection of over/under confidence zones."""
    # High confidence but low accuracy (overconfident)
    trace = create_test_trace(
        ["rejected", "rejected", "rejected"],
        [0.95, 0.90, 0.85]
    )

    result = compute_calibration([trace], n_bins=10)

    assert len(result.overconfident_zones) > 0


def test_empty_traces():
    """Should handle empty input gracefully."""
    result = compute_calibration([])
    assert result.ece == 0.0
    assert len(result.bins) == 11  # default 10 bins + edges

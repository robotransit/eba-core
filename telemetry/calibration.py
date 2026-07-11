"""Calibration utilities for v0.5.0 Empirical Behavioural Characterisation.

Functions to compute calibration curves, reliability diagrams,
and detect over/under-confidence from saved traces.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .trace_types import RunTrace, StepTrace


@dataclass
class CalibrationResult:
    """Container for calibration analysis results."""
    bins: List[float]                    # Confidence bin edges
    accuracy: List[float]                # Observed accuracy per bin
    counts: List[int]                    # Number of predictions per bin
    ece: float                           # Expected Calibration Error
    overconfident_zones: List[Tuple[float, float]]
    underconfident_zones: List[Tuple[float, float]]


def compute_calibration(
    traces: List[RunTrace],
    n_bins: int = 10,
    confidence_field: str = "confidence_after"
) -> CalibrationResult:
    """
    Compute reliability diagram and calibration metrics from traces.

    Args:
        traces: List of loaded RunTrace objects
        n_bins: Number of confidence bins (default 10)
        confidence_field: Which confidence value to use
    """
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    bin_sums = defaultdict(float)
    bin_counts = defaultdict(int)
    bin_correct = defaultdict(int)

    for run in traces:
        for step in run.steps:
            conf = getattr(step, confidence_field, None)
            outcome = step.outcome_category

            if conf is None or outcome is None:
                continue

            # Bin the confidence
            bin_idx = min(int(conf * n_bins), n_bins - 1)
            bin_sums[bin_idx] += conf
            bin_counts[bin_idx] += 1

            # Consider "executed" as correct for this example
            # (can be refined with ground-truth labels later)
            if outcome == "executed":
                bin_correct[bin_idx] += 1

    # Build results
    accuracy = []
    counts = []
    for i in range(n_bins):
        if bin_counts[i] > 0:
            acc = bin_correct[i] / bin_counts[i]
            accuracy.append(acc)
            counts.append(bin_counts[i])
        else:
            accuracy.append(0.0)
            counts.append(0)

    # Expected Calibration Error (ECE)
    ece = 0.0
    total = sum(counts)
    for i in range(n_bins):
        if counts[i] > 0:
            bin_conf = bin_sums[i] / counts[i]
            ece += (counts[i] / total) * abs(bin_conf - accuracy[i])

    # Simple over/under confidence zones (can be improved)
    overconfident = []
    underconfident = []
    for i in range(n_bins):
        if counts[i] > 5:  # minimum samples
            mid_conf = (bin_edges[i] + bin_edges[i + 1]) / 2
            if accuracy[i] < mid_conf - 0.1:
                overconfident.append((bin_edges[i], bin_edges[i + 1]))
            elif accuracy[i] > mid_conf + 0.1:
                underconfident.append((bin_edges[i], bin_edges[i + 1]))

    return CalibrationResult(
        bins=bin_edges,
        accuracy=accuracy,
        counts=counts,
        ece=ece,
        overconfident_zones=overconfident,
        underconfident_zones=underconfident,
    )


def print_calibration_report(result: CalibrationResult) -> None:
    """Pretty print a calibration report."""
    print("Calibration Report")
    print("-" * 50)
    print(f"ECE: {result.ece:.4f}")
    print(f"Total steps analyzed: {sum(result.counts)}")
    print("\nBin | Confidence Range | Accuracy | Count")
    print("-" * 50)
    for i in range(len(result.bins) - 1):
        print(f"{i:3d} | {result.bins[i]:.2f} - {result.bins[i+1]:.2f} | "
              f"{result.accuracy[i]:.3f}     | {result.counts[i]}")

    if result.overconfident_zones:
        print("\nOverconfident zones:", result.overconfident_zones)
    if result.underconfident_zones:
        print("Underconfident zones:", result.underconfident_zones)

"""Example: Calibration analysis for v0.5.0 traces."""

from eck.telemetry.trace_store import TraceStore
from eck.telemetry.calibration import compute_calibration, print_calibration_report

if __name__ == "__main__":
    store = TraceStore()

    # Load one or more saved runs
    traces = []
    for filename in store.list_traces():
        run = store.load_run(filename)
        if run:
            traces.append(run)
            print(f"Loaded {filename} with {run.total_steps} steps")

    if not traces:
        print("No traces found. Run trace_collection_example.py first.")
    else:
        result = compute_calibration(traces, n_bins=10)
        print_calibration_report(result)

        # Example: Save report
        with open("calibration_report.txt", "w", encoding="utf-8") as f:
            f.write("Calibration Report\n")
            f.write("=" * 50 + "\n")
            f.write(f"ECE: {result.ece:.4f}\n")
            f.write(f"Total steps: {sum(result.counts)}\n")

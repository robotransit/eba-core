"""Example: Ablation studies for v0.5.0 behavioural characterisation."""

from eck.telemetry.trace_store import TraceStore
from eck.telemetry.calibration import compute_calibration
from eck.policy_gate import DefaultPolicyGate, DemoPolicyGate

def run_ablation(objective: str, policy_gate, label: str, max_steps: int = 20):
    """Run a single ablation and return calibration result."""
    from eck.telemetry.trace_harness import TraceHarness

    harness = TraceHarness(
        objective=objective,
        llm_call=lambda p: f"Stub response for ablation {label}",
        policy_gate=policy_gate
    )

    trace = harness.run(max_steps=max_steps)
    harness.save_last_run(f"ablation_{label.lower()}.jsonl")

    print(f"Ablation '{label}': {trace.total_steps} steps, final mode {trace.final_policy_mode}")
    return trace


if __name__ == "__main__":
    objective = "Safely process mixed-risk administrative tasks"

    print("Running ablations...")

    default_trace = run_ablation(objective, DefaultPolicyGate(), "Default")
    demo_trace = run_ablation(objective, DemoPolicyGate(), "Demo")

    # Compare calibration
    store = TraceStore()
    traces_default = [store.load_run(f) for f in store.list_traces() if "default" in f.name.lower()]
    traces_demo = [store.load_run(f) for f in store.list_traces() if "demo" in f.name.lower()]

    print("\n=== Default Policy Gate Calibration ===")
    result_default = compute_calibration([t for t in traces_default if t])
    # print_calibration_report(result_default)  # uncomment to see full report

    print("\n=== Demo Policy Gate Calibration ===")
    result_demo = compute_calibration([t for t in traces_demo if t])
    # print_calibration_report(result_demo)

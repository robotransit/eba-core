"""Example usage of the v0.5.0 Trace Harness.

Run this to collect and save traces for empirical analysis.
"""

from eck.telemetry.trace_harness import TraceHarness
from eck.policy_gate import DefaultPolicyGate, DemoPolicyGate

def stub_llm(prompt: str) -> str:
    """Simple stub for testing — replace with real LLM call."""
    return f"Stub response to: {prompt[:100]}..."

if __name__ == "__main__":
    # Example 1: Default policy gate
    harness = TraceHarness(
        objective="Process a set of mixed-risk tasks safely",
        llm_call=stub_llm,
        policy_gate=DefaultPolicyGate()
    )

    trace = harness.run(max_steps=10, seed_task="Summarize the current status")
    harness.save_last_run("example_default_run.jsonl")

    print(f"Collected trace with {trace.total_steps} steps")
    print(f"Final policy mode: {trace.final_policy_mode}")
    print(f"Halted: {trace.halted}")

    # Example 2: Domain-specific gate (e.g. Demo)
    harness2 = TraceHarness(
        objective="Handle childcare-related tasks",
        llm_call=stub_llm,
        policy_gate=DemoPolicyGate()
    )

    trace2 = harness2.run(max_steps=5)
    harness2.save_last_run("example_demo_run.jsonl")
    print(f"Demo run collected with {trace2.total_steps} steps")

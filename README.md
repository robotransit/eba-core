# Epistemic Control Kernel (ECK)

**Epistemic Control Kernel (ECK)** is a minimal, reliability-first control kernel for autonomous agents.

ECK is a **framework-agnostic control and observability core**.  
It is designed to sit *beneath* agent behaviour rather than define it.

ECK enforces explicit phase separation, records epistemic signals, detects drift, and applies **policy-gated control** — without embedding planning, reasoning, tool orchestration, or agent ideology.

If something is not visible in code or tests, **it does not exist**.

---

## Current Status

### Releases

- **v0.1.0** — initial stable kernel  
- **v0.1.1** — test-suite completion and invariant locking  
  *(no runtime changes, no API changes)*

### v0.1.x Guarantees

The v0.1.x line is:

- **Behaviorally stable**
- **Test-complete**
- **Invariant-locked**

All core semantics are frozen.  
No feature work is permitted without a version escalation.

The enforcement surface completed in Commit 4c is fully proven via deterministic invariant tests.

---

## Design Philosophy

ECK is built around **epistemic control**, not task throughput.

Core principles:

- **Explicit phases**  
  Prediction, execution, and evaluation are separate and observable.

- **Observability before enforcement**  
  Signals (confidence, drift, feasibility) are recorded *before* they affect behaviour.

- **No silent coupling**  
  Signals do not alter behaviour unless an explicit policy mode allows it.

- **Single execution seam**  
  All real-world effects flow through one narrow, auditable interface.

- **Irreversible safety upgrades**  
  Policy modes may only move in safer directions during runtime.

- **Refusal over fabrication**  
  The kernel prefers halting or deferring over proceeding incorrectly.

---

## Architecture Overview

ECK separates **cognition**, **control**, and **effects**.

### Pure / Stateless Components  
(no side effects, no memory mutation)

- `prediction.generate_prediction`
- `task_generation.generate_subtasks`

### Execution Seam  
(single, auditable effects boundary)

- `execution.execute_task`

### Stateful Control Layer

- `ECKAgent` — orchestration and policy enforcement  
- `WorldModel` — append-only task history  
- `DriftMonitor` — epistemic error and instability tracking  
- `TaskQueue` — bounded work queue  

This architecture allows ECK to integrate with **any LLM stack** without inheriting framework assumptions.

---

## Policy Modes

ECK supports explicit policy modes:

- **NORMAL** — advisory signals only  
- **GUIDED** — recommendations visible but not enforced  
- **ENFORCED** — recommendations may gate execution  
- **HALT** — immediate stop *(irreversible without manual reset)*  

### Invariants (Test-Locked)

- Policy upgrades are **irreversible**
- User-configured policy mode is authoritative
- GUIDED mode **must not hard-block execution**
- ENFORCED mode may defer execution
- No split-brain: policy state is single-sourced and synchronized

All of the above are enforced by deterministic tests.

---

## Memory & Prediction

- Task memory is **append-only**
- Task lifecycle states are explicit and recorded
- Memory retrieval can be **fully disabled**

When memory retrieval is disabled:

- No retrieval calls occur *(verified by tests)*
- Prediction prompts are **bit-for-bit identical** to enabled-but-empty retrieval cases

This prevents silent prompt drift and preserves determinism.

---

## Critic Semantics

- Critic output must be valid JSON with the expected structure.
- Malformed, empty, or unparseable output results in **deterministic pessimistic failure**:
  - `success` is `False`
  - `severity` is `1.0` (maximal failure penalty)
  - Feedback is a non-empty string (for observability and auditability)
- Exact feedback wording is **not** part of the contract.
- Cross-validation disagreement also triggers failure with `severity == 1.0`.

These behaviours are locked by deterministic tests and reflect the kernel’s refusal-over-fabrication posture.

---

## What ECK Is Not

ECK is intentionally narrow.

It is **not**:

- A general agent framework  
- A planner or reasoning engine  
- A tool orchestration system  
- A LangChain / LangGraph replacement  
- A multi-agent system  
- A production-ready autonomous product  
- A confidence or factual correctness estimator  
- An opinionated AI ideology  

ECK exists to make agent behaviour **inspectable, interruptible, and correctable**.

---

## Examples

The `examples/` directory contains **demonstrations only**.

- `basic_run.py` — control-flow demonstration with a stub LLM  
- `local_llm_run.py` — minimal end-to-end run using a real local LLM  

Examples are **not** reference implementations and are **not** covered by API stability guarantees.

---

## Quick Start

You must supply your own LLM callable.

```
from eck.agent import ECKAgent

def llm(prompt: str) -> str:
    return \"stub response\"

agent = ECKAgent(
    objective=\"Replace with a real objective\",
    llm_call=llm,
)

agent.seed(\"Initial task\")

# Run one or more control cycles
while agent.step():
    pass  # add logging / sleep / monitoring here
```

---

## License

MIT License — see `LICENSE` for details.

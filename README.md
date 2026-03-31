# Epistemic Control Kernel (ECK)

**ECK** is a minimal, reliability-first microkernel for autonomous agents.

It sits *beneath* agent behaviour rather than defining it, enforcing explicit phase separation, recording epistemic signals, and applying **policy-gated control** — without embedding planning, reasoning, tool orchestration, or agent ideology.

If something is not visible in code or tests, it does not exist.

---

## Current Status

**v0.3.0** — Integrated control loop + telemetry wiring
(ADR-021–ADR-045)

* Deterministic control loop (confidence → policy → execution → critic) fully integrated
* Policy gate enforced as exclusive execution authority across the live agent loop
* End-to-end telemetry (ADR-045) with coherent per-step traces and deterministic nonce progression
* CI-enforced invariants extended to full control-cycle behavior

The v0.3.0 line is operational, trace-complete, and invariant-enforced at runtime. No feature work is permitted without a version escalation.


---

## Design Philosophy

ECK is built around **epistemic control**, not task throughput.

Core principles:
- Deterministic core behaviour
- Explicit phases and a single execution seam
- Observability before enforcement
- No silent coupling — signals never alter behaviour without explicit policy mediation
- Refusal over fabrication
- Irreversible safety upgrades

---

## Architecture

ECK follows a strict **microkernel-style architecture**:

- Small deterministic core (stdlib-only)
- Optional capability layers (memory retrieval, similarity scoring, prompt scaffolding) that remain advisory-only
- All behavioural authority stays inside the kernel via explicit policy mediation

Full details and the complete runtime model are in **[ARCHITECTURE.md](ARCHITECTURE.md)**.

All significant design decisions, invariants, and red lines are recorded in the **[Architecture Decision Records](docs/adr/)** (ADR-020–ADR-037).

---

## Quick Start

You must supply your own LLM callable.

```python
from eck.agent import ECKAgent

def llm(prompt: str) -> str:
    return "stub response"  # ← replace with real LLM call

agent = ECKAgent(
    objective="Replace with a real objective",
    llm_call=llm,
)

agent.seed("Initial task")

# step() executes a single kernel control cycle
while agent.step():
    pass  # ← add logging, sleep, timeout, monitoring, or a proper loop condition here
```

---

## What ECK Is Not

ECK is intentionally narrow. It is **not**:

- A general agent framework
- A planner or reasoning engine
- A tool orchestration system
- A LangChain / LangGraph replacement
- A multi-agent system
- A production-ready autonomous product

---

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — high-level system model and principles
- **[docs/adr/](docs/adr/)** — complete locked Architecture Decision Records
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — development guidelines

---

## License

MIT License — see [LICENSE](LICENSE) for details.

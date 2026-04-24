# Epistemic Control Kernel (ECK)

Autonomous agents are taking irreversible actions without deterministic
authorization boundaries. Frontier models demonstrate that high capability
does not guarantee reliable calibration — the top-ranked model on current
benchmarks reports an 86% hallucination rate on knowledge tasks. A
confident wrong answer that drives an irreversible action is a different
failure mode from a confident wrong answer that a human can correct.

**ECK is a proposed architecture for systems where agentic execution
authority must be bounded by explicit policy, calibrated epistemic
signals, and irreversible-action safeguards.**

---

## The Problem ECK Addresses

Without an explicit authorization boundary, an LLM agent's confidence
signal and its execution permission are the same thing. The model assesses
its own proposal, finds it acceptable, and acts. Nothing stands between
the proposal and the action except the model's self-assessment.

This structural condition is consistent with documented incidents:
autonomous agents purchasing items without consent, deleting drives,
moving files into unrecoverable states, and dropping databases — not because the
models were unsophisticated, but because no deterministic check stood
between proposal and execution.

ECK addresses this by separating three things that current agent
architectures conflate:

- **What the LLM proposes** — advisory only, never authoritative
- **What the epistemic state of the system permits** — tracked as a
  calibrated confidence signal (imperfect but structured) over sequences of outcomes, not
  self-reported per-call
- **What policy authorizes** — determined by a deterministic gate whose
  rules are explicit, testable, and domain-specific

---

## How ECK Works

ECK sits beneath agent behaviour rather than defining it. Every execution
attempt passes through a single, mandatory control cycle:

    propose → gate → authorize → perform → critic → confidence → trace

**The LLM is advisory only.** It proposes actions and evaluates outcomes.
It cannot authorize its own execution.

**The policy gate is the sole execution authority.** It evaluates the
proposed action against the current epistemic state and explicit domain
policy. Gate decisions are deterministic and testable.

**Confidence is epistemic input, not execution permission.** The
confidence signal tracks uncertainty over sequences of outcomes using a
smoothed accumulator with failure window semantics. A single
high-confidence proposal does not override a degraded epistemic
trajectory.

**Policy mode escalation is irreversible.** NORMAL → GUIDED → ENFORCED →
HALT. The kernel degrades gracefully under uncertainty and cannot be
talked back to a more permissive state by a confident model.

**Disabling the kernel has no silent effect.** Agent behaviour changes
visibly and immediately; no signal can alter behaviour without passing
through the policy gate.

ECK's core function is to separate proposal from execution authority.
No proposal can become an action without passing through a deterministic
policy decision.

---

## Who ECK Is For

ECK is relevant when three conditions are present:

1. **The domain is irreversibility-sensitive.** Some actions cannot be
   undone and the cost of a wrong execution is not recoverable by
   iteration.

2. **The policy logic is non-trivial and composed.** A single threshold
   check is auditable by inspection. A gate that must reason about
   epistemic trajectory, failure windows, domain-semantic rules, and
   policy mode state simultaneously is not. ECK makes that composition
   verifiable rather than assumed.

3. **The system operates over long horizons with drift.** A single-session
   agent with a narrow task can be inspected end-to-end. A persistent
   agent running across changing conditions cannot. Drift detection and
   formal halt semantics become load-bearing at scale.

These conditions compound. ECK's overhead is justified when the expected
cost of a silent policy failure — factoring in irreversibility,
compositional complexity, and horizon length — exceeds the cost of implementing and maintaining the control architecture.

If your system does not authorize actions with real-world consequences,
ECK is likely unnecessary.

---

## Current Status

**v0.4.0** — Validation, Enforcement and Observability

The v0.3.0 design baseline is locked (ADR-020–ADR-045). v0.4.0 adds
validation, enforcement, and observability infrastructure without
introducing new load-bearing semantics or changing the control loop.

**Delivered in v0.4.0:**
- Trace Analysis Service with strict no-control-authority invariant
- Adversarial test lane: single-seam invariant edge tests and multi-cycle
  sequence tests covering failure window lifecycle, EWMA dynamics, policy
  mode monotonicity, and HALT irreversibility
- Property-based testing (Hypothesis) with three universally quantified
  invariants: confidence boundedness, HALT absorption, gate execution
  exclusivity
- Mechanical enforcement layer: mypy curated strict profile and CodeQL
  security-extended, both blocking in CI

631 tests passing. 98.73% coverage. mypy clean. CodeQL clean.

The control semantics are stable and the kernel is adoptable today for
motivated builders willing to implement a domain-specific policy gate.
The tooling that makes policy authorship accessible to non-specialists —
the Compiled Policy Seam and consequence-aware execution — is planned for
v0.6.0 onwards. v0.5.0 moves into empirical behavioural characterisation:
verifying that the invariants hold in distribution across real traces, not
just unit tests.

---

## Quick Start

You must supply your own LLM callable.

    from eck.agent import ECKAgent

    def llm(prompt: str) -> str:
        return "stub response"  # replace with real LLM call

    agent = ECKAgent(
        objective="Replace with a real objective",
        llm_call=llm,
    )
    agent.seed("Initial task")

    while agent.step():
        pass  # add logging, sleep, timeout, or monitoring here

To supply a domain-specific policy gate:

    from eck.policy_gate import PolicyGate, PolicyDecision

    class MyPolicyGate(PolicyGate):
        def evaluate(self, proposed_action, confidence, context, **kwargs):
            # your deterministic rules here
            ...

    agent = ECKAgent(
        objective="...",
        llm_call=llm,
        policy_gate=MyPolicyGate(),
    )

---

## What ECK Is Not

ECK is intentionally narrow. It is not:

- A general agent framework
- A planner or reasoning engine
- A tool orchestration system
- A LangChain / LangGraph replacement
- A multi-agent system
- A production-ready autonomous product

ECK does not make agents more capable. It makes certain classes of failure
structurally impossible under its invariants.

---

## Honest Limitations

ECK is a well-constructed answer to a real problem. It is not a validated
answer. The necessity case rests on:

- Documented incidents of autonomous agents causing irreversible harm
  without deterministic authorization boundaries
- Convergent engineering evidence: organisations building reliable agentic
  systems independently converge on the same propose → gate → authorize
  pattern
- The structural argument that capability and calibration are not coupled,
  and that a system relying on model self-assessment alone is structurally
  exposed

What ECK has not yet demonstrated is that its specific architecture
produces materially better outcomes than a simpler deterministic check in
the domains where it matters most. That evidence requires deployment in
irreversibility-sensitive contexts. If you are building in such a context,
ECK is designed for you — and your deployment experience is the evidence
the project needs.

---

## Design Philosophy

- Deterministic core behaviour
- Explicit phases and a single execution seam
- Observability before enforcement
- No silent coupling — signals never alter behaviour without explicit
  policy mediation
- Refusal over fabrication
- Irreversible safety upgrades

If something is not visible in code or tests, it does not exist.

---

## Documentation

- **ARCHITECTURE.md** — high-level system model and principles
- **docs/adr/** — complete locked Architecture Decision Records
  (ADR-020–ADR-045)
- **docs/design-notes/** — informal design notes including the Trace
  Analysis Service
- **CONTRIBUTING.md** — development guidelines

---

## License

MIT License — see LICENSE for details.

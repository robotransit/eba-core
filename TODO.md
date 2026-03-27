# TODO
**Last updated:** 2026-03-27
**Current design baseline:** v0.2.0 (architecture & invariants locked)
**Current implementation state:** v0.2.0 complete

The v0.2.0 design is complete and formally locked through ADR-020–ADR-041.
All architectural decisions, invariants, guardrails, and CI foundations have
been codified and implemented.

**Implementation state:**
The v0.2.0 architecture is fully implemented. All locked invariants have been
converted into code, tested, and verified. 345 tests passing across Python
3.10, 3.11, and 3.12. 98.17% coverage. CI green on all three versions.

See [v0.2.0 implementation checklist](docs/v0.2.0-implementation-checklist.md)
for the full ADR-mapped completion record.

---

## Remaining Housekeeping (v0.2.0)

- Update GitHub Actions workflow actions to Node.js 24 before June 2nd 2026
  forced cutover (actions/checkout, actions/setup-python, actions/cache,
  actions/upload-artifact)

---

## v0.3.0 Roadmap — Complete and Harden the Architecture

### 1. Formal Model (TLA⁺ or Alloy)

Before hardening the execution surface, build a small formal model capturing:
- The agent step loop and policy mode state transitions
- The propose/authorize/perform separation
- Core safety properties: no unauthorized action, HALT stops all side effects,
  policy escalation is irreversible

Model-check these properties before writing the corresponding code.
The model's assumptions become the ADR's invariants — correct sequencing.

### 2. Execution Surface — propose/authorize/perform (ADR required)

`execute_task` is currently a stub. In production integrations it will perform
real effects (API calls, file writes, code execution). The kernel currently has
no authorization boundary between "LLM proposes an action" and "action is
performed." This is the primary remaining architectural gap.

Required work:
- New ADR defining the propose/authorize/perform contract
- Split `execute_task` into:
  - `propose_execution(task_text, llm_call)` → `ProposedAction` (advisory, structured)
  - `authorize_and_perform(proposed_action)` → outcome (kernel-enforced, policy-gated)
- `authorize_and_perform` enforces: policy-mode checks, whitelists, provenance,
  rate limits. Only this function may perform external effects.
- Runtime assertions mapping to model assumptions

### 3. Formal Telemetry Schema (ADR required)

**Prerequisite: execute_task ADR must land first.** The telemetry schema must
reflect the locked step() structure including propose/authorize/perform phases.
Designing the schema before that ADR risks building against a step() that is
about to change structurally.

Once the execution surface ADR is locked:

- **Formal event envelope** — canonical shape for all telemetry events:
  `event_type`, `version`, `timestamp`, `trace_id`, `step_id`,
  `deterministic_nonce`, `severity`, `source`, `payload`
  - `trace_id`: correlates a single agent run
  - `step_id`: correlates all events within a single `step()` cycle —
    directly addresses the current gap where correlation relies on `task_id`
    and timestamp, which is fragile
  - `deterministic_nonce`: monotonic integer per run for deterministic
    ordering and replay — aligns with ECK's determinism goals

- **Event type taxonomy** — finite, filterable set of canonical event names:
  `step.start`, `step.end`, `policy.evaluate`, `epistemic.signal`,
  `action.proposed`, `action.executed`, plus phase events matching the
  locked execution model. Specific phase names to be defined in the ADR.

- **`eck/telemetry.py`** — stdlib-only core module:
  - Constructs and emits validated event envelopes
  - Wraps existing `extra={}` into `telemetry_event` key — backwards
    compatible, existing log pipelines unaffected
  - Exposes `redact_hook`: user-supplied callable receiving payload and
    returning scrubbed payload — gives integrators a PII path without
    the kernel implementing policy
  - Lightweight validation toggle (no external deps by default)

- **Optional exporters as separate packages** — e.g. `eck.telemetry_otlp`
  installed separately, not as an extras group. Makes the optional/core
  boundary explicit at the package level. Consistent with ECK's existing
  optional dependency philosophy.

- **`telemetry/telemetry.schema.json`** and **`telemetry/event_catalog.md`**
  — machine-readable schema and human-readable event catalog in a dedicated
  `telemetry/` directory

- **Telemetry ADR** — documents schema versioning rules, the stdlib-only
  core constraint, and the optional exporter pattern

### 4. Property Testing and Static Analysis

Can begin in parallel with steps 1 and 2.

- **Hypothesis** — property-based testing for deterministic kernel functions:
  confidence signal bounds, drift monitor monotonicity, critic normalisation
  exhaustiveness, PartialStructure derivation for arbitrary inputs
- **mypy** — strict type checking; add to CI initially as non-blocking
- **CodeQL** — enable on repo (free for public repos via GitHub)
- **icontract** — runtime contract enforcement making ADR invariant violations
  fail-fast in development

### 5. Domain-Specific PolicyGate Implementations

`DefaultPolicyGate` is a bootstrapping placeholder with fixed thresholds and
no domain awareness. `PolicyContext` fields (`environment`, `safety_level`) and
`proposed_action` are currently uninterpreted. Future work includes
domain-specific subclasses that interpret these fields and apply
domain-appropriate rule sets.

### 6. Formal Verification (if higher assurance required)

If deployment context demands it:
- Commission formal verification of `authorize_and_perform` (Dafny or Coq)
- External security audit of the kernel TCB boundary
- TLA⁺ model extension to cover the full authorized execution surface

This step is appropriate before any safety-critical domain deployment.
Not required for v0.3.0 initial release.

---

## v0.4.0 Roadmap — Characterise and Validate

v0.4.0 is the empirical validation phase. Meaningful benchmarking requires
a real execution surface — the propose/authorize/perform work in v0.3.0 is
a prerequisite. Benchmarking against the current stub would tell us nothing.

### 1. Empirical Benchmarking

- Task success rate with ECK vs without ECK on equivalent task sets
- Confidence trajectory analysis — does confidence stabilise, drift, or
  oscillate across a run? Does it correlate with actual task quality?
- Halt correlation — do kernel halts correspond to genuine task failure?
- Critic category distribution — how often does partial vs success vs failure
  occur on real tasks with real LLMs?
- Parameter sensitivity — effect of varying `partial_threshold`,
  `guard_interval`, `confidence_alpha` on run length and goal completion rate

### 2. Behavioural Characterisation

- Does ECK make the system appear more calibrated to an external observer?
- Ablation studies — isolate the contribution of each kernel subsystem
  (confidence signal, drift monitor, partial outcomes, goal predicate)
- Comparison baseline: same LLM, same tasks, ECK wrapped vs unwrapped

### 3. Telemetry — PII, Sampling, and Compliance

Once domain modules are handling sensitive data:
- Define fields that must never appear in telemetry payloads
- Implement sampling and configurable verbosity per event_type for
  high-volume advisory calls
- Compliance integrations (append-only tamper-evident store, retention
  policies, audit trail requirements for regulated domains)
- Extend `redact_hook` interface with domain-specific scrubbing policies

### 4. Publish Findings

- Convert empirical results into a technical report or paper
- The evidenced empirical claim is what supports domain operator adoption
- This is the work that turns ECK from an architectural claim into a
  validated one

---

## Additional Future Work

- Add comprehensive end-to-end examples and usage patterns
- Expand policy mode examples and dynamic switching guidance
- Benchmark TaskQueue and memory retrieval at scale
- Explore optional advanced memory scoring mechanisms (subject to new ADR)
- v0.2.0 audit/observability layer — task lifecycle recording is currently
  absent, deferred to this phase (noted in agent.py)
- PartialStructure collapse_status — currently always "unresolved"; resolution
  tracking deferred to a future ADR
- ADR-038 full wiring — get_recommended_breadth() and should_execute() in
  utils.py are pre-gate utilities pending retirement once PolicyGate is the
  sole execution authority

---

All v0.2.0 work is tracked via the Architecture Decision Records in `docs/adr/`.
Contributions are welcome, but must respect the locked invariants in ADR-020–ADR-041.
See `ARCHITECTURE.md` and `docs/adr/` for the current design baseline.

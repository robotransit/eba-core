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

## v0.3.0 Roadmap — Complete and Harden the Architecture

### 1. Formal Model (TLA⁺ / PlusCal) — COMPLETE

Formal model of the propose/authorize/perform execution boundary verified
by TLC. Six state invariants and one temporal property checked exhaustively
across 79 distinct states. No errors found.

This model proves the execution boundary invariants, not full system
correctness. The verified invariants are the red lines for the
propose/authorize/perform ADR and must be enforced mechanically in the
implementation, not just described in the ADR.

See: `docs/formal/ECK.tla`, `docs/formal/ECK.cfg`

### 2. Execution Surface — propose/authorize/perform (ADR required)

`execute_task` is currently a stub. In production integrations it will perform
real effects (API calls, file writes, code execution). The kernel currently has
no authorization boundary between "LLM proposes an action" and "action is
performed." This is the primary remaining architectural gap.

Required work:
- New ADR defining the propose/authorize/perform contract, with the verified
  TLA⁺ invariants as non-negotiable red lines
- The execution surface must preserve the two orthogonal authorization
  questions proven in the formal model: gate authorization (may execution
  occur at all) and kernel authorization (is this specific action permitted)
- Split `execute_task` into:
  - `propose_execution(task_text, llm_call)` → `ProposedAction` (advisory, structured)
  - `authorize_and_perform(proposed_action)` → outcome (kernel-enforced, policy-gated)
- **All external side effects MUST occur exclusively inside
  `authorize_and_perform`, including transitive calls. No other code path
  may perform effects.**
- There must be no alternate code path — including error handling, retries,
  or callbacks — that can produce external side effects outside
  `authorize_and_perform`.
- `authorize_and_perform` must enforce both authorization conditions proven
  in the formal model:
  - gate authorization as a precondition (may execution occur at all)
  - kernel authorization at the action level (is this specific action permitted)
  - it must be the only function permitted to transition from authorized
    state to effect — directly mapping to the TLA⁺ proof obligations
- Runtime assertions mapping to model assumptions

### 3. Demonstration Policy Module (ADR required)

**Prerequisite: propose/authorize/perform ADR must be completed.**

**A demonstration PolicyGate module is a required v0.3.0 deliverable, not
a deferred validation item.**

**This is not a polish item. It is the primary safeguard against the project
becoming architecture-about-architecture.**

The central risk is that ECK proves it has a place for policy without ever
proving it can express meaningful policy. `DefaultPolicyGate` is a confidence
threshold with no domain awareness. If it remains unchanged, the system risks
collapsing to confidence-only gating.

**PolicyGate invariants — hard red lines for all PolicyGate implementations
including the demonstration module:**

- **PolicyGate must be side-effect free.** It may not perform external
  actions or mutate external state. All side effects remain exclusively
  within `authorize_and_perform`.
- **PolicyGate must not authorize or trigger execution directly.** It may
  only return a decision (EXECUTE / RETRY / DEGRADE / HALT) consumed by
  the kernel. It must not introduce any alternate execution path, side-effect
  path, or post-gate enforcement mechanism.
- **PolicyGate may inspect `ProposedAction` to determine whether execution
  should be permitted at the cycle level, but it must not perform
  action-level admissibility checks.** Final authorization of concrete
  effects remains exclusively within `authorize_and_perform`.
- **The demonstration module must not derive its decision solely from
  confidence or any monotonic function of confidence.** This prevents
  disguised threshold logic such as nonlinear transforms of the confidence
  signal.

These invariants apply to `DefaultPolicyGate`, the demonstration module, and
all future `PolicyGate` implementations without exception.

**Three things the demonstration module must prove:**

1. The gate can inspect `proposed_action` content in a principled way —
   `ProposedAction` is a real semantic object, not decorative structure.
   The demonstration module MUST rely on structured fields of `ProposedAction`
   as defined in the propose/authorize/perform ADR. Free-form text inspection
   alone is insufficient.
2. Contextual policy can change authorization outcomes even when confidence
   is high — `PolicyContext.safety_level` is operational, not placeholder
   metadata.
3. At least one non-EXECUTE outcome (RETRY / DEGRADE / HALT) where the
   decision is not derived from confidence thresholds and remains valid even
   at high confidence. The refusal logic must depend on a non-trivial semantic
   relationship within `ProposedAction` and/or `PolicyContext`, and must not
   be expressible as a confidence threshold, simple blacklist, or single-field
   type check alone.

   Tests MUST include:
   - a case where confidence ≥ high threshold (e.g. ≥ 0.9)
   - and the `PolicyGate` returns a non-EXECUTE outcome
   - and the decision reason is independent of confidence
   - and the decision logic is not expressible as a confidence threshold,
     simple blacklist, or single-field type check

   The demonstration tests are considered contract-compliance tests for the
   PolicyGate semantic floor and must remain stable under CI. This turns the
   requirement into something that cannot silently regress.

The third is the most important: a high-confidence non-EXECUTE outcome on
domain-semantic grounds proves that policy is not reducible to confidence —
that ECK carries something the confidence signal alone does not.

**What it must not be:**
- A wrapper around `if confidence < x`
- A thin blacklist
- A production claim disguised as a demo
- A large domain ontology
- An external wrapper or bypass around the PolicyGate contract

**What it must be:**
- Implemented as a `PolicyGate` subclass — through the existing contract,
  not around it
- A small but explicit domain rule set
- Structured inspection of `ProposedAction`
- Real use of `PolicyContext`

The domain choice is secondary, but must be rich enough to support at least
one non-trivial non-EXECUTE outcome that cannot be expressed as a simple
threshold or blacklist rule. Once a domain module exists, the question changes
from "is the architecture clean?" to "can this architecture express serious
policy?" That is a much healthier forcing function.

The demonstration module should emit telemetry events using the v0.3.0 schema
where available, but must not depend on full telemetry completion.

The demonstration module establishes the minimum expressive standard the
architecture must support. Future PolicyGate implementations in narrower
domains may be legitimately simpler, but the architecture must remain capable
of supporting semantically richer policy than confidence thresholds alone.

**Deliverable:** One concrete `PolicyGate` subclass + test suite that:
- demonstrates at least one high-confidence non-EXECUTE outcome
  (confidence ≥ threshold)
- where the decision is independent of confidence
- and the decision logic is not expressible as a confidence threshold,
  simple blacklist, or single-field type check
- and passes under CI with deterministic behaviour

### 4. Formal Telemetry Schema (ADR required)

**This is a structural design step; implementation may be partial in v0.3.0.**

**Prerequisite: the propose/authorize/perform ADR must land first.** The
telemetry schema must reflect the locked step() structure including
propose/authorize/perform phases. Designing the schema before that ADR risks
building against a step() that is about to change structurally.

Once the execution surface ADR is locked:

- **Formal event envelope** — canonical shape for all telemetry events:
  `event_type`, `version`, `timestamp`, `trace_id`, `step_id`,
  `deterministic_nonce`, `severity`, `source`, `payload`
  - `trace_id`: correlates a single agent run
  - `step_id`: correlates all events within a single `step()` cycle —
    directly addresses the current gap where correlation relies on `task_id`
    and timestamp, which is fragile
  - `deterministic_nonce`: monotonic integer per run derived exclusively
    from kernel state progression (e.g. cycle counter) — must not be
    derived from wall-clock time or randomness, preserving ECK's
    determinism guarantees

- **Event type taxonomy** — finite, filterable set of canonical event names:
  `step.start`, `step.end`, `policy.evaluate`, `epistemic.signal`,
  `action.proposed`, `action.executed`, plus phase events matching the
  locked execution model. Specific phase names to be defined in the ADR.

- **`eck/telemetry.py`** — stdlib-only core module:
  - Constructs and emits validated event envelopes
  - Wraps existing `extra={}` into `telemetry_event` key — backwards
    compatible; baseline operation should not require modification of
    existing logging call sites
  - Exposes `redact_hook`: user-supplied callable receiving payload and
    returning scrubbed payload — gives integrators a PII path without
    the kernel implementing policy
  - Lightweight validation toggle (no external deps by default)
  - Telemetry must not introduce any behavioural coupling or authority —
    observability only, consistent with the global advisory layer invariant

- **Optional exporters as separate packages** — e.g. `eck.telemetry_otlp`
  installed separately, not as an extras group. Makes the optional/core
  boundary explicit at the package level. Consistent with ECK's existing
  optional dependency philosophy.

- **`telemetry/telemetry.schema.json`** and **`telemetry/event_catalog.md`**
  — machine-readable schema and human-readable event catalog in a dedicated
  `telemetry/` directory

- **Telemetry ADR** — documents schema versioning rules, the stdlib-only
  core constraint, and the optional exporter pattern

### 5. Property Testing and Static Analysis

Can begin in parallel with steps 1 and 2.

- **Hypothesis** — property-based testing for deterministic kernel functions:
  confidence signal bounds, drift monitor monotonicity, critic normalisation
  exhaustiveness, PartialStructure derivation for arbitrary inputs
- **mypy** — strict type checking; add to CI initially as non-blocking
- **CodeQL** — enable on repo (free for public repos via GitHub)
- **icontract** — runtime contract enforcement making ADR invariant violations
  fail-fast in development

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
a real execution surface and a demonstration policy module — both v0.3.0
prerequisites. Benchmarking against stubs would tell us nothing.

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
- Does the demonstration policy module demonstrably change behaviour relative
  to DefaultPolicyGate on equivalent task sets?
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

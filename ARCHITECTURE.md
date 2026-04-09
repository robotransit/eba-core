# Architecture

## Overview

The Epistemic Control Kernel (ECK) follows a **microkernel-style architecture** that strictly separates a small deterministic core from optional capability layers.

The design prioritizes:

* Strict control over authority surfaces
* Deterministic and testable core behavior
* Explicit policy mediation for all behavioral effects

Core agent behavior must remain stable and predictable **regardless of optional capability layers**. Capability features (memory retrieval, similarity scoring, prompt scaffolding, etc.) must remain **advisory-only** and never alter core semantics unless explicitly mediated by the policy gate.

All significant architectural decisions are recorded in the [Architecture Decision Records (ADRs)](./docs/adr/).

---

## Design Baseline vs Implementation Layers

This document describes the **v0.3.0 design baseline**, which defines
the authoritative architecture and invariants of the Epistemic Control Kernel.

Subsequent releases (e.g. v0.4.0) may introduce validation, enforcement,
or observability layers (tests, analysis services, static checks) without
modifying core semantics.

Such layers must:
- preserve deterministic behavior
- introduce no new authority surfaces
- remain strictly non-interfering with control flow

Unless explicitly captured in a new ADR, these additions do not alter
the design baseline described in this document.

---

## System Model

At runtime, the ECK executes a deterministic agent loop with explicit separation between:

* proposal
* epistemic evaluation
* policy decision
* execution authorization
* execution
* telemetry emission

The full cycle is:

1. A task or action is proposed (`ProposedAction`)
2. The policy gate evaluates the proposal against epistemic state and returns a `PolicyDecision`
3. The agent loop enforces the decision prior to execution
4. If authorized, execution occurs via `authorize_and_perform(...)`
5. An `ExecutionResult` is produced
6. The critic evaluates the result and returns `CriticOutcome` + optional `PartialStructure`
7. Confidence is updated deterministically
8. Drift is recorded append-only and checked via periodic guard
9. Goal completion is evaluated deterministically
10. Telemetry is emitted as a coherent per-step trace

This establishes a strict separation between:

* **decision (policy gate)**
* **authorization (agent loop)**
* **execution (mechanical effect)**
* **epistemic evaluation (critic)**
* **observability (telemetry surface)**

The kernel operates as a compact, policy-mediated state machine whose transitions are driven exclusively by deterministic rules and critic-derived signals, never by LLM outputs directly.

---

## Execution Boundary (ADR-042)

The execution boundary formalises the transition from policy decision to effect.

Key components:

* `ProposedAction` — structured, pre-execution action representation
* `authorize_and_perform(...)` — single execution seam
* `ExecutionResult` — canonical post-execution result

Execution sequence:

BACKTICKS
propose → evaluate (policy gate) → authorize → perform → result
BACKTICKS

### Invariants

* Execution occurs **only** after explicit policy authorization
* Unauthorized actions must never execute
* `authorize_and_perform` is the sole effectful boundary
* Execution results must be fully captured in `ExecutionResult`
* No implicit execution paths exist outside the boundary
* Execution must be deterministic with respect to inputs

This boundary defines the kernel's **effect authority surface**.

---

## Policy Gate

The policy gate is the exclusive consumer of confidence for control decisions and the sole pre-execution mediation layer between epistemic state and execution.

The `PolicyGate` contract is expressed as a structural `typing.Protocol` with `@runtime_checkable`. Any class implementing `evaluate(proposed_action, confidence, context) -> PolicyDecision` with the correct signature satisfies the contract without requiring nominal inheritance.

The default implementation is `DefaultPolicyGate` — a conservative, domain-agnostic baseline that maps confidence bands to execution modes. Domain-specific policy modules may be injected at construction time.

### Domain-Specific Policy Modules (ADR-043 / ADR-044)

ADR-043 formalises the proof that policy is not reducible to confidence, demonstrated via the childcare domain `DemoPolicyGate`. Six load-bearing rules are evaluated in a fixed order: out-of-domain fallback, schema validation, high-safety unbounded refusal, child-facing transformation refusal, failure window, and baseline confidence thresholds.

ADR-044 defines out-of-domain evaluation semantics. Domain-specific policy modules that rely on `PolicyContext.environment` must not raise, must not silently passthrough, and must return an explicit non-EXECUTE `PolicyDecision` with a stable `rule_id` and `reason` identifying the domain mismatch. The kernel does not enforce policy-module/domain matching — that responsibility belongs to the operator.

See:

→ [docs/adr/ADR-038.md](docs/adr/ADR-038.md)
→ [docs/adr/ADR-039.md](docs/adr/ADR-039.md)
→ [docs/adr/ADR-043.md](docs/adr/ADR-043.md)
→ [docs/adr/ADR-044.md](docs/adr/ADR-044.md)

---

## Telemetry Surface (ADR-045)

The telemetry system provides structured, deterministic observability of the full agent cycle.

Location:

* `eck/telemetry.py`
* `telemetry/telemetry.schema.json`
* `telemetry/event_catalog.md`

Characteristics:

* Fully deterministic
* Side-effect free with respect to control flow
* Replay-safe — no behavioral impact when enabled or disabled
* Stdlib-only implementation

### Event Model

The system emits exactly six canonical event types representing the full cycle:

| Event | Source | Meaning |
|---|---|---|
| `step.start` | `agent` | cycle boundary opens |
| `action.proposed` | `execution` | proposal outcome |
| `policy.evaluate` | `policy_gate` | gate decision |
| `action.executed` | `execution` | execution outcome |
| `epistemic.signal` | `confidence` | confidence state transition |
| `step.end` | `agent` | cycle boundary closes |

### Trace Coherence

Each step is associated with three shared identifiers:

* `trace_id` — run-level correlation identifier, refreshed at `run()` start
* `step_id` — derived deterministically from `trace_id` and `deterministic_nonce` via `make_step_id()`
* `deterministic_nonce` — monotonic integer derived from `self.cycles` at step entry

All six events within a step share identical values for all three identifiers, enabling complete per-step trace reconstruction and deterministic replay.

### Replay Silence

`ConfidenceSignal.replay()` produces no `epistemic.signal` events. Telemetry is suppressed during replay for the same reason logging is suppressed — replay is an internal audit mechanism, not a live control cycle.

### Constraint

> Telemetry must never influence behavior.

---

## Core Architectural Principles

* **Deterministic Core**
  The agent loop, execution boundary, and policy gate must remain deterministic and stdlib-only.

* **Explicit Authority Surfaces**
  All authority transitions are explicit:

  * proposal → policy → authorization → execution

* **Policy Gate Exclusivity**
  The policy gate is the sole consumer of epistemic signals and the only authority for execution decisions.

* **Advisory Cognition**
  Memory, prompts, similarity, and LLM outputs are advisory-only.

* **Optional Capability Layers**
  All advanced features must be optional and removable without behavioral divergence.

* **Monotonic Safety**
  Policy mode upgrades are irreversible. Severe instability halts execution.

* **Epistemic Seriousness**
  Confidence is kernel-owned and updated deterministically from critic outcomes.

---

## Safety Boundaries ("Must Never Happen")

* No execution without policy authorization
* No authority surfaces outside the policy gate
* No LLM control over execution, policy, or lifecycle
* No non-deterministic behavior in core control flow
* No behavioral side-effects from telemetry
* No implicit execution paths outside `authorize_and_perform`
* No silent coupling between signals and behavior
* No new authority surfaces through memory, prompts, similarity, or capability layers
* No dependency creep — the core package must remain stdlib-only
* No split-brain state — new state variables must have a single source of truth

---

## Core vs Optional Capabilities

**Core** (always valid, even if all optionals are disabled):

* Agent loop semantics and policy mode behavior
* Policy gate contract and default control mediation
* Execution boundary (`authorize_and_perform`)
* `ProposedAction` / `ExecutionResult` model
* Confidence signal processor (EWMA, failure window, partial outcomes)
* Critic outcome taxonomy and `PartialStructure` derivation
* Drift monitoring and periodic guard
* Goal completion predicate
* Telemetry surface (deterministic, stdlib-only)

**Optional** (behind explicit toggles or extras):

* Memory retrieval
* Embedding similarity
* Prompt scaffolding
* Advanced evaluation layers

---

## Reserved Architectural Boundaries (Design-Level Only)

Two boundaries are defined as design commitments but are not yet implemented. Both follow the same pattern: design the boundary, name the types, do not implement until load exists.

See `docs/proposals/` for full specifications.

---

### Execution Kernel Boundary (EKB)

Separates semantic authority (what is allowed) from mechanical authority (how it is done).

Reserved form:

BACKTICKS
ECK (semantic authority)
    ↓
AuthorizedAction
    ↓
Execution Kernel (mechanical authority)
    ↓
KernelExecutionResult
    ↓
ECK (critic / confidence)
BACKTICKS

Current state: execution is embedded within `authorize_and_perform`. The EKB introduces no behavior at present.

Adoption triggers: multiple action types with materially different execution characteristics; resumability or replay requirements; shared execution surface across multiple ECK instances.

→ [docs/proposals/Proposal_-_Execution_Kernel_Boundary.md](docs/proposals/Proposal_-_Execution_Kernel_Boundary.md)

---

### Compiled Policy Seam

Defines the future ingestion path for document-derived policy.

Reserved form:

BACKTICKS
Policy Documents
    ↓
External Compiler (LLM-assisted, offline, fallible)
    ↓
CompiledPolicy (immutable artifact)
    ↓
Human Review / Approval (mandatory)
    ↓
ECK (deterministic enforcement via CompiledPolicyGate)
BACKTICKS

Reserved components: `CompiledPolicy` (placeholder type), `CompiledPolicyGate` (no-op wrapper around `DefaultPolicyGate`).

Current state: no compiled policy present. `DefaultPolicyGate` is sole authority.

Adoption triggers: document-based policy required in practice; hand-authored rules become insufficient; policy provenance required.

→ [docs/proposals/Proposal_-_External_Policy_Compiler_and_CompiledPolicyGate_Seam.md](docs/proposals/Proposal_-_External_Policy_Compiler_and_CompiledPolicyGate_Seam.md)

---

## v0.2.0 Architecture Sequence

The v0.2.0 architecture is defined through the ADR set ADR-020 through ADR-041.

ADR-020 establishes the roadmap and ordering constraints for the v0.2.0 architecture. The subsequent ADRs are grouped by subsystem for readability.

**Confidence Semantics**
- [ADR-021 — Rolling Confidence Update Cadence](docs/adr/ADR-021.md)
- [ADR-022 — Failure vs Non-Failure Classification](docs/adr/ADR-022.md)
- [ADR-023 — Basic Asymmetry & Recovery Shape (Semantics Only)](docs/adr/ADR-023.md)
- [ADR-024 — Minimal Input Signal Set for Confidence Update](docs/adr/ADR-024.md)
- [ADR-025 — Confidence Update Mechanics (EWMA)](docs/adr/ADR-025.md)

#### Confidence Signal Processor (PR1 Implementation)

The ECK confidence system is a deterministic, non-authoritative epistemic signal processor with strict kernel-enforced invariants (ADR-021–025).

The confidence signal is updated on every cycle via `ConfidenceSignal.update()`, which accepts a `CriticOutcome` and optional `PartialStructure`. For partial outcomes, `PartialStructure` (derived by the kernel from bounded LLM fields) determines the permitted movement class. Non-partial outcomes use `MovementClass.BOTH` by default.

See the formal specification for full invariants and system model:

→ [docs/confidence-signal-formal.md](docs/confidence-signal-formal.md)

**Policy Gate**
- [ADR-038 — Policy Gate Contract – Exclusive Consumer of Epistemic Signals](docs/adr/ADR-038.md)
- [ADR-039 — Agent Loop & Policy Gate Integration](docs/adr/ADR-039.md)

#### Policy Gate (PR2 Implementation)

The policy gate is the exclusive consumer of confidence for control decisions and the sole pre-execution mediation layer between epistemic state and execution. It enforces strict invariants including purity, determinism, side-effect freedom, monotonicity, and explicit default semantics. The policy gate is a pure, referentially transparent function of `(proposed_action, confidence, context)`.

ADR-039 establishes the agent loop as the enforcement point for the policy gate. No execution may occur without explicit gate authorization. No bypass paths are permitted.

**Memory Integration**
- [ADR-026 — Retrieval Semantics & Contract](docs/adr/ADR-026.md)
- [ADR-027 — Enable/Disable Semantics for Memory Retrieval](docs/adr/ADR-027.md)
- [ADR-028 — Retrieval Influence Semantics](docs/adr/ADR-028.md)
- [ADR-029 — Observability & Logging for Retrieval](docs/adr/ADR-029.md)
- [ADR-030 — Test & Invariant Lock for Memory Retrieval](docs/adr/ADR-030.md)

**Similarity and Optional Dependencies**
- [ADR-031 — Similarity Retrieval API Contract](docs/adr/ADR-031.md)
- [ADR-032 — Optional Embeddings + Cosine Integration](docs/adr/ADR-032.md)

**Prompt Integration**
- [ADR-033 — Prompts Integration Cleanup & Authority Guardrails](docs/adr/ADR-033.md)

**CI and Observability**
- [ADR-034 — CI Workflow Foundational Contract](docs/adr/ADR-034.md)
- [ADR-035 — GitHub Actions CI Workflow Implementation](docs/adr/ADR-035.md)
- [ADR-036 — Test Coverage & Invariant Enforcement Metrics](docs/adr/ADR-036.md)
- [ADR-037 — CI Observability & Logging](docs/adr/ADR-037.md)

**Drift Monitoring and Goal Completion**
- [ADR-040 — Drift Monitor Semantics](docs/adr/ADR-040.md)
- [ADR-041 — Goal Completion Predicate](docs/adr/ADR-041.md)

#### ECK Core Kernel Reconciliation (PR8 Implementation)

The v0.2.0 kernel reconciliation completes the epistemic control loop end-to-end.

**Drift monitoring (ADR-040):**
Drift evidence is append-only — no resets of history. Derived state (streak) may be cleared. Two independent halt conditions: streak-based halt and severe instability halt. Severe instability is enforced via a single periodic guard seam (`guard_interval=1` default delivers per-cycle semantics; increase for explicit grace period). No internal recovery — halt is the only response to severe instability.

**Goal completion predicate (ADR-041):**
Goal completion is a deterministic kernel predicate requiring all three conditions simultaneously: critic success, natural queue exhaustion (not policy-suppressed), and confidence ≥ threshold. The `subtasks_suppressed` flag disambiguates queue empty due to policy suppression from genuine completion. The LLM has no authority over this decision.

**PartialStructure derivation:**
The critic derives authoritative `PartialStructure` from bounded LLM fields (`conflict_kind`, `conflict_footprint`). The kernel normalises to closed enum vocabulary with deterministic fallbacks (`RESOLUTION_INSTABILITY` + `{LOCAL}`). `PartialStructure` exists if and only if `category == "partial"`. Partial confidence updates are now fully active.

**Critic disagreement semantics:**
Disagreement is detected at the derived-category level, not raw outcome token level. Disagreement escalates severity to 1.0 but preserves the category from the first call. A would-be partial outcome stays partial even under disagreement.

---

## v0.3.0 Architecture Sequence

The v0.3.0 architecture is defined through ADR-042 through ADR-045.

**Execution Boundary**
- [ADR-042 — Propose/Authorize/Perform Execution Boundary](docs/adr/ADR-042.md)

**Domain Policy**
- [ADR-043 — Demonstration Policy Module (Semantic Policy Capability)](docs/adr/ADR-043.md)
- [ADR-044 — Out-of-Domain Policy Module Evaluation Semantics](docs/adr/ADR-044.md)

**Telemetry**
- [ADR-045 — Formal Telemetry Schema and Observability Contract](docs/adr/ADR-045.md)

### Notable Additions

* Explicit execution seam (`authorize_and_perform`) with six formal invariants
* `ProposedAction` and `ExecutionResult` as first-class typed boundary objects
* `PolicyGate` converted from abstract base class to structural `typing.Protocol`
* Childcare domain policy proof (`DemoPolicyGate`) demonstrating policy is not reducible to confidence
* Formal out-of-domain handling — no silent passthrough, explicit non-EXECUTE required
* Deterministic telemetry surface with full per-step trace coherence
* Six canonical telemetry event types instrumented at source ownership boundaries
* `tests/test_telemetry_wiring.py` — trace-coherence integration tests driving live instrumented components

### Cycle Accounting

`self.cycles` is incremented inside `_end()` on all post-`step.start` exits — continued, goal completion, drift halt, and severe instability halt alike. This ensures:

* consistent cycle accounting regardless of return path
* accurate `deterministic_nonce` progression across steps
* honest `run()` iteration accounting

Pre-start exits (HALT mode, empty queue) do not call `_end()` and do not increment `self.cycles`.

---

## Relationship to ADRs

This document provides a structural map of the system. All invariants, constraints, and design reasoning are defined in the individual Architecture Decision Records under [docs/adr/](docs/adr/).

Reserved boundaries that are not yet implemented are documented in [docs/proposals/](docs/proposals/).

Informal design notes that do not form part of the formal ADR sequence are preserved in [docs/design-notes/](docs/design-notes/).

Readers seeking implementation rationale or detailed constraints should consult the relevant ADR or proposal document.

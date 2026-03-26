# Architecture

## Overview

The Epistemic Control Kernel (ECK) follows a **microkernel-style architecture** that strictly separates a small deterministic core from optional capability layers.

The design prioritizes:
- Strict control over authority surfaces
- Deterministic and testable core behavior
- Explicit policy gate for all behavioral effects

Core agent behavior must remain stable and predictable **regardless of optional capability layers**. Capability features (memory retrieval, similarity scoring, prompt scaffolding, etc.) must remain **advisory-only** and never alter core semantics unless explicitly mediated by the policy gate.

All significant architectural decisions are recorded in the [Architecture Decision Records (ADRs)](./docs/adr/).

## System Model

At runtime, the ECK executes a deterministic agent loop in which:

1. Tasks or actions are proposed or generated.
2. A critic evaluates outcomes and returns a typed `CriticOutcome` plus optional `PartialStructure`.
3. Epistemic signals (confidence) are updated according to explicit rules — including partial outcomes via kernel-normalised `PartialStructure`.
4. The policy gate evaluates proposed actions against epistemic state and returns an execution mode.
5. The agent loop enforces that decision before any execution occurs.
6. Drift is tracked append-only; the periodic guard checks for severe instability and halts if detected.
7. The goal completion predicate is evaluated deterministically — success, natural queue exhaustion, and confidence threshold must all be satisfied simultaneously.

This establishes a strict separation between decision (policy gate) and enforcement (agent loop).

The kernel operates as a compact, policy-mediated state machine whose state transitions are driven exclusively by deterministic rules and critic-derived signals, never directly by LLM reasoning or capability-layer outputs.

All behavioral influence flows through explicit policy gate mediation. External signals such as memory retrieval, similarity scores, or prompt scaffolding may provide contextual information but cannot directly alter execution.

This model ensures that cognition-like capabilities remain advisory while the kernel retains full authority over behavior.

## Core Architectural Principles

- **Deterministic Core**  
  The agent loop, policy modes, and execution seam must remain deterministic and stdlib-only. Core behavior must not depend on external services or optional dependencies.

- **Advisory Memory & Cognition**  
  Memory retrieval, critic feedback, similarity scoring, and prompts provide contextual information only. They must never become authority surfaces or directly control behavior.

- **Explicit Policy Gate**  
  All signals must be mediated by explicit policy gate logic before affecting execution, mode transitions, or gating, with confidence acting as the primary control signal consumed exclusively by the policy gate. All resulting control decisions must be enforced by the agent loop before execution.

- **Optional Capability Layers**  
  Advanced features must remain optional (via toggles or extras) and must not introduce mandatory dependencies, runtime coupling, or non-determinism into the core.

- **Monotonic Safety**  
  Policy mode upgrades are irreversible. Drift evidence is append-only. Severe instability halts via a single configurable enforcement seam — no internal recovery, no silent reset.

- **Epistemic Seriousness**  
  The confidence signal is updated on every cycle including partial outcomes. The critic never controls confidence dynamics directly — category derivation and PartialStructure normalisation are kernel authority. The LLM proposes bounded evidence; the kernel classifies and owns consequences.

## Safety Boundaries ("Must Never Happen")

- No new authority surfaces through memory, prompts, similarity, or other capability layers
- No silent coupling: signals must not alter behavior without explicit policy gate mediation
- No dependency creep: the core package must remain stdlib-only
- No prompt drift when retrieval is disabled (bit-for-bit prompt identity)
- No split-brain state: new state variables must have a single source of truth and deterministic tests
- No LLM authority over lifecycle decisions (goal completion, halt, policy mode)
- No internal recovery from severe instability — halt is the only response

## Core vs Optional Capabilities

**Core** (always valid, even if all optionals are disabled):
- Agent loop semantics
- Policy mode behavior
- Deterministic execution
- Stdlib-only operation
- Policy Gate contract and default control mediation
- Agent loop enforcement of policy gate decisions
- Confidence signal processor (EWMA, failure window, partial outcomes)
- Critic outcome taxonomy and PartialStructure derivation
- Drift monitoring and periodic guard
- Goal completion predicate

**Optional** (behind explicit toggles or extras):
- Embedding-based similarity
- Advanced memory scoring (future)
- Additional evaluation or prioritization prompts

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

#### Policy Gate (PR2 Implementation)

The policy gate is the exclusive consumer of confidence for control decisions and the sole pre-execution mediation layer between epistemic state and execution. It enforces strict invariants including purity, determinism, side-effect freedom, monotonicity, and explicit default semantics. The policy gate is a pure, referentially transparent function of (proposed_action, confidence, context).

See the ADR for full contract details and invariants:

→ [docs/adr/ADR-038.md](docs/adr/ADR-038.md)

**Agent Loop Enforcement**
- [ADR-039 — Agent Loop & Policy Gate Integration](docs/adr/ADR-039.md)

#### Agent Loop Enforcement (PR3 Implementation)

The agent loop is the runtime enforcement seam for policy gate decisions.
It ensures no execution occurs without prior gate authorization and that HALT, RETRY, and DEGRADE outcomes prevent execution of the current proposal.

See the ADR for full enforcement details and invariants:

→ [docs/adr/ADR-039.md](docs/adr/ADR-039.md)

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

## Relationship to ADRs

This ARCHITECTURE.md file provides a high-level map of the system. Detailed design reasoning, invariants, red lines, and test requirements are documented in the individual Architecture Decision Records under [docs/adr/](docs/adr/).

Readers seeking implementation rationale or detailed constraints should consult the relevant ADR.

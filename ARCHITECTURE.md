# Architecture

## Overview

The Epistemic Control Kernel (ECK) follows a **microkernel-style architecture** that strictly separates a small deterministic core from optional capability layers.

The design prioritizes:
- Strict control over authority surfaces
- Deterministic and testable core behavior
- Explicit policy mediation for all behavioral effects

Core agent behavior must remain stable and predictable **regardless of optional capability layers**. Capability features (memory retrieval, similarity scoring, prompt scaffolding, etc.) must remain **advisory-only** and never alter core semantics unless explicitly mediated by policy.

All significant architectural decisions are recorded in the [Architecture Decision Records (ADRs)](./docs/adr/).

## System Model

At runtime, the ECK executes a deterministic agent loop in which:

1. Tasks or actions are proposed or generated.
2. A critic evaluates outcomes or intermediate results.
3. Epistemic signals (such as confidence) are updated according to explicit rules.
4. Policy logic interprets signals and determines the next permitted execution mode or action.

The kernel operates as a compact, policy-mediated state machine whose state transitions are driven exclusively by deterministic rules and critic-derived signals, never directly by LLM reasoning or capability-layer outputs.

All behavioral influence flows through explicit policy mediation. External signals such as memory retrieval, similarity scores, or prompt scaffolding may provide contextual information but cannot directly alter execution.

This model ensures that cognition-like capabilities remain advisory while the kernel retains full authority over behavior.

## Core Architectural Principles

- **Deterministic Core**  
  The agent loop, policy modes, and execution seam must remain deterministic and stdlib-only. Core behavior must not depend on external services or optional dependencies.

- **Advisory Memory & Cognition**  
  Memory retrieval, critic feedback, similarity scoring, and prompts provide contextual information only. They must never become authority surfaces or directly control behavior.

- **Explicit Policy Mediation**  
  All signals (confidence, memory context, similarity scores, etc.) must be mediated by explicit policy logic before affecting execution, mode transitions, or gating.

- **Optional Capability Layers**  
  Advanced features must remain optional (via toggles or extras) and must not introduce mandatory dependencies, runtime coupling, or non-determinism into the core.

## Safety Boundaries ("Must Never Happen")

- No new authority surfaces through memory, prompts, similarity, or other capability layers  
- No silent coupling: signals must not alter behavior without explicit policy mediation  
- No dependency creep: the core package must remain stdlib-only  
- No prompt drift when retrieval is disabled (bit-for-bit prompt identity)  
- No split-brain state: new state variables must have a single source of truth and deterministic tests

## Core vs Optional Capabilities

**Core** (always valid, even if all optionals are disabled):
- Agent loop semantics
- Policy mode behavior
- Deterministic execution
- Stdlib-only operation

**Optional** (behind explicit toggles or extras):
- Embedding-based similarity
- Advanced memory scoring (future)
- Additional evaluation or prioritization prompts

## v0.2.0 Architecture Sequence

The v0.2.0 architecture is defined through the ADR set ADR-020 through ADR-037.

ADR-020 establishes the roadmap and ordering constraints for the v0.2.0 architecture. The subsequent ADRs are grouped by subsystem for readability.

**Confidence Semantics**
- [ADR-021 — Rolling Confidence Update Cadence](docs/adr/ADR-021.md)
- [ADR-022 — Failure vs Non-Failure Classification](docs/adr/ADR-022.md)
- [ADR-023 — Basic Asymmetry & Recovery Shape (Semantics Only)](docs/adr/ADR-023.md)
- [ADR-024 — Minimal Input Signal Set for Confidence Update](docs/adr/ADR-024.md)
- [ADR-025 — Confidence Update Mechanics (EWMA)](docs/adr/ADR-025.md)

  #### Confidence Signal Processor (PR1 Implementation)

  The ECK confidence system is a deterministic, non-authoritative epistemic signal processor with strict kernel-enforced invariants (ADR-021–025).

  See the formal specification for full invariants and system model:

  → [docs/confidence-signal-formal.md](docs/confidence-signal-formal.md)

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

## Relationship to ADRs

This ARCHITECTURE.md file provides a high-level map of the system. Detailed design reasoning, invariants, red lines, and test requirements are documented in the individual Architecture Decision Records under [docs/adr/](docs/adr/).

Readers seeking implementation rationale or detailed constraints should consult the relevant ADR.

# Architecture Decision Records (ADRs)

This directory contains the Architecture Decision Records (ADRs) for the Epistemic Control Kernel (ECK).

ADRs capture significant architectural decisions, including their context, rationale, invariants, and constraints. Once accepted and locked, ADRs become part of the permanent design record and are immutable except for minor editorial corrections that do not change meaning.

The ADR system ensures that architectural constraints, invariants, and trade-offs remain visible and traceable as the project evolves.

## ADR Conventions

- ADRs are numbered sequentially.
- Once locked, ADRs are immutable except for minor editorial corrections that do not change meaning.
- Later ADRs may refine or supersede earlier ones but must not silently change their meaning.

## ADR Index

### Historical / Deferred

- [ADR-00X — Deferred Enforcement via Breadth Recommendation](ADR-00X.md)  
  Early design note documenting the principle of delaying enforcement decisions until broader architectural context is available.

### v0.2.0 Architecture (Locked)

ADR-020 establishes the roadmap and ordering constraints for the v0.2.0 architecture. The subsequent ADRs are grouped by subsystem for readability.

**Confidence Semantics**
- [ADR-021 — Rolling Confidence Update Cadence](ADR-021.md)
- [ADR-022 — Failure vs Non-Failure Classification](ADR-022.md)
- [ADR-023 — Basic Asymmetry & Recovery Shape (Semantics Only)](ADR-023.md)
- [ADR-024 — Minimal Input Signal Set for Confidence Update](ADR-024.md)
- [ADR-025 — Confidence Update Mechanics (EWMA)](ADR-025.md)

**Memory Integration**
- [ADR-026 — Retrieval Semantics & Contract](ADR-026.md)
- [ADR-027 — Enable/Disable Semantics for Memory Retrieval](ADR-027.md)
- [ADR-028 — Retrieval Influence Semantics](ADR-028.md)
- [ADR-029 — Observability & Logging for Retrieval](ADR-029.md)
- [ADR-030 — Test & Invariant Lock for Memory Retrieval](ADR-030.md)

**Similarity and Optional Dependencies**
- [ADR-031 — Similarity Retrieval API Contract](ADR-031.md)
- [ADR-032 — Optional Embeddings + Cosine Integration](ADR-032.md)

**Prompts Integration**
- [ADR-033 — Prompts Integration Cleanup & Authority Guardrails](ADR-033.md)

**CI and Observability**
- [ADR-034 — CI Workflow Foundational Contract](ADR-034.md)
- [ADR-035 — GitHub Actions CI Workflow Implementation](ADR-035.md)
- [ADR-036 — Test Coverage & Invariant Enforcement Metrics](ADR-036.md)
- [ADR-037 — CI Observability & Logging](ADR-037.md)

**Policy Gate**
- [ADR-038 — Policy Gate Contract – Exclusive Consumer of Epistemic Signals](ADR-038.md)

**Agent Loop Enforcement**
- [ADR-039 — Agent Loop & Policy Gate Integration](ADR-039.md)

## Relationship to Architecture

The high-level system design is described in [ARCHITECTURE.md](../ARCHITECTURE.md).

ADRs provide the detailed reasoning, invariants, red lines, and test requirements that define the architecture. Readers seeking implementation rationale or detailed constraints should consult the relevant ADR.

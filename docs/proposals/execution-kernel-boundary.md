# Proposal: Execution Kernel Boundary (EKB)

> **Status: Exploratory proposal only.**
> This document is not an adopted architectural decision.
> It defines a reserved future boundary and explicit trigger conditions for adoption.
> No implementation work is implied by its existence.

---

## Status

Exploratory (Design Commitment Only — Pre-ADR)

---

## Purpose

This proposal defines a **reserved architectural boundary** between:

* **ECK (Epistemic Control Kernel)** — semantic authority (what is allowed)
* **Execution Layer (Execution Kernel)** — mechanical authority (what is done)

The goal is to:

* clarify an already implied separation in the architecture
* prevent future coupling under load
* provide a clean, predefined insertion point for execution complexity

**This is a design commitment, not an implementation commitment.**

No runtime changes, types, or modules should be introduced until a defined
trigger condition is met (see *Adoption Triggers*).

---

## Design Commitment (Explicit)

This document commits to the following:

* The semantic/mechanical boundary **exists conceptually in the architecture**
* When execution complexity becomes non-trivial, the boundary **must be introduced here**
* The interface shape defined below is the **intended form of that boundary**

This document explicitly does **not**:

* introduce new runtime abstractions
* modify existing execution flow
* require any implementation work at this stage

---

## Current State (v0.3.0)

Execution is currently embedded within ECK:

```ProposedAction
→ PolicyDecision
→ authorize_and_perform(...)
→ ExecutionResult
```
Where:

* **authorization** (policy gate) is semantic
* **execution** (LLM/tool call) is mechanical
* both are handled within the same function (`authorize_and_perform`)

---

## Architectural Observation

The system already enforces:

> Only authorized actions may produce effects

This is a **semantic invariant**.

However:

* the function enforcing this invariant also performs the effects
* the mechanical execution layer is **not explicitly owned**

Therefore:

* the boundary between **authorization** and **execution** is already implied
* but not explicitly represented

---

## Proposed Boundary

If/when implemented, the architecture becomes:

```
ECK (semantic authority)
↓
AuthorizedAction
↓
Execution Kernel (mechanical authority)
↓
KernelExecutionResult
↓
ECK (critic / confidence)
```

---

## Adoption Triggers (Load Conditions)

The Execution Kernel Boundary (EKB) MUST NOT be implemented until at least
one of the following conditions is met:

### 1. Multiple Action Types

* More than one action_type exists
* Action types have materially different execution characteristics

**Signal:** execution mechanics are no longer uniform

---

### 2. Resumability / Replay Requirement

* Execution requires:

  * checkpointing
  * retry orchestration
  * replay capability

**Signal:** execution becomes stateful or long-running

---

### 3. Shared Execution Surface

* Multiple ECK instances must:

  * share resources
  * coordinate execution
  * operate over a common runtime

**Signal:** execution must be centralized or standardized

---

### Rule

Until at least one of the above conditions is met:

> EKB remains a reserved boundary only.

---

## Non-Adoption Rationale (Current State)

At v0.3.0:

* Only one action type exists (llm_query)
* Execution is stateless and immediate
* No replay, checkpointing, or orchestration is required
* No shared execution surface exists

Therefore:

* Execution complexity is insufficient to justify a boundary
* Introducing EKB now would create an abstraction without load
* Premature abstraction risks misplacing the boundary when real load appears

**Conclusion:**
EKB is correctly defined but not yet justified for implementation.

---

## Future Interface Shape (Non-Binding)

The following structures represent the intended shape of the boundary
**if/when implemented**. These are not introduced into the codebase at this stage.

### AuthorizedAction

* Immutable semantic authorization output
* Contains policy + provenance + trace context
* Represents the final decision of ECK prior to execution

---

### KernelExecutionResult

* Purely mechanical outcome of execution
* Contains what happened, not what it means
* No epistemic interpretation

---

### ExecutionKernel Protocol

* Single method: execute(AuthorizedAction) → KernelExecutionResult
* No policy logic
* No confidence interaction

---

## Critical Constraints (Boundary Safety)

### 1. Epistemic Isolation of Failure Semantics

The Execution Kernel MUST NOT:

* reinterpret execution outcomes
* classify success/failure semantically
* transform outcomes beyond mechanical normalization

All epistemic classification remains strictly within:

> critic → confidence → policy

**Rationale:**
Allowing execution to interpret outcomes introduces hidden epistemic coupling,
violating ECK’s authority separation.

---

### 2. Determinism Preservation

The Execution Kernel MUST NOT:

* introduce unbounded non-determinism
* alter retry semantics without explicit mediation
* introduce timing-dependent behavioral divergence

Any non-determinism must be:

* externally bounded
* explicitly mediated
* observable via telemetry

**Invariant:**

> Identical inputs must produce identical control behavior

Execution variability must not break this invariant.

---

## Integration Point (If Adopted)

### Current flow

```
ProposedAction
→ PolicyDecision
→ authorize_and_perform(...)
→ ExecutionResult
```

---

### Future flow (conditional)

```
ProposedAction
→ PolicyDecision

IF EXECUTE:
→ AuthorizedAction
→ ExecutionKernel.execute(...)
→ KernelExecutionResult
ELSE:
→ synthetic ExecutionResult

→ critic_evaluate(...)
→ confidence.update(...)
```

---

## Minimal Implementation Path (Conditional)

If a trigger condition is met:

1. Extract execution logic from authorize_and_perform
2. Introduce ExecutionKernel interface
3. Wrap existing behavior in default implementation
4. Preserve identical external behavior

---

## Design Principles

### Authority Separation

* ECK: decides what may happen
* Execution Kernel: performs how it happens

---

### One-Way Authority Gradient

* ECK → execution (information)
* execution → ECK (results only)

---

### No Hidden Coupling

Execution must not:

* influence policy
* influence confidence
* inject control signals

---

### Semantic vs Mechanical Failure

| Type       | Owner            |
| ---------- | ---------------- |
| Semantic   | ECK              |
| Mechanical | Execution Kernel |

---

## What This Enables (If Adopted)

* replay / journaling
* resumable execution
* multi-agent coordination
* execution-level policy (rate limits, budgets)

---

## What This Does NOT Do

* change confidence semantics
* change policy gate behavior
* introduce new authority layers
* require infrastructure changes

---

## Recommendation

Do not implement at this stage.

* treat as a reserved boundary
* revisit only when trigger conditions are met

---

## Bottom Line

> The Execution Kernel Boundary is not a feature.
> It is a predefined place for future complexity to land safely.

It is not needed yet.
But when it is, it must already be correct.

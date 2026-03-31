# Proposal: Execution Kernel Boundary (EKB)

> **Status: Exploratory proposal only.**  
> This document is not an adopted architectural decision.  
> It defines a reserved future boundary and explicit trigger conditions for adoption.  
> No implementation work is implied by its existence.
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

```text id="1x9r0k"
ProposedAction
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

```text id="h3m1fz"
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

* More than one `action_type` exists
* Action types have materially different execution characteristics
  (e.g. LLM call vs API call vs file operation)

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

  * share tools/resources
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

* Only one action type exists (`llm_query`)
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

---

### AuthorizedAction

Immutable handoff from ECK to execution layer.

```python id="6c2zlf"
@dataclass(frozen=True)
class AuthorizedAction:
    action_type: str
    parameters: Mapping[str, Any]

    task_id: str
    provenance_id: str

    policy_rule_id: str
    policy_mode: str
    confidence: float

    trace_id: str | None = None
    step_id: str | None = None
    deterministic_nonce: int | None = None
```

---

### KernelExecutionResult

Mechanical outcome returned from execution layer.

```python id="pg3v4n"
@dataclass(frozen=True)
class KernelExecutionResult:
    performed: bool
    outcome: str

    refusal_reason: str | None = None

    execution_id: str | None = None
    journal_id: str | None = None
    checkpoint_id: str | None = None

    executor_status: str | None = None
    metadata: Mapping[str, Any] | None = None
```

---

### ExecutionKernel Protocol

```python id="r0nm4c"
class ExecutionKernel(Protocol):
    def execute(self, authorized_action: AuthorizedAction) -> KernelExecutionResult:
        ...
```

---

## Integration Point (If Adopted)

### Current flow

```text id="z8r6wb"
ProposedAction
→ PolicyDecision
→ authorize_and_perform(...)
→ ExecutionResult
```

---

### Future flow (conditional)

```text id="9ld4xs"
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

If a trigger condition is met, the boundary should be introduced via:

1. Extract execution logic from `authorize_and_perform`
2. Introduce `ExecutionKernel.execute(...)`
3. Wrap existing behavior in a default execution kernel
4. Maintain identical external behavior (no semantic change)

---

## Design Principles

### 1. Authority Separation

* ECK: decides **what may happen**
* Execution Kernel: decides **how it happens**

---

### 2. One-Way Authority Gradient

* ECK → execution (information flow)
* execution → ECK (results only)
* execution cannot modify policy or confidence

---

### 3. No Hidden Coupling

Execution layer must not:

* reinterpret confidence
* alter policy decisions
* inject control signals

---

### 4. Semantic vs Mechanical Failure

| Type       | Owner            | Example               |
| ---------- | ---------------- | --------------------- |
| Semantic   | ECK              | policy rejection      |
| Mechanical | Execution Kernel | tool failure, timeout |

---

## What This Enables (If Adopted)

* replay / journaling
* resumable execution
* multi-agent coordination
* execution policy layers (rate limits, budgets)

---

## What This Does NOT Do

This proposal does not:

* modify confidence semantics
* modify policy gate logic
* introduce new authority layers
* require infrastructure changes
* mandate execution complexity

---

## Recommendation

Do not implement at this stage.

Instead:

* treat this as a **reserved boundary definition**
* use it to guide future design decisions
* revisit only when a trigger condition is observed

---

## Bottom Line

> The Execution Kernel Boundary is not a feature.
> It is a **predefined place for future complexity to land safely**.

You do not need it yet.

But if you need it later, it must already be defined.

# Proposal: External Policy Compiler + CompiledPolicyGate Seam

## Status

Exploratory — Design Commitment Only (Pre-Implementation)

## Purpose

This proposal defines an ECK-correct mechanism for supporting document-based policy while preserving strict epistemic isolation and deterministic control.

It also explicitly introduces a seam for future compiled policy integration without implementing the system itself.

The approach separates:

- Policy interpretation (external, fallible)
- Policy enforcement (internal, deterministic)

---

## Core Principle — Authority Separation

All behavioral authority remains inside the deterministic kernel.

Therefore:

- The compiler must never participate in runtime execution
- The LLM must never influence evaluate() or step()
- The kernel must treat compiled policy strictly as immutable data
- ECK does not and will not invoke the compiler

---

## Architectural Flow (Future, Not Implemented)

```
Policy Documents
    ↓
External Policy Compiler (LLM-assisted, offline, fallible)
    ↓
CompiledPolicy (immutable artifact)
    ↓
Human Review / Approval (mandatory)
    ↓
ECK (deterministic enforcement via CompiledPolicyGate)
```

CompiledPolicy must not be loaded into ECK without explicit human approval.

---

## External Policy Compiler

### Role

- Ingest policy documents
- Extract simple, statically enforceable rules
- Produce a deterministic CompiledPolicy artifact

### Constraints

- External to ECK
- Fallible and not trusted
- Offline / pre-runtime only

ECK does not validate semantic correctness of compiled policy beyond structural compliance.

---

## CompiledPolicy Artifact (Seam Definition Only)

A placeholder type representing externally compiled policy.

### Properties

- Immutable
- Versioned
- Schema-bounded (future)
- Contains no executable logic

### Minimal placeholder definition

```
from dataclasses import dataclass

@dataclass(frozen=True)
class CompiledPolicy:
    version: str = "placeholder"
```

No schema is defined at this stage. This is a type-level seam only.

---

## CompiledPolicyGate (Seam Definition Only)

A wrapper around DefaultPolicyGate that introduces a future integration point for compiled policy.

### Definition

```
class CompiledPolicyGate:
    def __init__(
        self,
        base_gate,
        compiled_policy: CompiledPolicy | None = None,
    ):
        self.base_gate = base_gate
        self.compiled_policy = compiled_policy

    def evaluate(self, *args, **kwargs):
        return self.base_gate.evaluate(*args, **kwargs)
```

### Properties

- Fully deterministic
- No behavioral change
- No use of compiled_policy
- Pure delegation

This is a no-op wrapper that exists solely to reserve the seam.

### Protocol Conformance Note

When implemented, CompiledPolicyGate.evaluate(...) must match the PolicyGate protocol signature explicitly, including optional telemetry keyword arguments introduced in v0.3.0. The use of *args, **kwargs here is for seam definition only.

---

## Integration with ECK

No changes to the kernel are required.

Existing injection point:

```
self._policy_gate: PolicyGate = policy_gate or DefaultPolicyGate()
```

CompiledPolicyGate can be introduced via this mechanism without modifying:

- agent loop
- policy gate contract
- control flow

---

## Determinism Constraint (Future Enforcement)

When implemented, CompiledPolicyGate must:

- operate only on in-memory data
- perform no external calls
- introduce no runtime mutation
- preserve identical behavior under identical inputs

---

## Control Integrity Constraint

Compiled policy must not:

- alter the control loop
- introduce new execution modes
- bypass DefaultPolicyGate

It may only constrain decisions within the existing PolicyGate contract.

---

## Non-Goals

- No compiler implementation
- No schema definition
- No document ingestion
- No runtime policy updates
- No policy composition or precedence logic

---

## Trust Boundary

| Component      | Trust Level               |
| -------------- | ------------------------- |
| Compiler       | Not trusted               |
| CompiledPolicy | Structurally trusted only |
| ECK Kernel     | Fully authoritative       |

Failure mode is accepted:

``` Correct enforcement of incorrect rules ```

Mitigation remains external:

- human review
- versioning
- auditability

---

## Adoption Triggers

This seam becomes load-bearing when:

- document-based policy is required in practice
- hand-authored rules become insufficient
- policy provenance is required

---

## Rationale

This proposal does not implement compiled policy support.

It ensures:

- the kernel will not need redesign later
- future policy complexity has a defined landing point
- architectural boundaries remain intact

This mirrors the EKB approach:

``` Design the boundary, name the types, do not implement until load exists. ```

---

## Bottom Line

This proposal introduces a minimal seam for compiled policy without adding complexity or authority.

- No runtime changes
- No behavioral changes
- No new dependencies

Only:

- a placeholder type
- a no-op wrapper
- a reserved integration point

The kernel remains unchanged and fully authoritative.

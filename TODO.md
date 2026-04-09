# TODO

**Last updated:** 2026-04-09

**Current design baseline:** v0.3.0 (architecture & invariants locked)  
**Current implementation + assurance state:** v0.4.0 complete

---

## Implementation State

### v0.2.0 — Complete

The v0.2.0 architecture is fully implemented through ADR-020–ADR-041. All locked invariants have been converted into code, tested, and verified. CI green across Python 3.10, 3.11, and 3.12.

See [docs/v0.2.0-implementation-checklist.md](docs/v0.2.0-implementation-checklist.md) for the full ADR-mapped completion record.

---

### v0.3.0 — Complete and Tagged

All v0.3.0 deliverables are complete:

- **ADR-042** — Propose/authorize/perform execution boundary. `propose_execution`, `authorize_and_perform`, `ProposedAction`, `ExecutionResult`, six formal invariants enforced. TLA⁺ model verified.
- **ADR-043** — Demonstration policy module. Childcare domain `DemoPolicyGate` proves policy is not reducible to confidence. High-confidence non-EXECUTE outcome on domain-semantic grounds verified under CI.
- **ADR-044** — Out-of-domain policy module evaluation semantics. Explicit non-EXECUTE required on domain mismatch. No silent passthrough.
- **ADR-045** — Formal telemetry schema and observability contract. Six canonical event types instrumented at source ownership boundaries. Full per-step trace coherence.

**Design baseline locked at v0.3.0.** All guarantees derive from ADR-020–ADR-045.

---

### v0.4.0 — Trace Production and Empirical Foundation (Validation & Assurance Layer)

**Status:** Complete

v0.4.0 adds validation, enforcement, and observability infrastructure **without introducing new load-bearing semantics or changing the control loop**.

**Delivered:**
- Trace Analysis Service with strict no-control-authority invariant (deep-copy isolation, plain data outputs only)
- Adversarial deterministic test lane (single-seam and multi-cycle sequence tests)
- Property-based testing with Hypothesis (three core invariants: confidence boundedness, HALT absorption, gate execution exclusivity)
- Mechanical enforcement layer (mypy via ADR-046 curated strict profile + CodeQL security-extended blocking)

**Not delivered (deferred):**
- Operator-facing trace views and renderers
- Extended Hypothesis properties
- Empirical benchmarking suite

No new ADRs were created. No control semantics were changed. The design baseline remains v0.3.0.

---

## Deferred from v0.3.0 (Status after v0.4.0)

- **Hypothesis / property-based testing** — COMPLETE in v0.4.0
- **mypy strict** — COMPLETE via ADR-046 curated profile (blocking)
- **CodeQL** — PARTIAL: `python/security-extended` enabled (blocking); `python/quality` deferred
- **icontract** — CLOSED: evaluated and rejected (invariants enforced via typing, tests, and runtime structure)
- **Formal verification of authorize_and_perform** — STILL DEFERRED

---

## Roadmap

### v0.5.0 — Empirical Behavioural Characterisation

The validation phase. Moves from "correct by construction" to "correct in distribution."

**Trace-to-invariant alignment:**
- Verify invariants hold in distribution across real traces, not just unit tests
- Distributional validation — confidence trajectory vs critic outcome distribution, policy decision frequency vs confidence bands, drift signals vs execution refusal patterns, gate causes vs outcome classes

**Calibration studies:**
- Compare confidence bands against observed outcome frequencies
- Produce calibration curves per domain / task family
- Reliability diagrams
- Detect overconfidence and underconfidence zones

**Behavioural characterisation:**
- Ablation studies — isolate contribution of each kernel subsystem (confidence signal, drift monitor, partial outcomes, goal predicate)
- Does `DemoPolicyGate` demonstrably change behaviour relative to `DefaultPolicyGate` on equivalent task sets?
- Does ECK make the system appear more calibrated to an external observer?

**Publish findings:**
- Convert empirical results into a technical report
- The evidenced empirical claim is what supports domain operator adoption

---

### v0.6.0 — Compliance and Trust Surface

Governance of what parts of the kernel's internal truth can leave the system. The compiled policy seam activates.

**Telemetry governance:**
- Sampling rules, redaction rules, field-level contracts
- Define fields that must never appear in telemetry payloads
- Configurable verbosity per event_type for high-volume advisory calls
- Extend `redact_hook` interface with domain-specific scrubbing policies

**Policy provenance and audit integrity:**
- Signed policy module releases with versioned changelogs
- Policy module identity in audit traces and deployment manifests
- Tamper-evident logs, trace continuity guarantees, retention policies
- Compliance integrations for regulated domains

**Objective governance:**
- Objective manifest and approval metadata
- Deployment policy stating who may issue objectives
- Optional upstream objective review service

**Trust package:**
- Threat model, security whitepaper, incident handling policy
- Deployment hardening checklist
- Domain-specific assurance documentation

**Compiled Policy Seam activates (from `docs/proposals/`):**
- `CompiledPolicyGate` moves from no-op to active implementation
- External compiler buildable independently at any time
- Policy provenance requirement makes the seam load-bearing
- Document-based policy workflow enabled for non-developer operators
- Human review gate mandatory before any compiled policy enters the kernel

---

### v0.7.0 — Execution Context Formalisation and Multi-Agent

The deferred ADR-042 items become load-bearing. The EKB activates.

**Execution context object (deferred from ADR-042):**
- Active task identity and provenance lineage
- Full parameter schema validation beyond key presence
- Domain-specific execution contracts

**Action registry formalisation:**
- Schema validation beyond key presence
- Multiple action types with materially different execution characteristics

**Policy composition discipline:**
- Layered policy module template — schema validation layer, semantic rule layer, baseline fallback layer, explicit precedence order
- Rule registry format and per-rule tests
- Policy decision coverage reports

**Cross-agent isolation guarantees:**
- No shared confidence state
- No shared policy state unless explicitly mediated
- No implicit coordination channels

**ADR-038 full wiring:**
- Formal retirement of `get_recommended_breadth()` and `should_execute()`
- Completes ADR-038 Invariant I1 — policy gate becomes sole consumer of confidence for control decisions
- Requires trace-level validation from v0.5.0 to verify behavioral equivalence before and after retirement
- New ADR required

**Execution Kernel Boundary activates (from `docs/proposals/`):**
- `ExecutionKernel` boundary moves from reserved to active implementation
- Triggered by: multiple action types from action registry formalisation; provenance lineage from execution context; shared execution surface from multi-agent coordination
- `authorize_and_perform` split into semantic authorization (ECK) and mechanical execution (EKB)
- `AuthorizedAction` and `KernelExecutionResult` become first-class types

---

### v0.8.0 — Epistemic Calibration and Adaptive Policy

The system learns how well it knows. Calibration outputs feed policy configuration — never direct behavioral control.

**Calibration layer:**
- Compare confidence trajectories vs outcome frequencies across real deployments
- Detect over/underconfidence zones by domain and task family
- Produce domain-specific calibration artifacts

**Policy adaptation surface:**
- `DefaultPolicyGate` thresholds become configurable via calibration artifacts
- Still enforced only through the policy gate — confidence remains advisory
- Calibration outputs become policy inputs, never direct behavioral control

**Commercial product surface:**
- Domain-specific calibration datasets as virtuity.io product
- Calibration artifacts feed `CompiledPolicyGate` configuration
- Open-source: calibration framework; commercial: calibration datasets and tuned policies

---

## Reserved Architectural Boundaries

Two boundaries are defined as design commitments but not yet implemented. See `docs/proposals/` for full specifications.

- **Execution Kernel Boundary (EKB)** — activates in v0.7.0
- **Compiled Policy Seam** — activates in v0.6.0

---

## Persistent Deferred Items

Items deferred across multiple releases without a fixed release target:

- **v0.2.0 audit/observability layer** — task lifecycle recording is currently absent; noted in `agent.py`; deferred to a future phase
- **PartialStructure collapse_status** — currently always `"unresolved"`; resolution tracking deferred to a future ADR
- **Formal verification of authorize_and_perform** — Dafny or Coq; appropriate before safety-critical domain deployment; not required until then
- **Advanced memory scoring** — subject to new ADR
- **End-to-end examples and usage patterns** — comprehensive examples and policy mode guidance

---

## Contributions

All work must respect the locked invariants in ADR-020–ADR-045.  
See `ARCHITECTURE.md` and `docs/adr/` for the current design baseline.  
Informal design notes are in `docs/design-notes/`.  
Reserved boundaries are in `docs/proposals/`.

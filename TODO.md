# TODO

**Last updated:** 2026-04-02

**Current design baseline:** v0.3.0 (architecture & invariants locked)
**Current implementation state:** v0.3.0 complete and tagged

---

## Implementation State

### v0.2.0 — Complete

The v0.2.0 architecture is fully implemented through ADR-020–ADR-041. All locked invariants have been converted into code, tested, and verified. CI green across Python 3.10, 3.11, and 3.12.

See [docs/v0.2.0-implementation-checklist.md](docs/v0.2.0-implementation-checklist.md) for the full ADR-mapped completion record.

### v0.3.0 — Complete and Tagged

All v0.3.0 deliverables are complete:

- **ADR-042** — Propose/authorize/perform execution boundary. `propose_execution`, `authorize_and_perform`, `ProposedAction`, `ExecutionResult`, six formal invariants enforced. TLA⁺ model verified.
- **ADR-043** — Demonstration policy module. Childcare domain `DemoPolicyGate` proves policy is not reducible to confidence. High-confidence non-EXECUTE outcome on domain-semantic grounds verified under CI.
- **ADR-044** — Out-of-domain policy module evaluation semantics. Explicit non-EXECUTE required on domain mismatch. No silent passthrough.
- **ADR-045** — Formal telemetry schema and observability contract. Six canonical event types instrumented at source ownership boundaries. Full per-step trace coherence. `tests/test_telemetry_wiring.py` verifies live end-to-end trace.

598 tests passing. 98.48% coverage. CI green.

### Deferred from v0.3.0

The following v0.3.0 items were explicitly deferred and remain open:

- **Hypothesis / property-based testing** — deferred to v0.4.0 adversarial test lane
- **mypy strict** — deferred to v0.4.0 mechanical enforcement layer
- **CodeQL** — deferred to v0.4.0 mechanical enforcement layer
- **icontract** — deferred to v0.4.0 mechanical enforcement layer
- **Formal verification of authorize_and_perform** — deferred; appropriate before safety-critical domain deployment

---

## Roadmap

### v0.4.0 — Trace Production and Empirical Foundation

The first empirical phase. Meaningful characterisation requires the v0.3.0 execution surface and telemetry — both now in place.

**Trace infrastructure:**
- Operator-facing trace views and compact renderers — human-readable per-step summaries, confidence trajectory with policy overlays, reason/rule timelines
- Read-only trace analysis service — anomaly detection, confidence/pathology pattern flagging, stuck mode and drift spike identification; must not feed back into runtime control

**Adversarial test lane:**
- `tests/adversarial/` — fuzz action proposals, fuzz policy contexts, stress queue and iteration boundaries, inject malformed critic outputs, simulate pathological traces
- Hypothesis property-based tests for trace-level and sequence-level invariants:
  - no `step.start` without exactly one `step.end`
  - no execution when policy mode != EXECUTE
  - confidence monotonic constraints under failure windows
  - rejected/deferred → zero delta trajectories

**Mechanical enforcement layer:**
- mypy strict — add to CI initially as non-blocking, then blocking
- CodeQL — enable on repo
- icontract — runtime contract enforcement for load-bearing invariants; best targets: `authorize_and_perform` authority boundary, `PolicyGate` signature conformance, `ProposedAction` schema surface, confidence update invariants, telemetry event envelope validity

**Empirical benchmarking (initial):**
- Task success rate with ECK vs without ECK on equivalent task sets
- Halt correlation — do kernel halts correspond to genuine task failure?
- Critic category distribution — success vs failure vs partial vs deferred on real tasks
- Parameter sensitivity — effect of varying `partial_threshold`, `guard_interval`, `confidence_alpha`

---

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

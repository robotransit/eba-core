# Design Note: Trace Analysis Service

**Status:** Exploratory — Design Commitment Only

## Purpose

The Trace Analysis Service provides read-only inspection, querying, and summarization of telemetry events emitted under ADR-045.

It exists solely to give operators visibility into what the kernel did — never to influence what the kernel does.

## Core Invariant — No Control Authority (Load-Bearing)

The Trace Analysis Service **must never** acquire any control authority, directly or indirectly.

- It is strictly read-only and observational.
- Information flow is one-way only: kernel → analysis service.
- No output from the service (summaries, rendered views, filtered events, anomaly lists, etc.) may ever be consumed by the agent loop, policy gate, confidence signal, execution boundary, or any other control surface.
- The service must not mutate state, emit telemetry, or create any feedback path — explicit or implicit.
- Any design that would allow the analysis service to influence agent behavior (even "just for debugging") is forbidden.

This invariant is architectural and non-negotiable. It prevents the service from becoming an implicit second control kernel.

## Scope

**In scope** (purely observational):
- Querying and filtering traces
- Summarizing trace structure and event sequences
- Descriptive pattern detection (no scoring or classification that could feed control)
- Human-readable trace rendering for operators
- Replay-style validation for testing and auditing

**Out of scope**:
- Any real-time intervention or feedback loop
- Writing or modifying telemetry
- Any coupling that allows analysis outputs to affect control decisions
- Programmatic APIs intended for consumption by the kernel

## Architectural Constraints

- Must not import any control-path modules (`agent`, `policy_gate`, `confidence`, `execution`, etc.).
- Must operate exclusively on immutable copies or snapshots of events.
- Must remain framework-agnostic and compatible with the existing `trace_id` / `deterministic_nonce` scheme.

## Call Site Responsibility

The invariant is structurally enforced inside the service, but it must also be actively defended at every call site.

- Callers are responsible for serializing events to plain dicts before calling `ingest()`. Live kernel objects must never be passed.
- No return value from the analyzer may be used for any control decision, policy tuning, confidence update, or execution choice.
- Derived analysis results must not be re-injected into telemetry or the control path.
- "Just for debugging" tightening of the coupling is prohibited. Debugging belongs in operator tooling, not the kernel.

Any future change that blurs this boundary must be treated as a serious architectural regression.

## One-Way Call-Site Pattern (Enforcement)

The Trace Analysis Service is integrated via a strict one-way call-site pattern.

At each telemetry emission point:
- The caller emits the event via `emit_event(...)`.
- Immediately after, the caller passes a fresh plain-dict snapshot of the same event to `TraceAnalyzer.ingest(...)`.
- The analyzer is optional (`None` is valid) and must be treated as a write-only sink.

Constraints:
- The event passed to `ingest()` must be a newly constructed plain dict. It must not reference live kernel objects or reuse mutable structures without copying.
- The analyzer must never be queried or read from within the control path.
- No abstraction, hook, or shared pipeline may unify telemetry emission and analysis ingestion.
- The call must remain explicit and colocated with the emission site.

This pattern ensures:
- one-way information flow (kernel → analysis),
- no hidden coupling or shared state,
- and immediate visibility of the boundary at the exact point where it could otherwise erode.

Any change that removes duplication, introduces shared objects, or allows analyzer outputs to influence control is a violation of the core invariant.

## Success Criteria

- The service meaningfully improves operator visibility.
- Disabling the entire service has **zero** effect on agent behavior.
- The kernel remains tightly epistemically isolated.

The Trace Analysis Service is the epistemic counterpart to the deterministic control kernel:  
**it observes. It does not steer.**

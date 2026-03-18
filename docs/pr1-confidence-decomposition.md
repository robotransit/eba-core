# PR 1 — Confidence System Decomposition

**Implementation of Confidence Semantics (ADR-021–025)**

**Status:** Planning  
**Last updated:** 2026-03-18  
**Part of:** v0.2.0 Implementation (PR Plan)

This document decomposes PR 1 into concrete, implementable tasks while strictly respecting the locked invariants from ADR-021–025, the global invariants, and the current ConfidenceSignal implementation baseline.

---

## Objectives

Implement the complete confidence subsystem as defined in ADR-021–025, ensuring:

- Strictly event-driven updates tied to critic outcomes only
- Categorical outcome handling with severity scaling that affects magnitude only within permitted semantic bounds
- Asymmetric movement rules with a single-cycle failure window
- Minimal admissible input surface with optional downward-only influence
- Deterministic, reproducible confidence trajectories
- Strict separation between epistemic signaling and behavioral control

All changes must preserve:

- Confidence is epistemic only and never a direct behavioral authority
- All behavioral consequences remain mediated by explicit policy/gates
- No silent coupling
- stdlib-only core
- Exact alignment with the current ConfidenceSignal class design where already fixed

---

## Current Implementation Baseline

The current ConfidenceSignal baseline already fixes several important design choices that this decomposition must now reflect explicitly:

- Partial outcomes are structurally enriched via PartialStructure
- PartialStructure validation is strict and bidirectional
- Movement permission is derived in two stages: base_class then effective_class
- Gating is applied to both current raw delta and prior smoothed delta
- Failure-window logic depends on explicit capture of prior state before mutation
- Success and Partial raw delta semantics are downward-biased by severity
- Rejected and Deferred take a hardened no-update path
- Clamp attribution is based on actual effect, not only nominal cause
- Replay determinism is a required first-class behavior

---

## Task Breakdown

### 1. Core Confidence State Model

- Implement and stabilize the internal confidence state required by ADR-021–025 and the current class design.
- Required state: current confidence value (initialized to 0.5), fixed smoothing factor alpha, prior smoothed delta, prior failure-window state, cycle identifier, canonical logger obtained via `logging.getLogger("eck-core")`.
- Requirements: confidence value remains bounded in [0.0, 1.0]; state transitions are deterministic from fixed inputs; no hidden or time-based state evolution; no behavior depends on wall-clock passage, only on explicit update events.

### 2. Critic Outcome Taxonomy

- Implement the locked categorical outcome model from ADR-022.
- Required categories: Success, Failure, Partial, Rejected, Deferred.
- Requirements: severity is always present as a scalar in [0.0, 1.0]; severity affects magnitude only; severity must never reclassify an outcome; category semantics must remain primary; Rejected and Deferred must remain no-update categories.

### 3. Partial Outcome Structural Semantics

- Implement and preserve the structural model for Partial outcomes.
- Required types: PartialStructure, ConflictKind, ConflictLocus, MovementClass.
- Requirements: Partial outcomes must be accompanied by PartialStructure; non-Partial outcomes must not be accompanied by PartialStructure; validation must be strict and fail closed; ConflictKind must map deterministically to MovementClass; this mapping must be explicit and inspectable.
- Current baseline semantics to preserve: evidence conflict → BOTH, constraint conflict → DOWN_ONLY, decomposition conflict → NEITHER, resolution instability → NEITHER.

### 4. Hardened Validation Layer

- Implement airtight validation at the start of update processing.
- Required behavior: validation runs before any state mutation with semantic consequences; invalid Partial / PartialStructure combinations raise immediately; update logic must not silently correct malformed inputs; invalid inputs must not partially mutate state.
- Required edge cases: Partial without PartialStructure → error; non-Partial with PartialStructure → error.
- Acceptance intent: invalid structural inputs fail deterministically; no phantom update, no partial logging-based side effects, no silent coercion.

### 5. Event-Driven Update Cadence

- Implement the ADR-021 update cadence exactly.
- Requirements: confidence updates occur exactly once per cycle that produces a critic outcome requiring update; no update occurs before critic evaluation; no mid-cycle updates; no speculative updates; no retrospective batch updates; no updates on cycles without critic outcome; Rejected and Deferred do not produce confidence movement.
- Important implementation clarification: the update entrypoint may still be invoked with Rejected or Deferred, but these must resolve to a true no-update path with unchanged confidence; no path may create evidence-free motion.

### 6. Explicit Prior-State Capture

- Implement the update flow so that gate semantics depend on captured prior state, not partially mutated current state.
- Required captured values at update start: prior confidence value, prior smoothed delta, prior failure-window-active state.
- Requirements: failure-window logic must use state as it existed before the current update; smoothing behavior must use the prior smoothed delta from the previous update; logging and attribution must preserve prior/final distinction clearly.
- This is mandatory to avoid semantic leakage from in-progress mutation.

### 7. Raw Delta Computation

- Implement raw delta derivation in alignment with the current class baseline and ADR-025 semantics.

#### 7.1 Success raw delta
- Requirements: Success produces positive raw delta; severity acts as a downward-biased scaler on that positive movement; higher severity must not create stronger upward movement; the success delta remains category-consistent and bounded.

#### 7.2 Failure raw delta
- Requirements: Failure produces negative raw delta; severity scales magnitude downward; higher severity produces a larger negative movement; failure remains the canonical trigger for the single-cycle failure window.

#### 7.3 Partial raw delta
- Requirements: Partial raw delta is severity-sensitive and may be positive or negative depending on severity; low-severity partial may produce constrained positive movement; high-severity partial may produce negative movement; severity acts as a downward-biased scaler; raw delta remains subject to gating and does not bypass movement permissions.

#### 7.4 Rejected / Deferred
- Requirements: Rejected and Deferred produce no raw delta; confidence remains unchanged; these paths are true no-update paths.

### 8. Base-Class and Effective-Gate Derivation

- Implement two-stage movement permission semantics.

#### 8.1 Base movement class
- Requirements: for Partial, base_class is derived from PartialStructure.conflict_kind; for non-Partial, base_class defaults to BOTH.

#### 8.2 Effective movement class
- Requirements: effective_class is derived from base_class plus the captured prior failure-window state; failure-window restriction is applied after structural movement semantics are established; failure-window logic must not erase the distinction between structural restriction and failure-window restriction in observability.
- Required behavior under prior failure window: BOTH becomes DOWN_ONLY; UP_ONLY becomes NEITHER; DOWN_ONLY remains DOWN_ONLY; NEITHER remains NEITHER.

### 9. Directional Gating and Gated EWMA

- Implement gating exactly as the current class does: clamp both current and prior motion inputs before smoothing.

#### 9.1 Gated clamping
- Requirements: apply movement-class clamp to delta_raw; apply movement-class clamp to prior_smoothed_delta; clamping must occur before EWMA smoothing; gating must never be bypassed.

#### 9.2 Gated smoothing
- Requirements: EWMA is computed only over permitted values; smoothing must not reintroduce prohibited directional movement through the prior smoothed delta.
- This task is critical because it preserves the semantic meaning of permission gates under smoothing.

### 10. Bounded Accumulation

- Implement bounded accumulation after smoothing.
- Requirements: new confidence = prior confidence + smoothed delta; result is clamped into [0.0, 1.0]; boundedness must hold at all times; no intermediate or final value may escape the closed interval.

### 11. Single-Cycle Failure Window

- Implement ADR-023 asymmetry exactly.
- Requirements: a Failure outcome activates the failure window for the immediately following update; upward movement is forbidden during that following update; downward movement remains permitted; the window applies once and only once; the window must be consumed correctly even when the following event is a no-update category.
- Important current-baseline behavior to preserve: if the next outcome is Rejected or Deferred, confidence remains unchanged, and the pending failure window is consumed; no persistent multi-cycle suppression is allowed.

### 12. No-Update Path for Rejected / Deferred

- Implement the hardened no-update path as a first-class path, not as a degenerate regular update.
- Requirements: no raw delta; no smoothing update; no confidence movement; failure-window consumption occurs if active; observability records the path explicitly as no_update; no phantom movement is introduced through prior smoothed delta.
- This must remain semantically distinct from an update that happens to result in zero net change.

### 13. Clamp Attribution and Observability Semantics

- Implement observability that reflects actual effect, not only theoretical cause.
- Requirements: compute clamp attribution from whether clamping actually changed raw delta or prior smoothed delta; distinguish failure-window-derived restriction from structural movement restriction where possible; emit meaningful clamp reasons such as: no clamp, failure window clamped, movement class down only clamped, movement class neither clamped, generic movement class clamped.
- Observability must explain what happened causally without acquiring behavioral authority.

### 14. Structured Logging

- Implement structured logging through the immutable global logger invariant: `logging.getLogger("eck-core")`.
- Requirements: every update attempt is logged exactly once; no-update paths are logged explicitly; logs must support deterministic reconstruction of update behavior; logging must remain metadata/diagnostic only; logging must not create behavioral side effects.
- At minimum, logging for update paths should include: cycle id, timestamp, category, severity, prior value, base class, effective class, raw delta, permitted raw delta, permitted prior smoothed delta, smoothed delta, final value, clamp reason, partial structure metadata when present.
- At minimum, logging for no-update paths should include: cycle id, timestamp, category, severity, prior value, action = no_update, failure window consumed flag, final value.

### 15. Replay Determinism

- Implement and preserve deterministic replay as a first-class testing and audit mechanism.
- Requirements: replay must run a sequence of outcomes and optional PartialStructure; replay must return the resulting confidence trajectory; replay must restore original internal state after completion; identical inputs and fixed alpha must yield identical trajectories.
- Requirements for restoration: restore confidence value, restore prior smoothed delta, restore prior failure-window state, restore cycle id.
- Replay must not leave residual mutation behind.

### 16. Agent-Flow Integration Boundary

- Integrate the confidence subsystem into agent flow without violating locked control boundaries.
- Requirements: update occurs only after critic evaluation; exactly one update per eligible critic event; no execution or action-selection component may consume confidence directly; confidence may be passed only to the policy mediation layer; confidence must never become a direct authority surface.
- This must be explicitly enforced in integration points and tests.

### 17. Optional Signal Whitelist

- Implement ADR-024 optional signals within the currently locked constraints.
- Requirements: only explicitly allowed optional signals may influence raw delta derivation; optional signals are downward-only; optional signals must never produce upward deltas; optional signals must never override critic category semantics; optional signals must never override movement gates; optional signals must be fully disableable with zero phantom influence.
- If optional signals are not fully wired in this baseline, the decomposition must still preserve the whitelist boundary and testable no-effect behavior when disabled.

---

## Testing and Verification

1. Event cadence tests  
   - Sequence of critic outcomes requiring update produces exactly one update per eligible cycle  
   - No update before critic evaluation  
   - No critic output path leaves confidence unchanged  
   - Rejected / Deferred leave confidence unchanged

2. Validation tests  
   - Partial without PartialStructure raises  
   - Non-Partial with PartialStructure raises  
   - Invalid structural combinations do not partially mutate state

3. Raw delta semantic tests  
   - Success produces positive raw delta  
   - Higher success severity reduces upward movement  
   - Failure produces negative raw delta  
   - Higher failure severity produces larger negative movement  
   - Partial low severity can produce constrained positive delta  
   - Partial high severity can produce negative delta

4. Movement-class derivation tests  
   - Each ConflictKind maps to the correct base movement class  
   - Non-Partial defaults to BOTH  
   - Prior failure window correctly transforms effective movement class  
   - Structural restriction and failure-window restriction compose deterministically

5. Gated EWMA tests  
   - Raw delta is clamped according to effective class  
   - Prior smoothed delta is clamped according to effective class  
   - EWMA is computed from permitted values only  
   - Prohibited prior directional carryover cannot leak through smoothing

6. Failure-window tests  
   - Failure activates the single-cycle window  
   - Immediately following positive opportunity is blocked  
   - Downward movement remains permitted during the window  
   - Window lasts exactly one following update  
   - Rejected / Deferred consume the window without confidence movement

7. No-update path tests  
   - Rejected leaves confidence unchanged  
   - Deferred leaves confidence unchanged  
   - No-update path does not modify prior smoothed delta  
   - No-update path logs explicit no-update action

8. Bounding tests  
   - Confidence never drops below 0.0  
   - Confidence never exceeds 1.0  
   - Boundedness holds under repeated extreme failures and repeated successes

9. Replay tests  
   - Identical inputs and fixed alpha produce identical trajectories  
   - Replay restores original state fully after execution  
   - Replay output sequence length matches input sequence length

10. Logging tests  
    - Exactly one log entry per update attempt  
    - Update logs include required metadata  
    - No-update logs include required metadata  
    - Clamp reason reflects actual effect  
    - Logger name is exactly "eck-core"

11. Mediation-boundary tests  
    - Confidence is visible only to policy mediation  
    - Confidence does not directly alter execution or action selection  
    - No silent coupling exists between confidence changes and behavior

12. Optional signal tests  
    - With all optional signals disabled, behavior is critic-only  
    - Optional signals cannot produce upward movement  
    - Optional signals cannot override gates  
    - Optional signals have zero effect on Rejected / Deferred

---

## Acceptance Criteria

PR 1 is complete only if all of the following are true:

- Confidence updates are strictly event-driven and critic-bound
- Rejected and Deferred produce true no-update behavior
- PartialStructure validation is strict and enforced
- Movement permissions are derived via base_class then effective_class
- Gating clamps both raw delta and prior smoothed delta before EWMA
- Prior-state capture is explicit and correct
- Failure-window semantics are single-cycle and deterministic
- Confidence remains bounded in [0.0, 1.0]
- Replay is deterministic and state-restoring
- Structured logging uses exactly logging.getLogger("eck-core")
- Logging has no behavioral side effects
- Confidence never directly influences behavior
- No signal influences behavior without explicit policy mediation
- All invariants from ADR-021–025 are explicitly tested and enforced
- Core remains strictly stdlib-only

---

## Dependencies

- None.

This is the first implementation PR.

## Blocks

- Memory Retrieval (PR 2)

---

## Implementation Note

This decomposition is intentionally aligned to the current ConfidenceSignal baseline.

In particular, it explicitly incorporates:

- Structural Partial semantics
- Prior-state capture
- Two-stage gate derivation
- Gated EWMA over both current and prior motion inputs
- Hardened no-update handling
- Effect-based clamp attribution

Once this PR is merged, work may proceed to PR 2, subject to the currently active implementation priorities.

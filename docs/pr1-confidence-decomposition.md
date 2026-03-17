# PR 1 — Confidence System Decomposition
**Implementation of Confidence Semantics (ADR-021–025)**

**Status:** Planning  
**Last updated:** 2026-03-17  
**Part of:** v0.2.0 Implementation (PR Plan)

This document decomposes PR 1 into concrete, implementable tasks while strictly respecting the locked invariants from ADR-021–025 and global invariants.

---

## Objectives

Implement the complete confidence subsystem as defined in ADR-021–025, ensuring:
- Strictly event-driven updates (critic only)
- Categorical outcome handling with severity scaling within category
- Asymmetric movement rules with single-cycle failure window
- Minimal input signal whitelist
- Deterministic, reproducible confidence trajectories

All changes must preserve: no direct behavioral enforcement by confidence, mediation only via explicit policy, and stdlib-only core.

---

## Task Breakdown

### 1. Core Confidence Update Mechanism (ADR-021, ADR-025)

- [ ] Implement event-driven confidence update that occurs **exactly once** after a critic evaluation and never on cycles without critic output
- [ ] Implement the update sequence as defined in ADR-025:
  - Compute raw delta from critic outcome inputs (and any enabled ADR-024 optional downward-only inputs, where applicable)
  - Apply directional permission gates
  - Apply EWMA smoothing on the delta
  - Perform bounded accumulation into [0.0, 1.0] inclusive
- [ ] Set initial confidence value to 0.5
- [ ] Explicitly handle Rejected and Deferred outcomes by producing no delta and no update
- [ ] Add support for deterministic replay: given identical inputs and fixed α, reproduce the exact same confidence trajectory
- [ ] Ensure the confidence signal is passed only to the policy mediation layer — never consumed directly by execution or action-selection components

### 2. Critic Outcome Taxonomy (ADR-022)

- [ ] Define strict categorical outcomes: Failure, Success, Partial, Rejected, Deferred
- [ ] Implement severity scaling that affects magnitude only (never changes category or bypasses gating rules)

### 3. Permission Gates & Asymmetry (ADR-023)

- [ ] Implement single-cycle failure window:
  - Upward movement forbidden immediately after a Failure outcome
  - Downward movement always permitted
  - Window applies only to the immediately following update
- [ ] Ensure Partial and other categories interact correctly with the window

### 4. Minimal Input Signal Set & Whitelist (ADR-024)

- [ ] Implement whitelist containing only signals explicitly defined in ADR-024
- [ ] Support full disabling of optional signals with zero phantom influence
- [ ] Ensure no optional signal can override critic gates or enable upward movement

### 5. Integration into Agent Flow

- [ ] Integrate confidence update into the main agent step/critic evaluation loop
- [ ] Ensure update occurs exactly once per critic output event and never outside that boundary
- [ ] Confidence signal must be passed only to the policy mediation layer — never consumed directly by execution or action-selection components

### 6. Testing & Verification

- [ ] Unit tests for EWMA smoothing, bounding, and replay determinism
- [ ] Tests verifying failure window asymmetry and category interactions
- [ ] Tests verifying whitelist behavior (optional signals disabled = no influence)
- [ ] Tests ensuring confidence never bypasses policy mediation and no silent coupling occurs
- [ ] Edge case: no critic output → confidence unchanged

---

## Acceptance Criteria

- All functionality passes existing and new tests
- Updates are strictly event-driven (critic only)
- Confidence never directly influences behavior
- No signal influences behavior without explicit policy mediation (no silent coupling)
- All invariants from ADR-021–025 are explicitly tested and enforced
- Core remains strictly stdlib-only
- Deterministic replay produces identical trajectories for identical critic sequences

---

## Dependencies

- None (this is the first implementation PR)

## Blocks

- Memory Retrieval (PR 2)

---

This decomposition respects the locked ADRs and provides clear, actionable tasks while avoiding premature implementation details.

Once this PR is merged, we will move to PR 2 (Memory Retrieval).

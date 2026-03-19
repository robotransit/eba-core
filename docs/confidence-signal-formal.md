# ECK Confidence Signal Processor: Formal Architectural Uniqueness

## 1. System Model

The agent is a stateful kernel K with:

- Observation history H_t  
- Internal epistemic state E_t  
- Policy mediation layer P  
- Capability layers L = {L₁, L₂, …} (retrieval, memory, tools, etc.)  
- Action selector A

Confidence C_t ∈ [0,1] is computed deterministically in K:

C_t = f(C_{t-1}, outcome_t, signals_t)  

where f is the gated EWMA update with single-cycle failure window, and:

- f is deterministic: identical input sequences (outcome_{1:t}, signals_{1:t}) yield identical C_t  
- signals_t ⊆ S_whitelist (per ADR-024; only explicitly whitelisted signals are admissible)

The update function f is decomposed into:
- signal interpretation (raw delta)
- permission gating (movement class constraints)
- temporal smoothing (EWMA)
- bounded accumulation

All stages operate purely on internal epistemic state and do not invoke, depend on, or modify external capabilities.

## 2. Core Kernel Invariants

1. **Epistemic Isolation**  
   In the system dependency DAG, every path C_t → A must pass through an explicit policy gate G_p.  
   No direct edge C_t → A exists in the graph.

2. **Advisory-Only Principle**  
   Within the kernel and capability layers, C_t does not directly determine or gate any behavioral output and cannot influence behavior except through explicit policy mediation.

3. **Atomic Disable Equivalence**  
   Disabling any optional signal S yields identical confidence trajectories:  
   ∀ t, C_t(S=enabled) = C_t(S=disabled)

4. **No Silent Coupling**  
   Observable outputs O may include C_t as data, but C_t is never in the control dependencies of O.  
   Formally: C_t ∉ control dependencies of O.

5. **Single-Cycle Failure Window**  
   Let F_t = 𝟙[outcome_{t-1} = Failure].  
   Then:  
   effective_movement_t = DOWN_ONLY if F_t ∧ base_class = BOTH  
   effective_movement_t = NEITHER if F_t ∧ base_class = UP_ONLY  
   effective_movement_t = base_class otherwise  
   F_{t+1} = 0 regardless of outcome_t (single-cycle consumption).

All invariants are kernel-enforced (non-negotiable, non-bypassable).

## 3. Core Distinction

Most architectures couple epistemic estimation directly to control:

uncertainty → control

ECK enforces strict separation with a structural indirection layer:

uncertainty → signal → (optional, explicit policy mediation) → control

This indirection is structurally enforced at the kernel level.

## 4. Comparison with Existing Architectures

| Paradigm                              | Confidence Role                                      | Violates ECK Invariant(s)                                                                 |
|---------------------------------------|------------------------------------------------------|-------------------------------------------------------------------------------------------|
| Reflexion, Voyager, ReAct             | Reflection score or certainty drives retry/planning | #2 (advisory-only), #1 (epistemic isolation)                                              |
| Self-RAG, CRAG, Self-Refine           | Confidence thresholds trigger retrieval or revision | #2, #3 (atomic fallback), #4 (silent coupling via retrieval)                              |
| RLIF / Intuitor-style epistemic RL    | Epistemic signal used as reward or loss component    | #2, #1 (learning coupling)                                                                |
| Most RAG pipelines (HyDE, etc.)       | Uncertainty gates retrieval or output trust          | #2, #3 (disable non-equivalence)                                                          |
| LLM calibration research              | Output-level probability calibration                 | Orthogonal (external validity vs internal epistemic kernel)                               |
| Metacognitive agents (DEPS, etc.)     | Internal confidence modifies generation or planning  | #2 (behavioral authority)                                                                 |

We are not aware of any equivalent pattern in current literature or widely used open-source agent frameworks that enforces all five invariants simultaneously at the kernel level while treating confidence as a non-authoritative, pure epistemic signal processor.

## 5. Architectural Implications

The design enables:

- Capability layers cannot introduce implicit dependencies on confidence (enforced DAG constraint)  
- Optional signals can be disabled with zero behavioral divergence (atomic equivalence)  
- Confidence trajectories are deterministic and do not alter external system state (replayability, auditability)  
- Kernel invariants prevent confidence leakage into control surfaces

This constitutes a novel architectural pattern: a deterministic, non-authoritative epistemic signal processor with enforced control separation.

We are not aware of any equivalent pattern in current literature or widely used open-source agent frameworks.

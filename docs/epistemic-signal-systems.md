# Epistemic Signal Systems (ESS): A Formal Framework for Non-Authoritative Epistemic State in Agent Architectures

## 1. Introduction

Modern agent architectures increasingly rely on internal epistemic signals—confidence, uncertainty, retrieval relevance, or self-evaluation—to guide behavior. In most systems, these signals directly influence control decisions (e.g., triggering retrieval, retries, or plan revisions), creating implicit coupling between epistemic estimation and action.

We define a class of systems—Epistemic Signal Systems (ESS)—in which epistemic signals are:

- non-authoritative (do not directly control behavior)
- structurally separated from action selection
- deterministically updated
- governed by kernel-level invariants

This framework captures and generalizes the design instantiated in the Epistemic Control Kernel (ECK), and formalizes a novel architectural pattern for safe and composable agent design.

## 2. System Definition

An Epistemic Signal System (ESS) is a tuple:

(K, S, f, G, L, A)

Where:

- K: deterministic kernel (state machine)
- S_t ∈ ℝⁿ: epistemic signal state at time t
- f: signal update function
- G: policy mediation function
- L: set of capability layers (memory, retrieval, tools, etc.)
- A: action space

State evolution:

S_t = f(S_{t-1}, o_t, x_t)

Where:

- o_t: critic/evaluation outcome
- x_t ∈ X: admissible auxiliary signals
- X ⊆ S_whitelist

Action selection:

a_t = G(H_t, E_t, S_t, π)

Where:

- H_t: history
- E_t: internal state
- π: policy

## 3. Core Distinction

Most architectures couple epistemic estimation directly to control:

uncertainty → control

ESS enforces strict separation with a structural indirection layer:

uncertainty → signal → (optional, explicit policy mediation via a policy gate G_p) → control

This indirection is structurally enforced at the kernel level.

## 4. Core Kernel Invariants

An ESS must satisfy the following invariants:

- **I1. Epistemic Isolation (Graph Constraint)**  
  In the system dependency DAG:  
  ∀ paths S_t → A: path must pass through G  
  No direct edge exists: S_t → A ∉ DAG

- **I2. Advisory-Only Signals**  
  Signals are not authority surfaces:  
  S_t does not directly determine or gate behavior  
  Formally: ∀ behavioral surfaces B: S_t ∉ direct control dependencies of B

- **I3. Atomic Disable Equivalence**  
  For any optional signal source x ∈ X:  
  ∀ t, S_t(x=enabled) = S_t(x=disabled) when x is inactive.  
  This ensures:  
  - no hidden dependencies  
  - exact equivalence under feature disablement

- **I4. No Silent Coupling**  
  Signals may appear in observability but not control:  
  S_t ∉ control dependencies of O  
  Where O = logs, metrics, traces.

- **I5. Deterministic Signal Evolution**  
  The update function f is deterministic:  
  (S_{0:t}, o_{1:t}, x_{1:t}) uniquely determines S_t  
  This implies:  
  - replayability  
  - auditability

- **I6. Temporal Guard Constraints (Optional Class)**  
  Systems may define temporal constraints on signal dynamics.  
  Example (ECK instantiation):  
  Single-cycle failure window:  
  F_t = 1[outcome_{t-1} = Failure]  
  effective_class_t =  
  - DOWN_ONLY if F_t ∧ base_class = BOTH  
  - NEITHER if F_t ∧ base_class = UP_ONLY  
  - base_class otherwise  
  F_{t+1} = 0

## 5. Signal Update Structure

The update function f is decomposed into:

f = Accumulate ∘ Smooth ∘ Gate ∘ Interpret

Where:

- Interpret: maps outcomes → raw signal deltas  
- Gate: enforces movement constraints  
- Smooth: applies temporal filtering (e.g., EWMA)  
- Accumulate: bounded accumulation of gated deltas  

All stages operate purely on internal epistemic state and do not invoke, depend on, or modify external capabilities.

## 6. Theoretical Properties

**Theorem 1 — Non-Interference**  
Under I1 and I2:  
S_t cannot directly influence action selection without mediation.  

Proof sketch:  
By I1, all paths S_t → A pass through G.  
By I2, S_t is not a control dependency of behavior.  
Therefore, any influence of S_t on A requires explicit mediation via G.

**Theorem 2 — Replay Determinism**  
Under I5:  
Given identical input sequences, S_t is identical ∀ t.  

Implication: exact reproducibility, deterministic testing.

**Theorem 3 — Feature Isolation**  
Under I3:  
Optional signals cannot introduce hidden behavioral dependencies.  

Implication: safe feature toggling, modular extensibility.

**Theorem 4 — Observational Non-Interference**  
Under I4:  
Logging and observability cannot alter system behavior via S_t.

## 7. Instantiations

The ESS framework supports multiple signal types, including:

- Confidence signals  
- Retrieval relevance signals  
- Risk estimates  
- Self-evaluation signals  

ECK is a 1-dimensional ESS instance:

S_t ∈ [0,1]

with:

- EWMA smoothing  
- movement-class gating  
- failure-window temporal constraint

## 8. Comparison to Existing Systems

Most agent architectures implement:

epistemic signal → control

ESS enforces:

epistemic signal → mediation → control

This distinction yields:

- elimination of implicit coupling  
- deterministic signal evolution  
- composable capability layers

## 9. Architectural Implications

ESS enables:

- Safe composition of capability layers  
- Deterministic replay and auditability  
- Strict separation of estimation and control  
- Strong non-interference guarantees under the invariants

## 10. Conclusion

We introduce Epistemic Signal Systems (ESS), a class of architectures in which epistemic signals are:

- deterministic  
- non-authoritative  
- structurally isolated from control  

ECK is an instantiation of this framework.

This pattern enables a new approach to agent design in which epistemic estimation is first-class but non-controlling, allowing stronger guarantees around safety, modularity, and reproducibility.

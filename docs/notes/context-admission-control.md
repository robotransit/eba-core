# Context Admission Control in Recursive Training Systems

## Provenance

This note was developed through adversarial reasoning with AI assistance.
The mathematical framing is orthodox; the application to recursive training
systems is the contribution. It is offered as a reference point, not a
validated result.

---

## Abstract

In autoregressive and agentic learning systems, model outputs can re-enter
future context through synthetic data generation, reasoning traces, tool-use
logs, or self-play loops. This creates a closed-loop system in which errors
propagate not only through gradient-based updates but also through
environmental feedback. We argue that standard training formulations
implicitly treat the system as open-loop and therefore underestimate the
impact of contamination. We introduce **Context Admission Control (CAC)**
as a structural mechanism that restricts which generated outputs are
permitted to re-enter the context distribution. Using a control-theoretic
framing, we show that CAC attenuates the environmental feedback path,
reducing the system's effective gain and improving stability when
verification is cheap and sufficiently reliable.

---

## 1. Introduction

Modern LLM training and deployment increasingly involve recursive structures:

- synthetic data generation pipelines
- agent traces and tool-use logs
- self-play and iterative refinement loops

In these systems, model outputs are not terminal artifacts. They become
part of the **future input distribution**. As a result, training is not
purely a process of fitting parameters to a static dataset; it is a
**dynamical system with feedback**.

Standard formulations focus on gradient-based learning and treat errors
as sources of corrective signal. However, they do not explicitly model
the effect of errors that re-enter the system as context. This omission
leads to an underestimation of the impact of contamination.

---

## 2. Separation of Roles: Signal vs Distribution

Standard training conflates two roles of generated outputs:

- **optimization signal** — gradients used to update parameters
- **distribution shaping** — what the model learns to reproduce

This conflation is benign in static datasets but becomes problematic in
recursive systems where outputs re-enter as context.

Context Admission Control separates these roles:

- outputs may influence parameter updates
- only admitted outputs influence the future context distribution

This separation is the structural basis for controlling feedback dynamics.

---

## 3. Two Channels of Error Propagation

In recursive training systems, errors propagate through two distinct
channels.

### 3.1 Gradient Channel

Errors influence parameter updates via gradient descent:

- incorrect outputs → corrective gradients
- learning adjusts model weights accordingly

This channel is well-studied in the literature on noisy labels and
optimization.

### 3.2 Environmental (Context) Channel

Errors may also re-enter the system as input:

- incorrect outputs admitted to the distribution
- reused as prompts, traces, or synthetic data
- influence future generations directly

This channel is typically implicit but becomes dominant in recursive
systems.

---

## 4. Closed-Loop Formulation

When outputs re-enter as context, the system forms a **closed loop**:

```
model → generates output → admitted to context → influences next generation → ...
```

This can be decomposed into two coupled feedback paths:

```
        ┌───────────────────────────────┐
        │                               │
        │      Environmental Channel    │
        │  (context / input feedback)   │
        │                               ▼
┌──────────────┐    output     ┌──────────────────────────┐
│              │──────────────▶│                          │
│    Model     │               │  Context Distribution    │
│              │◀──────────────│   (future inputs)        │
└──────┬───────┘    context    └──────────────────────────┘
       │
       │ gradient
       ▼
┌──────────────┐
│              │
│  Parameters  │
│  (weights)   │
└──────────────┘
       ▲
       │
 Gradient Channel
(learning / updates)
```

Let the system be represented (locally) as a linearized operator **A**
over a state that includes both model parameters and context distribution.
The system's behavior is characterized by the spectral radius ρ(**A**):

- ρ < 1: perturbations decay (stable)
- ρ ≥ 1: perturbations persist or grow (unstable)

The environmental channel introduces additional feedback coupling,
increasing ρ.

---

## 5. Context Admission Control

We define Context Admission Control (CAC) as a structural constraint:

> No generated output may enter the future context distribution without
> passing through a deterministic admission policy.

The admission policy is defined by an external verifier that evaluates
outputs against a correctness criterion.

Examples include:

- unit tests for code
- formal proofs for mathematical reasoning
- ground-truth databases for factual claims

---

## 6. Effect on System Dynamics

CAC attenuates the environmental feedback path by blocking contaminated
outputs from re-entering the context distribution.

In the linearized system, this corresponds to reducing the magnitude of
the feedback terms in **A**. By standard results in control theory,
reducing feedback gain reduces the spectral radius of the system operator,
yielding:

$$\rho_{\text{with CAC}} < \rho_{\text{without CAC}}$$

when the admission policy removes a non-trivial portion of erroneous
outputs.

---

## 7. When CAC Is Advantageous

CAC is most effective under the following conditions:

**Recursive context usage** — outputs are reused as future inputs.

**Non-trivial error propagation** — errors influence subsequent
generations.

**Cheap, high-coverage verification** — the cost of evaluating
correctness is low relative to the cost of contamination.

In these regimes, the cost of contamination is not limited to gradient
bias. It becomes an environmental effect that compounds over time.

---

## 8. Relation to Existing Training Paradigms

Standard training implicitly assumes an open-loop system in which errors
influence learning but do not alter the future input distribution beyond
statistical effects.

CAC introduces an explicit control over the input distribution in
recursive settings, aligning training dynamics with systems in which
failure influences adaptation without being reproduced as behavior.

---

## 9. Limitations

CAC does not apply universally and introduces tradeoffs:

- **Verifier coverage** — correctness criteria may be incomplete
- **False decisions** — good outputs may be rejected; bad outputs may pass
- **Distribution narrowing** — excluding failures may reduce diversity
- **Latency and integration costs** — gating may affect throughput
- **Damped-feedback regimes** — if the system is already stable (ρ < 1),
  CAC provides limited benefit

These constraints define the domain of applicability.

---

## 10. Conclusion

Recursive training systems introduce an environmental feedback channel
that is not captured by standard open-loop analyses. This channel
increases the system's effective gain and can lead to instability when
contaminated outputs are reused as context.

Context Admission Control provides a structural mechanism to attenuate
this feedback path. When verification is cheap and sufficiently reliable,
CAC reduces the system's effective gain and improves stability.

The contribution is not new mathematics, but the application of
closed-loop stability analysis to recursive learning systems.

---

## One-line summary

In recursive training systems, outputs that re-enter future context create
a closed-loop feedback path; context admission control attenuates this
path, reducing the system's effective gain and restoring stability when
cheap, high-coverage verification is available.

ADR-00X: Deferred Enforcement via Breadth Recommendation

Status: Deferred/Informal
Date: 2026-01-17
Deciders: ECK Maintainers
Related: Commit 4b (Resolver), Commit 4c (Enforcement), Confidence/Breadth Docs

Context

ECK introduces a confidence signal intended to influence system behavior.
However, coupling confidence directly to enforcement or suppression introduces significant risks:

- Premature or silent behavioral restriction
- Irreversible suppression in low-confidence regimes
- Loss of observability into decision-making
- Inability to audit or reason about failures
- Overloading confidence semantics with policy decisions

To mitigate these risks, the project deliberately separates recommendation from enforcement.

Commit 4b introduces a pure resolver that maps (confidence, policy_mode) to a recommended breadth.
Commit 4c introduced hard enforcement, but only after the system demonstrated correctness, observability, and semantic stability.

This ADR formalizes that separation and constrains how enforcement may be introduced.

Decision

We adopt a staged enforcement model:

Recommendation phase (Commit 4b)

- Confidence is mapped to a breadth recommendation only.
- The resolver is pure, deterministic, and observational.
- No behavioral changes, gating, or suppression occur.
- Outputs are logged for auditability.

Enforcement phase (Commit 4c)

- Hard constraints may be applied only in ENFORCED policy mode.
- Enforcement must be explainable, reversible, and observable.
- All enforcement logic must consume the existing resolver output.
- No reinterpretation of confidence or breadth semantics is permitted.

This separation is intentional and mandatory.

Constraints (Architectural Invariants)

The following constraints are binding:

- Confidence must not directly cause behavior changes without passing through the resolver.
- The resolver must remain pure until explicitly superseded by a later, explicitly approved ADR.
- NORMAL mode must remain behaviorally identical to pre-confidence ECK.
- GUIDED mode may influence defaults but must not apply hard constraints.
- ENFORCED mode is the only mode where hard gating is permitted.
- HALT mode must short-circuit generation entirely.
- Enforcement actions must be attributable via logs.
- Failure asymmetry must hold (confidence cannot increase after failure).
- Manual overrides must take precedence over enforcement.

Consequences

Positive

- High auditability and debuggability
- Clear causal chain: confidence → recommendation → (optional) enforcement
- Safe incremental rollout of enforcement logic
- Reduced risk of silent or irreversible suppression
- Easier rollback and experimentation

Negative

- Additional implementation steps
- Requires discipline to avoid shortcutting enforcement
- Some logic duplication between recommendation and enforcement layers

These costs are accepted in favor of correctness and safety.

Alternatives Considered

Immediate enforcement (rejected):

Coupling confidence directly to behavior would obscure causality,
complicate debugging, and risk unsafe suppression.

Implicit enforcement in GUIDED mode (rejected):

Violates observability-before-control principle.
Makes behavior mode-dependent in non-obvious ways.

Status & Enforcement

This ADR is binding for Commit 4c and any future enforcement-related work.

Any change that:

- Collapses recommendation and enforcement, or
- Alters confidence/breadth semantics, or
- Introduces enforcement without observability

Requires a new ADR.

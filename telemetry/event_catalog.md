# telemetry/event_catalog.md

**Status:** Normative v1
**Version:** 1.0
**Governing ADR:** ADR-045 — Formal Telemetry Schema and Observability Contract

---

## Purpose

This document defines the **normative payload contract** for all v1 ECK telemetry event types.

It complements:

* `eck/telemetry.py` — envelope construction and emission
* `telemetry/telemetry.schema.json` — machine-readable envelope schema
* ADR-045 — architectural semantics and invariants

This catalog is **normative**, not merely descriptive.

For each event type, this document specifies:

* what the event represents
* which component **MUST** emit it
* which payload fields **MUST** be included
* which payload fields **MAY** be included
* an example event

---

## Global Rules

### 1. Envelope vs payload

The event envelope is governed by:

* ADR-045
* `telemetry/telemetry.schema.json`

The payload contract for each event type is governed by this document.

---

### 2. MUST vs MAY

* **MUST include** fields are required for compliant v1 instrumentation
* **MAY include** fields are optional and additive

Optional fields must not change the meaning of required fields.

---

### 3. Source values

For v1, the following `source` values are normative:

* `step.start` → `agent`
* `step.end` → `agent`
* `action.proposed` → `execution`
* `policy.evaluate` → `policy_gate`
* `action.executed` → `execution`
* `epistemic.signal` → `confidence`

These source values MUST be used by the initial telemetry instrumentation.

---

### 4. Behavioral boundary

Telemetry is **observability-only**.

No payload field may:

* alter execution behavior
* alter policy decisions
* alter confidence updates
* create an alternate authority path

---

## Event Types

---

## `step.start`

### Description

Represents the start of a single `step()` cycle in the agent loop.

This event establishes the beginning of a cycle-level telemetry trace and anchors all subsequent per-step events.

### Emitting component

**MUST** be emitted by:

* `agent`

### Payload fields

#### MUST include

* `objective`: `string`
  Agent objective for the run

* `queue_length`: `integer`
  Queue length at the start of the step

* `policy_mode`: `string`
  Current policy mode at step entry

#### MAY include

* `task_text`: `string`
  Active task text being processed

* `task_id`: `string`
  Active task identifier, if available

* `current_confidence`: `number`
  Confidence value at step entry

  This field may duplicate the most recent epistemic state for convenience of step-local analysis.

### Example event

```json
{
  "event_type": "step.start",
  "version": "1.0",
  "timestamp": 1711929600.123,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "agent",
  "payload": {
    "objective": "Complete the current task queue safely",
    "queue_length": 3,
    "policy_mode": "NORMAL",
    "task_text": "Summarise the uploaded document",
    "task_id": "task-001",
    "current_confidence": 0.72
  }
}
```

---

## `step.end`

### Description

Represents the end of a single `step()` cycle in the agent loop.

This event closes the cycle-level telemetry trace and records the step outcome.

### Emitting component

**MUST** be emitted by:

* `agent`

### Payload fields

#### MUST include

* `continued`: `boolean`
  Whether the agent will continue after this step

* `queue_length`: `integer`
  Queue length at step exit

* `policy_mode`: `string`
  Policy mode at step exit

#### MAY include

* `task_id`: `string`
  Active task identifier, if available

* `goal_satisfied`: `boolean`
  Whether the goal completion predicate was satisfied

* `halt_reason`: `string`
  Human-readable summary when the step ended in a stop condition

### Example event

```json
{
  "event_type": "step.end",
  "version": "1.0",
  "timestamp": 1711929600.456,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "agent",
  "payload": {
    "continued": true,
    "queue_length": 2,
    "policy_mode": "NORMAL",
    "task_id": "task-001"
  }
}
```

---

## `action.proposed`

### Description

Represents the result of the proposal phase at the execution boundary.

This event records whether a `ProposedAction` was successfully constructed for the current step.

### Emitting component

**MUST** be emitted by:

* `execution`

### Payload fields

#### MUST include

* `proposal_present`: `boolean`
  Whether a `ProposedAction` was produced

#### MUST include when `proposal_present == true`

* `action_type`: `string`
  Proposed action type

* `task_id`: `string`
  Proposed action task identifier

* `provenance_id`: `string`
  Proposed action provenance identifier

#### MAY include

* `parameter_keys`: `array[string]`
  Sorted list of parameter keys present on the proposal

  Example values may reflect the current demonstration policy module and are not universal required keys for all action types.

* `proposal_refusal_reason`: `string`
  Explanation for why no proposal was produced

### Example event

```json
{
  "event_type": "action.proposed",
  "version": "1.0",
  "timestamp": 1711929600.200,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "execution",
  "payload": {
    "proposal_present": true,
    "action_type": "llm_query",
    "task_id": "task-001",
    "provenance_id": "prov-123",
    "parameter_keys": ["audience", "bounded", "request_kind"]
  }
}
```

Example when no proposal is produced:

```json
{
  "event_type": "action.proposed",
  "version": "1.0",
  "timestamp": 1711929600.200,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "execution",
  "payload": {
    "proposal_present": false,
    "proposal_refusal_reason": "no_valid_proposal"
  }
}
```

---

## `policy.evaluate`

### Description

Represents evaluation of the policy gate for the current step.

This event records the policy decision returned by the policy gate and the minimum structured context required to interpret it.

### Emitting component

**MUST** be emitted by:

* `policy_gate`

### Payload fields

#### MUST include

* `mode`: `string`
  One of `EXECUTE`, `RETRY`, `DEGRADE`, `HALT`

* `cause`: `string`
  One of the `PolicyCause` values

* `rule_id`: `string`
  Stable machine-readable identifier for the decision rule

* `reason`: `string`
  Human-readable explanation of the policy decision

* `confidence`: `number`
  Confidence value presented to the policy gate

#### MAY include

* `action_type`: `string`
  Proposed action type, if a proposal was present

* `failure_window_active`: `boolean`
  Whether the policy context indicated an active failure window

* `environment`: `string | null`
  Policy context environment

* `safety_level`: `string | null`
  Policy context safety level

### Example event

```json
{
  "event_type": "policy.evaluate",
  "version": "1.0",
  "timestamp": 1711929600.250,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "policy_gate",
  "payload": {
    "mode": "DEGRADE",
    "cause": "SAFETY",
    "rule_id": "RULE_CHILD_TRANSFORM_REFUSED",
    "reason": "child-facing transformation requests are not permitted",
    "confidence": 0.95,
    "action_type": "llm_query",
    "failure_window_active": false,
    "environment": "childcare",
    "safety_level": null
  }
}
```

---

## `action.executed`

### Description

Represents the outcome of the execution boundary after authorization and effect handling.

This event covers both performed and refused execution outcomes.

### Emitting component

**MUST** be emitted by:

* `execution`

### Payload fields

#### MUST include

* `performed`: `boolean`
  Whether a real effect was performed

#### MUST include when `performed == true`

* `outcome`: `string`
  Canonical execution outcome string

#### MUST include when `performed == false`

* `refusal_reason`: `string`
  Machine-readable refusal reason returned by the execution boundary

#### MAY include

* `action_type`: `string`
  Executed or refused action type, if available

* `task_id`: `string`
  Task identifier, if available

* `provenance_id`: `string`
  Provenance identifier, if available

### Example event

```json
{
  "event_type": "action.executed",
  "version": "1.0",
  "timestamp": 1711929600.320,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "execution",
  "payload": {
    "performed": true,
    "outcome": "YES",
    "action_type": "llm_query",
    "task_id": "task-001",
    "provenance_id": "prov-123"
  }
}
```

Example refused execution:

```json
{
  "event_type": "action.executed",
  "version": "1.0",
  "timestamp": 1711929600.320,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "execution",
  "payload": {
    "performed": false,
    "refusal_reason": "action_type_not_whitelisted",
    "action_type": "file_write",
    "task_id": "task-001",
    "provenance_id": "prov-123"
  }
}
```

---

## `epistemic.signal`

### Description

Represents the epistemic update for a cycle.

This event records the resulting confidence value and the critic/update semantics required to interpret the signal.

### Emitting component

**MUST** be emitted by:

* `confidence`

### Payload fields

#### MUST include

* `confidence`: `number`
  Resulting confidence value in `[0.0, 1.0]`

* `category`: `string`
  MUST be one of:

  * `"success"`
  * `"failure"`
  * `"partial"`
  * `"rejected"`
  * `"deferred"`

* `updated`: `boolean`
  Whether confidence changed this cycle

#### MAY include

* `severity`: `number`
  Critic severity in `[0.0, 1.0]`, if applicable

* `prior_confidence`: `number`
  Confidence value before update

* `delta_raw`: `number`
  Raw update delta, if an update occurred

* `delta_smoothed`: `number`
  Smoothed update delta, if an update occurred

### Example event

```json
{
  "event_type": "epistemic.signal",
  "version": "1.0",
  "timestamp": 1711929600.380,
  "trace_id": "trace-abc",
  "step_id": "trace-abc:step:12",
  "deterministic_nonce": 12,
  "severity": "INFO",
  "source": "confidence",
  "payload": {
    "confidence": 0.78,
    "category": "success",
    "updated": true,
    "severity": 0.1,
    "prior_confidence": 0.74,
    "delta_raw": 0.05,
    "delta_smoothed": 0.04
  }
}
```

---

## Versioning Note

This catalog defines the **normative v1 payload contract** for all six event types.

At v1:

* the event envelope is machine-validated by `telemetry/telemetry.schema.json`
* `epistemic.signal` includes additional payload-level schema constraints
* payload constraints for the remaining event types are defined normatively here and may be promoted into future schema versions once instrumentation stabilizes

Any incompatible payload change requires:

* catalog update
* schema update where applicable
* version bump as required by ADR-045

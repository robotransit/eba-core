# eck/execution.py
"""
Execution boundary for the Epistemic Control Kernel (ECK).

Implements the propose/authorize/perform split defined in ADR-042.

Subsystem responsibilities:
  propose_execution      — advisory only; calls LLM, parses ProposedAction;
                           no effects, no gate consultation
  authorize_and_perform  — sole effects boundary; enforces gate precondition,
                           action whitelist, required parameter keys, provenance;
                           returns ExecutionResult for contract-level refusals
                           and performed effects; raises AssertionError for
                           invariant violations (non-compliant caller)

Thin-slice implementation note (ADR-042 section 5a):
  This is the initial v0.3.0 thin-slice implementation. It enforces a
  subset of the full execution envelope as explicitly documented in ADR-042.

  Enforced:
    - proposed_action is not None (INV3 — raises AssertionError on violation)
    - policy_mode != PolicyMode.HALT (INV6 — raises AssertionError on violation)
    - action_type within registered whitelist
    - required parameter keys present for action_type
    - provenance_id non-empty

  Deferred:
    - active-task context verification (task_id matching) — deferred until
      execution context object is formalised in a subsequent slice
    - full parameter schema validation beyond key presence — deferred until
      deployment-specific schemas are defined

ADR references:
  ADR-042: Propose/Authorize/Perform Execution Boundary
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from .config import PolicyMode
from .types import ExecutionResult, ProposedAction
from .utils import generate_id

logger = logging.getLogger("eck-core")


# ── Action whitelist ──────────────────────────────────────────────────────────
#
# Thin-slice whitelist (ADR-042 section 5a):
#   "llm_query" — calls the LLM with a prompt parameter; proves the boundary
#                 can carry a real action with a real execution result
#
# Deployment-specific registries will extend or replace this in later slices.

_WHITELISTED_ACTIONS: frozenset[str] = frozenset({"llm_query"})

# Required parameter keys per action type (thin-slice schema — key presence only).
# Full type/value schema validation is deferred (ADR-042 section 5a).
_REQUIRED_PARAMS: dict[str, frozenset[str]] = {
    "llm_query": frozenset({"prompt"}),
}


# ── propose_execution ─────────────────────────────────────────────────────────

def propose_execution(
    task_text: str,
    llm_call: Callable[[str], str],
    task_id: str | None = None,
) -> ProposedAction | None:
    """
    Call the LLM and parse its response into a ProposedAction (ADR-042).

    Advisory only — no effects, no gate consultation. Returns None on any
    parse or validation failure. A None return is a per-cycle no-op and
    MUST NOT be interpreted as a system halt or policy escalation signal.

    Fail closed: any response that cannot be parsed into a valid,
    whitelisted ProposedAction returns None. This includes non-string
    LLM responses, JSON parse failures, unwhitelisted action types,
    malformed parameters, and ProposedAction construction failures.

    Note on provenance_id: in this thin slice, provenance_id is a synthetic
    correlation ID generated at proposal time. It is not yet derived from
    the actual LLM call identity. This is an honest placeholder — true call
    provenance will be formalised when the telemetry schema is locked.

    Args:
        task_text: The current task description (used as prompt context).
        llm_call:  LLM callable.
        task_id:   Optional task correlation ID. Generated if not provided.

    Returns:
        ProposedAction if parsing succeeds, None otherwise.
    """
    tid = task_id or generate_id()
    provenance_id = generate_id()
    raw = ""

    prompt = (
        f"Given this task, propose an action to perform.\n\n"
        f"Task: {task_text}\n\n"
        f"Respond with ONLY valid JSON:\n"
        f'{{\n'
        f'  "action_type": "llm_query",\n'
        f'  "parameters": {{"prompt": "<your prompt>"}}\n'
        f'}}\n\n'
        f"Respond with valid JSON only. No other text."
    )

    try:
        raw = llm_call(prompt)
        if not isinstance(raw, str):
            logger.warning(
                "propose_execution: LLM returned non-string response",
                extra={
                    "task_id": tid,
                    "response_type": type(raw).__name__,
                },
            )
            return None
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        logger.warning(
            "propose_execution: LLM response unparseable",
            extra={
                "task_id": tid,
                "error": str(e),
                "response_preview": raw[:80] if isinstance(raw, str) else "",
            },
        )
        return None

    action_type = str(data.get("action_type", "")).strip().lower()
    if action_type not in _WHITELISTED_ACTIONS:
        logger.warning(
            "propose_execution: action_type not in whitelist",
            extra={
                "task_id": tid,
                "action_type": action_type,
                "whitelist": sorted(_WHITELISTED_ACTIONS),
            },
        )
        return None

    parameters = data.get("parameters", {})
    if not isinstance(parameters, dict):
        logger.warning(
            "propose_execution: parameters is not a dict",
            extra={"task_id": tid, "action_type": action_type},
        )
        return None

    # Validate required parameter keys (thin slice — key presence only,
    # not full type/value schema validation per ADR-042 section 5a).
    required = _REQUIRED_PARAMS.get(action_type, frozenset())
    missing = required - set(parameters.keys())
    if missing:
        logger.warning(
            "propose_execution: missing required parameters",
            extra={
                "task_id": tid,
                "action_type": action_type,
                "missing": sorted(missing),
            },
        )
        return None

    try:
        proposal = ProposedAction(
            action_type=action_type,
            parameters=parameters,
            task_text=task_text,
            task_id=tid,
            provenance_id=provenance_id,
        )
    except (TypeError, ValueError) as e:
        logger.warning(
            "propose_execution: ProposedAction construction failed",
            extra={"task_id": tid, "error": str(e)},
        )
        return None

    logger.info(
        "propose_execution: proposal constructed",
        extra={
            "task_id": tid,
            "action_type": action_type,
            "provenance_id": provenance_id,
        },
    )
    return proposal


# ── authorize_and_perform ─────────────────────────────────────────────────────

def authorize_and_perform(
    proposed_action: ProposedAction,
    policy_mode: PolicyMode,
    llm_call: Callable[[str], str] | None = None,
) -> ExecutionResult:
    """
    Sole effects boundary for the ECK execution surface (ADR-042).

    Enforces both authorization conditions from the formal model:
      INV2 (kernel authorization): action whitelist + required parameter keys
      INV3 (proposal present): raises AssertionError if None — non-compliant caller
      INV6 (no effect in HALT): raises AssertionError if HALT — non-compliant caller

    Note on INV1 (gate precondition): enforced by agent loop sequencing —
    this function is only called when gate returned ExecutionMode.EXECUTE.
    The policy_mode != HALT check here is a secondary defensive assertion.

    Note on task_id active-context verification: deferred from this thin
    slice — authorize_and_perform has no access to the current active task
    context. Will be addressed when the execution context is formalised
    (ADR-042 section 5a).

    Invariant violations (None proposal, HALT mode) raise AssertionError
    rather than returning ExecutionResult — these indicate non-compliant
    callers, not ordinary authorization refusals. Explicit raise is used
    rather than assert, which can be stripped by Python's -O flag.

    Contract-level authorization failures (whitelist, schema, provenance,
    non-string LLM response) return ExecutionResult(performed=False) and
    never raise.

    All external side effects occur exclusively inside this function,
    including transitive calls.

    Args:
        proposed_action: The ProposedAction to authorize and perform.
        policy_mode:     Current policy mode (defensive HALT check — INV6).
        llm_call:        LLM callable (required for llm_query actions).

    Returns:
        ExecutionResult with performed=True on success,
        performed=False with refusal_reason on any contract-level refusal.
    """
    # ── Invariant enforcement (non-compliant caller — raises, does not refuse) ─
    if proposed_action is None:
        raise AssertionError(
            "authorize_and_perform: proposed_action must not be None (INV3) — "
            "non-compliant caller"
        )
    if policy_mode == PolicyMode.HALT:
        raise AssertionError(
            "authorize_and_perform: must not be called in HALT mode (INV6) — "
            "non-compliant caller"
        )

    task_id = proposed_action.task_id
    action_type = proposed_action.action_type

    # ── Kernel authorization: whitelist check ─────────────────────────────────
    if action_type not in _WHITELISTED_ACTIONS:
        logger.info(
            "authorize_and_perform: action_type not in whitelist — refused",
            extra={
                "task_id": task_id,
                "action_type": action_type,
                "provenance_id": proposed_action.provenance_id,
                "performed": False,
                "refusal_reason": "action_type_not_whitelisted",
            },
        )
        return ExecutionResult(
            performed=False,
            outcome="",
            refusal_reason="action_type_not_whitelisted",
        )

    # ── Kernel authorization: required parameter keys check ───────────────────
    # Thin slice: key presence only, not full type/value schema validation
    # (ADR-042 section 5a).
    required = _REQUIRED_PARAMS.get(action_type, frozenset())
    missing = required - set(proposed_action.parameters.keys())
    if missing:
        refusal = f"missing_required_parameters:{','.join(sorted(missing))}"
        logger.info(
            "authorize_and_perform: missing required parameters — refused",
            extra={
                "task_id": task_id,
                "action_type": action_type,
                "provenance_id": proposed_action.provenance_id,
                "performed": False,
                "refusal_reason": refusal,
            },
        )
        return ExecutionResult(
            performed=False,
            outcome="",
            refusal_reason=refusal,
        )

    # ── Kernel authorization: provenance check ────────────────────────────────
    if not proposed_action.provenance_id or not proposed_action.provenance_id.strip():
        logger.info(
            "authorize_and_perform: provenance_id absent — refused",
            extra={
                "task_id": task_id,
                "action_type": action_type,
                "performed": False,
                "refusal_reason": "missing_provenance_id",
            },
        )
        return ExecutionResult(
            performed=False,
            outcome="",
            refusal_reason="missing_provenance_id",
        )

    # ── Perform effect ────────────────────────────────────────────────────────
    try:
        if action_type == "llm_query":
            if llm_call is None:
                logger.info(
                    "authorize_and_perform: llm_query requires llm_call — refused",
                    extra={
                        "task_id": task_id,
                        "action_type": action_type,
                        "provenance_id": proposed_action.provenance_id,
                        "performed": False,
                        "refusal_reason": "llm_call_not_provided",
                    },
                )
                return ExecutionResult(
                    performed=False,
                    outcome="",
                    refusal_reason="llm_call_not_provided",
                )
            prompt = str(proposed_action.parameters["prompt"])
            raw_outcome = llm_call(prompt)
            if not isinstance(raw_outcome, str):
                logger.info(
                    "authorize_and_perform: llm_query returned non-string — refused",
                    extra={
                        "task_id": task_id,
                        "action_type": action_type,
                        "provenance_id": proposed_action.provenance_id,
                        "performed": False,
                        "refusal_reason": "llm_query_non_string_response",
                        "response_type": type(raw_outcome).__name__,
                    },
                )
                return ExecutionResult(
                    performed=False,
                    outcome="",
                    refusal_reason="llm_query_non_string_response",
                )
            outcome = " ".join(raw_outcome.strip().split())
            logger.info(
                "authorize_and_perform: llm_query performed",
                extra={
                    "task_id": task_id,
                    "action_type": action_type,
                    "provenance_id": proposed_action.provenance_id,
                    "performed": True,
                    "outcome": outcome,
                },
            )
            return ExecutionResult(
                performed=True,
                outcome=outcome,
                refusal_reason=None,
            )

    except Exception as e:  # pragma: no cover
        logger.warning(
            "authorize_and_perform: unexpected error during effect",
            extra={
                "task_id": task_id,
                "action_type": action_type,
                "provenance_id": proposed_action.provenance_id,
                "error": str(e),
            },
        )
        return ExecutionResult(
            performed=False,
            outcome="",
            refusal_reason=f"unexpected_error:{e}",
        )

    # Defensive: unreachable if whitelist and action handlers are in sync
    return ExecutionResult(  # pragma: no cover
        performed=False,
        outcome="",
        refusal_reason=f"unhandled_action_type:{action_type}",
    )

# tests/test_execution.py
"""Tests for propose_execution() and authorize_and_perform() (ADR-042)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from eck.config import PolicyMode
from eck.execution import authorize_and_perform, propose_execution
from eck.types import ExecutionResult, ProposedAction


# ── LLM stubs ─────────────────────────────────────────────────────────────────

def _llm_valid_proposal(prompt: str) -> str:
    """Returns a valid llm_query proposal."""
    return json.dumps({
        "action_type": "llm_query",
        "parameters": {"prompt": "do the thing"},
    })


def _llm_non_string(prompt: str):
    """Returns a non-string response."""
    return None


def _llm_bad_json(prompt: str) -> str:
    """Returns unparseable JSON."""
    return "not json at all"


def _llm_unwhitelisted(prompt: str) -> str:
    """Returns a valid JSON proposal with an unwhitelisted action type."""
    return json.dumps({
        "action_type": "file_write",
        "parameters": {"path": "/tmp/x", "content": "y"},
    })


def _llm_non_dict_parameters(prompt: str) -> str:
    """Returns a proposal where parameters is a list, not a dict."""
    return json.dumps({
        "action_type": "llm_query",
        "parameters": ["prompt", "do the thing"],
    })


def _llm_missing_required_params(prompt: str) -> str:
    """Returns a valid llm_query proposal missing the required 'prompt' key."""
    return json.dumps({
        "action_type": "llm_query",
        "parameters": {},
    })


def _make_proposal(
    action_type: str = "llm_query",
    parameters: dict | None = None,
    task_text: str = "task",
    task_id: str = "tid-001",
    provenance_id: str = "prov-001",
) -> ProposedAction:
    """Construct a minimal valid ProposedAction for use in authorize tests."""
    return ProposedAction(
        action_type=action_type,
        parameters=parameters if parameters is not None else {"prompt": "do the thing"},
        task_text=task_text,
        task_id=task_id,
        provenance_id=provenance_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# propose_execution tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeExecutionValidPath(unittest.TestCase):
    """propose_execution — valid proposal construction."""

    def test_valid_proposal_returns_proposed_action(self) -> None:
        """Valid LLM response returns a ProposedAction instance."""
        result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsInstance(result, ProposedAction)

    def test_valid_proposal_action_type(self) -> None:
        """Returned ProposedAction has correct action_type."""
        result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "llm_query")

    def test_valid_proposal_parameters(self) -> None:
        """Returned ProposedAction carries the parsed parameters dict."""
        result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNotNone(result)
        self.assertIsInstance(result.parameters, dict)
        self.assertIn("prompt", result.parameters)

    def test_valid_proposal_task_text(self) -> None:
        """Returned ProposedAction carries the originating task_text."""
        result = propose_execution("my task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNotNone(result)
        self.assertEqual(result.task_text, "my task")

    def test_valid_proposal_task_id_preserved(self) -> None:
        """Returned ProposedAction carries the supplied task_id."""
        result = propose_execution("task", _llm_valid_proposal, task_id="tid-abc")
        self.assertIsNotNone(result)
        self.assertEqual(result.task_id, "tid-abc")

    def test_valid_proposal_provenance_id_non_empty(self) -> None:
        """Returned ProposedAction has a non-empty provenance_id."""
        result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNotNone(result)
        self.assertTrue(result.provenance_id.strip())

    def test_task_id_generated_when_not_provided(self) -> None:
        """When task_id is not provided, a non-empty ID is generated."""
        result = propose_execution("task", _llm_valid_proposal)
        self.assertIsNotNone(result)
        self.assertTrue(result.task_id.strip())

    def test_proposal_is_immutable(self) -> None:
        """Returned ProposedAction is a frozen dataclass — mutation raises."""
        result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNotNone(result)
        with self.assertRaises((AttributeError, TypeError)):
            result.action_type = "mutated"


class TestProposeExecutionFailClosed(unittest.TestCase):
    """propose_execution — fail-closed on all invalid inputs."""

    def test_non_string_llm_response_returns_none(self) -> None:
        """Non-string LLM response → None."""
        result = propose_execution("task", _llm_non_string, task_id="tid-001")
        self.assertIsNone(result)

    def test_bad_json_returns_none(self) -> None:
        """Unparseable JSON response → None."""
        result = propose_execution("task", _llm_bad_json, task_id="tid-001")
        self.assertIsNone(result)

    def test_empty_string_response_returns_none(self) -> None:
        """Empty string response → None."""
        result = propose_execution("task", lambda p: "", task_id="tid-001")
        self.assertIsNone(result)

    def test_unwhitelisted_action_type_returns_none(self) -> None:
        """Unwhitelisted action_type → None."""
        result = propose_execution("task", _llm_unwhitelisted, task_id="tid-001")
        self.assertIsNone(result)

    def test_non_dict_parameters_returns_none(self) -> None:
        """Parameters that is not a dict → None."""
        result = propose_execution("task", _llm_non_dict_parameters, task_id="tid-001")
        self.assertIsNone(result)

    def test_missing_required_parameter_keys_returns_none(self) -> None:
        """Missing required parameter keys → None."""
        result = propose_execution("task", _llm_missing_required_params, task_id="tid-001")
        self.assertIsNone(result)

    def test_proposed_action_construction_failure_returns_none(self) -> None:
        """ProposedAction construction raising ValueError → None (fail closed)."""
        with patch("eck.execution.ProposedAction", side_effect=ValueError("construction failed")):
            result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNone(result)

    def test_proposed_action_construction_type_error_returns_none(self) -> None:
        """ProposedAction construction raising TypeError → None (fail closed)."""
        with patch("eck.execution.ProposedAction", side_effect=TypeError("type error")):
            result = propose_execution("task", _llm_valid_proposal, task_id="tid-001")
        self.assertIsNone(result)

    def test_none_return_is_not_system_halt(self) -> None:
        """None return from propose_execution is a per-cycle no-op, not a halt.
        Verified by calling twice — second call still works normally."""
        result1 = propose_execution("task", _llm_bad_json, task_id="tid-001")
        self.assertIsNone(result1)
        result2 = propose_execution("task", _llm_valid_proposal, task_id="tid-002")
        self.assertIsNotNone(result2)


# ─────────────────────────────────────────────────────────────────────────────
# authorize_and_perform tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorizeAndPerformInvariantViolations(unittest.TestCase):
    """authorize_and_perform — invariant violations raise AssertionError."""

    def test_none_proposal_raises_assertion_error(self) -> None:
        """proposed_action=None raises AssertionError (INV3 — non-compliant caller)."""
        with self.assertRaises(AssertionError):
            authorize_and_perform(
                proposed_action=None,
                policy_mode=PolicyMode.NORMAL,
            )

    def test_halt_mode_raises_assertion_error(self) -> None:
        """policy_mode=HALT raises AssertionError (INV6 — non-compliant caller)."""
        with self.assertRaises(AssertionError):
            authorize_and_perform(
                proposed_action=_make_proposal(),
                policy_mode=PolicyMode.HALT,
            )

    def test_none_proposal_does_not_return_execution_result(self) -> None:
        """None proposal raises — does not return a refused ExecutionResult."""
        try:
            authorize_and_perform(
                proposed_action=None,
                policy_mode=PolicyMode.NORMAL,
            )
            self.fail("Expected AssertionError was not raised")
        except AssertionError:
            pass
        except Exception as e:
            self.fail(f"Expected AssertionError, got {type(e).__name__}: {e}")


class TestAuthorizeAndPerformContractRefusals(unittest.TestCase):
    """authorize_and_perform — contract-level refusals return ExecutionResult."""

    def test_unwhitelisted_action_type_returns_refused(self) -> None:
        """Unwhitelisted action_type → performed=False."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(action_type="file_write"),
            policy_mode=PolicyMode.NORMAL,
        )
        self.assertFalse(result.performed)
        self.assertEqual(result.refusal_reason, "action_type_not_whitelisted")

    def test_unwhitelisted_action_type_outcome_empty(self) -> None:
        """Unwhitelisted action_type → outcome is empty string."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(action_type="file_write"),
            policy_mode=PolicyMode.NORMAL,
        )
        self.assertEqual(result.outcome, "")

    def test_missing_required_parameter_returns_refused(self) -> None:
        """Missing required parameter key → performed=False."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(parameters={}),
            policy_mode=PolicyMode.NORMAL,
        )
        self.assertFalse(result.performed)
        self.assertIn("missing_required_parameters", result.refusal_reason)

    def test_missing_required_parameter_outcome_empty(self) -> None:
        """Missing required parameter key → outcome is empty string."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(parameters={}),
            policy_mode=PolicyMode.NORMAL,
        )
        self.assertEqual(result.outcome, "")

    def test_llm_call_not_provided_returns_refused(self) -> None:
        """llm_query without llm_call → performed=False."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=None,
        )
        self.assertFalse(result.performed)
        self.assertEqual(result.refusal_reason, "llm_call_not_provided")

    def test_llm_query_non_string_response_returns_refused(self) -> None:
        """llm_query where LLM returns non-string → performed=False."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: None,
        )
        self.assertFalse(result.performed)
        self.assertEqual(result.refusal_reason, "llm_query_non_string_response")

    def test_contract_refusal_returns_execution_result_instance(self) -> None:
        """Contract-level refusal returns an ExecutionResult instance."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(action_type="file_write"),
            policy_mode=PolicyMode.NORMAL,
        )
        self.assertIsInstance(result, ExecutionResult)

    def test_contract_refusal_never_raises(self) -> None:
        """Contract-level refusals return ExecutionResult — never raise."""
        try:
            result = authorize_and_perform(
                proposed_action=_make_proposal(parameters={}),
                policy_mode=PolicyMode.NORMAL,
            )
            self.assertIsInstance(result, ExecutionResult)
        except Exception as e:
            self.fail(
                f"Contract refusal should not raise — got {type(e).__name__}: {e}"
            )


class TestAuthorizeAndPerformSuccessPath(unittest.TestCase):
    """authorize_and_perform — successful llm_query execution."""

    def test_llm_query_returns_performed_true(self) -> None:
        """Successful llm_query → performed=True."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "the result",
        )
        self.assertTrue(result.performed)

    def test_llm_query_refusal_reason_none(self) -> None:
        """Successful llm_query → refusal_reason is None."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "the result",
        )
        self.assertIsNone(result.refusal_reason)

    def test_llm_query_outcome_matches_llm_response(self) -> None:
        """Successful llm_query → outcome carries normalised LLM response."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "the result",
        )
        self.assertEqual(result.outcome, "the result")

    def test_llm_query_outcome_whitespace_normalised(self) -> None:
        """Successful llm_query → outcome has internal whitespace normalised."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "  messy   whitespace  response  ",
        )
        self.assertEqual(result.outcome, "messy whitespace response")

    def test_llm_query_returns_execution_result_instance(self) -> None:
        """Successful llm_query returns an ExecutionResult instance."""
        result = authorize_and_perform(
            proposed_action=_make_proposal(),
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "ok",
        )
        self.assertIsInstance(result, ExecutionResult)

    def test_llm_query_prompt_passed_to_llm(self) -> None:
        """The prompt parameter from ProposedAction is passed to llm_call."""
        received = {}

        def capture_llm(prompt: str) -> str:
            received["prompt"] = prompt
            return "ok"

        authorize_and_perform(
            proposed_action=_make_proposal(
                parameters={"prompt": "specific prompt text"}
            ),
            policy_mode=PolicyMode.NORMAL,
            llm_call=capture_llm,
        )
        self.assertEqual(received.get("prompt"), "specific prompt text")

    def test_non_halt_policy_modes_permit_execution(self) -> None:
        """NORMAL, GUIDED, and ENFORCED policy modes all permit execution."""
        for mode in (PolicyMode.NORMAL, PolicyMode.GUIDED, PolicyMode.ENFORCED):
            with self.subTest(mode=mode):
                result = authorize_and_perform(
                    proposed_action=_make_proposal(),
                    policy_mode=mode,
                    llm_call=lambda p: "ok",
                )
                self.assertTrue(result.performed)


class TestAuthorizeAndPerformDeterminism(unittest.TestCase):
    """authorize_and_perform — deterministic replay."""

    def test_identical_inputs_produce_identical_results(self) -> None:
        """Identical ProposedAction and policy state → identical ExecutionResult."""
        proposal = _make_proposal()

        result1 = authorize_and_perform(
            proposed_action=proposal,
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "fixed response",
        )
        result2 = authorize_and_perform(
            proposed_action=proposal,
            policy_mode=PolicyMode.NORMAL,
            llm_call=lambda p: "fixed response",
        )
        self.assertEqual(result1, result2)


if __name__ == "__main__":
    unittest.main()

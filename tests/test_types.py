# tests/test_types.py
"""Tests for shared kernel types (ADR-022, ADR-042)."""

from __future__ import annotations

import unittest

from eck.types import (
    ConflictKind,
    ConflictLocus,
    CriticOutcome,
    ExecutionResult,
    PartialStructure,
    ProposedAction,
    make_critic_outcome,
)


# ─────────────────────────────────────────────────────────────────────────────
# ProposedAction tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProposedActionValidConstruction(unittest.TestCase):
    """ProposedAction — valid construction."""

    def _make(self, **kwargs) -> ProposedAction:
        defaults = dict(
            action_type="llm_query",
            parameters={"prompt": "do the thing"},
            task_text="task",
            task_id="tid-001",
            provenance_id="prov-001",
        )
        defaults.update(kwargs)
        return ProposedAction(**defaults)

    def test_valid_construction_succeeds(self) -> None:
        """Valid fields produce a ProposedAction without error."""
        p = self._make()
        self.assertEqual(p.action_type, "llm_query")
        self.assertEqual(p.task_id, "tid-001")
        self.assertEqual(p.provenance_id, "prov-001")
        self.assertEqual(p.task_text, "task")
        self.assertIsInstance(p.parameters, dict)

    def test_empty_parameters_dict_accepted(self) -> None:
        """Empty parameters dict is valid."""
        p = self._make(parameters={})
        self.assertEqual(p.parameters, {})

    def test_is_frozen(self) -> None:
        """ProposedAction is immutable — mutation raises."""
        p = self._make()
        with self.assertRaises((AttributeError, TypeError)):
            p.action_type = "mutated"


class TestProposedActionInvariantEnforcement(unittest.TestCase):
    """ProposedAction.__post_init__ — invariant violations raise ValueError."""

    def _make(self, **kwargs) -> ProposedAction:
        defaults = dict(
            action_type="llm_query",
            parameters={"prompt": "do the thing"},
            task_text="task",
            task_id="tid-001",
            provenance_id="prov-001",
        )
        defaults.update(kwargs)
        return ProposedAction(**defaults)

    def test_empty_action_type_raises(self) -> None:
        """Empty action_type string raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(action_type="")

    def test_whitespace_only_action_type_raises(self) -> None:
        """Whitespace-only action_type raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(action_type="   ")

    def test_non_dict_parameters_raises(self) -> None:
        """Non-dict parameters raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(parameters=["not", "a", "dict"])

    def test_none_parameters_raises(self) -> None:
        """None parameters raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(parameters=None)

    def test_non_string_task_text_raises(self) -> None:
        """Non-string task_text raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(task_text=123)

    def test_empty_task_id_raises(self) -> None:
        """Empty task_id string raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(task_id="")

    def test_whitespace_only_task_id_raises(self) -> None:
        """Whitespace-only task_id raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(task_id="   ")

    def test_empty_provenance_id_raises(self) -> None:
        """Empty provenance_id string raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(provenance_id="")

    def test_whitespace_only_provenance_id_raises(self) -> None:
        """Whitespace-only provenance_id raises ValueError."""
        with self.assertRaises(ValueError):
            self._make(provenance_id="   ")


# ─────────────────────────────────────────────────────────────────────────────
# ExecutionResult tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionResultValidConstruction(unittest.TestCase):
    """ExecutionResult — valid construction."""

    def test_performed_true_valid(self) -> None:
        """performed=True with outcome string and no refusal_reason is valid."""
        r = ExecutionResult(performed=True, outcome="ok", refusal_reason=None)
        self.assertTrue(r.performed)
        self.assertEqual(r.outcome, "ok")
        self.assertIsNone(r.refusal_reason)

    def test_performed_false_valid(self) -> None:
        """performed=False with empty outcome and refusal_reason is valid."""
        r = ExecutionResult(performed=False, outcome="", refusal_reason="gate:HALT")
        self.assertFalse(r.performed)
        self.assertEqual(r.outcome, "")
        self.assertEqual(r.refusal_reason, "gate:HALT")

    def test_is_frozen(self) -> None:
        """ExecutionResult is immutable — mutation raises."""
        r = ExecutionResult(performed=True, outcome="ok", refusal_reason=None)
        with self.assertRaises((AttributeError, TypeError)):
            r.performed = False


class TestExecutionResultInvariantEnforcement(unittest.TestCase):
    """ExecutionResult.__post_init__ — invariant violations raise ValueError."""

    def test_non_string_outcome_raises(self) -> None:
        """Non-string outcome raises ValueError."""
        with self.assertRaises(ValueError):
            ExecutionResult(performed=True, outcome=None, refusal_reason=None)

    def test_non_string_refusal_reason_raises(self) -> None:
        """Non-string, non-None refusal_reason raises ValueError."""
        with self.assertRaises(ValueError):
            ExecutionResult(performed=False, outcome="", refusal_reason=123)

    def test_performed_true_with_refusal_reason_raises(self) -> None:
        """performed=True with a refusal_reason raises ValueError (split-brain)."""
        with self.assertRaises(ValueError):
            ExecutionResult(performed=True, outcome="ok", refusal_reason="some reason")

    def test_performed_false_with_non_empty_outcome_raises(self) -> None:
        """performed=False with non-empty outcome raises ValueError (split-brain)."""
        with self.assertRaises(ValueError):
            ExecutionResult(performed=False, outcome="some outcome", refusal_reason="reason")

    def test_performed_false_with_empty_refusal_reason_raises(self) -> None:
        """performed=False with empty refusal_reason raises ValueError."""
        with self.assertRaises(ValueError):
            ExecutionResult(performed=False, outcome="", refusal_reason="")

    def test_performed_false_with_none_refusal_reason_raises(self) -> None:
        """performed=False with None refusal_reason raises ValueError."""
        with self.assertRaises(ValueError):
            ExecutionResult(performed=False, outcome="", refusal_reason=None)


# ─────────────────────────────────────────────────────────────────────────────
# CriticOutcome and make_critic_outcome tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMakeCriticOutcome(unittest.TestCase):
    """make_critic_outcome — canonical constructor and derived success field."""

    def test_success_category_derives_success_true(self) -> None:
        """category='success' → success=True."""
        o = make_critic_outcome(category="success", severity=0.1, feedback="ok")
        self.assertTrue(o.success)
        self.assertEqual(o.category, "success")

    def test_failure_category_derives_success_false(self) -> None:
        """category='failure' → success=False."""
        o = make_critic_outcome(category="failure", severity=0.8, feedback="fail")
        self.assertFalse(o.success)

    def test_partial_category_derives_success_false(self) -> None:
        """category='partial' → success=False."""
        o = make_critic_outcome(category="partial", severity=0.3, feedback="minor")
        self.assertFalse(o.success)

    def test_rejected_category_derives_success_false(self) -> None:
        """category='rejected' → success=False."""
        o = make_critic_outcome(category="rejected", severity=0.0, feedback="refused")
        self.assertFalse(o.success)

    def test_deferred_category_derives_success_false(self) -> None:
        """category='deferred' → success=False."""
        o = make_critic_outcome(category="deferred", severity=0.0, feedback="deferred")
        self.assertFalse(o.success)

    def test_severity_preserved(self) -> None:
        """Severity is preserved in the returned CriticOutcome."""
        o = make_critic_outcome(category="success", severity=0.42, feedback="ok")
        self.assertAlmostEqual(o.severity, 0.42)

    def test_feedback_preserved(self) -> None:
        """Feedback string is preserved in the returned CriticOutcome."""
        o = make_critic_outcome(category="success", severity=0.1, feedback="looks good")
        self.assertEqual(o.feedback, "looks good")

    def test_returns_critic_outcome_instance(self) -> None:
        """make_critic_outcome returns a CriticOutcome instance."""
        o = make_critic_outcome(category="success", severity=0.1, feedback="ok")
        self.assertIsInstance(o, CriticOutcome)

    def test_success_field_consistent_with_category(self) -> None:
        """success field is always consistent with category == 'success'."""
        for category in ("success", "failure", "partial", "rejected", "deferred"):
            with self.subTest(category=category):
                o = make_critic_outcome(
                    category=category, severity=0.0, feedback="x"
                )
                self.assertEqual(o.success, category == "success")


# ─────────────────────────────────────────────────────────────────────────────
# PartialStructure tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialStructure(unittest.TestCase):
    """PartialStructure — construction and field types."""

    def test_valid_construction(self) -> None:
        """Valid PartialStructure constructs without error."""
        ps = PartialStructure(
            collapse_status="unresolved",
            conflict_kind=ConflictKind.EVIDENCE_CONFLICT,
            conflict_footprint=frozenset({ConflictLocus.LOCAL, ConflictLocus.FACTUAL}),
        )
        self.assertEqual(ps.collapse_status, "unresolved")
        self.assertEqual(ps.conflict_kind, ConflictKind.EVIDENCE_CONFLICT)
        self.assertIn(ConflictLocus.LOCAL, ps.conflict_footprint)
        self.assertIn(ConflictLocus.FACTUAL, ps.conflict_footprint)

    def test_conflict_footprint_is_frozenset(self) -> None:
        """conflict_footprint is a frozenset."""
        ps = PartialStructure(
            collapse_status="unresolved",
            conflict_kind=ConflictKind.RESOLUTION_INSTABILITY,
            conflict_footprint=frozenset({ConflictLocus.LOCAL}),
        )
        self.assertIsInstance(ps.conflict_footprint, frozenset)

    def test_all_conflict_kinds_constructible(self) -> None:
        """All ConflictKind values can be used in a PartialStructure."""
        for kind in ConflictKind:
            with self.subTest(kind=kind):
                ps = PartialStructure(
                    collapse_status="unresolved",
                    conflict_kind=kind,
                    conflict_footprint=frozenset({ConflictLocus.LOCAL}),
                )
                self.assertEqual(ps.conflict_kind, kind)

    def test_all_conflict_loci_constructible(self) -> None:
        """All ConflictLocus values can appear in conflict_footprint."""
        ps = PartialStructure(
            collapse_status="unresolved",
            conflict_kind=ConflictKind.EVIDENCE_CONFLICT,
            conflict_footprint=frozenset(ConflictLocus),
        )
        for locus in ConflictLocus:
            self.assertIn(locus, ps.conflict_footprint)


if __name__ == "__main__":
    unittest.main()

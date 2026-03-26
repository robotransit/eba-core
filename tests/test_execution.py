# tests/test_execution.py
"""Tests for execute_task() and _safe_eval()."""

from __future__ import annotations

import unittest

from eck.execution import execute_task


def dummy_llm(prompt: str) -> str:
    """Dummy LLM returning messy whitespace to test normalization."""
    return "  LLM   response  with \n extra   spaces  "


class TestExecuteTask(unittest.TestCase):
    """execute_task() — LLM path and tool path."""

    def test_without_tools_calls_llm(self) -> None:
        outcome = execute_task("some task", dummy_llm, use_tools=False)
        self.assertEqual(outcome, "LLM response with extra spaces")

    def test_with_tools_falls_back_to_llm(self) -> None:
        outcome = execute_task("Just a normal task", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "LLM response with extra spaces")

    def test_calculator_success(self) -> None:
        outcome = execute_task("CALC: 2 + 3", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation result: 5")

    def test_calculator_case_insensitive(self) -> None:
        outcome = execute_task("calc: 2 + 3", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation result: 5")

    def test_calculator_leading_trailing_spaces(self) -> None:
        outcome = execute_task("  CALC: 2 + 3  ", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation result: 5")

    def test_calculator_power_operator(self) -> None:
        outcome = execute_task("CALC: 2 ** 3", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation result: 8")

    def test_calculator_disallowed_operator_fails(self) -> None:
        """// is ast.FloorDiv which is not in _ALLOWED_OPERATORS — hits line 31."""
        outcome = execute_task("CALC: 2 // 3", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation failed (invalid expression)")

    def test_calculator_div_zero_fails(self) -> None:
        outcome = execute_task("CALC: 1 / 0", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation failed (invalid expression)")

    def test_calculator_unary_operator_fails(self) -> None:
        """Unary operator produces UnaryOp node — hits the unsupported node path (line 31)."""
        outcome = execute_task("CALC: -1", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation failed (invalid expression)")

    def test_calculator_string_expression_fails(self) -> None:
        """String expression produces Name node — hits the unsupported node path (line 31)."""
        outcome = execute_task("CALC: abc", dummy_llm, use_tools=True)
        self.assertEqual(outcome, "Calculation failed (invalid expression)")


if __name__ == "__main__":
    unittest.main()

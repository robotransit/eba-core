# tests/test_prompts.py
"""Tests for prompt templates and formatting utilities (ADR-033)."""

from __future__ import annotations

import unittest

from eck.prompts import (
    INITIAL_TASK_PROMPT_TEMPLATE,
    PREDICTION_PROMPT_TEMPLATE,
    SUBTASK_GENERATION_PROMPT,
    format_prompt,
)


class TestFormatPrompt(unittest.TestCase):
    """format_prompt utility."""

    def test_substitutes_placeholders_correctly(self) -> None:
        """format_prompt replaces all placeholders correctly."""
        template = "Hello {name}, your age is {age}."
        result = format_prompt(template, name="Alice", age=30)
        self.assertEqual(result, "Hello Alice, your age is 30.")

    def test_no_remaining_braces_after_substitution(self) -> None:
        """No unsubstituted placeholders remain after format_prompt."""
        result = format_prompt(
            INITIAL_TASK_PROMPT_TEMPLATE,
            objective="test objective",
        )
        self.assertNotIn("{objective}", result)


class TestInitialTaskPrompt(unittest.TestCase):
    """INITIAL_TASK_PROMPT_TEMPLATE contract."""

    def test_contains_objective_placeholder(self) -> None:
        """Template references {objective}."""
        self.assertIn("{objective}", INITIAL_TASK_PROMPT_TEMPLATE)

    def test_formatted_contains_objective(self) -> None:
        """Formatted prompt contains the objective text."""
        result = format_prompt(
            INITIAL_TASK_PROMPT_TEMPLATE,
            objective="world peace",
        )
        self.assertIn("world peace", result)

    def test_requests_single_task_output(self) -> None:
        """Template asks for a single task string only."""
        self.assertIn("only", INITIAL_TASK_PROMPT_TEMPLATE.lower())


class TestSubtaskGenerationPrompt(unittest.TestCase):
    """SUBTASK_GENERATION_PROMPT contract."""

    def test_contains_json_array_instruction(self) -> None:
        """Template instructs LLM to return a valid JSON array."""
        self.assertIn("Return ONLY a valid JSON array", SUBTASK_GENERATION_PROMPT)

    def test_contains_objective_and_task_placeholders(self) -> None:
        """Template references {objective} and {current_task}."""
        self.assertIn("{objective}", SUBTASK_GENERATION_PROMPT)
        self.assertIn("{current_task}", SUBTASK_GENERATION_PROMPT)


class TestPredictionPrompt(unittest.TestCase):
    """PREDICTION_PROMPT_TEMPLATE contract."""

    def test_contains_brief_string_instruction(self) -> None:
        """Template instructs LLM to return a brief string prediction."""
        self.assertIn("Return ONLY a brief string prediction", PREDICTION_PROMPT_TEMPLATE)

    def test_contains_required_placeholders(self) -> None:
        """Template references {memory_context}, {objective}, {task_text}."""
        self.assertIn("{memory_context}", PREDICTION_PROMPT_TEMPLATE)
        self.assertIn("{objective}", PREDICTION_PROMPT_TEMPLATE)
        self.assertIn("{task_text}", PREDICTION_PROMPT_TEMPLATE)

    def test_empty_memory_context_no_leading_blank_line(self) -> None:
        """Empty memory_context produces no leading blank line in formatted prompt."""
        result = format_prompt(
            PREDICTION_PROMPT_TEMPLATE,
            memory_context="",
            objective="test",
            task_text="do something",
        )
        self.assertFalse(result.startswith("\n"))

    def test_adr_033_goal_achieved_prompt_absent(self) -> None:
        """GOAL_ACHIEVED_PROMPT must not exist in eck.prompts (ADR-033)."""
        import eck.prompts as prompts_module
        self.assertFalse(
            hasattr(prompts_module, "GOAL_ACHIEVED_PROMPT"),
            "GOAL_ACHIEVED_PROMPT must not exist — removed per ADR-033",
        )

    def test_adr_033_critic_evaluation_prompt_absent(self) -> None:
        """CRITIC_EVALUATION_PROMPT must not exist in eck.prompts (ADR-033)."""
        import eck.prompts as prompts_module
        self.assertFalse(
            hasattr(prompts_module, "CRITIC_EVALUATION_PROMPT"),
            "CRITIC_EVALUATION_PROMPT must not exist — superseded by critic.py",
        )

    def test_adr_033_prioritization_prompt_absent(self) -> None:
        """PRIORITIZATION_PROMPT must not exist in eck.prompts (ADR-033)."""
        import eck.prompts as prompts_module
        self.assertFalse(
            hasattr(prompts_module, "PRIORITIZATION_PROMPT"),
            "PRIORITIZATION_PROMPT must not exist — removed per ADR-033",
        )


if __name__ == "__main__":
    unittest.main()

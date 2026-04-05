# eck/prompts.py
"""
Prompt templates and formatting utilities for ECK LLM calls.

All prompts are defined as constants here for easy maintenance and testing.

ADR-033 compliance (removed prompts):
  - GOAL_ACHIEVED_PROMPT: removed — lifecycle decisions must not be
    delegated to unconstrained LLM output (ADR-033). Replacement
    deterministic predicate defined in ADR-041.
  - PRIORITIZATION_PROMPT: removed — queue ordering must remain
    deterministic and prompt-independent (ADR-033).
  - CRITIC_EVALUATION_PROMPT: removed — superseded by _build_prompt()
    in critic.py which uses the ADR-022 compliant outcome/severity schema.
"""

from typing import Any

INITIAL_TASK_PROMPT_TEMPLATE = """
Generate the very first concrete task to start pursuing the objective: {objective}

Return a concise, actionable task string only.
"""

SUBTASK_GENERATION_PROMPT = """
You are an autonomous agent working toward the objective: "{objective}"

Given the completed task: "{current_task}"

Generate 0-5 concise subtasks that directly advance the objective.
If no further subtasks are needed (goal achieved or task complete), return an empty list.
Stay strictly on-topic; subtasks must align with the objective.

Return ONLY a valid JSON array of strings, e.g.:
["Subtask 1", "Subtask 2"]
or
[]
"""

# memory_context may be empty; it is informational only (ADR-028).
# When empty the prompt collapses cleanly with no leading blank line.
PREDICTION_PROMPT_TEMPLATE = """{memory_context}Predict the expected outcome for this task toward the objective '{objective}'.

Task: {task_text}

Return ONLY a brief string prediction of the result.
"""


def format_prompt(template: str, **kwargs: Any) -> str:
    """Format a prompt template with variables."""
    return template.format(**kwargs)

# NOTE:
# memory_context is opaque, human-readable text.
# Prediction must not interpret, parse, or branch on its contents.
# All semantic interpretation belongs to policy layers only.

from typing import Callable, Any

from .prompts import format_prompt, PREDICTION_PROMPT_TEMPLATE
from .memory import MemoryRetrieval
from .config import ECKConfig


def build_prediction_context(
    task_text: str,
    objective: str,  # forward seam — may be used by future richer retrieval backends
    memory: MemoryRetrieval,
    config: ECKConfig,
    embedding_model: Any | None = None,
) -> str:
    """
    Build optional memory context for the prediction prompt.

    Delegates entirely to MemoryRetrieval contract (ADR-026–030).
    Returns empty string when disabled or no relevant outcomes found.
    Memory context is opaque text — must not be interpreted here.
    """
    if not config.enable_memory_retrieval:
        return ""

    integration = memory.retrieve(
        user_input=task_text,
        embedding_model=embedding_model,
    )

    if integration is None:
        return ""

    return integration.formatted_block


def generate_prediction(
    task_text: str,
    objective: str,
    llm_call: Callable[[str], str],
    memory: MemoryRetrieval,
    config: ECKConfig,
    embedding_model: Any | None = None,
    max_length: int = 200,
) -> str:
    """
    Generate a concise prediction of the expected task outcome.

    This function is pure: it formats the prompt, calls the LLM, and safely parses the result.
    No side effects, no logging, no state changes.

    Memory context is opaque text. Do not interpret here.
    """
    # Build memory context (empty if disabled or no relevant outcomes)
    memory_context = build_prediction_context(
        task_text, objective, memory, config, embedding_model
    )

    prompt = format_prompt(
        PREDICTION_PROMPT_TEMPLATE,
        memory_context=memory_context,
        objective=objective,
        task_text=task_text,
    )

    raw_prediction = llm_call(prompt).strip()

    # Normalize internal whitespace (collapse multiples, remove newlines/tabs)
    raw_prediction = " ".join(raw_prediction.split())

    # Protect against empty/whitespace-only output
    if not raw_prediction:
        raw_prediction = "(no prediction generated)"

    # Optional length constraint
    if len(raw_prediction) > max_length:
        raw_prediction = raw_prediction[:max_length].rstrip(" .,!?") + "..."

    return raw_prediction

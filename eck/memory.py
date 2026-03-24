# eck/memory.py
"""Memory Retrieval subsystem (ADRs 026–030)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, NamedTuple, Optional, Sequence, Tuple


logger = logging.getLogger("eck-core")


class TaskRecord(NamedTuple):
    """Concrete immutable record for mock WorldModel-backed retrieval (provisional)."""
    task_id: int                  # Unique identifier
    description: str              # User or system description
    created_at: datetime          # Fixed timestamp of creation
    completed: bool = False       # Completion status
    priority: int = 0             # Optional priority (higher = more important)


class RetrievalQuery(NamedTuple):
    """Deterministic query proposal (phase 1)."""
    text: str


class RetrievalExecution(NamedTuple):
    """Immutable retrieved items (phase 3)."""
    items: Tuple[TaskRecord, ...]


class RetrievalIntegration(NamedTuple):
    """Canonical prompt block (phase 4)."""
    formatted_block: str
    item_count: int
    context_length: int


class MemoryRetrieval:
    """Memory Retrieval Contract (ADR-026–030) — provisional v2 (increment 2).

    This increment adds:
    - Provisional concrete TaskRecord schema for mock backend
    - Immutable mock world model with fixed timestamps for determinism
    - Deterministic empty-query handling (returns empty execution)
    - Canonical formatting per locked PR4 contract
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize with retrieval toggle (default disabled)."""
        self._enabled = enabled
        self._logger = logging.getLogger("eck-core")
        self._run_id = 0

        # Immutable mock world model (fixed timestamps for determinism)
        self._mock_world_model: Tuple[TaskRecord, ...] = (
            TaskRecord(task_id=1, description="Complete project report", created_at=datetime(2025, 1, 1, 10, 0), completed=False, priority=5),
            TaskRecord(task_id=2, description="Review code changes", created_at=datetime(2025, 1, 2, 14, 30), completed=True, priority=3),
            TaskRecord(task_id=3, description="Schedule meeting with team", created_at=datetime(2025, 1, 3, 9, 15), completed=False, priority=7),
        )

    def build_retrieval_query(self, user_input: str) -> RetrievalQuery:
        """Phase 1: Deterministic query proposal (always runs)."""
        return RetrievalQuery(text=user_input.strip().lower())

    def retrieval_permitted(self) -> bool:
        """Phase 2: Hard permission gate."""
        return self._enabled

    def _run_retrieval(self, query: RetrievalQuery) -> RetrievalExecution:
        """Phase 3: Retrieve items (internal — only called when permitted).

        Execution is side-effect free and read-only.
        Empty query returns empty execution (explicitly defined).
        Results are sorted newest-first to match the formatter header.
        """
        if not self.retrieval_permitted():
            raise RuntimeError("retrieval_permitted() must be checked before calling _run_retrieval")

        if not query.text:
            return RetrievalExecution(items=())  # explicit empty-query handling

        # Deterministic filtering + explicit sort for "most recent first"
        matched = [
            record for record in self._mock_world_model
            if query.text in record.description.lower()
        ]
        matched.sort(key=lambda r: r.created_at, reverse=True)
        return RetrievalExecution(items=tuple(matched))

    def _format_timestamp(self, dt: datetime) -> str:
        """Strict canonical YYYY-MM-DDTHH:MM:SSZ (second precision, always Z, UTC)."""
        dt = dt.replace(microsecond=0)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def integrate_retrieval(self, execution: Optional[RetrievalExecution]) -> Optional[RetrievalIntegration]:
        """Phase 4: Produce canonical prompt block (or None if disabled/empty).

        Formatting surface (ADR-026) remains unchanged.
        """
        if execution is None or not execution.items:
            return None

        formatted = self.format_memory_context(execution.items)

        return RetrievalIntegration(
            formatted_block=formatted,
            item_count=len(execution.items),
            context_length=len(formatted),
        )

    def format_memory_context(self, records: Sequence[TaskRecord]) -> str:
        """
        Canonical deterministic formatting per locked PR4 contract.

        - Empty sequence → ""
        - Fixed sentinels + single-line fields
        - Preserves input order exactly
        - No trailing newline after footer
        """
        if not records:
            return ""

        lines: list[str] = [
            "=== BEGIN MEMORY CONTEXT ===",
            "Order: most recent first",
            "",
        ]

        for i, rec in enumerate(records, start=1):
            task_id = str(rec.task_id).strip().replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
            description = rec.description.strip().replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
            outcome = ("Completed" if rec.completed else "Pending").strip()
            timestamp_str = self._format_timestamp(rec.created_at)

            lines.extend([
                f"Record {i}",
                f"Task ID: {task_id}",
                f"Timestamp: {timestamp_str}",
                f"Summary: {description}",
                f"Outcome: {outcome}",
                "",  # separator
            ])

        # Remove trailing blank line before footer
        if lines[-1] == "":
            lines.pop()

        lines.append("=== END MEMORY CONTEXT ===")

        return "\n".join(lines)

    def log_observability(self, enabled: bool, item_count: int, context_length: int) -> None:
        """Phase 5: Exactly one structured metadata log entry per enabled attempt."""
        self._run_id += 1
        self._logger.info("memory.retrieval", extra={
            "run_id": self._run_id,
            "enabled": enabled,
            "item_count": item_count,
            "context_length": context_length,
            "event_type": "retrieval_attempt"
        })

    def retrieve(self, user_input: str, embedding_model: Any | None = None) -> Optional[RetrievalIntegration]:
        """Public entrypoint: full five-phase contract in one call.

        If disabled: zero retrieval activity (no log, no execution, None integration).
        If enabled: execution (possibly empty), integration, one deterministic log entry.

        embedding_model is an optional internal advisory hook (passed from ECKAgent when available).
        It does not affect formatting surface (ADR-026) or disabled/empty retrieval invariants.
        """
        query = self.build_retrieval_query(user_input)

        if not self.retrieval_permitted():
            return None  # zero activity when disabled

        # Enabled path only
        item_count = 0
        context_length = 0
        integration = None
        try:
            # Empty query is always empty, even when embeddings are active
            if not query.text:
                execution = RetrievalExecution(items=())
            else:
                # Get candidate set (broader for optional similarity)
                if embedding_model is not None:
                    candidate_items = list(self._mock_world_model)
                else:
                    execution = self._run_retrieval(query)
                    candidate_items = list(execution.items)

                # Advisory similarity ordering (changes order only)
                if embedding_model is not None:
                    from .similarity import _optional_retrieve_similar
                    ordered_items = _optional_retrieve_similar(candidate_items, query.text, len(candidate_items), embedding_model)
                else:
                    from .similarity import retrieve_similar
                    ordered_items = retrieve_similar(candidate_items, query.text, len(candidate_items))

                execution = RetrievalExecution(items=tuple(ordered_items))

            item_count = len(execution.items)
            integration = self.integrate_retrieval(execution)
            context_length = integration.context_length if integration else 0
        finally:
            self.log_observability(
                enabled=True,
                item_count=item_count,
                context_length=context_length
            )

        return integration

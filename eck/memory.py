from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple, Optional, Tuple


class TaskRecord(NamedTuple):
    """Immutable record from the append-only WorldModel (placeholder)."""
    pass  # Fields TBD in later PRs


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
    """Memory Retrieval Contract (ADR-026–030) — provisional v1.

    Implements the five-phase decomposition with strict invariants:
    - Prompt equivalence: disabled/empty → identical prompt bytes
    - Atomic fallback: disabled → no execution, no backend access
    - Advisory-only: retrieval output never directly alters behavior
    - No phase leakage: each phase is semantically isolated
    - Metadata-only logging: no TaskRecord content ever logged
    - Deterministic proposal and integration: identical inputs yield identical outputs
    - Exactly one log entry per attempt, even on error paths
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize with retrieval toggle (default disabled)."""
        self._enabled = enabled
        self._logger = logging.getLogger("eck-core")
        self._run_id = 0

    def build_retrieval_query(self, user_input: str) -> RetrievalQuery:
        """Phase 1: Deterministic query proposal (always runs).

        Identical user_input must produce identical RetrievalQuery.text.
        """
        # Placeholder — real implementation must be deterministic
        return RetrievalQuery(text=user_input)

    def retrieval_permitted(self) -> bool:
        """Phase 2: Hard permission gate."""
        return self._enabled

    def _run_retrieval(self, query: RetrievalQuery) -> RetrievalExecution:
        """Phase 3: Retrieve items (internal — only called when permitted).

        Execution must be side-effect free and must not mutate any persistent state.
        """
        # Real backend access would go here (e.g., vector search, index)
        # For now: return empty or mock data
        return RetrievalExecution(items=())  # placeholder

    def integrate_retrieval(self, execution: Optional[RetrievalExecution]) -> Optional[RetrievalIntegration]:
        """Phase 4: Produce canonical prompt block (or None if disabled/empty).

        Integration must be deterministic: identical RetrievalExecution inputs must produce identical RetrievalIntegration outputs.
        When None is returned or execution is empty, no memory section or placeholder may be inserted into the prompt.
        """
        if execution is None or not execution.items:
            return None

        # Real canonical formatting would go here (deterministic)
        # Placeholder implementation is deferred — raise until locked format is defined
        raise NotImplementedError("Canonical non-empty retrieval integration format not yet implemented.")

    def log_observability(self, enabled: bool, item_count: int, context_length: int) -> None:
        """Phase 5: Exactly one structured metadata log entry per attempt.

        An “attempt” corresponds to a single invocation of the retrieval pipeline per agent cycle.
        A stable identifier field (run_id) is always present.
        """
        self._run_id += 1
        self._logger.info("memory.retrieval", extra={
            "run_id": self._run_id,
            "timestamp": datetime.now().isoformat(),
            "enabled": enabled,
            "item_count": item_count,
            "context_length": context_length,
            "event_type": "retrieval_attempt"
        })

    def retrieve(self, user_input: str) -> Optional[RetrievalIntegration]:
        """Public entrypoint: full five-phase contract in one call.

        Proposal always occurs.
        Permission check decides execution.
        If disabled: no execution, None integration, one log entry.
        If enabled: execution (possibly empty), integration, one log entry.
        Logging occurs exactly once per attempt, even if execution or integration raises.
        """
        query = self.build_retrieval_query(user_input)

        if not self.retrieval_permitted():
            self.log_observability(enabled=False, item_count=0, context_length=0)
            return None

        # Enabled path — logging must occur exactly once per attempt
        item_count = 0
        context_length = 0
        integration = None
        try:
            execution = self._run_retrieval(query)
            item_count = len(execution.items) if execution else 0
            integration = self.integrate_retrieval(execution)
            context_length = integration.context_length if integration else 0
        finally:
            # Logging belongs in finally to preserve the exactly-once observability invariant
            # for both success and failure paths on enabled retrieval attempts
            self.log_observability(
                enabled=True,
                item_count=item_count,
                context_length=context_length
            )

        return integration

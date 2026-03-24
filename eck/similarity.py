# eck/similarity.py
"""Similarity Retrieval subsystem (ADRs 031–032)."""

from __future__ import annotations

from typing import List, Optional, Tuple, Any

from eck.memory import TaskRecord


def retrieve_similar(
    tasks: List[TaskRecord],
    query_embedding: Optional[Any],
    limit: int,
) -> List[TaskRecord]:
    """
    Retrieve top similar TaskRecords using deterministic core heuristic (ADR-031).

    Core path ignores query_embedding (fallback behavior).
    Order is newest-first (reverse-chronological by created_at).
    Advisory-only: pure output, no side-effects.
    """
    return _core_retrieve_similar(tasks, limit)


def retrieve_scored(
    tasks: List[TaskRecord],
    query_embedding: Optional[Any],
    limit: int,
) -> List[Tuple[TaskRecord, float]]:
    """
    Retrieve top similar TaskRecords with heuristic scores (ADR-031 core path).

    Core path ignores query_embedding.
    Scores are deterministic normalized values (1.0 for top, decreasing).
    Ties resolved reverse-chronologically.
    Advisory-only.
    """
    return _core_retrieve_scored(tasks, limit)


# ── Core stdlib-only implementation (always used in fallback) ────────────────────────────────

def _core_retrieve_similar(
    tasks: List[TaskRecord],
    limit: int,
) -> List[TaskRecord]:
    """Core deterministic reverse-chronological retrieval (ignores embeddings)."""
    if limit <= 0:
        return []

    sorted_tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)
    return sorted_tasks[:limit]


def _core_retrieve_scored(
    tasks: List[TaskRecord],
    limit: int,
) -> List[Tuple[TaskRecord, float]]:
    """Core deterministic reverse-chronological scoring (ignores embeddings)."""
    if limit <= 0:
        return []

    sorted_tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)
    result: List[Tuple[TaskRecord, float]] = []

    for i, task in enumerate(sorted_tasks[:limit]):
        # Deterministic normalized pseudo-score (1.0 for most recent, decreasing)
        score = 1.0 - (i / max(limit, 1))
        result.append((task, score))

    return result


# ── Optional cosine path (to be wired from ECKAgent) ───────────────────────────────────────

def _optional_retrieve_similar(
    tasks: List[TaskRecord],
    query_embedding: Optional[Any],
    limit: int,
    embedding_model: Any | None,
) -> List[TaskRecord]:
    """
    Private optional path: cosine similarity when model is available.
    Falls back silently to core path if no model.
    Equal-score ties resolved reverse-chronologically.
    """
    if embedding_model is None or query_embedding is None:
        return _core_retrieve_similar(tasks, limit)

    # TODO: Implement cosine similarity using embedding_model
    # For now: silent fallback to core
    return _core_retrieve_similar(tasks, limit)


def _optional_retrieve_scored(
    tasks: List[TaskRecord],
    query_embedding: Optional[Any],
    limit: int,
    embedding_model: Any | None,
) -> List[Tuple[TaskRecord, float]]:
    """
    Private optional path: cosine scoring when model is available.
    Falls back silently to core path if no model.
    """
    if embedding_model is None or query_embedding is None:
        return _core_retrieve_scored(tasks, limit)

    # TODO: Implement cosine scoring using embedding_model
    # For now: silent fallback to core
    return _core_retrieve_scored(tasks, limit)

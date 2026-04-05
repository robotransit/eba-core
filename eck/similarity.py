# eck/similarity.py
"""Similarity Retrieval subsystem (ADRs 031–032)."""

from __future__ import annotations

from typing import List, Optional, Tuple, Any, Sequence

from eck.memory import TaskRecord


# Lazy numpy import (only when optional path is used)
_np: Any | None = None
_np_failed: bool = False


def _get_np() -> Any | None:  # pragma: no cover
    """
    Lazy import of numpy with explicit failure sentinel.

    Returns the cached numpy module, or None if numpy is unavailable or
    a prior import attempt failed.
    """
    global _np, _np_failed

    if _np_failed:
        return None

    if _np is None:
        try:
            import numpy as np  # type: ignore[import-not-found]
            _np = np
        except Exception:
            _np_failed = True
            return None

    return _np


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


# ── Core stdlib-only implementation (always used in fallback) ─────────────────

def _core_retrieve_similar(
    tasks: Sequence[TaskRecord],
    limit: int,
) -> List[TaskRecord]:
    """Core deterministic reverse-chronological retrieval (ignores embeddings)."""
    if limit <= 0:
        return []

    sorted_tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)
    return sorted_tasks[:limit]


def _core_retrieve_scored(
    tasks: Sequence[TaskRecord],
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


# ── Private helper for cosine score ──────────────────────────────────────────
# pragma: no cover — requires numpy (optional extras, capability layer only)

def _cosine_score(query_emb, task_emb, np) -> float:  # pragma: no cover
    """Compute cosine similarity with zero-norm guard."""
    norm_q = np.linalg.norm(query_emb)
    norm_t = np.linalg.norm(task_emb)
    if norm_q == 0 or norm_t == 0:
        return 0.0
    return float(np.dot(query_emb, task_emb) / (norm_q * norm_t))


# ── Optional cosine path (wired from ECKAgent) ────────────────────────────────
# These functions require sentence-transformers and numpy (optional extras).
# They are excluded from core CI coverage and tested in the capability layer.

def _optional_retrieve_similar(  # pragma: no cover
    tasks: Sequence[TaskRecord],
    query_embedding: Optional[Any],
    limit: int,
    embedding_model: Any | None,
) -> List[TaskRecord]:
    """
    Optional path: real cosine similarity when model is available.
    Equal-score ties resolved reverse-chronologically.
    Silent atomic fallback to core path on any failure.

    Note:
    In the current integration, query_embedding is treated as query text and
    encoded within this function. Future revisions may pass a precomputed
    embedding instead, but this does not affect current behavior.

    Excluded from core CI coverage — requires optional extras (ADR-032).
    Tested in capability layer.
    """
    if embedding_model is None or query_embedding is None:
        return _core_retrieve_similar(tasks, limit)

    if limit <= 0:
        return []

    # Check optional dependency boundary first
    np = _get_np()
    if np is None:
        return _core_retrieve_similar(tasks, limit)

    try:
        query_text = str(query_embedding)
        query_emb = embedding_model.encode(query_text, convert_to_numpy=True)

        task_texts = [task.description for task in tasks]
        task_embs = embedding_model.encode(task_texts, convert_to_numpy=True)

        # Normalize shapes for robustness (single vector vs batch)
        query_emb = np.asarray(query_emb)
        if query_emb.ndim > 1:
            query_emb = query_emb[0]

        task_embs = np.asarray(task_embs)
        if task_embs.ndim == 1:
            task_embs = task_embs.reshape(1, -1)

        # Explicit cardinality guard: mismatch → silent fallback
        if len(task_embs) != len(tasks):
            return _core_retrieve_similar(tasks, limit)

        scored = []
        for task, task_emb in zip(tasks, task_embs):
            score = _cosine_score(query_emb, task_emb, np)
            # score desc, created_at desc (newer wins on ties), task
            scored.append((score, task.created_at, task))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        ordered = [item[2] for item in scored[:limit]]
        return ordered
    except Exception:
        # Silent atomic fallback
        return _core_retrieve_similar(tasks, limit)


def _optional_retrieve_scored(  # pragma: no cover
    tasks: Sequence[TaskRecord],
    query_embedding: Optional[Any],
    limit: int,
    embedding_model: Any | None,
) -> List[Tuple[TaskRecord, float]]:
    """
    Optional path: real cosine scoring when model is available.
    Silent atomic fallback to core path on any failure.

    Note:
    In the current integration, query_embedding is treated as query text and
    encoded within this function. Future revisions may pass a precomputed
    embedding instead, but this does not affect current behavior.

    Excluded from core CI coverage — requires optional extras (ADR-032).
    Tested in capability layer.
    """
    if embedding_model is None or query_embedding is None:
        return _core_retrieve_scored(tasks, limit)

    if limit <= 0:
        return []

    # Check optional dependency boundary first
    np = _get_np()
    if np is None:
        return _core_retrieve_scored(tasks, limit)

    try:
        query_text = str(query_embedding)
        query_emb = embedding_model.encode(query_text, convert_to_numpy=True)

        task_texts = [task.description for task in tasks]
        task_embs = embedding_model.encode(task_texts, convert_to_numpy=True)

        # Normalize shapes for robustness (single vector vs batch)
        query_emb = np.asarray(query_emb)
        if query_emb.ndim > 1:
            query_emb = query_emb[0]

        task_embs = np.asarray(task_embs)
        if task_embs.ndim == 1:
            task_embs = task_embs.reshape(1, -1)

        # Explicit cardinality guard: mismatch → silent fallback
        if len(task_embs) != len(tasks):
            return _core_retrieve_scored(tasks, limit)

        scored = []
        for task, task_emb in zip(tasks, task_embs):
            score = _cosine_score(query_emb, task_emb, np)
            scored.append((task, score))

        # Sort by score desc, then by created_at desc for ties
        scored.sort(key=lambda x: (x[1], x[0].created_at), reverse=True)
        return scored[:limit]
    except Exception:
        # Silent atomic fallback
        return _core_retrieve_scored(tasks, limit)

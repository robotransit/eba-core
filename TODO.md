# TODO.md for Epistemic Control Kernel (ECK)

Last updated: 2026-02-03  
Current release line: v0.1.1 (stable, invariant-locked)

This file records **intentional future work** for ECK.
Items may be revised, reordered, or dropped during v0.2.x design without implying
regression or defect in any released version.

This file outlines outstanding tasks, placeholders, unfinished features, and
planned enhancements based on a review of the repository state as of  
**ECK v0.1.1 (2026-01-27)**.

All items listed here are **explicitly out of scope for the v0.1.x series** and do
**not** affect the correctness, completeness, or invariants of the currently
tagged releases (v0.1.0, v0.1.1).

The v0.1.x line is considered **behaviorally stable** and **test-complete**.
Future work targets **v0.2.0 and beyond**.

---

## Core Functionality

These items address known placeholders in the codebase and the integration of
existing but currently unused components.

- **High: Implement dynamic rolling confidence signal**  
  In `eck/agent.py`, `self.current_confidence` is currently hardcoded to `0.5`
  with the comment  
  `"Current confidence (placeholder — future: rolling signal)"`.  
  Integrate an Exponentially Weighted Moving Average (EWMA) mechanism as outlined in:
  - `docs/eck-confidence-ewma-sketch.md`
  - `docs/eck-rolling-confidence-semantics.md`
  - `docs/appendix/eck-confidence-failure-asymmetry.md`  
  Update the agent loop to compute and update confidence based on task outcomes,
  drift signals, and feasibility checks.  
  **Safety invariant**: Confidence updates must not directly trigger enforcement
  without explicit policy mediation.  
  Reference asymmetry semantics in
  `docs/appendix/eck-confidence-failure-asymmetry.md`.

- **High: Finalize and test memory-aware prediction context wiring**  
  In `eck/memory.py`, methods such as `retrieve_similar` and `retrieve_scored` are
  implemented and partially wired (memory is passed into
  `build_prediction_context` via `generate_prediction`).  
  Complete controlled activation when `config.enable_memory_retrieval` is `True`,
  add tests for observability, and ensure read-only influence with **no behavioral
  authority**.

- **Medium: Upgrade task similarity computation to embedding-based cosine similarity**  
  In `eck/memory.py`, `get_similar()` (on `WorldModel`) currently uses a basic string
  overlap metric, with the comment:  
  `"Placeholder similarity function (string overlap) — future: use real cosine sim on embeddings."`  
  Replace with an embedding-based cosine similarity approach using:
  - a lightweight embedding library (e.g. `sentence-transformers`) as an optional
    dependency, with a stdlib fallback if unavailable, or
  - a TF-IDF fallback.  
  Update configuration thresholds and preserve backward compatibility.  
  **Safety invariant**: Must remain optional (stdlib fallback or config toggle) to
  preserve the core no-dependency guarantee.

- **Medium: Incorporate unused prompts or remove them**  
  In `eck/prompts.py`, verify actual runtime usage of all defined prompts.
  `PRIORITIZATION_PROMPT` and possibly `GOAL_ACHIEVED_PROMPT` currently lack clear
  integration.  
  Either integrate them (e.g. prioritization after subtask generation) or remove
  them to reduce conceptual and maintenance overhead.

- **Medium: Define concrete formulas and constants for confidence asymmetry**  
  Formalize EWMA parameters, decay rates, failure penalties, enforcement thresholds,
  and persistence semantics, as deferred in  
  `docs/appendix/eck-confidence-failure-asymmetry.md`.  
  Implement in code (e.g. in `drift.py` or a dedicated confidence module) and update
  documentation accordingly.

- **Low: Document task seeding patterns in `README.md` / `examples/*.py`**  
  `ECKAgent.seed()` is already public and functional.  
  Improve documentation clarity in `README.md` and/or `examples/*.py`
  to illustrate recommended seeding patterns.

---

## Testing

Comprehensive deterministic unit and integration tests are in place as of v0.1.1.

Future testing work (v0.2.0+) may include:

- Regression protection for newly introduced features
- Confidence dynamics and rolling signal behaviour
- Performance and scalability characteristics

- **Low: Implement CI workflow**  
  Add a GitHub Actions pipeline (pytest on push/PR, formatting, linting, coverage).
  CI must not introduce behavioral dependencies (e.g. network calls or external APIs).  
  *(No additional deterministic tests are required for v0.1.x; the existing suite
  is complete.)*

---

## Documentation

- **Medium: Add usage guide for policy modes**  
  Expand `docs/eck-policy-modes.md` with examples of dynamic switching (e.g. based
  on drift) and the resulting impacts on execution breadth and confidence.

- **Low: Consolidate confidence documentation**  
  Merge scattered confidence-related files into a single coherent guide,
  cross-referencing asymmetry and EWMA semantics in
  `docs/appendix/eck-confidence-failure-asymmetry.md`.

- **Low: Add CONTRIBUTING.md issue templates**  
  Provide templates for bug reports, feature proposals, and documentation changes.

---

## Miscellaneous / Refinements

- **Low: Add optional dependencies for advanced features**  
  Introduce an `embeddings` extra in `pyproject.toml`
  (e.g. `sentence-transformers`), while keeping the core strictly stdlib-only.

- **Low: Benchmark and optimize queue/performance**  
  Evaluate `TaskQueue` behaviour at large `max_size` values and add performance
  tests if scaling becomes relevant.

---

Contributions are welcome; please see `CONTRIBUTING.md` for invariants, scope,
and contribution guidelines.

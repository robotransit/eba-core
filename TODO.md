# TODO
**Last updated:** 2026-03-26
**Current design baseline:** v0.2.0 (architecture & invariants locked)
**Current implementation state:** v0.2.0 complete

The v0.2.0 design is complete and formally locked through ADR-020–ADR-041.
All architectural decisions, invariants, guardrails, and CI foundations have
been codified and implemented.

**Implementation state:**
The v0.2.0 architecture is fully implemented. All locked invariants have been
converted into code, tested, and verified. 345 tests passing across Python
3.10, 3.11, and 3.12. 98.17% coverage. CI green on all three versions.

See [v0.2.0 implementation checklist](docs/v0.2.0-implementation-checklist.md)
for the full ADR-mapped completion record.

---

## Remaining Housekeeping (v0.2.0)

- Update GitHub Actions workflow actions to Node.js 24 before June 2nd 2026
  forced cutover (actions/checkout, actions/setup-python, actions/cache,
  actions/upload-artifact)

---

## Future Work (v0.3.0 and beyond)

**High priority (post-v0.2.0)**
- Add comprehensive end-to-end examples and usage patterns
- Expand policy mode examples and dynamic switching guidance
- Benchmark TaskQueue and memory retrieval at scale
- Explore optional advanced memory scoring mechanisms (subject to new ADR)
- v0.2.0 audit/observability layer — task lifecycle recording is currently
  absent, deferred to this phase (noted in agent.py)
- PartialStructure collapse_status — currently always "unresolved"; resolution
  tracking deferred to a future ADR
- ADR-038 full wiring — get_recommended_breadth() and should_execute() in
  utils.py are pre-gate utilities pending retirement once PolicyGate is the
  sole execution authority

**Medium / Low priority**
- Add CONTRIBUTING.md, issue templates, and clearer contribution guidelines
- Consider optional performance optimisations (only after v0.2.0 is stable)
- Further formal verification experiments (TLA⁺ / model checking of the kernel)

---

All v0.2.0 work is tracked via the Architecture Decision Records in `docs/adr/`.
Contributions are welcome, but must respect the locked invariants in ADR-020–ADR-041.
See `ARCHITECTURE.md` and `docs/adr/` for the current design baseline.

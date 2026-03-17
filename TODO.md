# TODO

**Last updated:** 2026-03-17

**Current design baseline:** v0.2.0 (architecture & invariants locked)  
**Current implementation state:** pre-v0.2.0

The v0.2.0 design is now complete and formally locked through ADR-020–ADR-037.  
All major architectural decisions, invariants, guardrails, and CI foundations have been codified.

**Important note:**  
None of the v0.2.0 ADRs have been converted into implementation code yet.  
The current codebase remains at the pre-v0.2.0 state. Implementation of the locked v0.2.0 architecture is now the next phase of the project.

This file now records only remaining implementation work for the locked v0.2.0 design and intentional future work beyond v0.2.0. Items from the old v0.1.x TODO list have been retired because they are now covered by the locked ADRs.

---

## Immediate Next Phase (v0.2.0 Implementation)

- Implement the locked v0.2.0 architecture in ADR order, beginning with confidence semantics, then memory retrieval, then similarity/prompt guardrails, then CI  
- Convert all locked invariants into code (confidence, memory retrieval, similarity, prompt guardrails, CI workflows)  
- Maintain strict adherence to the locked red lines and test requirements  
- Update CI to enforce the new two-layer structure (core + capability)

---

## Future Work (v0.3.0 and beyond)

**High priority (post-v0.2.0 implementation)**

- Add comprehensive end-to-end examples and usage patterns  
- Expand policy mode examples and dynamic switching guidance  
- Benchmark TaskQueue and memory retrieval at scale  
- Explore optional advanced memory scoring mechanisms (subject to new ADR)

**Medium / Low priority**

- Add CONTRIBUTING.md issue templates and clearer contribution guidelines  
- Consider optional performance optimisations (only after v0.2.0 is stable)  
- Further formal verification experiments (TLA⁺ / model checking of the kernel)

---

All v0.2.0 design work is now tracked via the Architecture Decision Records in `docs/adr/`.

Contributions are welcome, but must respect the locked invariants in ADR-020–ADR-037.  
See `ARCHITECTURE.md` and `docs/adr/` for the current design baseline.

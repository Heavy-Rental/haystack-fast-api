# Proposal: Phase 2d-iii candidate validation

| Field | Value |
|-------|-------|
| **Status** | Archived / as-built |
| **Date** | 2026-08-13 |
| **Capability** | `dynamic-pricing` |
| **Phase** | 2d-iii |
| **Tasks** | [`tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD |

## Why

Phase 2d-ii produced `model_v2.pkl` and `current_v2.json` without changing the
serving artifacts. Before any separately reviewed Phase 2e promotion, the
candidate needs a repeatable, read-only comparison against the current model
using the same 27 live assets, the same feature rows, and the same accuracy
holdout.

The existing plan says “materially lower” clamp rate and “no material” accuracy
regression but does not make those terms executable. This change defines the
gate before implementing the validation script.

## Scope

- Add `ml-experiments/candidate_validation_check.py`.
- Load current and candidate artifacts directly; do not call the serving
  loader or `reload_model()`.
- Compare all live assets at 1/7/14/30 days with identical model inputs.
- Compare both models on the same deterministic v2 holdout.
- Print results and save the ignored comparison chart under
  `ml-experiments/outputs/phase2d/`.
- Add unit tests for row construction, clamp accounting, accuracy comparison,
  artifact compatibility, and the promotion gate.

## Out of scope

- Renaming, copying, or overwriting `model.pkl` / `current.json`.
- Calling `reload_model()` or changing any runtime route.
- Phase 2e promotion.
- Database writes or seed-data changes.

## Gap audit result

The completion audit restored the Phase 2d-ii calibration constants that were used to create the candidate but were absent from the tracked scratch table. A fresh seed-42 generation now byte-matches the ignored v2 CSV (`sha256=3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05`). The formal gate now locks its artifact/data identities and non-asset inputs and chart path, validates candidate-data provenance, rejects invalid guardrails, and provides the exact regeneration command. The measured gate result and serving artifacts remain unchanged.

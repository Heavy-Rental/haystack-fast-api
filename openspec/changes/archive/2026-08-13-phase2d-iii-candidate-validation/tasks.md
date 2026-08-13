# Tasks: Phase 2d-iii candidate validation

## Spec and test first

- [x] Define the read-only comparison and executable Phase 2e gate.
- [x] Add unit tests for validation rows, clamp summaries, common-holdout
  accuracy, artifact compatibility, and gate outcomes.

## Implementation

- [x] Add `ml-experiments/candidate_validation_check.py`.
- [x] Generate the ignored comparison chart and capture the live 27-asset
  results.
- [x] Verify serving artifacts are unchanged.

## Converge

- [x] Run targeted tests, Ruff, and the full default pytest suite.
- [x] Update dynamic-pricing docs/spec/design with the measured result.
- [x] Record whether Phase 2e is unblocked; do not perform Phase 2e.

## Gap audit

- [x] Restore the approved Phase 2d-ii constants in tracked `pricing_tables.py` and prove deterministic CSV byte equivalence.
- [x] Lock formal artifact/data identities and non-asset inputs and chart path and remove gate-tuning CLI overrides.
- [x] Validate candidate-data SHA-256, row counts, and metadata metrics.
- [x] Add missing-data guidance and invalid-guardrail coverage; expand the focused suite to 8 tests.

## Explicit non-goals

- [ ] Promote `model_v2.pkl` / `current_v2.json`.
- [ ] Reload or restart the serving model.
- [ ] Write to the Spring-owned database.

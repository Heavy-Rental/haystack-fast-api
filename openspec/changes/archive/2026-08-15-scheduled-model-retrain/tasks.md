# Tasks: Scheduled monthly retrain with validated promotion

One phase = one PR. See `docs/dynamic-pricing-scheduled-retrain-plan.md` for
the full Jira subtask table and branch names.

## Phase 3a — foundations: validation gate + real-data quality probe

- [x] Extract `app/services/pricing/promotion_gate.py` from
      `ml-experiments/candidate_validation_check.py`'s pure functions
      (`build_validation_rows`, `evaluate_model`, `summarize_predictions`,
      `evaluate_common_holdout`, `assess_gate`, `validate_artifact_contract`,
      `validate_model_features`, `load_live_assets`)
- [x] Refactor `candidate_validation_check.py` to import from
      `promotion_gate.py`; keep only script-specific pieces
      (`EXPECTED_CANDIDATE_DATA_SHA256`/`validate_candidate_data_provenance`,
      `render_chart`, `_print_results`, `main()`)
- [x] Generalize `assess_gate` with `expected_asset_count: int | None = None`
      / `min_asset_count: int = 1`; preserve `candidate_validation_check.py`'s
      exact-match behavior via `expected_asset_count=EXPECTED_ASSET_COUNT`
- [x] Regression: `tests/test_candidate_validation_check.py` passes unmodified
- [x] New `ml-experiments/real_training_data_check.py`: live-query
      `booking_items`/`bookings`/`assets`/`asset_categories`, report
      null/zero-rate of `daily_rate`/`subtotal` per status and per category
- [x] Run the probe against the live seeded DB; record the result (gates 3b)

Evidence (2026-08-18): `primary_snapshot` PASS — 98 booking-item rows measured,
76 realized-status rows, zero null/zero/negative `daily_rate` or `subtotal`
values across all rows, and positive realized signal in all four ML categories.
Focused Ruff passed; focused pytest passed 15/15, including the original
`test_candidate_validation_check.py` unchanged. Full pytest regression passed
427 tests with 5 optional tests skipped.

## Phase 3b — real-data extraction + blend/cutover

- [x] Add `daily_rate`/`subtotal` to `app/models/booking_item.py`
- [x] Add `created_at`/`total_amount` to `app/models/booking.py`
- [x] `repository.py::fetch_real_training_rows(db, resolution, *, statuses=REALIZED_PRICE_STATUSES) -> pd.DataFrame`
- [x] TDD: `tests/test_pricing_real_training_rows.py` (status filter, null/zero
      `daily_rate` dropped, category mapping, `lead_time_days` incl.
      `created_at is null` fallback, real DB-shaped compiled-SQL assertion)
- [x] New `app/services/pricing/blend.py::build_training_dataset()`
      (per-category cutover + sample weighting)
- [x] TDD: `tests/test_pricing_blend.py` (cutover, blend, weight array, empty
      real-rows degrades to pure-synthetic)
- [x] Extend `train.py::train()` with optional `data`/`sample_weight` params
      (backward-compatible, existing callers unaffected)

## Phase 3c — retrain job orchestration

- [x] New `app/services/pricing/retrain_job.py::run_scheduled_retrain()`:
      blend → train candidate → gate via `promotion_gate` → promote/rollback
- [x] `retrain_state.json` persistence (`load_state()`/`save_state()`)
- [x] TDD: `tests/test_pricing_retrain_job.py` (gate-pass promotion, gate-fail
      no-op, `train()`/blend exception handled, live-read failure handled,
      promotion-failure rollback, state round-trip)

Evidence (2026-08-19): 6 new Phase 3c tests passed; the cross-phase 3a–3c
focused suite passed 29/29. Full pytest regression passed 445 tests with 5
optional tests skipped; focused Ruff and `git diff --check` passed. All tests
redirected runtime candidate/backup/state paths to temporary directories, so
no serving artifact or database row changed.

## Phase 3d — scheduler, app wiring, docs & regression

- [x] Add `apscheduler>=3.10.4,<4` to `pyproject.toml`
- [x] New `PRICING_RETRAIN_*` settings in `app/config.py`
      (`PRICING_RETRAIN_ENABLED` default `False`, `_INTERVAL_DAYS` default 30,
      `_MISFIRE_GRACE_SECONDS`, `_MIN_REAL_ROWS_PER_CATEGORY`,
      `_REAL_SAMPLE_WEIGHT`; cutover/weight defaults adjusted to 125/10 on 2026-08-19)
- [x] New `app/services/pricing/scheduler.py`
      (`compute_next_run_time()`, `build_scheduler()`, `AsyncIOScheduler`,
      job wrapped in `asyncio.to_thread(...)`)
- [x] Additive `lifespan` block in `app/main.py` (start/stop scheduler when
      enabled, mirrors existing `decomposer` pattern)
- [x] `.gitignore` additions: `retrain_state.json`, `model_candidate.pkl`,
      `current_candidate.json`, `model_previous.pkl`, `current_previous.json`
- [x] TDD: `tests/test_pricing_scheduler.py` (`compute_next_run_time`'s three
      branches, job registration, `PRICING_RETRAIN_ENABLED` unset leaves
      `lifespan` unaffected)
- [x] Full regression: `uv run pytest tests/` + `ruff check .`
- [x] Route-inventory check: confirm no HTTP route for retrain exists
      anywhere (`app.openapi()["paths"]`)
- [x] This proposal/tasks pair finalized; `docs/dynamic-pricing-scheduled-retrain-plan.md` finalized

Evidence (2026-08-19): 6 new scheduler tests passed; the Phase 3a–3d focused
suite passed 38/38; the full suite passed 451 tests with 5 optional skips.
Ruff and `git diff --check` passed. OpenAPI inventory found 5 application
paths and zero retrain routes. Automated verification did not run a live
retrain, so no serving artifact or database row changed.

## Explicit non-goals (this change)

- [ ] Manual "retrain now" HTTP endpoint — permanently scrapped
- [ ] Real geocoding for `distance_km`
- [x] Phase 2e (Phase 2d candidate promotion) — completed separately 2026-08-17
- [ ] Multi-generation rollback history beyond one rolling backup
- [x] Merging the finished requirement into live `spec.md`/`design.md`
      (Phase 3e, 2026-08-27; ADR-0005)

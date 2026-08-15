# Tasks: Scheduled monthly retrain with validated promotion

One phase = one PR. See `docs/dynamic-pricing-scheduled-retrain-plan.md` for
the full Jira subtask table and branch names.

## Phase 3a — foundations: validation gate + real-data quality probe

- [ ] Extract `app/services/pricing/promotion_gate.py` from
      `ml-experiments/candidate_validation_check.py`'s pure functions
      (`build_validation_rows`, `evaluate_model`, `summarize_predictions`,
      `evaluate_common_holdout`, `assess_gate`, `validate_artifact_contract`,
      `validate_model_features`, `load_live_assets`)
- [ ] Refactor `candidate_validation_check.py` to import from
      `promotion_gate.py`; keep only script-specific pieces
      (`EXPECTED_CANDIDATE_DATA_SHA256`/`validate_candidate_data_provenance`,
      `render_chart`, `_print_results`, `main()`)
- [ ] Generalize `assess_gate` with `expected_asset_count: int | None = None`
      / `min_asset_count: int = 1`; preserve `candidate_validation_check.py`'s
      exact-match behavior via `expected_asset_count=EXPECTED_ASSET_COUNT`
- [ ] Regression: `tests/test_candidate_validation_check.py` passes unmodified
- [ ] New `ml-experiments/real_training_data_check.py`: live-query
      `booking_items`/`bookings`/`assets`/`asset_categories`, report
      null/zero-rate of `daily_rate`/`subtotal` per status and per category
- [ ] Run the probe against the live seeded DB; record the result (gates 3b)

## Phase 3b — real-data extraction + blend/cutover

- [ ] Add `daily_rate`/`subtotal` to `app/models/booking_item.py`
- [ ] Add `created_at`/`total_amount` to `app/models/booking.py`
- [ ] `repository.py::fetch_real_training_rows(db, resolution, *, statuses=REALIZED_PRICE_STATUSES) -> pd.DataFrame`
- [ ] TDD: `tests/test_pricing_real_training_rows.py` (status filter, null/zero
      `daily_rate` dropped, category mapping, `lead_time_days` incl.
      `created_at is null` fallback, real DB-shaped compiled-SQL assertion)
- [ ] New `app/services/pricing/blend.py::build_training_dataset()`
      (per-category cutover + sample weighting)
- [ ] TDD: `tests/test_pricing_blend.py` (cutover, blend, weight array, empty
      real-rows degrades to pure-synthetic)
- [ ] Extend `train.py::train()` with optional `data`/`sample_weight` params
      (backward-compatible, existing callers unaffected)

## Phase 3c — retrain job orchestration

- [ ] New `app/services/pricing/retrain_job.py::run_scheduled_retrain()`:
      blend → train candidate → gate via `promotion_gate` → promote/rollback
- [ ] `retrain_state.json` persistence (`load_state()`/`save_state()`)
- [ ] TDD: `tests/test_pricing_retrain_job.py` (gate-pass promotion, gate-fail
      no-op, `train()`/blend exception handled, live-read failure handled,
      promotion-failure rollback, state round-trip)

## Phase 3d — scheduler, app wiring, docs & regression

- [ ] Add `apscheduler>=3.10.4,<4` to `pyproject.toml`
- [ ] New `PRICING_RETRAIN_*` settings in `app/config.py`
      (`PRICING_RETRAIN_ENABLED` default `False`, `_INTERVAL_DAYS` default 30,
      `_MISFIRE_GRACE_SECONDS`, `_MIN_REAL_ROWS_PER_CATEGORY`,
      `_REAL_SAMPLE_WEIGHT`)
- [ ] New `app/services/pricing/scheduler.py`
      (`compute_next_run_time()`, `build_scheduler()`, `AsyncIOScheduler`,
      job wrapped in `asyncio.to_thread(...)`)
- [ ] Additive `lifespan` block in `app/main.py` (start/stop scheduler when
      enabled, mirrors existing `decomposer` pattern)
- [ ] `.gitignore` additions: `retrain_state.json`, `model_candidate.pkl`,
      `current_candidate.json`, `model_previous.pkl`, `current_previous.json`
- [ ] TDD: `tests/test_pricing_scheduler.py` (`compute_next_run_time`'s three
      branches, job registration, `PRICING_RETRAIN_ENABLED` unset leaves
      `lifespan` unaffected)
- [ ] Full regression: `uv run pytest tests/` + `ruff check .`
- [ ] Route-inventory check: confirm no HTTP route for retrain exists
      anywhere (`app.openapi()["paths"]`)
- [ ] This proposal/tasks pair finalized; `docs/dynamic-pricing-scheduled-retrain-plan.md` finalized

## Explicit non-goals (this change)

- [ ] Manual "retrain now" HTTP endpoint — permanently scrapped
- [ ] Real geocoding for `distance_km`
- [ ] Phase 2e (Phase 2d candidate promotion) — separate, in flight
- [ ] Multi-generation rollback history beyond one rolling backup
- [ ] Merging the finished requirement into live `spec.md`/`design.md`
      (separate, later archival change)

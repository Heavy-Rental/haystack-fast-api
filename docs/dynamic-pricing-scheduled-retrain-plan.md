# Dynamic Pricing — Scheduled Retrain Execution Plan (Phase 3)

> **This file tracks tasks and schedule only**, scoped to the scheduled-retrain
> feature. Decisions and rationale live in
> `openspec/changes/2026-08-15-scheduled-model-retrain/proposal.md` — don't
> duplicate reasoning here; link back to that instead.
>
> **Runs in parallel with the existing `dynamic-pricing-execution-plan.md`**
> (Phase 2e promotion completed 2026-08-17; its artifact swap remains separate from this Phase 3 plan). This file and that one touch a disjoint set of files: this feature
> only adds new modules plus additive changes to `app/config.py`/
> `app/main.py`/`pyproject.toml`/`.gitignore`. No merge risk between the two
> efforts. `openspec/specs/dynamic-pricing/{spec.md,design.md}` (the live,
> authoritative specs) are touched only once, at the very end (Phase 3e,
> below), not mid-flight.

Last updated: 2026-08-17

Naming: this feature claims the "**Phase 3**" name `openspec/specs/dynamic-pricing/spec.md`'s
own Status field already reserves for "real-data blend + scheduled retrain" —
the 2026-08-12 change log on the other execution plan explicitly notes Phase 3
was *deliberately not reused* for Phase 2d's calibration work, i.e. it was
sitting there unclaimed for exactly this.

---

## What this replaces

`openspec/specs/dynamic-pricing/spec.md`'s "Requirement: Manual retrain path
(US-2)" spec'd a "retrain now" HTTP endpoint as a demo safety net. It was
descoped repeatedly (moved out of Phase 2b, then to subtask 5 / demo prep) and
**never actually built** — `app/services/pricing/train.py`'s `train()`/
`retrain()` exist and work in-process, but nothing has ever called them except
by hand.

**Decision: scrap the manual endpoint entirely.** The scheduler built here is
the sole retrain trigger, monthly. No HTTP route for on-demand retrain exists
or should be added — see the `spec.md`/`design.md` update planned for Phase 3e.

---

## Open items carried into this plan

- [ ] **`distance_km` has no real equivalent anywhere in the schema.**
      `Booking.site_latitude`/`site_longitude` exist but real geocoding is a
      separate, pre-existing open item (noted since Phase 2c on the other
      execution plan). Workaround here: impute real training rows'
      `distance_km` via `ml-experiments/generate_synthetic_data.py::sample_distance_km()`,
      the same distribution synthetic rows already use. Stopgap, not a fix —
      revisit once real geocoding lands.
- [ ] **Data quality of the seeded bookings' `booking_items.daily_rate`/`subtotal`
      is unverified.** No existing spec or check (including
      `domain-seed-data/spec.md`'s own verification queries) confirms these
      columns are populated or realistic. Phase 3a's data-quality probe is a
      live check, not an assumption — if it finds the data unusable, Phase
      3b's real-data blending is blocked pending a Spring Boot seed-data fix,
      same escalation path Phase 2d-ii used for the `id=10` seed anomaly.
- [ ] **`PRICING_RETRAIN_MIN_REAL_ROWS_PER_CATEGORY` (default 20) and
      `PRICING_RETRAIN_REAL_SAMPLE_WEIGHT` (default 5.0) are starting points,
      not derived values.** Same category of open decision as Phase 2d's
      category-anchor refit — needs a product/pricing-owner sanity check
      before the defaults are trusted, not just a code review.
- [ ] **The realized-price status set (`{CONFIRMED, MOBILISED, COMPLETED}`)**
      used to decide which bookings count as real training signal is a
      reasonable-but-unconfirmed interpretation of "a price was actually
      agreed/charged." Worth an explicit sign-off.

---

## Execution plan — Phase 3a–3d, one sub-phase = one PR

| # | Status | Jira subtask | Branch | Covers | Depends on |
|---|---|---|---|---|---|
| 3a | ☐ | Phase 3a — foundations: validation gate + real-data quality probe | `feature/ml-3a-foundations` | New `app/services/pricing/promotion_gate.py`, extracted from `ml-experiments/candidate_validation_check.py`'s pure functions (that script refactored to import from it; `assess_gate` generalized with `expected_asset_count`/`min_asset_count`) — pure refactor, zero behavior change, `tests/test_candidate_validation_check.py` passes unmodified. Plus new read-only `ml-experiments/real_training_data_check.py`: live-query `booking_items`/`bookings`/`assets`/`asset_categories`, report null/zero-rate of `daily_rate`/`subtotal` per status/category — gates Phase 3b. | — |
| 3b | ☐ | Phase 3b — real-data extraction + blend/cutover | `feature/ml-3b-real-data-blend` | `daily_rate`/`subtotal` added to `app/models/booking_item.py`; `created_at`/`total_amount` added to `app/models/booking.py`; new `repository.py::fetch_real_training_rows()`; new `app/services/pricing/blend.py` (`build_training_dataset()` — per-category cutover + sample weighting); `train.py::train()` extended with `data`/`sample_weight` params. New `tests/test_pricing_real_training_rows.py`, `tests/test_pricing_blend.py`. | 3a (data confirmed usable by the probe) |
| 3c | ☐ | Phase 3c — retrain job orchestration | `feature/ml-3c-retrain-job` | New `app/services/pricing/retrain_job.py` (`run_scheduled_retrain()`: build blended dataset → train candidate → gate via `promotion_gate` → promote/rollback; `retrain_state.json` persistence). New `tests/test_pricing_retrain_job.py`. | 3a (gate), 3b (blend) |
| 3d | ☐ | Phase 3d — scheduler, app wiring, docs & regression | `feature/ml-3d-scheduler-and-docs` | `apscheduler` dependency; new `PRICING_RETRAIN_*` config fields (`app/config.py`); new `app/services/pricing/scheduler.py`; additive `lifespan` block in `app/main.py`; `.gitignore` additions; new `tests/test_pricing_scheduler.py`. Plus finalizing this doc and the OpenSpec proposal/tasks, and full-suite regression + Ruff across all of 3a–3d. | 3c |
| 3e | ☐ *(separate, later, not part of this plan's PR count)* | Phase 3e — merge into live spec | TBD | Fold the finished requirement into `openspec/specs/dynamic-pricing/{spec.md,design.md}`; retire "Manual retrain path (US-2)". Deliberately deferred past this plan's own close, same as Phase 2e is deferred past Phase 2d on the other execution plan today. | 3d, archival decision |

Four PRs (3a–3d) ship the feature; the chain is strictly sequential since each
PR wires directly into the next. Full architecture detail (function
signatures, `AsyncIOScheduler` vs. `BackgroundScheduler` rationale, state
persistence design, promotion/rollback mechanics) lives in
`openspec/changes/2026-08-15-scheduled-model-retrain/proposal.md` and this
change's PR descriptions as each phase lands — not duplicated here.

---

## Verification (full feature, once all four phases land)

```bash
cd haystack-fast-api

# Focused suite
uv run pytest tests/test_pricing_promotion_gate.py tests/test_pricing_real_training_rows.py \
  tests/test_pricing_blend.py tests/test_pricing_retrain_job.py tests/test_pricing_scheduler.py \
  tests/test_candidate_validation_check.py -v

# Full regression
uv run pytest tests/ -q
ruff check .

# Manual end-to-end smoke
PRICING_RETRAIN_ENABLED=true PRICING_RETRAIN_INTERVAL_DAYS=1 uv run uvicorn app.main:app
# confirm the job registers/fires (log line), inspect
# app/services/pricing/artifacts/retrain_state.json for a recorded outcome,
# confirm model.py's _model_version changes only on an actual promotion

# Data-quality gate (before trusting real-data blending)
uv run python ml-experiments/real_training_data_check.py
```

---

## Change log (of this execution plan, not the feature)

| Date | Note |
|------|------|
| 2026-08-15 | Initial plan split out as a new, parallel-track file (per explicit decision — Phase 2e is still open on `dynamic-pricing-execution-plan.md`). Consolidated from an initial 7-sub-phase draft to 4 PRs (3a–3d) per explicit preference for fewer, larger review units. |

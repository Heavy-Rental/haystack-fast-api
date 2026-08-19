# Dynamic Pricing — Scheduled Retrain Execution Plan (Phase 3)

> **This file tracks tasks and schedule only**, scoped to the scheduled-retrain
> feature. Decisions and rationale live in
> `openspec/changes/2026-08-15-scheduled-model-retrain/proposal.md` — don't
> duplicate reasoning here; link back to that instead.
>
> **Runs in parallel with the existing `dynamic-pricing-execution-plan.md`**
> (Phase 2e promotion completed 2026-08-17; its artifact swap remains separate
> from this Phase 3 plan). Phase 3a added the reusable gate/probe modules and
> refactored the historical candidate-validation script to import the shared
> implementation. Phase 3b added real-data extraction, shared distance
> imputation, per-category cutover, and weighted in-memory training. Phase 3c
> added candidate orchestration, gated promotion/rollback, and durable retrain
> state. Phase 3d will make additive scheduler/config changes. Per the
> 2026-08-18 documentation sync, Phase 3a's completed requirements are recorded in
> `openspec/specs/dynamic-pricing/{spec.md,design.md}`. Phase 3e still owns
> the final merge of completed Phase 3b–3d behavior and retirement of US-2.

Last updated: 2026-08-19

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
`retrain()` existed and worked in-process, but nothing called training except
by hand before Phase 3c. Phase 3c now calls `train()` only for candidate
artifacts; no runtime trigger exists until Phase 3d wires the scheduler.

**Decision: scrap the manual endpoint entirely.** The scheduler completed in
Phase 3d will be the sole retrain trigger, monthly. No HTTP route for on-demand
retrain exists or should be added. Phase 3a foundations are now recorded in the live spec/design; Phase 3e will retire US-2 after the scheduler itself lands.

---

## Open items carried into this plan

- [ ] **`distance_km` has no real equivalent anywhere in the schema.**
      `distance_km` is now imputed through the shared
      `app/services/pricing/training_sampling.py::sample_distance_km()` helper;
      `ml-experiments/generate_synthetic_data.py` imports the same helper, so
      real and synthetic rows retain one distribution. Stopgap, not a fix —
      revisit once real geocoding lands.
- [x] ~~**Data quality of seeded `booking_items.daily_rate`/`subtotal` was unverified.**~~
      **Resolved by Phase 3a (2026-08-18):** the read-only live probe measured
      98 rows/76 realized rows in `primary_snapshot`; null/zero/negative rates
      were 0% for both fields and every ML category had positive realized signal.
      Phase 3b consumed this confirmed data source and is complete.
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
| 3a | ☑ | Phase 3a — foundations: validation gate + real-data quality probe | `feature/ml-3a-foundations` | New `app/services/pricing/promotion_gate.py`, extracted from `ml-experiments/candidate_validation_check.py`'s pure functions (that script refactored to import from it; `assess_gate` generalized with `expected_asset_count`/`min_asset_count`) — pure refactor, zero behavior change, `tests/test_candidate_validation_check.py` passes unmodified. Plus new read-only `ml-experiments/real_training_data_check.py`: live-query `booking_items`/`bookings`/`assets`/`asset_categories`, report null/zero/negative rates of `daily_rate`/`subtotal` per status/category — gates Phase 3b. | — |
| 3b | ☑ | Phase 3b — real-data extraction + blend/cutover | `feature/ml-3b-real-data-blend` | Added `daily_rate`/`subtotal` and `created_at`/`total_amount` ORM fields; `real_training.py::fetch_real_training_rows()` is re-exported by `repository.py`; `training_sampling.py::sample_distance_km()` is shared with the synthetic generator; `blend.py::build_training_dataset()` performs per-category cutover and weighting; `train.py::train()` accepts optional `data`/`sample_weight`. Added `tests/test_pricing_real_training_rows.py` and `tests/test_pricing_blend.py`. | 3a (data confirmed usable by the probe) |
| 3c | ☑ | Phase 3c — retrain job orchestration | `feature/ml-3c-retrain-job` | Added `app/services/pricing/retrain_job.py`: blended training writes only candidate paths; current/candidate artifacts are freshly loaded and checked through `promotion_gate`; a pass takes a rolling backup, atomically swaps both serving files, and reloads the singleton; a promotion error rolls both files back. Every outcome is returned rather than raised and atomically persisted to dedicated `retrain_state.json`. Added `tests/test_pricing_retrain_job.py`. | 3a (gate), 3b (blend) |
| 3d | ☐ | Phase 3d — scheduler, app wiring, docs & regression | `feature/ml-3d-scheduler-and-docs` | `apscheduler` dependency; new `PRICING_RETRAIN_*` config fields (`app/config.py`); new `app/services/pricing/scheduler.py`; additive `lifespan` block in `app/main.py`; `.gitignore` additions; new `tests/test_pricing_scheduler.py`. Plus finalizing this doc and the OpenSpec proposal/tasks, and full-suite regression + Ruff across all of 3a–3d. | 3c |
| 3e | ☐ *(separate, later, outside the four plan PRs)* | Phase 3e — merge completed runtime requirement into live spec | TBD | Fold finished Phase 3b–3d behavior into `openspec/specs/dynamic-pricing/{spec.md,design.md}` and retire "Manual retrain path (US-2)". Phase 3a foundations were synchronized early on 2026-08-18; they are not repeated here. | 3d, archival decision |

Four PRs (3a–3d) ship the feature; the chain is strictly sequential since each
PR wires directly into the next. Full architecture detail (function
signatures, `AsyncIOScheduler` vs. `BackgroundScheduler` rationale, state
persistence design, promotion/rollback mechanics) lives in
`openspec/changes/2026-08-15-scheduled-model-retrain/proposal.md` and this
change's PR descriptions as each phase lands — not duplicated here.

---

## Phase 3b verification (completed 2026-08-19)

- Focused Phase 3b tests: 11 passed.
- Full regression: 439 passed, 5 optional tests skipped; Ruff and `git diff --check` passed.
- Shared distance sampler: 1,000 seed-42 outputs matched the prior synthetic implementation exactly; the generator CLI smoke also passed.
- Live read-only extraction: undegraded `primary_snapshot`, 76 rows — boom lift 21, excavator 15, forklift 16, scissor lift 24.
- Planned defaults (`min_real_rows_per_category=20`, `real_sample_weight=5.0`) produced 2,606 blended rows; boom/scissor cut over, excavator/forklift remained blended. Training succeeded to `/tmp`; no production artifacts or DB rows changed.

---

## Phase 3c verification (completed 2026-08-19)

- New Phase 3c tests: 6 passed, covering gate-pass promotion/backup/reload,
  gate-fail no-op, candidate-build failure, live-read failure, promotion-time
  rollback, and state missing/round-trip behavior.
- Cross-phase 3a–3c focused suite: 29 passed.
- Full regression: 445 passed, 5 optional tests skipped; focused Ruff and
  `git diff --check` passed.
- Tests monkeypatched every runtime artifact path to a temporary directory;
  no committed serving artifact or database row changed.

---

## Remaining full-feature verification (after Phase 3d)

```bash
cd haystack-fast-api

# Focused suite
uv run pytest tests/test_pricing_promotion_gate.py tests/test_real_training_data_check.py \
  tests/test_pricing_real_training_rows.py \
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
| 2026-08-18 | Phase 3a completed. Extracted the reusable promotion gate with recurring-job asset-floor mode while preserving the Phase 2d script’s exact 27-asset behavior; added and tested the four-table read-only real-price probe. Live `primary_snapshot` gate passed: 98 total/76 realized booking-item rows, no null/zero/negative `daily_rate` or `subtotal`, positive realized signal in every ML category. |
| 2026-08-18 (documentation convergence) | Synchronized Phase 3a as-built behavior into the live `spec.md`/`design.md`, resolved the data-quality open item, and kept Phase 3b–3d plus final US-2 retirement explicitly pending. |
| 2026-08-19 | Phase 3b completed. Added Spring-owned price/booking ORM fields, `real_training.py` extraction with schema-resolution threading, a shared `training_sampling.py` distance sampler, per-category synthetic cutover and real-row weighting, and in-memory weighted training. Live `primary_snapshot` extraction returned 76 rows (21 boom lift, 15 excavator, 16 forklift, 24 scissor lift); the default threshold produced a 2,606-row blended smoke dataset and trained successfully without touching production artifacts. Full regression: 439 passed, 5 skipped; Ruff passed. |
| 2026-08-19 | Phase 3c completed. Added the synchronous never-raise retrain job, candidate-only training paths, fresh current/candidate artifact validation, recurring minimum-fleet gate mode, atomic one-generation backup/swap, rollback and serving reload, plus dedicated atomic state persistence. Six new tests, 29 cross-phase focused tests, and the full 445-test regression passed; 5 optional tests skipped. |

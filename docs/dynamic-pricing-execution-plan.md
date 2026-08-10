# Dynamic Pricing Feature — Execution Plan

> **This file tracks tasks and schedule only.** Decisions and rationale live in
> `dynamic-pricing-masterplan.md` — don't duplicate reasoning here; link back to
> the relevant masterplan section instead.

Last updated: 2026-08-07

Timeline: 5 days total. Day 1–3 = Phase 1 (offline experimentation). Day 4–5 = Phase 2 (productionize).

---

## Day-by-day schedule

**Day 1 — Phase 1a: synthetic data generation**
- Scaffold `ml-experiments/` (sibling to `app/`, per masterplan phase order)
- Write full `generate_synthetic_data.py`: base rates (Pollisum/Ben's Rental rate cards), non-linear duration discounting, monsoon seasonality, utilization bands by category, `distance_km` delivery-distance premium (sampled, not geocoded — see masterplan), References docstring
- Sanity-check generated data distributions (not just "it ran")

**Day 2–3 — Phase 1b: feature engineering, training & SHAP review** ✅ done
- Feature engineering: one-hot `AssetCategory.name`, ordinal `condition` (`NEEDS_REPAIR=0…EXCELLENT=3`), `duration_days`, `capacity`, `distance_km`, `platform_height` (added after baseline SHAP review — see masterplan)
- Train baseline XGBoost model
- SHAP review — confirm duration↓ price and condition (worse → lower price) behave correctly, holding the other fixed
- Finalize `feature_schema.py` based on SHAP findings
- Retrain final model, save artifacts (`.pkl` + `current.json`)

**Day 3 (extension) — Phase 1c: prototype `predict_price()` (ml-experiments)**
- New file `ml-experiments/predict_price.py`: in-process `predict_price(...)` function, loads `model.pkl` once, builds features via the existing `feature_schema.build_features()` — no changes to the locked Phase 1b schema
- Guardrail clamping using static per-category `pricing_tables.CATEGORY_BASE_RATE` bounds — a stand-in, since this prototype has no DB/Asset access; Phase 2a still clamps against the real per-asset `Asset.minDailyRate`/`maxDailyRate` (see masterplan "Locked decisions")
- Purpose: unblock the upcoming agent prototype so it can fetch experimental ML pricing before Phase 2 productionizes the real service
- Verification: lightweight `__main__` smoke-check block only (one prediction per category), consistent with `shap_review.py`/`category_metrics.py` — no new `tests/` files for this ml-experiments scratch code

**Day 3 (extension) — Phase 1d: real-time features (ml-experiments)** ✅ done
- `pricing_tables.py`: `CAPACITY_BINS`/`HEIGHT_BINS` + lead-time/utilization constants (see file comments and masterplan for rationale)
- `feature_schema.py`: `period_utilization`/`lead_time_days` in `NUMERIC_FEATURES`; new `spec_band()`
- `generate_synthetic_data.py`: sampling for both features, `firmness_premium()` rewired to live `period_utilization`, References docstring, sanity checks
- `train.py`: rerun only. `shap_review.py`: two new sweep checks, renumbered `[n/9]`
- `predict_price.py`: both features as **optional kwargs with fallback defaults** (keeps `pricing_client.py` working pre-Phase-1e)
- `demo_scenarios.py` (new): condition/duration scenario pairs, raw+clamped bar charts — see masterplan for why it's here and not Day 5
- Also: `booking_month` resolved, fuel price documented rejected, masterplan/spec updated to reflect all of the above, SHAP importance tuned (see masterplan)

**Day 3 (extension, cont.) — Phase 1e: production DB wiring (separate branch/PR, not started)**
- First-ever read-only SQLAlchemy `Asset`/`AssetCategory`/`Booking` models (`app/models/`, `schema="primary_snapshot"` — see masterplan) + `app/repositories/pricing_repository.py` (`compute_period_utilization()`, `compute_lead_time_days()`)
- Shared read-resilience resolver (spec §5.3.1, new 2026-08-10): 3-tier fallback for every `primary_snapshot` read — retry on transient mid-recreate failure, degrade to reading `public` on sustained failure (mark the prediction degraded), fail loud on cold start (neither schema exists). Built once here so Phase 2a's guardrail-bound `Asset` read reuses it rather than a second implementation.
- Thread `db`/`start_date`/`end_date` through the call chain: `app/api/recommendations.py` → `.../recommendations.py` → `.../predict_price_adapter.py` → `.../pricing_client.py`, graceful fallback when unavailable
- Status filter, overlap rule, and `capacity` null fallback per masterplan/spec §5.2
- No longer blocked — schema, casing, `BookingStatus`, and DB topology all confirmed 2026-08-09 (see open items)

**Day 4 — Phase 2a: productionize pricing service**
- Build `app/services/pricing/` package: `model.py`, `train.py`, `feature_schema.py`, `artifacts/` — ports Phase 1d's `feature_schema.py` (already has the new features/`spec_band()`) and **relocates** (doesn't rebuild) Phase 1e's `pricing_repository.py` into `model.py`
- Guardrail clamping against `Asset.minDailyRate` / `maxDailyRate`
- Implement `/predict-price` as an **in-process function call** — called directly from `app.pipelines`, not an HTTP route (see masterplan Architecture)

**Day 5 — Phase 2b: integration, tests, demo prep**
- Wire the pricing function into the agentic pipeline → persist to `RecommendationItem.mlPredictedPrice`
- Unit tests: feature schema transforms, guardrail clamping, prediction shape
- Manual "retrain now" endpoint as demo safety net (full APScheduler-based scheduled retrain is Phase 3 — out of scope for this 5-day build, flag as post-MVP in demo/report)
- README, final polish, rehearse demo

---

## Jira subtasks / branches

| # | Status | Jira subtask | Branch | Covers | Day |
|---|---|---|---|---|---|
| 1 | ☑ | Phase 1 — synthetic data generation | `feature/ml-1-synthetic-data` | Scaffold `ml-experiments/` + full `generate_synthetic_data.py` | 1 |
| 2 | ☑ | Phase 1 — feature engineering, training & SHAP review | `feature/ml-2-train-and-shap` | Feature engineering, baseline training, SHAP review, finalize `feature_schema.py`, retrain final model, save artifacts | 2–3 |
| 2b | ☑ | Phase 1c — prototype `predict_price()` (ml-experiments) | `feature/ml-2b-predict-price-prototype` | `ml-experiments/predict_price.py`: in-process prototype + guardrail clamping (static per-category bounds), for the upcoming agent prototype | 3 (ext.) |
| 2c | ☑ | Phase 1d — real-time features (ml-experiments) | `HR-75-ml-2-c-period-utilization-lead-time` | See Day 3 (extension) above; also `demo_scenarios.py` (nominally subtask 5 scope, scaffolded early) | 3 (ext., cont.) |
| 2d | ☐ | Phase 1e — production DB wiring for `period_utilization` | TBD (separate branch, created when this starts) | First-ever read-only `Asset`/`AssetCategory`/`Booking` models (`app/models/`), `app/repositories/pricing_repository.py` + its shared 3-tier read-resilience resolver (spec §5.3.1), wired through `predict_price_adapter.py`/`pricing_client.py`/`recommendations.py`/the API route | 3 (ext., cont.) |
| 3 | ☐ | Phase 2 — productionize pricing service | `feature/ml-3-pricing-service` | `app/services/pricing/` package, guardrail clamping, in-process `predict_price()` function | 4 |
| 4 | ☐ | Phase 2 — pipeline integration & tests | `feature/ml-4-integration-tests` | Wire into agentic pipeline → `mlPredictedPrice`, unit tests, manual "retrain now" endpoint | 5 (AM) |
| 5 | ☐ | Demo prep & docs | `feature/ml-5-demo-prep` | README, rehearse demo, final polish. **Live demo script itself already built under subtask 2c** — this subtask's remaining scope is rehearsal/polish/README, not writing `demo_scenarios.py` from scratch. | 5 (PM) |

PR/review notes:
- Subtasks 1–2, 2b, 2c (`ml-experiments/`, scratch code): lighter-weight review, merge fast.
- Subtasks 2d, 3–4 (`app/`, production code): full review — this is what the agentic pipeline and teammates depend on. 2d specifically touches the live recommendation pipeline ahead of the rest of Phase 2, so review it with the same weight as 3–4, not as scratch.

---

## Open items carried from masterplan

- [ ] Real retrain interval (monthly vs. quarterly) — not needed for this 5-day build, deferred to Phase 3.
- [ ] Full APScheduler scheduled retrain — explicitly out of scope for this build; manual "retrain now" endpoint is the stand-in.
- [x] ~~`booking_month`/seasonality as a feature — Phase 1b found a mild, not-fully-clean per-month error pattern (January worst); lean is against adding it, but not locked. Decide during Phase 2, before finalizing the productionized `feature_schema.py`.~~ — **resolved in Phase 1d: not added** (`period_utilization` already captures realized seasonality). See masterplan.
- [ ] Phase 1c's guardrail bounds (`ml-experiments/predict_price.py`, static per-category `pricing_tables.CATEGORY_BASE_RATE`) are a stand-in only — Phase 2a must still clamp against the real per-asset `Asset.minDailyRate`/`maxDailyRate`, not reuse this prototype's bound source.
- [x] ~~**Before implementing Phase 1e's `period_utilization` aggregate query**: confirm `BookingStatus.CONFIRMED` actually exists (only `PENDING`/`CANCELLED` are ever named in this repo) and confirm exact `Asset`/`Booking` table/column names and casing against the real Spring Boot schema — the masterplan's field list is diagram-sourced, not verified.~~ — **resolved (2026-08-09)**: see masterplan for full detail (snake_case columns, real `BookingStatus` lifecycle, status filter, overlap rule). **Correction, same day**: cross-checking `SPEC-spring-entity-repository.md` found `BookingStatus` includes `CANCELLED` (real, reachable — cancellation happens); an earlier "happy-path-only" claim in this resolution was wrong. Filter membership itself didn't change — see masterplan.
- [x] ~~Confirm `Asset.capacity` is reliably populated before relying on it as a spec-band bucketing key.~~ — **resolved (2026-08-09)**: null for every non-forklift seed row; permanent per-category fallback added (masterplan, spec §5.2).
- [x] ~~Confirm which Postgres schema pricing's SQLAlchemy models should read from.~~ — **resolved (2026-08-09)**: `primary_snapshot`, not `public` (masterplan, spec §5.3).
- [x] ~~`Asset.condition` is nullable (`SPEC-spring-entity-repository.md` §5.3) and `feature_schema.encode_condition()` currently raises `ValueError` on a null value — needs a fallback default, same category of fix as `capacity`. Not yet designed; pending a decision on the default value.~~ — **resolved (2026-08-09)**: falls back to `"GOOD"`, not NaN (masterplan, spec §5.2/§8).

---

## Change log (of this execution plan, not the feature)

| Date | Note |
|------|------|
| 2026-08-04 | Initial execution plan split out from `dynamic-pricing-masterplan.md`. Consolidated to 5 Jira subtasks/branches, reduced from an earlier 13-subtask draft to cut PR frequency, especially during Phase 1. |
| 2026-08-04 | Added `distance_km` to the Day 1 generator task and Day 2–3 feature-engineering list, per the new locked `distance_km` decision in the masterplan. |
| 2026-08-04 | Phase 1b complete: subtasks 1–2 checked off. Added `platform_height` to the Day 2–3 feature-engineering list — discovered mid-review via a per-category MAE/R² breakdown showing boom lift/scissor lift fitting far worse than forklift/excavator; see masterplan for the decision. Next: write `SPEC-dynamic-pricing.md` (+ `SPEC-domain-seed-data.md`) per the masterplan's phase order, before starting Phase 2. |
| 2026-08-04 | `SPEC-dynamic-pricing.md` written. Added `booking_month`/seasonality as an open item carried into Phase 2 (Day 4 task + Open items list) — a per-`booking_month` MAE/R² check found a mild pattern worth a deliberate decision, not locked either way. |
| 2026-08-05 | Added Phase 1c: prototype `predict_price()` in `ml-experiments/` (new "Day 3 (extension)" task, subtask 2b) — a lightweight, DB-free version so the upcoming agent prototype can fetch experimental ML pricing before Phase 2a lands. Guardrail bounds are a static per-category stand-in, not the real per-asset clamp Phase 2a still implements. |
| 2026-08-07 | Added Phase 1d (real-time features, subtask 2c, branch `HR-75-ml-2-c-period-utilization-lead-time`) and Phase 1e (production DB wiring for `period_utilization`, subtask 2d, separate branch TBD) as new "Day 3 (extension, cont.)" tasks. Resolved the `booking_month` open item (not added). Added a new open item: confirm `BookingStatus.CONFIRMED` and exact Asset/Booking column casing before Phase 1e. Updated Day 4's task list to note `app/services/pricing/feature_schema.py` picks up the new features automatically via the Phase 1d port, and that Phase 2 relocates rather than rebuilds Phase 1e's repository query. |
| 2026-08-07 | Corrected Phase 1d's `predict_price.py` task: the two new features are **optional kwargs with fallback defaults**, not required — required kwargs would break `pricing_client.py`'s existing call the moment Phase 1d merges, ahead of Phase 1e threading real values through. Added `demo_scenarios.py` (script-based live demo for a lecturer, since `predict_price(...)` is in-process only) to subtask 2c's scope, pulled forward from its nominal `feature/ml-5-demo-prep` slot since it's low-risk (placeholder data, no dependency on the rest of Phase 1d). Updated subtask 5's row to reflect that the script itself is already built by then — remaining Day 5 PM scope is rehearsal/polish only. |
| 2026-08-07 | Subtask 2c (Phase 1d) marked done — implemented and verified. Condensed Day 3/Day 4 task descriptions (rationale now lives only in masterplan, per this file's own "don't duplicate reasoning" convention); no scope changes. |
| 2026-08-09 | Resolved the schema/casing/`BookingStatus`/capacity/DB-topology open items by confirming directly against `postgres-haystack`/`postgres-primary` — unblocks Phase 1e (see Open items). Updated Phase 1e's Day 3 (extension, cont.) task description accordingly; no longer "blocked." Full detail in masterplan/spec, not duplicated here. |
| 2026-08-09 (correction, same day) | Cross-checked the above against a new `SPEC-spring-entity-repository.md` (authoritative Java entity/enum reference). Corrected the `BookingStatus` open item: `CANCELLED` is real, cancellation happens — not happy-path-only as recorded earlier the same day. No change to `period_utilization`'s filter membership. Added a new open item: `Asset.condition` is nullable and crashes `feature_schema.encode_condition()` today — needs a fallback default, not yet designed. |
| 2026-08-09 (later same day) | Resolved the `condition` open item: falls back to `"GOOD"`, not NaN (masterplan, spec §5.2/§8). |
| 2026-08-10 | Added the shared 3-tier read-resilience resolver (spec §5.3.1) to Phase 1e's scope — retry on transient `primary_snapshot` failures, degrade to `public` on sustained failures, fail loud on cold start. Updated Phase 1e's Day 3 (extension, cont.) description and subtask 2d's "Covers" cell; no schedule/branch change. |

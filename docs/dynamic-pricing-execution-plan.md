# Dynamic Pricing Feature — Execution Plan

> **This file tracks tasks and schedule only.** Decisions and rationale live in
> `dynamic-pricing-masterplan.md` — don't duplicate reasoning here; link back to
> the relevant masterplan section instead.

Last updated: 2026-08-05

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

**Day 4 — Phase 2a: productionize pricing service**
- Decide `booking_month`/seasonality inclusion before porting `feature_schema.py` — open item, see masterplan
- Build `app/services/pricing/` package: `model.py`, `train.py`, `feature_schema.py`, `artifacts/`
- Guardrail clamping against `Asset.minDailyRate` / `maxDailyRate`
- Implement `/predict-price` as an **in-process function call** (see masterplan Architecture section) — called directly from `app.pipelines`, not exposed as an HTTP route

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
| 3 | ☐ | Phase 2 — productionize pricing service | `feature/ml-3-pricing-service` | `app/services/pricing/` package, guardrail clamping, in-process `predict_price()` function | 4 |
| 4 | ☐ | Phase 2 — pipeline integration & tests | `feature/ml-4-integration-tests` | Wire into agentic pipeline → `mlPredictedPrice`, unit tests, manual "retrain now" endpoint | 5 (AM) |
| 5 | ☐ | Demo prep & docs | `feature/ml-5-demo-prep` | README, rehearse demo, final polish | 5 (PM) |

PR/review notes:
- Subtasks 1–2, 2b (`ml-experiments/`, scratch code): lighter-weight review, merge fast.
- Subtasks 3–4 (`app/services/pricing/`, production code): full review — this is what the agentic pipeline and teammates depend on.

---

## Open items carried from masterplan

- [ ] Real retrain interval (monthly vs. quarterly) — not needed for this 5-day build, deferred to Phase 3.
- [ ] Full APScheduler scheduled retrain — explicitly out of scope for this build; manual "retrain now" endpoint is the stand-in.
- [ ] `booking_month`/seasonality as a feature — Phase 1b found a mild, not-fully-clean per-month error pattern (January worst); lean is against adding it, but not locked. Decide during Phase 2 (`feature/ml-3-pricing-service`), before finalizing the productionized `feature_schema.py`.
- [ ] Phase 1c's guardrail bounds (`ml-experiments/predict_price.py`, static per-category `pricing_tables.CATEGORY_BASE_RATE`) are a stand-in only — Phase 2a must still clamp against the real per-asset `Asset.minDailyRate`/`maxDailyRate`, not reuse this prototype's bound source.

---

## Change log (of this execution plan, not the feature)

| Date | Note |
|------|------|
| 2026-08-04 | Initial execution plan split out from `dynamic-pricing-masterplan.md`. Consolidated to 5 Jira subtasks/branches, reduced from an earlier 13-subtask draft to cut PR frequency, especially during Phase 1. |
| 2026-08-04 | Added `distance_km` to the Day 1 generator task and Day 2–3 feature-engineering list, per the new locked `distance_km` decision in the masterplan. |
| 2026-08-04 | Phase 1b complete: subtasks 1–2 checked off. Added `platform_height` to the Day 2–3 feature-engineering list — discovered mid-review via a per-category MAE/R² breakdown showing boom lift/scissor lift fitting far worse than forklift/excavator; see masterplan for the decision. Next: write `SPEC-dynamic-pricing.md` (+ `SPEC-domain-seed-data.md`) per the masterplan's phase order, before starting Phase 2. |
| 2026-08-04 | `SPEC-dynamic-pricing.md` written. Added `booking_month`/seasonality as an open item carried into Phase 2 (Day 4 task + Open items list) — a per-`booking_month` MAE/R² check found a mild pattern worth a deliberate decision, not locked either way. |
| 2026-08-05 | Added Phase 1c: prototype `predict_price()` in `ml-experiments/` (new "Day 3 (extension)" task, subtask 2b) — a lightweight, DB-free version so the upcoming agent prototype can fetch experimental ML pricing before Phase 2a lands. Guardrail bounds are a static per-category stand-in, not the real per-asset clamp Phase 2a still implements. |

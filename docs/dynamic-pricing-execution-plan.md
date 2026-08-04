# Dynamic Pricing Feature — Execution Plan

> **This file tracks tasks and schedule only.** Decisions and rationale live in
> `dynamic-pricing-masterplan.md` — don't duplicate reasoning here; link back to
> the relevant masterplan section instead.

Last updated: 2026-08-04

Timeline: 5 days total. Day 1–3 = Phase 1 (offline experimentation). Day 4–5 = Phase 2 (productionize).

---

## Day-by-day schedule

**Day 1 — Phase 1a: synthetic data generation**
- Scaffold `ml-experiments/` (sibling to `app/`, per masterplan phase order)
- Write full `generate_synthetic_data.py`: base rates (Pollisum/Ben's Rental rate cards), non-linear duration discounting, monsoon seasonality, utilization bands by category, `distance_km` delivery-distance premium (sampled, not geocoded — see masterplan), References docstring
- Sanity-check generated data distributions (not just "it ran")

**Day 2–3 — Phase 1b: feature engineering, training & SHAP review**
- Feature engineering: one-hot `AssetCategory.name`, ordinal `condition` (`NEEDS_REPAIR=0…EXCELLENT=3`), `duration_days`, `capacity`, `distance_km`
- Train baseline XGBoost model
- SHAP review — confirm duration↓ price and condition (worse → lower price) behave correctly, holding the other fixed
- Finalize `feature_schema.py` based on SHAP findings
- Retrain final model, save artifacts (`.pkl` + `current.json`)

**Day 4 — Phase 2a: productionize pricing service**
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
| 1 | ☐ | Phase 1 — synthetic data generation | `feature/ml-1-synthetic-data` | Scaffold `ml-experiments/` + full `generate_synthetic_data.py` | 1 |
| 2 | ☐ | Phase 1 — feature engineering, training & SHAP review | `feature/ml-2-train-and-shap` | Feature engineering, baseline training, SHAP review, finalize `feature_schema.py`, retrain final model, save artifacts | 2–3 |
| 3 | ☐ | Phase 2 — productionize pricing service | `feature/ml-3-pricing-service` | `app/services/pricing/` package, guardrail clamping, in-process `predict_price()` function | 4 |
| 4 | ☐ | Phase 2 — pipeline integration & tests | `feature/ml-4-integration-tests` | Wire into agentic pipeline → `mlPredictedPrice`, unit tests, manual "retrain now" endpoint | 5 (AM) |
| 5 | ☐ | Demo prep & docs | `feature/ml-5-demo-prep` | README, rehearse demo, final polish | 5 (PM) |

PR/review notes:
- Subtasks 1–2 (`ml-experiments/`, scratch code): lighter-weight review, merge fast.
- Subtasks 3–4 (`app/services/pricing/`, production code): full review — this is what the agentic pipeline and teammates depend on.

---

## Open items carried from masterplan

- [ ] Real retrain interval (monthly vs. quarterly) — not needed for this 5-day build, deferred to Phase 3.
- [ ] Full APScheduler scheduled retrain — explicitly out of scope for this build; manual "retrain now" endpoint is the stand-in.

---

## Change log (of this execution plan, not the feature)

| Date | Note |
|------|------|
| 2026-08-04 | Initial execution plan split out from `dynamic-pricing-masterplan.md`. Consolidated to 5 Jira subtasks/branches, reduced from an earlier 13-subtask draft to cut PR frequency, especially during Phase 1. |
| 2026-08-04 | Added `distance_km` to the Day 1 generator task and Day 2–3 feature-engineering list, per the new locked `distance_km` decision in the masterplan. |

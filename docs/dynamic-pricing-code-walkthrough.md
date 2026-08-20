# Dynamic Pricing — Code Walkthrough (Presentation Prep)

Personal study guide for the "code quality" presentation. Goal: be able to jump
straight to the right file/function when asked "show me the code for X."
Organized around the questions you're likely to get, not around the dev
timeline.

Full authoritative spec/design docs (read these if you need the *decisions*,
not just the code):
- [`openspec/specs/dynamic-pricing/spec.md`](../openspec/specs/dynamic-pricing/spec.md) — requirements, user stories
- [`openspec/specs/dynamic-pricing/design.md`](../openspec/specs/dynamic-pricing/design.md) — technical design, incident writeups
- [`docs/dynamic-pricing-masterplan.md`](dynamic-pricing-masterplan.md) — original feature/model plan
- [`docs/dynamic-pricing-execution-plan.md`](dynamic-pricing-execution-plan.md) — phase-by-phase build log
- [`docs/dynamic-pricing-scheduled-retrain-plan.md`](dynamic-pricing-scheduled-retrain-plan.md) — retrain scheduler plan

---

## 1. Elevator pitch

We predict a fair daily rental rate for a piece of equipment (forklift,
scissor lift, boom lift, excavator) using an XGBoost regression model trained
on rental attributes (category, condition, duration, capacity, platform
height, delivery distance) plus two **live, real-time** signals — how booked-up
similar equipment is (`period_utilization`) and how far ahead the customer is
booking (`lead_time_days`). The raw prediction is then **clamped** to that
specific asset's real `minDailyRate`/`maxDailyRate` guardrails so the model
can never quote outside business-approved bounds. The model **retrains itself
monthly**, blending in real booking data as it accumulates, and only goes live
if it passes an automated quality gate against the model currently serving.

Two consumers call the same `predict_price()` function — there is exactly one
prediction code path in production:
1. **Internal quote API** (`POST /internal/v1/pricing/quote`) — Spring Boot
   calls this at checkout for an authoritative price.
2. **Recommendation pipeline** — attaches an estimated price to each
   recommended asset candidate.

---

## 2. Request-flow diagram

```
                        ┌─────────────────────────────┐
                        │  app/services/pricing/model.py │
                        │        predict_price()         │
                        └───────────────┬─────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
   feature_schema.py              repository.py                artifacts/model.pkl
   build_features()          compute_period_utilization()      (XGBoost, loaded once
   (one-hot category,        compute_lead_time_days()          at import time)
    ordinal condition)       resolve_effective_capacity()
        │                               │
        │                       read_resilience.py
        │                  resolve_pricing_schema()
        │                (primary_snapshot → public
        │                  → PricingSchemaUnavailable)
        │                               │
        └───────────────┬───────────────┘
                        │
              clamp to [min_daily_rate, max_daily_rate]
                        │
              PricePrediction dataclass
                        │
        ┌───────────────┴───────────────┐
        │                               │
  api/internal_pricing.py      pipelines/predict_price_adapter.py
  POST /internal/v1/            (via services/pricing_client.py)
  pricing/quote                 used inside services/recommendations.py's
  (Spring Boot → Haystack,      candidate → availability → PRICE → rank
   never renter-facing)         pipeline
```

---

## 3. File map

### Core service package — `app/services/pricing/`

| File | What it does | Ask about this file if asked... |
|---|---|---|
| [`model.py`](../app/services/pricing/model.py) | **The prediction entry point.** Loads `artifacts/model.pkl` once at import; `predict_price()` builds the feature row, calls `model.predict()`, clamps to guardrails. | "How does prediction work end to end?" |
| [`feature_schema.py`](../app/services/pricing/feature_schema.py) | Defines the model's locked feature contract: `CATEGORIES`, `CONDITION_ORDER`, `FEATURE_COLUMNS`, `build_features()`, `spec_band()`. | "What features go into the model? Why these features?" |
| [`train.py`](../app/services/pricing/train.py) | `train()` — fits an `XGBRegressor` on a dataframe, evaluates MAE/RMSE/R², writes `model.pkl` + `current.json`. Supports optional `sample_weight` (used by the retrain job). | "How do you train the model?" |
| [`retrain_job.py`](../app/services/pricing/retrain_job.py) | `run_scheduled_retrain()` — the full orchestration: build candidate → evaluate vs. current via the promotion gate → promote or reject, with atomic file swap + rollback. | "How does the retrain job work?" / "show me retrain code" |
| [`scheduler.py`](../app/services/pricing/scheduler.py) | APScheduler job wired into FastAPI's `lifespan`; runs `retrain_job.run_scheduled_retrain()` off the event loop on an interval (default monthly). | "How often does it retrain? What triggers it?" |
| [`promotion_gate.py`](../app/services/pricing/promotion_gate.py) | `assess_gate()` — compares candidate vs. currently-serving model on live assets (clamp rate) + a common holdout (MAE/R²) before allowing promotion. | "How do you prevent a bad retrain from going live?" |
| [`blend.py`](../app/services/pricing/blend.py) | `build_training_dataset()` — per-category cutover from synthetic → real booking data once a category has enough real rows; real rows get an up-weighted `sample_weight`. | "How do you mix synthetic and real training data?" |
| [`real_training.py`](../app/services/pricing/real_training.py) | `fetch_real_training_rows()` — turns realized bookings (`CONFIRMED`/`MOBILISED`/`COMPLETED`) into training rows. | "Where does real training data come from?" |
| [`repository.py`](../app/services/pricing/repository.py) | Live DB reads: `compute_period_utilization()`, `compute_lead_time_days()`, `get_asset_for_pricing()`, `resolve_effective_capacity()`. | "How is period_utilization computed live?" |
| [`read_resilience.py`](../app/services/pricing/read_resilience.py) | `resolve_pricing_schema()` — 3-tier resilience (retry → degrade to `public` schema → raise `PricingSchemaUnavailable`) against the replicated `primary_snapshot` schema. | "What happens if the DB read fails?" |
| [`category_mapping.py`](../app/services/pricing/category_mapping.py) | `to_feature_name()` / `to_db_name()` — translates Spring Boot's business category names (`"Fork Lift"`) ↔ the model's training convention (`"forklift"`). | "Any interesting bugs you found?" — **this is a great story, see §6** |
| [`pricing_tables.py`](../app/services/pricing/pricing_tables.py) | Static constants: capacity/height bins for `spec_band()`, category utilization fallbacks, synthetic-data generation parameters. | "Where do the fallback defaults come from?" |
| [`training_sampling.py`](../app/services/pricing/training_sampling.py) | `sample_distance_km()` — shared stochastic distance imputation (no real delivery-distance data exists yet). | (minor — utility) |
| `artifacts/` | `model.pkl` / `current.json` = **currently serving**. `model_candidate.pkl` / `_previous.pkl` = retrain-job working files. `retrain_state.json` = last run's outcome. | "Where's the actual model file?" |

### API / integration layer

| File | What it does |
|---|---|
| [`app/api/internal_pricing.py`](../app/api/internal_pricing.py) | `POST /internal/v1/pricing/quote`. Resolves `asset_id → real Asset row` server-side, calls `predict_price()`, returns a clamped quote. Registered directly in `main.py`, **not** under the public `/api/v1` router — deliberately not renter-facing. |
| [`app/schemas/pricing.py`](../app/schemas/pricing.py) | Pydantic request/response models for the quote endpoint (`PricingQuoteRequest`, `QuoteItemResult`, etc.). |
| [`app/services/pricing_client.py`](../app/services/pricing_client.py) | Thin wrapper around `predict_price()` that adds response shaping: currency, `deposit_rate`, `total_price`, human-readable `explanation` text. |
| [`app/pipelines/predict_price_adapter.py`](../app/pipelines/predict_price_adapter.py) | A Haystack pipeline `@component` (`PredictPriceAdapter`) that calls `pricing_client.predict_price_for_asset()` for every recommendation candidate. |
| [`app/services/recommendations.py`](../app/services/recommendations.py) (`_recommend_for_unit_need`, ~line 155) | Orchestrates the recommendation pipeline: filter candidates → check availability → **price** (via `PredictPriceAdapter`) → rank → assemble. |
| [`app/main.py`](../app/main.py) | Wires the retrain scheduler into the FastAPI `lifespan` (start on boot if `pricing_retrain_enabled`, shut down cleanly on exit); mounts `internal_pricing_router`. |
| [`app/config.py`](../app/config.py) | Settings: `pricing_schema`, `pricing_retrain_enabled`, `pricing_retrain_interval_days`, `pricing_retrain_min_real_rows_per_category`, `pricing_retrain_real_sample_weight`. |

### Model prototyping / offline tooling — `ml-experiments/`

Not production code — this is where the model was **first** designed and
validated before being "ported" into `app/services/pricing/`. Useful if asked
about the *original* experimentation/model-selection process.

| File | What it does |
|---|---|
| [`ml-experiments/generate_synthetic_data.py`](../ml-experiments/generate_synthetic_data.py) | Generates the synthetic training dataset (rate-card-grounded base rates, seasonality, condition multipliers, duration discount curve, noise). Cited sources in its docstring (Pollisum/Ben's Rental rate cards, NEA monsoon calendar, BCA construction demand). |
| [`ml-experiments/train.py`](../ml-experiments/train.py) | Original prototype trainer — `app/services/pricing/train.py` is its "ported" production version. |
| [`ml-experiments/shap_review.py`](../ml-experiments/shap_review.py) | SHAP feature-importance review — this is *why* `platform_height` and `period_utilization`/`lead_time_days` exist as features (earlier model fit boom/scissor lifts poorly without height). |
| [`ml-experiments/predict_price.py`](../ml-experiments/predict_price.py) | The original prototype `predict_price()` — production's `model.py` "supersedes" this (real per-asset guardrails instead of a static per-category table). |
| [`ml-experiments/candidate_validation_check.py`](../ml-experiments/candidate_validation_check.py), [`guardrail_calibration_check.py`](../ml-experiments/guardrail_calibration_check.py) | One-off offline validation scripts used during model development. |

### Tests — `tests/`

| Test file | Covers |
|---|---|
| `test_pricing_model.py` | `predict_price()` — clamping, category validation, live vs. fallback signals |
| `test_pricing_feature_schema.py` | `build_features()`, `spec_band()`, encoding |
| `test_pricing_repository.py` | `compute_period_utilization()`, `compute_lead_time_days()` |
| `test_pricing_read_resilience.py` | 3-tier schema resolution / degrade / cold-start |
| `test_pricing_retrain_job.py` | Full retrain orchestration: build → gate → promote/rollback |
| `test_pricing_promotion_gate.py` | Gate math: clamp-rate reduction, MAE/R² regression checks |
| `test_pricing_blend.py` | Synthetic/real dataset blending + sample weights |
| `test_pricing_real_training_rows.py` | Extracting training rows from realized bookings |
| `test_pricing_scheduler.py` | APScheduler wiring, next-run-time computation |
| `test_internal_pricing_api.py` | `POST /internal/v1/pricing/quote` end to end |
| `test_pricing_client_phase1e.py`, `test_pricing_phase1e_wiring.py`, `test_pricing_phase2b_wiring.py`, `test_pricing_phase2e_promotion.py` | Phase-specific wiring/regression tests (named after build phases — see §5) |
| `test_predict_asset_price_tool.py` | Pricing exposed as an agent tool (if asked in an LLM-agent context) |

---

## 4. Deep dives for likely questions

### "How do you implement dynamic pricing / how does prediction work?"
→ [`app/services/pricing/model.py`](../app/services/pricing/model.py) `predict_price()` (line ~118)

Walk through it in this order:
1. Validate `category` is one of the 4 known categories (line 173) — raises `ValueError` rather than silently one-hot-encoding to all-zeros.
2. `condition` defaults to `"GOOD"` if null; `capacity` defaults to the category midpoint via `resolve_effective_capacity()`.
3. If a DB session + dates are given, `period_utilization`/`lead_time_days` are computed **live** (repository.py); otherwise static fallbacks from `pricing_tables.py`.
4. Build the one feature row via `feature_schema.build_features()`.
5. `_model.predict(features)` → raw price.
6. Clamp: `clamped_price = min(max(raw_price, min_rate), max_rate)`.
7. Return a `PricePrediction` dataclass (raw price, clamped price, whether it was clamped, degraded flag, model version).

### "What features does the model use, and why?"
→ [`feature_schema.py`](../app/services/pricing/feature_schema.py) module docstring (very thorough — read it directly, it's basically presentation notes already written for you)

- One-hot `category` (4 values), ordinal `condition` (`NEEDS_REPAIR`→0 … `EXCELLENT`→3)
- `duration_days`, `capacity`, `distance_km`
- `platform_height` — **only** for scissor/boom lift, left as native NaN (not 0) for forklift/excavator so XGBoost's missing-value handling routes around it, rather than teaching the model a fake height
- `period_utilization`, `lead_time_days` — the two *live* signals, added in a later phase after SHAP review showed the model needed real-time demand signal, not just static attributes
- **Deliberately excluded** (and why): `minDailyRate`/`maxDailyRate`/`price_clamped` (would leak the target), identifiers, `purchaseYear` (SHAP-tested, not useful), booking-month seasonality (redundant with `period_utilization`), fuel price (no reliable data source, would add an external API dependency)

### "Show me the code for the training part."
Two layers, don't conflate them:
- **One-shot / manual retrain**: [`app/services/pricing/train.py`](../app/services/pricing/train.py) `train()` (line 46) — takes a dataframe, does an 80/20 split, fits `XGBRegressor` (params at line 36: 300 estimators, depth 5, lr 0.05), evaluates MAE/RMSE/R², writes `model.pkl` + `current.json` metadata.
- **Scheduled retrain**: see next question — that's the one with real orchestration logic.

### "Show me the code for the retrain job."
→ [`app/services/pricing/retrain_job.py`](../app/services/pricing/retrain_job.py) `run_scheduled_retrain()` (line ~293) — this is the meatiest single function, walk through it as a pipeline:

1. `_build_candidate()` (line 172): reads synthetic CSV + real booking rows (`repository.fetch_real_training_rows`), blends them (`blend.build_training_dataset`), trains into `model_candidate.pkl`/`current_candidate.json` — **never overwrites the serving model yet**.
2. `_evaluate_candidate()` (line 202): runs the candidate and the current serving model through `promotion_gate.py` — same live assets, same holdout set.
3. If the gate fails → `status="gate_failed"`, nothing changes, old model keeps serving.
4. If it passes → `_promote()` (line 267): atomically copies `current → previous` (backup), `candidate → current`, then `pricing_model.reload_model()` hot-swaps the in-memory model **without restarting the app**. If promotion itself throws, it automatically rolls back to the backup.
5. Every outcome (`promoted` / `gate_failed` / `error`) is durably recorded via `save_state()` → `artifacts/retrain_state.json`, using atomic tempfile-then-`rename` writes so a crash mid-write can't corrupt it.

→ Trigger: [`scheduler.py`](../app/services/pricing/scheduler.py) — an APScheduler `AsyncIOScheduler` job registered in `main.py`'s `lifespan`, running `retrain_job.run_scheduled_retrain()` via `asyncio.to_thread()` (keeps the blocking DB reads + XGBoost fit off the event loop). Default interval and enable flag are `app/config.py` settings (`pricing_retrain_interval_days`, `pricing_retrain_enabled`).

### "How do you make sure a retrained model isn't worse before it goes live?"
→ [`promotion_gate.py`](../app/services/pricing/promotion_gate.py) `assess_gate()` (line 254). Checks, **all** of which must pass:
- Live asset count sanity check
- At durations 7 and 14 days: candidate's clamp rate must be **at least 20 points lower** than current's (`MIN_CLAMP_REDUCTION = 0.20`) AND under 50% (`MAX_CANDIDATE_CLAMP_RATE`)
- On a common deterministic holdout: candidate MAE can't regress more than 5%, R² can't regress more than 0.01
This is intentionally **reused** by both the retrain job and an earlier one-off validation script (Phase 2d) — one gate implementation, not duplicated logic.

### "How do the guardrails / clamping work?"
→ `model.py` line 225: `clamped_price = min(max(raw_price, min_rate), max_rate)`. `min_rate`/`max_rate` are the **real** per-asset `Asset.minDailyRate`/`Asset.maxDailyRate` — always caller-supplied, never a static per-category table (that static table, `pricing_tables.CATEGORY_BASE_RATE`, exists only as a leftover reference/prototype constant, kept for tests).

### "What's period_utilization / lead_time_days and how are they computed live?"
→ [`repository.py`](../app/services/pricing/repository.py) `compute_period_utilization()` (line 145): fraction of same-category-and-spec-band assets that have an overlapping booking in a "live hold" status (`PENDING_DEPOSIT`, `PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`) over the requested date window. `compute_lead_time_days()` (line 140) is just `start_date - today`.
"Spec-band" (`feature_schema.spec_band()`) groups assets by category + a capacity/height bucket so a fully-booked small excavator doesn't make a large excavator look artificially scarce.

### "What happens if the database read fails?"
→ [`read_resilience.py`](../app/services/pricing/read_resilience.py) — 3-tier resolution, decided once per `predict_price()` call and reused for every read in that call (never mixes schemas mid-request):
1. Retry against `primary_snapshot` a few times (transient failure)
2. Degrade to reading `public` instead (at most one sync cycle stale) — sets `degraded=True`, doesn't fail the request
3. If neither schema has the tables at all (cold start, container never synced) → raises `PricingSchemaUnavailable`, which propagates to a 500 rather than being silently swallowed

### "How does dynamic pricing plug into the recommendation feature?"
→ [`app/services/recommendations.py`](../app/services/recommendations.py) `_recommend_for_unit_need()` (line ~155) — pipeline order: **candidates → availability filter → `PredictPriceAdapter` → rank**. `PredictPriceAdapter` ([`predict_price_adapter.py`](../app/pipelines/predict_price_adapter.py)) is a Haystack `@component` that calls `pricing_client.predict_price_for_asset()` per candidate, which itself is a thin wrapper around the same `model.predict_price()`.

### "Where's the actual API endpoint, and why isn't it public?"
→ [`app/api/internal_pricing.py`](../app/api/internal_pricing.py) — `POST /internal/v1/pricing/quote`, service-to-service only (Spring Boot backend → this Haystack service), for authoritative checkout pricing. Deliberately registered directly on the FastAPI `app` in `main.py` (line 92) instead of under the shared `/api/v1` router, so it can never accidentally become renter-facing.

---

## 5. "Despite spec-driven AI development" — evidence you actually understand it

If pushed on "how much do you really know this, given an agent wrote it,"
these are concrete, defensible things to point to:

1. **You can name a real bug that was found and fixed**: see §6 below (category name mismatch). That's a much stronger answer than reciting what the code does.
2. **The feature set has documented rejections, not just inclusions** — `feature_schema.py`'s docstring lists what was tried and *excluded* (purchase year, seasonality, fuel price) and why. Being able to explain why a feature *isn't* there is a good signal of understanding, not just memorization.
3. **The promotion gate is a real regression-prevention mechanism**, not just "we retrain and hope" — you can explain the actual numeric thresholds (§4).
4. **The system degrades gracefully instead of crashing** — 3-tier read resilience, per-item error handling in the quote endpoint (one bad `asset_id` doesn't fail the whole batch — see `internal_pricing.py`'s `_quote_one_item`).
5. **The build happened in traceable phases** — file/test names like `test_pricing_phase1e_wiring.py`, `test_pricing_phase2b_wiring.py` map to `docs/dynamic-pricing-execution-plan.md`'s phase log, so you can point to *when* and *why* a given piece was added, not just that it exists.

---

## 6. The category-name bug (good "gotcha" story for Q&A)

**What happened:** The real database (owned by the Spring Boot service) stores
equipment categories using business-friendly names — `"Fork Lift"`,
`"Scissors Lift"`, `"Boom Lift"`, `"Excavator"`. The trained model's one-hot
feature columns use a different, ML-convention naming —
`"forklift"`, `"scissor lift"`, `"boom lift"`, `"excavator"` — baked in at
training time (see `feature_schema.CATEGORIES`).

`compute_period_utilization()`'s original query joined
`AssetCategory.name == category` using the ML-convention string. That join
**never matched a single real row**, silently falling back to a static
per-category utilization constant every single time — no exception, no
degraded flag, so it looked like it was working.

**The fix:** [`category_mapping.py`](../app/services/pricing/category_mapping.py) —
a small explicit two-way mapping dict (`DB_NAME_TO_FEATURE_NAME` /
`FEATURE_NAME_TO_DB_NAME`), with `to_feature_name()`/`to_db_name()` raising
`KeyError` loudly on an unrecognized name instead of silently mismatching.
Direction matters: the DB name is the source of truth (owned by another
service's business data), the ML slug is the derived form — so the fix
normalizes at the boundary, and never renames the DB values to match the
model.

**Why it's a good story:** it shows the kind of bug that's easy for an
AI-agent-generated integration to introduce silently (two naming conventions
that both look "fine" in isolation, fail only at the join), and that it was
caught by actually querying the live database rather than trusting unit
tests alone. Full writeup: `openspec/specs/dynamic-pricing/design.md`,
section "Category name mapping".

---

## 7. Quick cheat-sheet (fastest lookup table)

| If asked... | Open this file, go to... |
|---|---|
| "Show me the prediction function" | `model.py` → `predict_price()` |
| "Show me the training code" | `train.py` → `train()` |
| "Show me the retrain job" | `retrain_job.py` → `run_scheduled_retrain()` |
| "How often / what triggers retraining" | `scheduler.py` → `build_scheduler()` |
| "How do you validate a new model before deploying it" | `promotion_gate.py` → `assess_gate()` |
| "What features does the model use" | `feature_schema.py` (top-of-file docstring + `FEATURE_COLUMNS`) |
| "How are guardrails enforced" | `model.py` line ~225 (the `min()`/`max()` clamp) |
| "How is 'how booked up is similar equipment' computed" | `repository.py` → `compute_period_utilization()` |
| "What if the DB is down / mid-sync" | `read_resilience.py` → `resolve_pricing_schema()` |
| "Where's the actual API route" | `api/internal_pricing.py` |
| "How does this connect to recommendations" | `recommendations.py` → `_recommend_for_unit_need()`, `predict_price_adapter.py` |
| "Any real bugs you found" | §6 above — category name mapping |
| "Where's the trained model file" | `app/services/pricing/artifacts/model.pkl` + `current.json` |
| "How do you mix real and synthetic training data" | `blend.py` → `build_training_dataset()` |
| "Where does real training data come from" | `real_training.py` → `fetch_real_training_rows()` |

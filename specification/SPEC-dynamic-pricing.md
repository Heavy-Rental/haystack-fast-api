# Specification: Dynamic Pricing

| Field | Value |
|-------|--------|
| **Document type** | SDD feature spec |
| **Status** | Draft — Phase 2 (productionize) and Phase 3 (seeding + scheduled retrain) not yet implemented |
| **Feature module** | `app/services/pricing/` (to be created) |
| **Depends on** | [`SPEC-project-setup.md`](./SPEC-project-setup.md) — environment, layering, uv, Postgres (normative) |
| **Related, not specs** | `docs/dynamic-pricing-masterplan.md` (decision log — this spec restates only what Phase 2 needs to build against, not the full reasoning trail) and `docs/dynamic-pricing-execution-plan.md` (day-by-day tasks/branches) |
| **Built on** | `ml-experiments/` — Phase 1 offline experimentation (scratch, outside SDD, no spec). This spec productionizes the model and feature schema already trained and validated there. |
| **Explicitly out of scope here** | `SPEC-domain-seed-data.md` (Phase 3 seed *data* — not yet written; separate spec since the schema is shared across other features). The Phase 3 **blend/cutover design decision** for this model (§5.8) is in scope here, distinct from seed data itself. |

**Read [`SPEC-project.md`](./SPEC-project.md) and [`SPEC-project-setup.md`](./SPEC-project-setup.md) before this document.**

> **Phase 1c note (2026-08-05):** `ml-experiments/predict_price.py` prototypes this spec's `predict_price(...)` contract early — guardrail clamping included — so the in-development agent prototype can call it before Phase 2 (this spec) lands. It remains `ml-experiments/` scratch code, out of SDD scope like the rest of Phase 1, and its guardrail bounds are a **static per-category stand-in** (`pricing_tables.CATEGORY_BASE_RATE`), not the real per-asset `Asset.minDailyRate`/`maxDailyRate` this spec requires (§5.4). It is fully superseded once this spec is implemented — do not treat it as satisfying any requirement in §4.

---

## 1. Purpose

Phase 1 (`ml-experiments/`) produced and validated a baseline XGBoost model that predicts `price_per_day` for equipment rentals from `category`, `condition`, `duration_days`, `capacity`, `distance_km`, and `platform_height`. Phase 1d added two real-time features on top of that static baseline — `period_utilization` and `lead_time_days` — so the model responds to live supply/demand rather than asset attributes alone. This spec defines how that model and its feature schema get **productionized** into `app/services/pricing/` so the agentic recommendation pipeline can call it in-process and persist a data-driven price suggestion, without duplicating the decision log in `docs/dynamic-pricing-masterplan.md`.

---

## 2. Outcomes

When this spec is implemented:

- `app.pipelines` (or wherever the agentic recommendation step lives) can call a single in-process function to get a guardrail-clamped price prediction for a given asset/booking combination.
- The model output is **price per day** for a given duration window. There is **no** public `/predict-price` renter route (in-process only). The recommendation pipeline may surface structured pricing on `item.pricing` for the portal mockup: **`daily_rate`** (duration-scoped prediction) and app-layer **`total_price` = `daily_rate × duration_days`** — not a fabricated weekly rate. Persistence field `RecommendationItem.mlPredictedPrice` remains the production landing place when Spring-backed models exist.
- A manual "retrain now" path exists as a demo safety net, without requiring the full APScheduler-based scheduled retrain (Phase 3).
- The feature schema, encoding rules, and artifact format match what Phase 1b already validated — no silent re-derivation of decisions already locked in the masterplan.

---

## 3. Scope

### In scope
- `app/services/pricing/` package: `model.py` (load + predict), `train.py` (retrain), `feature_schema.py` (ported from `ml-experiments/feature_schema.py`), `artifacts/` (`.pkl` + `current.json`).
- Guardrail clamping of the raw model output to `Asset.minDailyRate`/`Asset.maxDailyRate`.
- An in-process `predict_price(...)` function, called directly from the pipeline — not an HTTP route.
- A manual "retrain now" endpoint (internal/ops use, not renter-facing).
- Minimal SQLAlchemy read models for exactly the columns pricing touches (see §5.3) — mapped onto the existing Spring-Boot-owned schema, no new tables, no Alembic. Includes `Booking.startDate`/`endDate`/`status` and `Asset.category_id`/`capacity`/`platform_height`, needed ahead of the rest of this package for `period_utilization`'s live query (Phase 1e, see §5.3).
- Unit tests: feature schema transforms, guardrail clamping, prediction shape.

### Out of scope (this spec)
- `/predict-price` as a public HTTP endpoint (masterplan: resolved as in-process function call).
- Full APScheduler scheduled retrain (Phase 3).
- Real geocoding for `distance_km` (Phase 1 uses a sampled proxy; still true in Phase 2 — no live bookings to geocode against yet).
- `purchaseYear` as a feature (evaluated in Phase 1b, not added — see masterplan).
- `booking_month`/seasonality as a feature (evaluated in Phase 1d, not added — `period_utilization` already captures realized seasonality; see §5.2, §8, masterplan).
- Fuel price as a feature (considered and rejected in Phase 1d — see §8).
- Seed data (`SPEC-domain-seed-data.md`, separate spec).
- Any renter-facing pricing UI/API.

---

## 4. Requirements

**US-1 — Pipeline gets a price prediction**
As the agentic recommendation pipeline, when I have a candidate asset and a proposed booking (duration, distance), I need a predicted `price_per_day` so the recommendation includes a data-driven price.

- GIVEN a valid asset (with `category`, `condition`, `capacity`, and — for scissor lift/boom lift — `platform_height`) and a proposed `duration_days`/`distance_km`
  WHEN the pipeline calls `predict_price(...)`
  THEN it receives a numeric `price_per_day` clamped to `[Asset.minDailyRate, Asset.maxDailyRate]`.

- GIVEN an asset whose category is forklift or excavator (no `platform_height`)
  WHEN `predict_price(...)` is called
  THEN `platform_height` is passed through as missing (NaN), not a sentinel — matching how the model was trained (§5.2), and prediction succeeds.

- GIVEN the raw model output falls outside `[minDailyRate, maxDailyRate]`
  WHEN guardrail clamping runs
  THEN the returned price is clamped to that range, matching how `price_per_day` was itself generated in the Phase 1 training data (already guardrail-clamped — see `ml-experiments/generate_synthetic_data.py`).

- GIVEN a candidate asset and a proposed rental window (`start_date`/`end_date`)
  WHEN `predict_price(...)` is called
  THEN `period_utilization` is computed as a live aggregate — the fraction of assets in the same `category` + spec-band (bucketed from `capacity`/`platform_height`, §5.2) with a `CONFIRMED`/`PENDING`, non-cancelled booking overlapping the requested window — not a forecast, and not a static per-category constant.

- GIVEN a proposed `start_date`
  WHEN `predict_price(...)` is called
  THEN `lead_time_days = start_date − today` is computed and passed as a feature; no new persisted column is required.

- GIVEN a rental window that no other booking currently overlaps
  WHEN `period_utilization` is computed
  THEN a low value (and often a lower predicted price) is the **correct, intended** result — the same scarcity-pricing mechanism airline/hotel pricing uses, where booking early into an unclaimed window is rewarded with a lower price. This is not an early-bird bug to "fix."

**US-2 — Manual retrain as a demo safety net**
As an operator, I need to trigger a retrain on demand (without redeploying) so a stale model can be refreshed before a demo, ahead of the real scheduled retrain landing in Phase 3.

- GIVEN new/updated historical booking data is available
  WHEN the manual retrain path is invoked
  THEN `train.py`'s logic runs, `artifacts/model.pkl` and `artifacts/current.json` are overwritten, and subsequent `predict_price(...)` calls use the new model without an app restart.

**US-3 — Prediction never reaches renters directly**
As the system, I must not expose raw or clamped model predictions through any renter-facing route.

- GIVEN the pricing service
  WHEN it is called
  THEN it is only ever invoked from `app.pipelines` (or a protected internal/ops path for retrain), never from a public router.

---

## 5. Design

### 5.1 Architecture

Per the masterplan's locked decision: `predict_price(...)` is an **in-process Python function call**, not an HTTP endpoint — no auth, serialization, or separate test client overhead, since the pipeline and pricing service share ownership. Lives at `app.services.pricing`, called directly from `app.pipelines`.

```
app/services/pricing/
├── __init__.py
├── model.py           # load current.json + model.pkl once, expose predict_price(...)
├── train.py            # retrain entrypoint (ports ml-experiments/train.py's logic)
├── feature_schema.py   # ports ml-experiments/feature_schema.py near-verbatim
└── artifacts/
    ├── model.pkl
    └── current.json
```

### 5.2 Feature schema (locked, from Phase 1b + Phase 1d)

Ports `ml-experiments/feature_schema.py` directly — same `CATEGORIES`, `CONDITION_ORDER`, `FEATURE_COLUMNS`, `build_features()`/`get_target()` logic. No changes expected beyond adapting the input from a `pandas.DataFrame` (CSV-sourced in Phase 1) to a single row/dict sourced from ORM objects (§5.3).

| Feature | Encoding | Notes |
|---|---|---|
| `category` | one-hot, fixed `CATEGORIES` order | via `AssetCategory.name`; never encode the raw FK |
| `condition` | ordinal, `NEEDS_REPAIR=0…EXCELLENT=3` | `Asset.condition` |
| `duration_days` | numeric passthrough | `Booking.endDate − Booking.startDate` |
| `capacity` | numeric passthrough | `Asset.capacity` |
| `distance_km` | numeric passthrough | Phase 1/2: still a sampled proxy, not geocoded (see Scope) |
| `platform_height` | numeric, **NaN for forklift/excavator** | `Asset.platform_height`; left as a native missing value for XGBoost, not imputed — see masterplan for why |
| `period_utilization` | numeric passthrough, `[0,1]` | Live aggregate over same `category` + spec-band (see below); status `CONFIRMED`/`PENDING`, non-cancelled; computed at prediction time — **Phase 1d/1e**, not a Phase 1b feature |
| `lead_time_days` | numeric passthrough | `Booking.startDate − today`; derived, no new column — **Phase 1d** |

Target: `price_per_day` (training-time only; not part of the prediction input).

**Spec-band sub-categorization (Phase 1d), for `period_utilization`.** Grouping by raw `category` alone would be misleading — a fully-booked small-excavator fleet shouldn't make a large excavator look scarce. Utilization is computed at category + spec-band instead: excavator/forklift key primarily off `capacity`, scissor lift/boom lift key primarily off `platform_height`. Band boundaries are **fixed constants** (`pricing_tables.CAPACITY_BINS`/`HEIGHT_BINS`), grounded in load-class/aerial-lift-catalog height-tier conventions (cited in `generate_synthetic_data.py`'s References docstring, same standard as the existing rate-card/monsoon/BCA citations) — not dynamically derived from the current fleet's distribution. Bands are computed on the fly from the existing `capacity`/`platform_height` columns; **no new persisted band column**. The exact boundary values and band count are **not locked to any specific numbers in this spec** — they're set by whoever implements Phase 1d, cross-checked against the ranges already in `pricing_tables.CATEGORY_CAPACITY_KG`/`CATEGORY_PLATFORM_HEIGHT_M` so bands actually partition the fleet, and empirically sanity-checked via `generate_synthetic_data.py --strict`.

**Scarcity pricing is intentional, not a bug (Phase 1d).** An early booking on a not-yet-claimed window legitimately produces a lower `period_utilization`, and often a lower predicted price — the same mechanism airline/hotel pricing uses. Do not "fix" this as an early-bird pricing bug.

**Resolved (Phase 1d): `booking_month`/seasonality — not added.** Previously an open decision (Phase 1b found a mild per-`booking_month` pattern, January worst, but small enough the lean was against adding it). Now closed: `period_utilization` already captures realized seasonal demand — the monsoon-season dip shows up directly as lower utilization for outdoor/earthmoving categories — so a separate calendar feature would be largely redundant with a live signal the model can already use. See `docs/dynamic-pricing-masterplan.md`'s changelog for the full reasoning.

### 5.3 Data access (open item — confirm before implementing)

Pricing needs read access to `AssetCategory.name`, `Asset.category_id`/`capacity`/`condition`/`platform_height`/`minDailyRate`/`maxDailyRate`, and `Booking.startDate`/`endDate`/`status` (the last needed for `period_utilization`'s overlap query, §5.2), plus write access to `RecommendationItem.mlPredictedPrice`. **`app/models/` currently has no concrete models** — just a `Base` re-export placeholder. Per the masterplan, Spring Boot owns the schema/migrations; Python maps onto the existing tables (no Alembic, no new tables).

Before implementing `model.py`, confirm against the actual Spring Boot schema (not just the ERD/Class Diagram field names referenced in the masterplan):
- Exact table/column names and casing (the masterplan's field list is diagram-sourced, e.g. `purchaseYear`/`baseDailyRate` read as camelCase — confirm whether the real Postgres columns are camelCase or snake_case).
- Whether `Asset.platform_height` exists as a real column yet, or needs to be added by whoever owns that migration.
- **(Phase 1d/1e)** Whether `BookingStatus` actually has a `CONFIRMED` member — only `PENDING`/`CANCELLED` are ever named anywhere in this repo, but `period_utilization`'s overlap query (§5.2) requires filtering on `CONFIRMED`/`PENDING`, non-cancelled bookings.

Introduce only the minimal SQLAlchemy declarative models pricing actually reads/writes (not a full domain model set) — narrow surface, less staleness risk if the shared schema evolves elsewhere.

**Phase 1e note**: `period_utilization`'s live query is pulled forward ahead of the rest of this package — it lives in `app/repositories/pricing_repository.py`, backed by the first-ever read-only SQLAlchemy models in this repo (`app/models/asset_category.py`/`asset.py`/`booking.py`), wired into the *existing* prototype call path (`app/services/pricing_client.py` → `ml-experiments/predict_price.py`) rather than waiting for `app/services/pricing/model.py` to exist. When this package is built, it **relocates** that repository logic rather than rebuilding it.

### 5.4 Guardrail clamping

```
predicted = model.predict(features)
clamped = min(max(predicted, asset.minDailyRate), asset.maxDailyRate)
```

Read per-asset at prediction time (admin-editable via the asset's admin-portal tag) — no separate config table or env var.

### 5.5 Artifact contract

`current.json` shape is already implemented and validated in `ml-experiments/artifacts/current.json` — reuse as-is:

```json
{
  "trained_at": "...",
  "feature_columns": [...],
  "condition_order": {...},
  "categories": [...],
  "target_column": "price_per_day",
  "hyperparameters": {...},
  "metrics": {"mae": ..., "rmse": ..., "r2": ...},
  "row_counts": {...},
  "data_source": "..."
}
```

`model.py` loads `model.pkl` + `current.json` once (module-level or app-lifespan-scoped), not per-request.

### 5.6 Reference metrics (Phase 1b baseline, synthetic data)

Offline-only, on synthetic data — expect this to move once Phase 3 seeds real historical bookings. Recorded here so a Phase 2 regression is easy to notice:

| Category | MAE | R² |
|---|---|---|
| scissor lift | 5.49 | 0.969 |
| excavator | 17.99 | 0.947 |
| boom lift | 11.56 | 0.954 |
| forklift | 4.80 | 0.958 |
| **Overall** | **9.95** | **0.976** |

### 5.7 Security notes

No auth stack exists yet in this codebase (`SPEC-project-setup.md` §5.4). The manual retrain path (US-2) must **not** be registered as a public route until a real auth SDD exists — restrict it at the network/ops level in the interim (e.g. not exposed to renter clients), and flag this explicitly if it needs to be demoed publicly before auth lands.

### 5.8 Phase 3 — cold-start bootstrap, blend, per-category cutover (design decision)

A fresh deployment has no real transaction history. `period_utilization`/`lead_time_days` are always live-computable even with few bookings, but the model's *learned price-response function* still needs something to have taught it how to weigh those features — that has to be grounded synthetic data until real history exists. Resolution rides on the Phase 3 scheduled retrain job already scoped in `docs/dynamic-pricing-masterplan.md`/`docs/dynamic-pricing-execution-plan.md` — **not a new mechanism**:

- **Bootstrap (now)**: 100% grounded synthetic data. Guardrail clamping (`Asset.minDailyRate`/`maxDailyRate`) bounds worst-case error in the meantime.
- **Blend**: extend the Phase 3 retrain job's `train.py` call with sample weighting by data source/recency (`model.fit(X, y, sample_weight=...)`) — real data weighted higher as its volume grows. **Design decision only — no code change until real data exists to weight against**; writing the weighting logic now would be dead code.
- **Cutover**: per category, not all at once. Each category (excavator, forklift, scissor lift, boom lift) drops its synthetic rows independently once it clears its own minimum real-sample threshold (exact threshold TBD, non-blocking open item). Categories graduate at different rates on purpose — e.g. forklifts likely accumulate real bookings faster than excavators.

Full reasoning trail lives in `docs/dynamic-pricing-masterplan.md`'s Phase 3 section, per this spec's own precedence convention (§header table "Related, not specs") — this subsection restates only the contract Phase 3 needs to build against.

---

## 6. Verification

- Unit tests (new, under `tests/`): feature schema transforms (one-hot columns, ordinal mapping, NaN passthrough for non-aerial `platform_height`), guardrail clamping (below-min, above-max, in-range cases), prediction output shape/type.
- Manual smoke: call `predict_price(...)` for one asset per category (mirroring `ml-experiments/shap_review.py`'s per-category sweeps) and confirm clamped output is within `[minDailyRate, maxDailyRate]`.
- Manual retrain smoke: invoke the retrain path, confirm `artifacts/current.json`'s `trained_at` updates and a subsequent prediction reflects the new model.
- Regression check: re-run `ml-experiments/category_metrics.py`-equivalent logic (or port it) against the productionized model periodically; flag if any category's MAE/R² drifts materially from §5.6.

---

## 7. Implementation tasks

Maps to `docs/dynamic-pricing-execution-plan.md`'s Day 4–5 subtasks:

1. `feature/ml-3-pricing-service` (Day 4): scaffold `app/services/pricing/`, port `feature_schema.py` (already includes `period_utilization`/`lead_time_days`/`spec_band()` from Phase 1d), implement `model.py`/`train.py`, guardrail clamping, minimal SQLAlchemy read models (§5.3 — confirm schema first; relocates, doesn't rebuild, Phase 1e's `pricing_repository.py`).
2. `feature/ml-4-integration-tests` (Day 5 AM): wire `predict_price(...)` into `app.pipelines` → persist `RecommendationItem.mlPredictedPrice`; unit tests per §6; manual retrain endpoint.

---

## 8. Key decisions / non-goals

Full rationale lives in `docs/dynamic-pricing-masterplan.md` — summarized here for implementers who only read this spec:

| Decision | Why |
|---|---|
| In-process function, not HTTP route | Same owner for pipeline + pricing service; no cross-team contract to negotiate |
| Guardrails via `Asset.minDailyRate`/`maxDailyRate`, not a config table | Already admin-editable per asset; matches how training data itself was clamped |
| `platform_height` as native NaN, not imputed | Correct tool for "structurally not applicable"; XGBoost's missing-value routing was built for this |
| No Alembic / no new tables | Spring Boot owns schema; Python maps onto existing tables only |
| Sync SQLAlchemy + psycopg only | Matches `SPEC-project-setup.md`'s environment default; no async wiring for this feature |
| Manual retrain now, full APScheduler later | Demo safety net now; scheduled retrain is Phase 3 scope |
| `period_utilization` and `lead_time_days` both kept, despite being correlated | They answer different questions (is this window already claimed vs. how much notice did the booker give); a SHAP review (Phase 1d) compares which the model actually leans on, rather than assuming and dropping one upfront |
| `period_utilization` grouped by category **+ spec-band**, not raw category | A fully-booked small-excavator fleet shouldn't make a large excavator look scarce; excavator/forklift key off `capacity`, scissor/boom lift key off `platform_height` |
| Spec-band boundaries are fixed constants, not derived from current fleet distribution | Stable, reproducible bucketing that doesn't drift as the fleet composition changes; grounded in load-class/aerial-catalog-tier conventions (see `generate_synthetic_data.py` References) |
| `booking_month`/seasonality: resolved, **not added** | `period_utilization` already captures realized seasonality (monsoon dip shows up as lower utilization) — a calendar feature would be largely redundant |
| Fuel price: considered and **rejected** as a feature | Indirect/lagged signal (fuel cost → construction activity → demand, not a direct per-booking effect); would require a new external API dependency, conflicting with the in-process/no-outbound-calls architecture; on synthetic data specifically would be untrainable noise unless the generator fabricates a fuel-price-to-price correlation — a shakier "did you just make this up" risk than the existing grounded references |

**Non-goals**: renter-facing pricing API/UI, real geocoding, `purchaseYear` feature, `booking_month`/seasonality feature, fuel-price feature, Alembic migrations, async DB access, full auth/JWT stack (blocks nothing here, but the retrain path should not assume it's protected until one exists).

---

## 9. Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-04 | Initial draft, written at the Phase 1→2 boundary per the masterplan's phase order. Productionization plan for the Phase 1b-validated model (category/condition/duration_days/capacity/distance_km/platform_height, R²=0.976 overall on synthetic holdout). Not yet implemented — `app/services/pricing/` does not exist yet. |
| 1.1.0 | 2026-08-04 | Added `booking_month`/seasonality as an explicit open decision (§5.2, §8) carried into implementation task 1 (§7) — a per-`booking_month` MAE/R² check in Phase 1b found a mild pattern worth a deliberate call, not locked either way. |
| 1.2.0 | 2026-08-05 | Added Phase 1c disambiguation note (after header table) — `ml-experiments/predict_price.py` prototypes this spec's contract early for the upcoming agent prototype, with static per-category guardrail bounds standing in for the real per-asset clamp this spec requires. No change to scope, requirements, or design — this spec's implementation is still Phase 2, not started. |
| 1.2.1 | 2026-08-06 | Clarified outcomes: no public `/predict-price`; recommend API may expose `daily_rate` + app-layer `total_price` (not fabricated weekly); model still predicts per-day only. |
| 1.3.0 | 2026-08-07 | Phase 1d/1e: added `period_utilization` (live category+spec-band booking-overlap aggregate, computed at prediction time, not a forecast) and `lead_time_days` (derived from `start_date − today`) to the feature schema (§5.2), plus fixed-constant spec-band bucketing (excavator/forklift by `capacity`, scissor/boom lift by `platform_height`) with no new persisted column. Documented that early-booking scarcity pricing is intentional, not a bug. Resolved `booking_month`/seasonality as **not added** (§5.2, §8) — superseded by `period_utilization`. Documented fuel price as considered-and-rejected (§3, §8). Added §5.8, a Phase 3 cold-start bootstrap → blend → per-category cutover design decision (no code yet). Added a third "confirm before implementing" open item to §5.3 (`BookingStatus.CONFIRMED` membership) and noted `period_utilization`'s live query is pulled forward into Phase 1e (`app/repositories/pricing_repository.py` + first-ever read-only SQLAlchemy models), ahead of and later relocated into this package. Clarified the header table's "out of scope" framing to distinguish seed *data* (still out of scope) from the Phase 3 design decision itself (in scope via §5.8). |

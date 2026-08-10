# Dynamic Pricing Specification

| Field | Value |
|-------|--------|
| **Status** | Draft — Phase 2 (productionize) and Phase 3 (seeding + scheduled retrain) not yet implemented |
| **Feature module** | `app/services/pricing/` (to be created) |
| **Standards** | OpenSpec · Spec-kit user stories · OpenSPDD (see [`design.md`](./design.md)) |
| **Depends on** | [`../project-setup/spec.md`](../project-setup/spec.md) |
| **Related, not specs** | `docs/dynamic-pricing-masterplan.md` (decision log); `docs/dynamic-pricing-execution-plan.md` (day-by-day tasks) |
| **Built on** | `ml-experiments/` — Phase 1 offline experimentation (scratch, outside SDD) |
| **Related capabilities** | [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md); [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) |
| **Legacy source** | `specification/SPEC-dynamic-pricing.md` |

**Read** [`../../project.md`](../../project.md) and [`../project-setup/spec.md`](../project-setup/spec.md) before this document.

> **Phase 1c note (2026-08-05):** `ml-experiments/predict_price.py` prototypes this capability’s `predict_price(...)` contract early — guardrail clamping included — so the in-development agent prototype can call it before Phase 2 lands. It remains `ml-experiments/` scratch code, out of SDD scope like the rest of Phase 1, and its guardrail bounds are a **static per-category stand-in** (`pricing_tables.CATEGORY_BASE_RATE`), not the real per-asset `Asset.minDailyRate`/`maxDailyRate` this spec requires. It is fully superseded once this capability is implemented — do not treat it as satisfying any requirement below.

---

## Purpose

Phase 1 (`ml-experiments/`) produced and validated a baseline XGBoost model that predicts `price_per_day` for equipment rentals from `category`, `condition`, `duration_days`, `capacity`, `distance_km`, and `platform_height`. Phase 1d added two real-time features — `period_utilization` and `lead_time_days` — so the model responds to live supply/demand rather than asset attributes alone. This capability defines how that model and its feature schema get **productionized** into `app/services/pricing/` so the agentic recommendation pipeline can call it in-process and persist a data-driven price suggestion, without duplicating the decision log in `docs/dynamic-pricing-masterplan.md`.

---

## Outcomes

When this capability is implemented:

- `app.pipelines` (or wherever the agentic recommendation step lives) can call a single in-process function to get a guardrail-clamped price prediction for a given asset/booking combination.
- The model output is **price per day** for a given duration window. There is **no** public `/predict-price` renter route (in-process only). The recommendation pipeline may surface structured pricing on `item.pricing` for the portal mockup: **`daily_rate`** (duration-scoped prediction) and app-layer **`total_price` = `daily_rate × duration_days`** — not a fabricated weekly rate. Persistence field `RecommendationItem.mlPredictedPrice` remains the production landing place when Spring-backed models exist.
- A manual "retrain now" path exists as a demo safety net, without requiring the full APScheduler-based scheduled retrain (Phase 3).
- The feature schema, encoding rules, and artifact format match what Phase 1b already validated — no silent re-derivation of decisions already locked in the masterplan.

---

## Scope

### In scope

- `app/services/pricing/` package: `model.py` (load + predict), `train.py` (retrain), `feature_schema.py` (ported from `ml-experiments/feature_schema.py`), `artifacts/` (`.pkl` + `current.json`).
- Guardrail clamping of the raw model output to `Asset.minDailyRate`/`Asset.maxDailyRate`.
- An in-process `predict_price(...)` function, called directly from the pipeline — not an HTTP route.
- A manual "retrain now" endpoint (internal/ops use, not renter-facing).
- Minimal SQLAlchemy read models for exactly the columns pricing touches — mapped onto the existing Spring-Boot-owned schema, no new tables, no Alembic. Includes `Booking.startDate`/`endDate`/`status`, `BookingItem.assetId` (the actual booking↔asset link), and `Asset.category_id`/`capacity`/`platform_height`, needed for `period_utilization`'s live query. **Implemented** (2026-08-10, Phase 1e): `app/models/asset_category.py`/`asset.py`/`booking.py`/`booking_item.py`; `app/repositories/pricing_repository.py`; `app/repositories/pricing_read_resilience.py` (tiered fallback, see [`design.md`](./design.md)).
- Unit tests: feature schema transforms, guardrail clamping, prediction shape.

### Out of scope (this capability)

- `/predict-price` as a public HTTP endpoint (masterplan: resolved as in-process function call).
- Full APScheduler scheduled retrain (Phase 3).
- Real geocoding for `distance_km` (Phase 1 uses a sampled proxy; still true in Phase 2).
- `purchaseYear` as a feature (evaluated in Phase 1b, not added — see masterplan).
- `booking_month`/seasonality as a feature (evaluated in Phase 1d, not added — `period_utilization` already captures realized seasonality).
- Fuel price as a feature (considered and rejected in Phase 1d).
- Seed data (`SPEC-domain-seed-data.md`, separate spec — not yet written). The Phase 3 **blend/cutover design decision** for this model is in scope via design (§5.8 / REASONS Approach), distinct from seed data itself.
- Any renter-facing pricing UI/API.

---

## User Scenarios & Testing

### User Story 1 - Pipeline gets a price prediction (Priority: P1)

As the agentic recommendation pipeline, when I have a candidate asset and a proposed booking (duration, distance), I need a predicted `price_per_day` so the recommendation includes a data-driven price.

**Independent Test:** Unit tests for feature transforms, guardrail clamp, and prediction shape; call `predict_price(...)` for one asset per category.

**Acceptance Scenarios:**

1. **Given** a valid asset (with `category`, `condition`, `capacity`, and — for scissor lift/boom lift — `platform_height`) and a proposed `duration_days`/`distance_km`, **When** the pipeline calls `predict_price(...)`, **Then** it receives a numeric `price_per_day` clamped to `[Asset.minDailyRate, Asset.maxDailyRate]`.

2. **Given** an asset whose category is forklift or excavator (no `platform_height`), **When** `predict_price(...)` is called, **Then** `platform_height` is passed through as missing (NaN), not a sentinel — matching how the model was trained, and prediction succeeds.

3. **Given** the raw model output falls outside `[minDailyRate, maxDailyRate]`, **When** guardrail clamping runs, **Then** the returned price is clamped to that range, matching how `price_per_day` was itself generated in the Phase 1 training data (already guardrail-clamped — see `ml-experiments/generate_synthetic_data.py`).

4. **Given** a candidate asset and a proposed rental window (`start_date`/`end_date`), **When** `predict_price(...)` is called, **Then** `period_utilization` is computed as a live aggregate — the fraction of assets in the same `category` + spec-band (bucketed from `capacity`/`platform_height`) with a `CONFIRMED`/`PENDING`, non-cancelled booking overlapping the requested window — not a forecast, and not a static per-category constant.

5. **Given** a proposed `start_date`, **When** `predict_price(...)` is called, **Then** `lead_time_days = start_date − today` is computed and passed as a feature; no new persisted column is required.

6. **Given** a rental window that no other booking currently overlaps, **When** `period_utilization` is computed, **Then** a low value (and often a lower predicted price) is the **correct, intended** result — airline/hotel-style scarcity pricing; not an early-bird bug to "fix."

7. **Given** `primary_snapshot` is transiently unavailable (mid-recreate), **When** `predict_price(...)` reads it, **Then** the read is retried with a short bounded backoff before falling back further, and a prediction is still returned undegraded once the retry succeeds.

8. **Given** `primary_snapshot` is unavailable beyond that retry window (a failed sync cycle, not a brief mid-recreate gap), **When** `predict_price(...)` reads any `primary_snapshot`-sourced value, **Then** all reads for that call consistently fall back to `public` instead, and the resulting price is marked degraded rather than presented as equivalent to a live-source prediction.

9. **Given** neither `primary_snapshot` nor `public` has the needed schema/relation (cold start), **When** `predict_price(...)` is called, **Then** it fails loud (raises) rather than returning a fabricated price.

### User Story 2 - Manual retrain as a demo safety net (Priority: P2)

As an operator, I need to trigger a retrain on demand (without redeploying) so a stale model can be refreshed before a demo, ahead of the real scheduled retrain landing in Phase 3.

**Independent Test:** Invoke retrain path; confirm `artifacts/current.json` `trained_at` updates and subsequent prediction reflects new model.

**Acceptance Scenarios:**

1. **Given** new/updated historical booking data is available, **When** the manual retrain path is invoked, **Then** `train.py`'s logic runs, `artifacts/model.pkl` and `artifacts/current.json` are overwritten, and subsequent `predict_price(...)` calls use the new model without an app restart.

### User Story 3 - Prediction never reaches renters directly (Priority: P1)

As the system, I must not expose raw or clamped model predictions through any renter-facing route.

**Independent Test:** Code review / route inventory — no public `/predict-price`.

**Acceptance Scenarios:**

1. **Given** the pricing service, **When** it is called, **Then** it is only ever invoked from `app.pipelines` (or a protected internal/ops path for retrain), never from a public renter router.

---

## Requirements

### Requirement: In-process predict_price for pipeline (US-1)

The pricing package SHALL expose an in-process `predict_price(...)` function returning a numeric `price_per_day` for a given asset/booking combination, callable from the recommendation pipeline without a public HTTP renter route.

#### Scenario: Clamped prediction
- **GIVEN** a valid asset and proposed duration/distance
- **WHEN** `predict_price(...)` is called
- **THEN** the result is a numeric `price_per_day` clamped to `[Asset.minDailyRate, Asset.maxDailyRate]`

#### Scenario: Missing platform_height for non-aerial
- **GIVEN** forklift or excavator (no platform height)
- **WHEN** `predict_price(...)` is called
- **THEN** `platform_height` is NaN (native missing), not a sentinel, and prediction succeeds

#### Scenario: Guardrail clamp out of range
- **GIVEN** raw model output outside asset rate bounds
- **WHEN** guardrail clamping runs
- **THEN** returned price is within `[minDailyRate, maxDailyRate]`

### Requirement: Live period_utilization feature

`period_utilization` SHALL be computed at prediction time as the fraction of assets in the same `category` + spec-band with a `CONFIRMED`/`PENDING`, non-cancelled booking overlapping the requested window. It is not a forecast and not a static per-category constant.

#### Scenario: Live aggregate
- **GIVEN** a rental window and fleet bookings
- **WHEN** `predict_price(...)` runs
- **THEN** `period_utilization` reflects overlapping bookings in the same category + spec-band

#### Scenario: Scarcity pricing intentional
- **GIVEN** a window with no overlapping bookings
- **WHEN** period utilization is low
- **THEN** a lower predicted price is accepted as intended scarcity pricing (not a bug)

### Requirement: lead_time_days feature

`lead_time_days = start_date − today` SHALL be computed and passed as a feature; no new persisted column is required.

#### Scenario: Derived lead time
- **GIVEN** a proposed `start_date`
- **WHEN** `predict_price(...)` is called
- **THEN** `lead_time_days` is derived without a new DB column

### Requirement: Manual retrain path (US-2)

A manual "retrain now" path SHALL run `train.py` logic, overwrite `artifacts/model.pkl` and `artifacts/current.json`, and make subsequent `predict_price(...)` calls use the new model without app restart. The path MUST NOT be registered as a public renter route until auth SDD exists (network/ops restriction interim).

#### Scenario: Retrain hot-swap
- **WHEN** manual retrain is invoked successfully
- **THEN** `trained_at` updates and next predictions use the new model without restart

### Requirement: No renter-facing predict route (US-3)

Pricing predictions SHALL NOT be exposed through any renter-facing route. Invocation is limited to `app.pipelines` or protected internal/ops retrain.

#### Scenario: No public /predict-price
- **WHEN** public routers are inventoried
- **THEN** no renter-facing `/predict-price` endpoint exists

### Requirement: Surface pricing on recommend items (app-layer)

When recommend surfaces pricing, expose **`daily_rate`** (duration-scoped) and **`total_price` = `daily_rate × duration_days`**. MUST NOT fabricate **`weekly_rate`**. Model still predicts per-day only. Persistence: `RecommendationItem.mlPredictedPrice` when Spring-backed models exist.

#### Scenario: Recommend pricing fields
- **WHEN** recommend attaches pricing to a selected item
- **THEN** `daily_rate` and `total_price` are present (when include_pricing) and no fabricated weekly rate

### Requirement: Feature schema parity with Phase 1

Feature schema, encoding rules, and artifact format SHALL match Phase 1b/1d validation (`CATEGORIES`, `CONDITION_ORDER`, `FEATURE_COLUMNS`, `build_features()` / `get_target()`). No silent re-derivation of locked masterplan decisions.

#### Scenario: Same feature columns
- **WHEN** production `feature_schema` is used
- **THEN** it ports `ml-experiments/feature_schema.py` near-verbatim (row/dict from ORM instead of DataFrame)

### Requirement: Minimal ORM surface (no Alembic / no new tables)

Pricing SHALL use minimal SQLAlchemy read models mapped onto Spring-owned schema only — no new tables, no Alembic. Confirm real Postgres column names/casing and `BookingStatus.CONFIRMED` membership before implementing `model.py`.

#### Scenario: Spring owns schema
- **WHEN** pricing models are introduced
- **THEN** they map existing tables only; no Alembic migrations from this package

### Requirement: Sync SQLAlchemy + psycopg

Pricing data access SHALL use sync SQLAlchemy + psycopg (project-setup default); no async wiring for this feature without a dedicated SDD.

#### Scenario: Driver alignment
- **WHEN** pricing repositories query Postgres
- **THEN** they use the project sync engine path

### Requirement: Tiered read resilience against primary_snapshot

Every pricing DB read against `primary_snapshot` SHALL share one 3-tier fallback (retry on transient mid-recreate failure → degrade to reading `public` on sustained failure, marked degraded → fail loud on cold start), decided once per `predict_price(...)` call and applied to every read in that call — not resolved independently per query. Full design: [`design.md`](./design.md) "Read resilience: tiered fallback".

#### Scenario: Transient failure recovers
- **GIVEN** `primary_snapshot` is mid-recreate
- **WHEN** a read hits `UndefinedTable`
- **THEN** it retries with bounded backoff and returns an undegraded prediction on success

#### Scenario: Sustained failure degrades to public
- **GIVEN** `primary_snapshot` stays unavailable beyond the retry budget
- **WHEN** `predict_price(...)` reads pricing data
- **THEN** all reads for that call fall back to `public` and the result is marked degraded

#### Scenario: Cold start fails loud
- **GIVEN** neither `primary_snapshot` nor `public` has the needed relation
- **WHEN** `predict_price(...)` is called
- **THEN** it raises rather than returning a fabricated price

---

## Verification

- Unit tests (new, under `tests/`): feature schema transforms (one-hot columns, ordinal mapping, NaN passthrough for non-aerial `platform_height`), guardrail clamping (below-min, above-max, in-range cases), prediction output shape/type.
- Manual smoke: call `predict_price(...)` for one asset per category (mirroring `ml-experiments/shap_review.py`'s per-category sweeps) and confirm clamped output is within `[minDailyRate, maxDailyRate]`.
- Illustrative, non-exhaustive: `ml-experiments/demo_scenarios.py` — condition-effect and duration-effect scenario pairs, raw vs. guardrail-clamped output side by side. Not a substitute for unit tests or `shap_review.py`.
- Manual retrain smoke: invoke retrain path, confirm `artifacts/current.json` `trained_at` updates and subsequent prediction reflects the new model.
- Regression check: re-run `ml-experiments/category_metrics.py`-equivalent logic against the productionized model periodically; flag if any category's MAE/R² drifts materially from reference metrics in design.
- Read-resilience unit tests: mock the session/engine to raise `UndefinedTable` on demand. Cover all three tiers: (1) transient failure that clears within the retry budget still returns an undegraded prediction, (2) sustained failure falls back to `public` and the returned `PriceResult` is marked degraded, (3) both schemas unavailable raises rather than returning a price. Also cover that a single call never mixes sources across its reads.

---

## Implementation tasks

Maps to `docs/dynamic-pricing-execution-plan.md` Day 4–5 subtasks:

0. **Phase 1e — done (2026-08-10)**, on `HR-87-ml-2-d-production-db-wiring-for-period-utilization`: `app/models/asset_category.py`/`asset.py`/`booking.py`/`booking_item.py`, `app/repositories/pricing_repository.py`, `app/repositories/pricing_read_resilience.py`, wired through `pricing_client.py` → `predict_price_adapter.py` → `recommendations.py`. Not wired into `app/api/recommendations.py` — no route calls `RecommendationService` yet (tests only); `RecommendationService.__init__`'s new `db` param is ready for when that route lands. 20 new unit tests.
1. `feature/ml-3-pricing-service` (Day 4): scaffold `app/services/pricing/`, port `feature_schema.py` (includes `period_utilization`/`lead_time_days`/`spec_band()` from Phase 1d), implement `model.py`/`train.py`, guardrail clamping, **relocate** (don't rebuild) Phase 1e's read models/`pricing_repository.py`/`pricing_read_resilience.py` into this package — the guardrail-bound `Asset` read must go through the same resolver, not a second fallback implementation.
2. `feature/ml-4-integration-tests` (Day 5 AM): wire `predict_price(...)` into `app.pipelines` → persist `RecommendationItem.mlPredictedPrice`; unit tests per Verification; manual retrain endpoint.

---

## Key decisions / non-goals

Full rationale: `docs/dynamic-pricing-masterplan.md`. Summary for implementers:

| Decision | Why |
|---|---|
| In-process function, not HTTP route | Same owner for pipeline + pricing service; no cross-team contract to negotiate |
| Guardrails via `Asset.minDailyRate`/`maxDailyRate`, not a config table | Already admin-editable per asset; matches how training data itself was clamped |
| `platform_height` as native NaN, not imputed | Correct tool for "structurally not applicable"; XGBoost missing-value routing |
| No Alembic / no new tables | Spring Boot owns schema; Python maps onto existing tables only |
| Sync SQLAlchemy + psycopg only | Matches project-setup environment default |
| Manual retrain now, full APScheduler later | Demo safety net now; scheduled retrain is Phase 3 |
| `period_utilization`/`lead_time_days` both kept, despite correlation | Answer different questions; SHAP compares which the model leans on |
| `period_utilization` grouped by category **+ spec-band** | Raw category alone is misleading (small vs. large excavator) |
| Spec-band boundaries are fixed constants | Reproducible, don't drift with fleet composition |
| `booking_month`/seasonality: resolved, **not added** | `period_utilization` already captures realized seasonality |
| Fuel price: considered and **rejected** | Indirect/lagged signal, new external API, untrainable on synthetic without fabricated correlation |

**Non-goals**: renter-facing pricing API/UI, real geocoding, `purchaseYear` feature, `booking_month`/seasonality feature, fuel-price feature, Alembic migrations, async DB access, full auth/JWT stack (retrain path should not assume protection until auth exists).

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-04 | Initial draft at Phase 1→2 boundary. Productionization plan for Phase 1b model. Not yet implemented — `app/services/pricing/` does not exist. |
| 1.1.0 | 2026-08-04 | Added `booking_month`/seasonality as open decision (later resolved not added). |
| 1.2.0 | 2026-08-05 | Phase 1c disambiguation — `ml-experiments/predict_price.py` prototypes contract with static per-category guardrails. |
| 1.2.1 | 2026-08-06 | Outcomes: no public `/predict-price`; recommend may expose `daily_rate` + app-layer `total_price`. |
| 1.3.0 | 2026-08-07 | Phase 1d/1e: `period_utilization` + `lead_time_days`; spec-band; scarcity pricing intentional; booking_month not added; fuel rejected; Phase 3 blend/cutover design decision; BookingStatus.CONFIRMED open item; period_utilization query pulled to Phase 1e. |
| 1.3.1 | 2026-08-07 | Spec-band boundaries implementation decision; demo_scenarios.py verification pointer. |
| 1.3.2 | 2026-08-07 | Phase 1d verified; final metrics MAE 10.68 / R² 0.974 overall; condensed prose — full reasoning in masterplan. |
| 2.0.0 | 2026-08-10 | Migrated to OpenSpec Requirement/Scenario + design REASONS under `openspec/specs/dynamic-pricing/` |
| 2.1.0 | 2026-08-10 | Ported forward Phase 1e work from `HR-87-ml-2-d-production-db-wiring-for-period-utilization` (developed on the legacy `specification/SPEC-dynamic-pricing.md` before it was stubbed to point here): confirmed real schema (snake_case, `BookingItem.assetId` as the actual booking↔asset link, `primary_snapshot`/`public` schema split), `condition`/`capacity` null fallbacks, and the 3-tier read-resilience design for `primary_snapshot` reads (retry → degrade to `public` → fail loud on cold start). Added corresponding US-1 acceptance scenarios, a Read Resilience requirement, verification cases, and Phase 1e implementation task. No prior content changed. |

**Design / feature schema / artifacts / Phase 3 cutover:** [`design.md`](./design.md)

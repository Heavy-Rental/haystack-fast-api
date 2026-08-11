# Dynamic Pricing Specification

| Field | Value |
|-------|--------|
| **Status** | Draft — Phase 2 (productionize) in progress; Phase 3 (real-data blend + scheduled retrain) not yet implemented |
| **Feature module** | `app/services/pricing/` (to be created) |
| **Standards** | OpenSpec · Spec-kit user stories · OpenSPDD (see [`design.md`](./design.md)) |
| **Depends on** | [`../project-setup/spec.md`](../project-setup/spec.md); [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md) (Phase 2 prep dependency — **executed & verified 2026-08-11**; the data side is no longer a blocker, only the category-name mapping code fix below remains) |
| **Related, not specs** | `docs/dynamic-pricing-masterplan.md` (decision log); `docs/dynamic-pricing-execution-plan.md` (day-by-day tasks) |
| **Built on** | `ml-experiments/` — Phase 1 offline experimentation (scratch, outside SDD) |
| **Related capabilities** | [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md); [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) |
| **Legacy source** | `specification/SPEC-dynamic-pricing.md` |

**Read** [`../../project.md`](../../project.md) and [`../project-setup/spec.md`](../project-setup/spec.md) before this document.

> **Phase 1c note (2026-08-05):** `ml-experiments/predict_price.py` prototypes this capability’s `predict_price(...)` contract early — guardrail clamping included — so the in-development agent prototype can call it before Phase 2 lands. It remains `ml-experiments/` scratch code, out of SDD scope like the rest of Phase 1, and its guardrail bounds are a **static per-category stand-in** (`pricing_tables.CATEGORY_BASE_RATE`), not the real per-asset `Asset.minDailyRate`/`maxDailyRate` this spec requires. It is fully superseded once this capability is implemented — do not treat it as satisfying any requirement below.
>
> **Persistence note (2026-08-10, locked 2026-08-11):** Haystack does not persist `ml_predicted_price`. `predict_price(...)` returns the price on the recommendation response (`item.pricing.daily_rate`); Spring Boot persists it to `RecommendationItem.mlPredictedPrice` on its side. Pricing's database access is **read-only** — no code path in this service writes to Postgres. Full rationale: `docs/dynamic-pricing-masterplan.md` change log, 2026-08-10. This rests on every prediction happening inside a synchronous Spring Boot → Haystack request (so a response always exists to carry the value back) — re-check this premise if a batch/offline re-pricing path is ever planned.
>
> **Category-name mismatch note (found + scoped 2026-08-11):** `AssetCategory.name` in the real DB (`Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`) does not match `feature_schema.CATEGORIES`'s naming (`excavator`, `scissor lift`, `boom lift`, `forklift`), used everywhere in pricing code and in every candidate dict built so far. Confirmed live against `heavy_rental`: `compute_period_utilization()`'s `AssetCategory.name == category` join has **never matched a real row** — it silently falls back to the static `pricing_tables.CATEGORY_UTILIZATION` constant every time a feature_schema-style name is passed (no error, no degraded flag), or raises `ValueError` from `spec_band()` if a DB-style name is passed instead. `tests/test_pricing_repository.py` doesn't catch this because it mocks `session.execute` directly, bypassing the real `WHERE` clause. Zero production impact so far only because no route threads a real `db` session yet. **Fixed as part of Phase 2 scope** — see the new "Category name normalization" requirement below and `design.md`'s "Data access" section.

---

## Purpose

Phase 1 (`ml-experiments/`) produced and validated a baseline XGBoost model that predicts `price_per_day` for equipment rentals from `category`, `condition`, `duration_days`, `capacity`, `distance_km`, and `platform_height`. Phase 1d added two real-time features — `period_utilization` and `lead_time_days` — so the model responds to live supply/demand rather than asset attributes alone. This capability defines how that model and its feature schema get **productionized** into `app/services/pricing/` so the agentic recommendation pipeline can call it in-process and return a data-driven price suggestion on the recommendation response, without duplicating the decision log in `docs/dynamic-pricing-masterplan.md`.

---

## Outcomes

When this capability is implemented:

- `app.pipelines` (or wherever the agentic recommendation step lives) can call a single in-process function to get a guardrail-clamped price prediction for a given asset/booking combination.
- The model output is **price per day** for a given duration window. There is **no** public `/predict-price` renter route (in-process only). The recommendation pipeline may surface structured pricing on `item.pricing` for the portal mockup: **`daily_rate`** (duration-scoped prediction) and app-layer **`total_price` = `daily_rate × duration_days`** — not a fabricated weekly rate. Haystack does not persist this value: `predict_price(...)` returns it on the response only, and Spring Boot persists it to `RecommendationItem.mlPredictedPrice` on its side (locked 2026-08-11 — see `docs/dynamic-pricing-masterplan.md` change log, 2026-08-10/2026-08-11).
- Every read that filters or buckets by `AssetCategory.name` normalizes between the DB's canonical business names and `feature_schema.CATEGORIES`'s naming convention — `period_utilization` reflects real bookings, not a silently-substituted static constant.
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
- **Category name normalization** between `AssetCategory.name` (DB canonical business names) and `feature_schema.CATEGORIES` (ML naming convention) — found missing 2026-08-11; in scope for Phase 2a alongside the Phase 1e→2a relocation, not a separate follow-up. See "Requirement: Category name normalization" below and `design.md`.
- Unit tests: feature schema transforms, guardrail clamping, prediction shape, category-name normalization (using real DB-shaped names, not the mocked-query pattern that missed this the first time).

### Out of scope (this capability)

- `/predict-price` as a public HTTP endpoint (masterplan: resolved as in-process function call).
- Full APScheduler scheduled retrain (Phase 3).
- Real geocoding for `distance_km` (Phase 1 uses a sampled proxy; still true in Phase 2).
- `purchaseYear` as a feature (evaluated in Phase 1b, not added — see masterplan).
- `booking_month`/seasonality as a feature (evaluated in Phase 1d, not added — `period_utilization` already captures realized seasonality).
- Fuel price as a feature (considered and rejected in Phase 1d).
- Seed data **execution** (the actual row inserts happened on the Spring Boot side; requirements specified in [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md), written **and executed** 2026-08-11 — see that spec's "Execution result"/"State after reseed" for what changed and the confirmed numbers). The Phase 3 **blend/cutover design decision** for this model is in scope via design (§5.8 / REASONS Approach), distinct from seed data itself.
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

When recommend surfaces pricing, expose **`daily_rate`** (duration-scoped) and **`total_price` = `daily_rate × duration_days`**. MUST NOT fabricate **`weekly_rate`**. Model still predicts per-day only. Persistence of `RecommendationItem.mlPredictedPrice` is Spring Boot's responsibility, not this service's — Haystack returns the predicted price in the response and does not write it (locked 2026-08-11; see `docs/dynamic-pricing-masterplan.md` change log, 2026-08-10/2026-08-11).

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

### Requirement: Category name normalization

Every code path that filters, buckets, or one-hot-encodes by category SHALL normalize between `AssetCategory.name` (DB canonical business names: `Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`) and `feature_schema.CATEGORIES` (ML naming: `excavator`, `scissor lift`, `boom lift`, `forklift`) at the read boundary, via a single shared mapping — not independently per call site, and not by renaming either side's canonical values. `compute_period_utilization()`'s `AssetCategory.name == category` join and `spec_band()`'s category argument SHALL both resolve correctly regardless of which naming convention the caller's `category` string happens to be in.

#### Scenario: Live query matches real category rows
- **GIVEN** a `category` value in `feature_schema.CATEGORIES` naming (e.g. `"excavator"`)
- **WHEN** `compute_period_utilization()` queries `AssetCategory.name`
- **THEN** it matches the real DB row (`"Excavator"`) and computes a genuine live aggregate — not a silent fallback to the static per-category constant

#### Scenario: No silent fallback on name mismatch
- **GIVEN** the category-normalization mapping is applied
- **WHEN** `predict_price(...)` runs against real DB category rows
- **THEN** `period_utilization`'s live-query path executes (zero matching rows is only ever a genuine "no assets in this band" case, never a naming artifact)

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
- Category-normalization test: exercise `compute_period_utilization()`/`spec_band()` with **real DB-shaped** `AssetCategory.name` values (`"Excavator"`, `"Scissors Lift"`, etc.) through the actual `WHERE` clause — not `session.execute` mocked to bypass it, the gap that let the 2026-08-11 mismatch ship unnoticed. At least one test should run against a live/test Postgres instance (or a query-builder-level assertion on the generated SQL) rather than only a fully mocked session.

---

## Implementation tasks

Maps to `docs/dynamic-pricing-execution-plan.md` Day 4–5 subtasks:

0. **Phase 1e — done (2026-08-10)**, on `HR-87-ml-2-d-production-db-wiring-for-period-utilization`: `app/models/asset_category.py`/`asset.py`/`booking.py`/`booking_item.py`, `app/repositories/pricing_repository.py`, `app/repositories/pricing_read_resilience.py`, wired through `pricing_client.py` → `predict_price_adapter.py` → `recommendations.py`. Not wired into `app/api/recommendations.py` — no route calls `RecommendationService` yet (tests only); `RecommendationService.__init__`'s new `db` param is ready for when that route lands. 20 new unit tests.
1. `feature/ml-3-pricing-service` (Day 4): scaffold `app/services/pricing/`, port `feature_schema.py` (includes `period_utilization`/`lead_time_days`/`spec_band()` from Phase 1d), implement `model.py`/`train.py`, guardrail clamping, **relocate** (don't rebuild) Phase 1e's read models/`pricing_repository.py`/`pricing_read_resilience.py` into this package — the guardrail-bound `Asset` read must go through the same resolver, not a second fallback implementation. **Also fix the category-name mismatch** (found 2026-08-11) as part of this relocation — add the DB-name ↔ `feature_schema.CATEGORIES` mapping at the point where `AssetCategory.name` is read, per `design.md`. Don't relocate the bug unfixed.
2. `feature/ml-4-integration-tests` (Day 5 AM): wire `predict_price(...)` into `app.pipelines` → return the prediction in the recommendation response (`item.pricing.daily_rate`); no DB write — Spring Boot persists `RecommendationItem.mlPredictedPrice` on its side (locked 2026-08-11; see masterplan). Unit tests per Verification; manual retrain endpoint.

**External dependency — resolved (2026-08-11):** richer Spring Boot seed data per [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md) landed same-day and was independently verified (8→27 assets, 20→90 bookings, full status/condition coverage, 0 orphaned bookings). Phase 2's own verification (period_utilization spot-checks, per-asset differentiated pricing in a demo) is now unblocked on the data side — the category-name mapping fix above is the only remaining blocker for `period_utilization` to actually reflect it.

---

## Key decisions / non-goals

Full rationale: `docs/dynamic-pricing-masterplan.md`. Summary for implementers:

| Decision | Why |
|---|---|
| In-process function, not HTTP route | Same owner for pipeline + pricing service; no cross-team contract to negotiate |
| Guardrails via `Asset.minDailyRate`/`maxDailyRate`, not a config table | Already admin-editable per asset; matches how training data itself was clamped |
| `platform_height` as native NaN, not imputed | Correct tool for "structurally not applicable"; XGBoost missing-value routing |
| No Alembic / no new tables | Spring Boot owns schema; Python maps onto existing tables only |
| Pricing does not persist `mlPredictedPrice` — returns it in the response instead (**locked 2026-08-11**) | `mlPredictedPrice` is a JPA-mapped field Spring Boot already owns; a second writer risks being clobbered by either the entity's own flush or the sync job's merge-upsert. Makes pricing's DB access read-only. |
| Sync SQLAlchemy + psycopg only | Matches project-setup environment default |
| Manual retrain now, full APScheduler later | Demo safety net now; scheduled retrain is Phase 3 |
| `period_utilization`/`lead_time_days` both kept, despite correlation | Answer different questions; SHAP compares which the model leans on |
| `period_utilization` grouped by category **+ spec-band** | Raw category alone is misleading (small vs. large excavator) |
| Spec-band boundaries are fixed constants | Reproducible, don't drift with fleet composition |
| `booking_month`/seasonality: resolved, **not added** | `period_utilization` already captures realized seasonality |
| Fuel price: considered and **rejected** | Indirect/lagged signal, new external API, untrainable on synthetic without fabricated correlation |
| Category-name mapping fixed in Haystack code, not by renaming DB data | `AssetCategory.name` is Spring-Boot canonical business data; `feature_schema.CATEGORIES` is baked into trained model artifacts (one-hot columns) — the ML-side slug is the derived representation, so it adapts, not the source of truth |
| Richer seed data was a Phase 2 prep dependency, not deferred wholly to Phase 3 — **executed 2026-08-11** | Original 8-asset/20-booking fixture was too thin/stale to exercise Phase 2's own acceptance scenarios meaningfully; Spring Boot's reseed (8→27 assets, 20→90 bookings) confirmed live to produce non-degenerate `period_utilization` values (0.75/0.25/0.0 across test windows); see `../domain-seed-data/spec.md` |

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
| 2.2.0 | 2026-08-11 | **Phase 2 prep.** (1) Locked the "Haystack does not persist `mlPredictedPrice`" decision — was "agreed in principle, pending confirmation"; confirmed 2026-08-11, all "pending confirmation" language in this doc updated. (2) Found and scoped a real bug: `AssetCategory.name` (DB) vs. `feature_schema.CATEGORIES` (code) naming mismatch means `compute_period_utilization()` has never executed its live-query path against real data — confirmed by live query against `heavy_rental`. Added "Requirement: Category name normalization", folded the fix into Phase 2a's implementation task (not a separate follow-up), and added a category-normalization test-coverage note to Verification. (3) Added dependency on new [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md) — richer Spring Boot seed data reclassified from Phase-3-only to a Phase 2 prep dependency, since today's fixture (8 assets, 20 bookings, single stale 11-day window) is too thin to verify Phase 2's own acceptance scenarios meaningfully. Full detail: `docs/dynamic-pricing-masterplan.md` change log, 2026-08-11. |
| 2.3.0 | 2026-08-11 (same day) | **Seed-data dependency resolved.** Spring Boot executed the `../domain-seed-data/spec.md` reseed same-day; Haystack independently re-queried `heavy_rental` and confirmed it (8→27 assets, 0 capacity nulls, 4/4 condition spread per category, all 6 `BookingStatus` values, 0 orphaned bookings, 20→90 bookings spanning 2026-06-22→2026-09-24). Updated "Depends on", the seed-data scope bullet, the "External dependency" callout, and the Key decisions row to reflect execution rather than a pending ask. The category-name mapping fix (2.2.0) remains the only open item — the reseed doesn't change that, it only makes the fix's effect demonstrable once it lands. |

**Design / feature schema / artifacts / Phase 3 cutover:** [`design.md`](./design.md)

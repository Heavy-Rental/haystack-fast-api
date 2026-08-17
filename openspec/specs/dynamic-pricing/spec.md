# Dynamic Pricing Specification

| Field | Value |
|-------|--------|
| **Status** | Phase 2a/2b/2c **implemented**. Phase 6 / S6 **as-built (2026-08-12)** — in-process agent tool `predict_asset_price` → `pricing_client` (same entrypoint as pipeline); never silent zeros; `tests/test_predict_asset_price_tool.py`. Phase 2d-i/2d-ii/2d-iii **done**; Phase 2e promotion **done (2026-08-17)** with v1 rollback artifacts and a 27-asset production-path smoke. Phase 3 (real-data blend + scheduled retrain) not yet implemented. Phase 7 Pricing Workers [7]×N **as-built S7.3**; Call 2 graph enrich **as-built S7.5** (`RECOMMEND_VIA_AGENT_GRAPH`) |
| **Feature module** | `app/services/pricing/` — **implemented** (2026-08-11): `model.py`, `train.py`, `feature_schema.py`, `pricing_tables.py`, `category_mapping.py`, `repository.py`, `read_resilience.py`, `artifacts/` |
| **Standards** | OpenSpec · Spec-kit user stories · OpenSPDD (see [`design.md`](./design.md)) |
| **Depends on** | [`../project-setup/spec.md`](../project-setup/spec.md); [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md) (Phase 2 prep dependency — data executed/verified and category-name normalization implemented 2026-08-11) |
| **Related, not specs** | `docs/dynamic-pricing-masterplan.md` (decision log); `docs/dynamic-pricing-execution-plan.md` (day-by-day tasks) |
| **Built on** | `ml-experiments/` — Phase 1 offline experimentation (scratch, outside SDD) |
| **Related capabilities** | [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md); [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) |
| **Legacy source** | `specification/SPEC-dynamic-pricing.md` (removed 2026-08-13; see [`../../TRACEABILITY.md`](../../TRACEABILITY.md)) |

**Read** [`../../project.md`](../../project.md) and [`../project-setup/spec.md`](../project-setup/spec.md) before this document.

> **Phase 1c note (2026-08-05):** `ml-experiments/predict_price.py` prototypes this capability’s `predict_price(...)` contract early — guardrail clamping included — so the in-development agent prototype can call it before Phase 2 lands. It remains `ml-experiments/` scratch code, out of SDD scope like the rest of Phase 1, and its guardrail bounds are a **static per-category stand-in** (`pricing_tables.CATEGORY_BASE_RATE`), not the real per-asset `Asset.minDailyRate`/`maxDailyRate` this spec requires. It is fully superseded once this capability is implemented — do not treat it as satisfying any requirement below.
>
> **Persistence note (2026-08-10, locked 2026-08-11):** Haystack does not persist `ml_predicted_price`. `predict_price(...)` returns the price on the recommendation response (`item.pricing.daily_rate`); Spring Boot persists it to `RecommendationItem.mlPredictedPrice` on its side. Pricing's database access is **read-only** — no code path in this service writes to Postgres. Full rationale: `docs/dynamic-pricing-masterplan.md` change log, 2026-08-10. This rests on every prediction happening inside a synchronous Spring Boot → Haystack request (so a response always exists to carry the value back) — re-check this premise if a batch/offline re-pricing path is ever planned.
>
> **Category-name mismatch note (found 2026-08-11, fixed 2026-08-11):** `AssetCategory.name` in the real DB (`Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`) does not match `feature_schema.CATEGORIES`'s naming (`excavator`, `scissor lift`, `boom lift`, `forklift`), used everywhere in pricing code and in every candidate dict built so far. Confirmed live against `heavy_rental`: `compute_period_utilization()`'s `AssetCategory.name == category` join had **never matched a real row** — it silently fell back to the static `pricing_tables.CATEGORY_UTILIZATION` constant every time a feature_schema-style name was passed (no error, no degraded flag), or raised `ValueError` from `spec_band()` if a DB-style name was passed instead. **Fixed same day** via `app/services/pricing/category_mapping.py` (`DB_NAME_TO_FEATURE_NAME`/`to_db_name()`), applied inside the relocated `repository.py`'s `compute_period_utilization()`. Re-verified live against `heavy_rental` post-fix: `period_utilization` now returns genuine varied fractions per category/spec-band (e.g. 0.75/1.00/0.00 across real assets), not the static constant. See "Requirement: Category name normalization" below and `design.md`'s "Category name mapping" section.
>
> **Internal pricing quote API note (2026-08-11):** Beyond the in-process `predict_price(...)` the recommendation pipeline uses, Spring Boot needs a synchronous, service-to-service HTTP endpoint for an authoritative per-asset quote at checkout (`POST /internal/v1/pricing/quote`) — a consumer this spec didn't originally anticipate. This is **not** a renter-facing route (called only by Spring Boot's backend, never a browser/mobile client) and does not reverse the "no public `/predict-price` renter route" outcome below. **Hard dependency**: this endpoint needs Phase 2a's real per-asset guardrail clamping and the category-name mapping fix (both elsewhere in this doc) already in place — it cannot be built against `ml-experiments/predict_price.py`'s static-table stand-in without returning Spring Boot the wrong guardrail-bound shape it was already told to expect. See "Requirement: Internal pricing quote endpoint" (US-4) and `design.md`'s "Internal quote API" for the full contract.


---

## Purpose

Phase 1 (`ml-experiments/`) produced and validated a baseline XGBoost model that predicts `price_per_day` for equipment rentals from `category`, `condition`, `duration_days`, `capacity`, `distance_km`, and `platform_height`. Phase 1d added two real-time features — `period_utilization` and `lead_time_days` — so the model responds to live supply/demand rather than asset attributes alone. This capability defines how that model and its feature schema get **productionized** into `app/services/pricing/` so the agentic recommendation pipeline can call it in-process and return a data-driven price suggestion on the recommendation response, without duplicating the decision log in `docs/dynamic-pricing-masterplan.md`.

---

## Outcomes

When this capability is implemented:

- `app.pipelines` (or wherever the agentic recommendation step lives) can call a single in-process function to get a guardrail-clamped price prediction for a given asset/booking combination.
- Multi-agent Pricing Workers (and tests) can call the allowlisted in-process tool **`predict_asset_price`**, which uses the same `pricing_client` entrypoint as the pipeline (Phase 6 / S6 as-built; graph fan-out is Phase 7).
- The model output is **price per day** for a given duration window. There is **no** public `/predict-price` renter route (in-process only). The recommendation pipeline may surface structured pricing on `item.pricing` for the portal mockup: **`daily_rate`** (duration-scoped prediction) and app-layer **`total_price` = `daily_rate × duration_days`** — not a fabricated weekly rate. Haystack does not persist this value: `predict_price(...)` returns it on the response only, and Spring Boot persists it to `RecommendationItem.mlPredictedPrice` on its side (locked 2026-08-11 — see `docs/dynamic-pricing-masterplan.md` change log, 2026-08-10/2026-08-11).
- Every read that filters or buckets by `AssetCategory.name` normalizes between the DB's canonical business names and `feature_schema.CATEGORIES`'s naming convention — `period_utilization` reflects real bookings, not a silently-substituted static constant.
- Spring Boot can request an authoritative, guardrail-clamped price per asset at checkout via a new internal-only `POST /internal/v1/pricing/quote` endpoint — service-to-service only, never called directly by a renter-facing client. See `design.md`'s "Internal quote API".
- A manual "retrain now" path exists as a demo safety net, without requiring the full APScheduler-based scheduled retrain (Phase 3).
- The feature schema, encoding rules, and artifact format match what Phase 1b already validated — no silent re-derivation of decisions already locked in the masterplan.

---

## Scope

### In scope

- `app/services/pricing/` package: `model.py` (load + predict), `train.py` (retrain), `feature_schema.py` (ported from `ml-experiments/feature_schema.py`), `artifacts/` (`.pkl` + `current.json`). **Implemented** (2026-08-11, Phase 2a) — also added `category_mapping.py` (the DB-name fix below), and `repository.py`/`read_resilience.py`, relocated into this package from `app/repositories/` (Phase 1e; that directory is now empty). See [`design.md`](./design.md) "Architecture" for the as-built layout.
- Guardrail clamping of the raw model output to `Asset.minDailyRate`/`Asset.maxDailyRate`. **Implemented**: `min_daily_rate`/`max_daily_rate` are required `predict_price(...)` parameters, clamped against directly — no static per-category fallback exists in this package (unlike the `ml-experiments` prototype it supersedes).
- An in-process `predict_price(...)` function, called directly from the pipeline — not an HTTP route. **Implemented** as `app/services/pricing/model.py`'s `predict_price(...)`; **wired** into `app.pipelines` (2026-08-11, Phase 2b) — `pricing_client.py`'s `predict_price_for_asset()` now calls it directly, no longer the `ml-experiments` prototype. See Implementation tasks.
- A manual "retrain now" endpoint (internal/ops use, not renter-facing). `train.py`'s `retrain()` (in-process retrain + `model.reload_model()` hot-swap) **implemented**; the HTTP endpoint itself moved out of Phase 2b's lean scope (2026-08-11 resequencing) to run alongside subtask 5 (demo prep) — still not yet implemented.
- Minimal SQLAlchemy read models for exactly the columns pricing touches — mapped onto the existing Spring-Boot-owned schema, no new tables, no Alembic. Includes `Booking.startDate`/`endDate`/`status`, `BookingItem.assetId` (the actual booking↔asset link), and `Asset.category_id`/`capacity`/`platform_height`, needed for `period_utilization`'s live query. **Implemented** (2026-08-10, Phase 1e; relocated 2026-08-11, Phase 2a): `app/models/asset_category.py`/`asset.py`/`booking.py`/`booking_item.py` (unchanged, still at `app/models/`); `app/services/pricing/repository.py`; `app/services/pricing/read_resilience.py` (tiered fallback, see [`design.md`](./design.md)).
- **Category name normalization** between `AssetCategory.name` (DB canonical business names) and `feature_schema.CATEGORIES` (ML naming convention) — found missing 2026-08-11. **Fixed same day** via `app/services/pricing/category_mapping.py`. See "Requirement: Category name normalization" below and `design.md`.
- **`POST /internal/v1/pricing/quote`**: internal, service-to-service HTTP endpoint (Spring Boot → Haystack) returning an authoritative, guardrail-clamped quote per requested asset for a rental window. Not renter-facing; not registered under the public `/api/v1` router. Reuses `app/services/pricing/model.py`'s `predict_price(...)` — no second prediction path. Full request/response contract: `design.md` "Internal quote API". Added 2026-08-11, after Spring Boot proposed the contract. **Implemented and verified (2026-08-11)** — `app/api/internal_pricing.py`, registered directly on the app (not via `api_router`), plus a new `app/services/pricing/repository.py::get_asset_for_pricing()` to resolve category/condition/capacity/platform_height/guardrail bounds server-side from `asset_id` alone. One implementation resolution beyond the illustrative contract: `asset_id` is `int` (matches the real `Asset.id` primary key), not the string-code form design.md's example JSON showed.
- Unit tests: feature schema transforms, guardrail clamping, prediction shape, category-name normalization (using real DB-shaped names, not the mocked-query pattern that missed this the first time), and the internal quote endpoint's request/response shape. **Implemented**: `tests/test_pricing_feature_schema.py`, `tests/test_pricing_model.py` (24 tests), `tests/test_pricing_repository.py`'s two category-mapping regression tests, and `tests/test_internal_pricing_api.py` (5 new tests: multi-item shape, per-item guardrail bounds from real `Asset` rows, per-item `degraded` independence, unresolvable `asset_id` handling, route-inventory check) — full suite 149 passing (was 144).

### Out of scope (this capability)

- `/predict-price` as a **public, renter-facing** HTTP endpoint (masterplan: resolved as in-process function call for the recommendation pipeline). Distinct from the internal `/internal/v1/pricing/quote` endpoint above, which only Spring Boot's backend calls, never a renter client.
- `POST /internal/v1/pricing/estimate` — considered (Spring Boot's original proposal) and dropped: the browse/detail page shows a flat, non-ML base price before checkout, so no scenario needs a lightweight live-ML call before a quote exists.
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

### User Story 4 - Spring Boot gets an authoritative quote at checkout (Priority: P1)

As Spring Boot, when a customer requests a quote for one or more assets over a rental window, I need a synchronous internal endpoint that returns an authoritative, guardrail-clamped price per asset, so I can freeze it onto the rental plan.

**Independent Test:** Integration test posting a multi-item request to `POST /internal/v1/pricing/quote`; assert per-item guardrail-clamped `daily_rate`/`total_price` and per-item `model_version`/`degraded`.

**Acceptance Scenarios:**

1. **Given** a request with one or more `{item_id, asset_id}` pairs, `start_date`, `end_date`, and `distance_km`, **When** `POST /internal/v1/pricing/quote` is called, **Then** the response contains one result per item with `daily_rate`, `total_price`, `was_clamped`, `min_daily_rate`, `max_daily_rate`, `model_version`, and `degraded`.

2. **Given** an `asset_id`, **When** the endpoint calls `predict_price(...)`, **Then** `category`/`condition`/`capacity`/`platform_height` and the guardrail bounds are all resolved server-side from the real `Asset`/`AssetCategory` row — the request never supplies them.

3. **Given** a multi-item request where one item's `primary_snapshot` read degrades to `public` and another's does not, **When** the response is assembled, **Then** each item's own `degraded` reflects only its own resolution — one item's degraded state does not force another's.

4. **Given** an `asset_id` that does not resolve to a real `Asset` row, **When** the endpoint processes that item, **Then** it returns a clear per-item error rather than a raw exception, without failing the rest of the batch.

5. **Given** this endpoint, **When** its callers are inventoried, **Then** it is only ever called by Spring Boot's backend, never by a renter-facing client directly — consistent with User Story 3.

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

Pricing predictions SHALL NOT be exposed through any renter-facing route. Invocation is limited to `app.pipelines`, the internal service-to-service `POST /internal/v1/pricing/quote` endpoint (US-4, Spring Boot only), the in-process agent tool `predict_asset_price` (US-5), or protected internal/ops retrain.

#### Scenario: No public /predict-price
- **WHEN** public routers are inventoried
- **THEN** no renter-facing `/predict-price` endpoint exists, and `/internal/v1/pricing/quote` is not registered under the public `/api/v1` router

### Requirement: In-process agent tool predict_asset_price (US-5 / S6)

The app SHALL expose an in-process agent tool named **`predict_asset_price`** (stable tool name for LangGraph traces / Pricing Worker **[7]**) that obtains prices only via `app.services.pricing_client.predict_price_for_asset` — the same entrypoint as the service recommend path (`PredictPriceAdapter`) and, indirectly, the same production `predict_price(...)` as US-4. The tool SHALL return a structured dict with at least `daily_rate`, `total_price`, `currency`, `was_clamped`, `model_version`, and `explanation`. It MUST NOT invent rates, MUST NOT expose a public HTTP price API, and MUST NOT return a non-positive `daily_rate` (silent zeros forbidden — fail loud). Optional `asset_id` is metadata echo only (not a second prediction path). Live `period_utilization` / `lead_time_days` remain computed inside the model when `db` + dates are provided. Wiring into multi-agent recommend Workers **[7]×N** is Phase 7 and out of scope for this requirement's implementation gate.

#### Scenario: Golden shape
- **GIVEN** valid asset features and per-asset `min_daily_rate` / `max_daily_rate`
- **WHEN** `predict_asset_price(...)` is called
- **THEN** the result is a dict containing `daily_rate`, `total_price`, `currency`, `was_clamped`, `model_version`, `explanation` with `daily_rate > 0`

#### Scenario: Single source of truth with service path
- **GIVEN** the same inputs
- **WHEN** `predict_asset_price` and `predict_price_for_asset` both run
- **THEN** `daily_rate`, `total_price`, and `model_version` match

#### Scenario: Silent zero forbidden
- **GIVEN** an underlying path that would yield `daily_rate <= 0`
- **WHEN** `predict_asset_price` runs
- **THEN** it raises rather than returning a zero-priced dict

#### Scenario: Tool name contract
- **WHEN** tool names are inventoried
- **THEN** the constant equals `"predict_asset_price"`

### Requirement: Internal pricing quote endpoint (US-4)

The pricing package SHALL expose `POST /internal/v1/pricing/quote`, an internal service-to-service HTTP endpoint (Spring Boot → Haystack only, never renter-facing) returning an authoritative, guardrail-clamped price per requested asset for a given rental window. It SHALL reuse the same `app/services/pricing/model.py` `predict_price(...)` path as the recommendation pipeline — no second prediction implementation. Full request/response contract: `design.md` "Internal quote API".

#### Scenario: Per-item guardrail-clamped result
- **GIVEN** a request with one or more `{item_id, asset_id}` items, `start_date`, `end_date`, `distance_km`
- **WHEN** `POST /internal/v1/pricing/quote` is called
- **THEN** the response contains, per item, `daily_rate`, `total_price`, `was_clamped`, `min_daily_rate`, `max_daily_rate`, `model_version`, `degraded` — bounds sourced from that item's real `Asset.minDailyRate`/`maxDailyRate`

#### Scenario: Server-side feature resolution
- **GIVEN** an `asset_id`
- **WHEN** the endpoint resolves features for `predict_price(...)`
- **THEN** `category`/`condition`/`capacity`/`platform_height` are read from the `Asset`/`AssetCategory` row server-side (through the `DB_NAME_TO_FEATURE_NAME` mapping) — the request body never carries them

#### Scenario: Independent per-item degradation
- **GIVEN** a multi-item request where one item's read degrades to `public` and another's does not
- **WHEN** the response is assembled
- **THEN** each item's `degraded` field reflects only that item's own read-resilience resolution

#### Scenario: Not renter-facing
- **GIVEN** the endpoint
- **WHEN** its callers are inventoried
- **THEN** it is registered outside the public `/api/v1` router and called only by Spring Boot's backend

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

### Requirement: Phase 2d-iii candidate validation is a read-only, common-input comparison

The system SHALL provide a standalone validation command that directly loads the current and v2 candidate pricing artifacts, evaluates both over the same live-asset feature rows at 1/7/14/30 days, and scores both over the same deterministic v2 holdout. It SHALL reuse the production feature schema and production clamp formula. It MUST NOT replace or reload the serving artifacts.

#### Scenario: Candidate materially reduces realistic-duration clamping

- **GIVEN** all 27 live pricing assets and compatible current/candidate artifacts
- **WHEN** both models are evaluated over identical rows
- **THEN** at both 7 and 14 days the candidate clamp rate is at least 20 percentage points below current
- **AND** the candidate clamp rate at each duration is no more than 50%

#### Scenario: Candidate accuracy is compared fairly

- **GIVEN** the Phase 2d-ii v2 dataset
- **WHEN** the deterministic trainer holdout (`seed=42`, `test_size=0.2`) is rebuilt
- **THEN** both models are scored on the exact same holdout rows
- **AND** the candidate MAE is no more than 5% worse than current
- **AND** the candidate R² is no more than 0.01 below current

#### Scenario: Formal gate inputs cannot be tuned

- **WHEN** the Phase 2d-iii formal comparison runs
- **THEN** it requires exactly 27 assets and durations 1/7/14/30
- **AND** it fixes `distance_km=20.0`, category-utilization fallbacks, and `lead_time_days=0.0`
- **AND** the CLI exposes no current/candidate artifact, data-path, asset-count, distance, or output override for the formal gate

#### Scenario: Candidate data provenance is verified

- **GIVEN** the ignored Phase 2d-ii v2 CSV
- **WHEN** candidate accuracy is evaluated
- **THEN** its SHA-256 is `3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05`
- **AND** its total/test row counts match `current_v2.json`
- **AND** the recomputed candidate MAE/RMSE/R² match `current_v2.json`
- **AND** a missing CSV reports the exact seed-42 regeneration command

#### Scenario: Validation does not promote the candidate

- **WHEN** Phase 2d-iii completes, whether the gate passes or fails
- **THEN** `model.pkl` and `current.json` remain byte-for-byte untouched
- **AND** the command does not invoke `reload_model()`
- **AND** promotion remains a separate Phase 2e action

### Requirement: Phase 2e promotion is recoverable and identity-verifiable

The system SHALL preserve the pre-promotion serving model and metadata as v1 rollback artifacts before the validated Phase 2d candidate becomes the serving artifact. After promotion, the serving model and metadata SHALL be byte-for-byte identical to the validated v2 candidate artifacts.

#### Scenario: Promotion preserves both generations

- **GIVEN** the Phase 2d-iii gate passed for `model_v2.pkl` and `current_v2.json`
- **WHEN** Phase 2e promotes the candidate
- **THEN** the former serving artifact bytes are preserved as the v1 rollback pair
- **AND** the serving pair matches the reviewed v2 pair byte-for-byte
- **AND** both versioned generations remain available for audit and rollback

### Requirement: Phase 2e verifies the production prediction path

The system SHALL reload the promoted serving artifacts through the production model loader and SHALL verify predictions through `predict_price()`, including all supported categories and the documented excavator watch case. Verification SHALL confirm finite positive predictions, per-asset guardrail enforcement, and the promoted metadata version.

#### Scenario: Hot reload activates the promoted model

- **WHEN** the serving singleton is reloaded after promotion
- **THEN** a new model object is loaded from the serving artifacts
- **AND** returned predictions report `prod-2026-08-13`

#### Scenario: Serving smoke reproduces candidate behavior

- **GIVEN** all 27 live pricing assets and the fixed Phase 2d-iii inputs
- **WHEN** the promoted model is exercised through `predict_price()` at 1/7/14/30 days
- **THEN** every raw prediction is finite and positive
- **AND** every returned daily rate remains inside its per-asset guardrails
- **AND** aggregate clamp rates are 11.11%/25.93%/29.63%/29.63%
- **AND** excavator clamp rates are 0%/42.86%/57.14%/57.14%

---

## Verification

- Unit tests (new, under `tests/`): feature schema transforms (one-hot columns, ordinal mapping, NaN passthrough for non-aerial `platform_height`), guardrail clamping (below-min, above-max, in-range cases), prediction output shape/type. **Done** (2026-08-11): `tests/test_pricing_feature_schema.py`, `tests/test_pricing_model.py`.
- Manual smoke: call `predict_price(...)` for one asset per category (mirroring `ml-experiments/shap_review.py`'s per-category sweeps) and confirm clamped output is within `[minDailyRate, maxDailyRate]`. **Done** — both as a unit test (`test_predict_price_one_per_category_smoke`) and live against all 27 real `heavy_rental` assets (2026-08-11); see execution-plan.md's Phase 2d entry for a finding from that live run (guardrail/duration-discount scale calibration, not a Phase 2a defect).
- Illustrative, non-exhaustive: `ml-experiments/demo_scenarios.py` — condition-effect and duration-effect scenario pairs, raw vs. guardrail-clamped output side by side. Not a substitute for unit tests or `shap_review.py`.
- Manual retrain smoke: invoke retrain path, confirm `artifacts/current.json` `trained_at` updates and subsequent prediction reflects the new model.
- Regression check: re-run `ml-experiments/category_metrics.py`-equivalent logic against the productionized model periodically; flag if any category's MAE/R² drifts materially from reference metrics in design.
- Read-resilience unit tests: mock the session/engine to raise `UndefinedTable` on demand. Cover all three tiers: (1) transient failure that clears within the retry budget still returns an undegraded prediction, (2) sustained failure falls back to `public` and the returned `PriceResult` is marked degraded, (3) both schemas unavailable raises rather than returning a price. Also cover that a single call never mixes sources across its reads.
- Category-normalization test: exercise `compute_period_utilization()`/`spec_band()` with **real DB-shaped** `AssetCategory.name` values (`"Excavator"`, `"Scissors Lift"`, etc.) through the actual `WHERE` clause — not `session.execute` mocked to bypass it, the gap that let the 2026-08-11 mismatch ship unnoticed. At least one test should run against a live/test Postgres instance (or a query-builder-level assertion on the generated SQL) rather than only a fully mocked session.
- Internal quote endpoint tests: multi-item request/response shape; per-item guardrail bounds sourced from real `Asset` rows (not the static `ml-experiments` stand-in); per-item `degraded` independence within one multi-item request; an unresolvable `asset_id` returns a per-item error without failing the rest of the batch; route inventory confirms it is not registered under the public `/api/v1` router. **Implemented** (2026-08-11): `tests/test_internal_pricing_api.py`, 5 tests, all against a mocked session/collaborators (HTTP shape/wiring test — guardrail-clamping math and `compute_period_utilization()`'s SQL are covered elsewhere, not re-tested here).
- Pipeline-integration tests: `pricing_client.py` calls the production `predict_price(...)`, not the `ml-experiments` prototype; `item.pricing.daily_rate` populates on the recommend response and stays within the selected asset's guardrail bounds. Not a re-test of guardrail-clamping math or feature-schema transforms — Phase 2a's tests already cover those. **Implemented** (2026-08-11): `tests/test_pricing_client_phase1e.py` (wrapper shaping/threading, mocked `predict_price`), `tests/test_pricing_phase2b_wiring.py` (2 tests against the real loaded model, end to end through `PredictPriceAdapter` and `RecommendationService`).

- Agent tool tests (US-5 / S6): golden shape from real model; SoT parity with `predict_price_for_asset`; `was_clamped` pass-through; silent zero / non-positive rate raises; tool name `"predict_asset_price"`; optional `asset_id` echo. **Implemented** (2026-08-12): `tests/test_predict_asset_price_tool.py`.
- Phase 2d-iii candidate-validation tests: shared-row construction and production fallbacks; below/above guardrail direction; non-finite/inverted guardrail rejection; direct clamp-rate summaries; both models scored on the same v2 holdout; missing-data regeneration guidance; SHA/row-count/candidate-metric provenance; artifact-schema mismatch rejection; gate pass/fail across clamp, accuracy, and 27-asset completeness. **Implemented** (2026-08-13): `tests/test_candidate_validation_check.py`, 8 tests. The live run loaded 27 undegraded `primary_snapshot` assets; candidate clamp rates at 7/14 days were 25.93%/29.63% vs. current 92.59%/100%, and common-holdout MAE/R² were 16.6376/0.9866 vs. current 151.2595/0.1165. All Phase 2e gates and candidate-data provenance checks passed; serving artifacts were hash-verified unchanged.
- Phase 2d-iii chart verification: `candidate_validation_check.png` shows overall current/candidate clamp rates in the upper grouped bars and category-level `current − candidate` reduction in the lower heatmap. All category cells improved. At 7/14/30 days, reductions were boom lift `71.43/71.43/71.43`, excavator `57.14/42.86/42.86`, forklift `83.33/83.33/83.33`, and scissor lift `57.14/85.71/85.71` percentage points. Excavator remains the post-promotion watch item because its candidate clamp rate is `42.86%` at 7 days and `57.14%` at 14/30 days. Final verification: 8 focused tests and 391 full-suite tests passed; 5 tests skipped; Ruff and diff hygiene passed.
- Phase 2e promotion verification: `tests/test_pricing_phase2e_promotion.py` locks v1 rollback and v2 serving identities and exercises all categories through the reloaded production model. `ml-experiments/phase2e_serving_smoke.py` live-verified 27 undegraded `primary_snapshot` assets through `predict_price()`; clamp rates exactly reproduced the candidate at 1/7/14/30 days, including the excavator watch case. **Implemented 2026-08-17.**

---

## Implementation tasks

Maps to `docs/dynamic-pricing-execution-plan.md` Day 4–5 subtasks:

0. **Phase 1e — done (2026-08-10)**, on `HR-87-ml-2-d-production-db-wiring-for-period-utilization`: `app/models/asset_category.py`/`asset.py`/`booking.py`/`booking_item.py`, `app/repositories/pricing_repository.py`, `app/repositories/pricing_read_resilience.py`, wired through `pricing_client.py` → `predict_price_adapter.py` → `recommendations.py`. Not wired into `app/api/recommendations.py` — no route calls `RecommendationService` yet (tests only); `RecommendationService.__init__`'s new `db` param is ready for when that route lands. 20 new unit tests.
1. ☑ **`feature/ml-3-pricing-service` (Day 4) — done (2026-08-11).** Scaffolded `app/services/pricing/`, ported `feature_schema.py`/`pricing_tables.py` (unchanged logic), implemented `model.py`/`train.py`, real per-asset guardrail clamping, **relocated** (not rebuilt) Phase 1e's read models/`pricing_repository.py`/`pricing_read_resilience.py` into this package as `repository.py`/`read_resilience.py` — the guardrail-bound `Asset` read goes through the same resolver, no second fallback implementation. **Fixed the category-name mismatch** (found 2026-08-11) as part of this relocation via new `category_mapping.py`, applied inside `repository.py`'s `compute_period_utilization()`. Also closed a gap found while removing the `ml-experiments` prototype's static guardrail table: an unrecognized `category` used to raise `KeyError` from that table lookup (an accident, not a real check) — with the table gone, it would have silently one-hot-encoded to an all-zero row and predicted from garbage input with no error at all (confirmed empirically); `model.py` now raises `ValueError` explicitly instead. 24 new tests (`test_pricing_feature_schema.py`, `test_pricing_model.py`, plus 2 new regression tests in `test_pricing_repository.py`), full suite 144 passing. Live-verified against all 27 real `heavy_rental` assets post-fix. `pricing_client.py`'s own predict-routing is intentionally untouched (still calls the `ml-experiments` prototype) — only its import paths changed, mechanically required by the relocation above; the actual production swap is task 2's job. **Finding from the live verification, not a defect**: guardrail bounds appear scale-mismatched against the model's duration-discount curve — see `docs/dynamic-pricing-execution-plan.md`'s Phase 2d entry.
2. ☑ `feature/ml-4-integration-tests` (Day 5, lean) — **done (2026-08-11).** Wired `predict_price(...)` into `app.pipelines`: `pricing_client.py`'s `predict_price_for_asset()` now calls `app.services.pricing.model.predict_price(...)` directly (the `_ensure_loaded()`/`_predict_fn` `ml-experiments` loader and its static `_fallback_daily_rate()` table are gone), returning the prediction in the recommendation response (`item.pricing.daily_rate`); no DB write — Spring Boot persists `RecommendationItem.mlPredictedPrice` on its side (locked 2026-08-11; see masterplan). Since `predict_price(...)` requires real per-asset `min_daily_rate`/`max_daily_rate`, `predict_price_adapter.py`'s `PredictPriceAdapter.run()` now reads them off each candidate dict too. Per the trimmed lean scope (2026-08-11 resequencing), only pipeline-integration tests were added — guardrail-clamping/feature-schema tests are already covered by task 1's 24 tests, and the manual retrain endpoint stays out of this task's scope (moved to subtask 5). Rewrote `tests/test_pricing_client_phase1e.py` and added `tests/test_pricing_phase2b_wiring.py` (2 new pipeline-integration tests against the real loaded model); updated candidate fixtures elsewhere in `tests/` that lacked the now-required guardrail fields. 154 total tests passing (was 149).
3. ☑ `feature/ml-6-internal-pricing-api` — **done (2026-08-11).** Built ahead of `feature/ml-4-integration-tests` (lean Phase 2b), not alongside/after it — resequenced the same day since this endpoint's only real dependency is task 1 (Phase 2a), already satisfied; it never touches `pricing_client.py`/`predict_price_adapter.py`/`recommendations.py`, task 2's exclusive surface. See `docs/dynamic-pricing-masterplan.md` "Phase 2b/2c sequencing and lean 2b scope". Adds `app/api/internal_pricing.py` (`POST /internal/v1/pricing/quote`, registered directly on the app, not via `api_router`), `app/schemas/pricing.py` (request/response models), and `app/services/pricing/repository.py::get_asset_for_pricing()` (new — resolves category/condition/capacity/platform_height/guardrail bounds server-side from `asset_id`, through the same tiered `read_resilience` resolver as every other pricing read). Reuses `predict_price(...)` — no second prediction path. 5 new tests (`tests/test_internal_pricing_api.py`), 149 total passing. Contract: `design.md` "Internal quote API".
4. ☑ **Phase 6 / S6 — `predict_asset_price` agent tool (2026-08-12).** `app/agents/tools.py`: `TOOL_PREDICT_ASSET_PRICE` + `predict_asset_price(...)` → `pricing_client.predict_price_for_asset` (single SoT with pipeline); silent-zero guard; optional `asset_id` echo. Tests: `tests/test_predict_asset_price_tool.py`. Phase 7 Pricing Workers graph **not** in this task. OpenSpec archive: `openspec/changes/archive/2026-08-12-s6-predict-asset-price-tool/`.

5. ☑ **Phase 2d-iii candidate validation — done (2026-08-13), `HR-146-ml-candidate-validation`.** Added the direct-artifact, common-input validation script and 8 focused tests. The formal gate locks 27 assets/20 km/fallback utilization/zero lead time, verifies the ignored v2 CSV's SHA-256, row counts, and candidate metrics, and reports an actionable regeneration command when it is absent. The live 1/7/14/30-day run and common-v2-holdout comparison passed every explicit promotion gate. No artifact was renamed, copied, overwritten, or reloaded; Phase 2e remains separate. The ignored chart shows no category regression; excavator is the documented residual watch item.

6. ☑ **Phase 2e model promotion — done (2026-08-17).** Preserved the former serving pair as `model_v1.pkl`/`current_v1.json`, retained the reviewed v2 pair, and copied v2 byte-for-byte onto `model.pkl`/`current.json`. Added artifact-identity and production-path tests plus a live smoke that calls `reload_model()` and `predict_price()` over all 27 real assets at 1/7/14/30 days. The serving model reports `prod-2026-08-13`; aggregate and excavator clamp rates exactly match Phase 2d-iii.

**External dependency — resolved (2026-08-11):** richer Spring Boot seed data per [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md) landed same-day and was independently verified (8→27 assets, 20→90 bookings, full status/condition coverage, 0 orphaned bookings). Combined with task 1's category-mapping fix (also done same-day), `period_utilization` now genuinely reflects live bookings — both halves of what Phase 2's own verification needed are in place.

---

## Key decisions / non-goals

Full rationale: `docs/dynamic-pricing-masterplan.md`. Summary for implementers:

| Decision | Why |
|---|---|
| In-process function, not HTTP route | Same owner for pipeline + pricing service; no cross-team contract to negotiate |
| Agent tool `predict_asset_price` wraps `pricing_client` only (S6) | Single SoT for pipeline + future Pricing Workers [7]; no second model path; silent zeros forbidden |
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
| `/internal/v1/pricing/quote`: new internal HTTP surface, distinct from "no public renter route" | Spring Boot needs a synchronous authoritative quote at checkout; still never renter-facing, still no duplicated ML/pricing logic outside this package |
| `distance_km` computed and sent by Spring Boot (postal-code based), not geocoded by Haystack | Real geocoding stays a non-goal for this capability; Spring Boot already has both addresses. Open follow-up: sanity-check real computed values against the synthetic training distribution before trusting prediction quality at scale |
| `deposit_rate` stays a fixed constant (0.30), returned in the quote response, not accepted as a request param | Single source of truth without adding request surface for a value that isn't currently asset/category-dependent; downstream consumers should read it from the response instead of hardcoding their own copy |
| No `/internal/v1/pricing/estimate` endpoint | Browse/detail page shows a flat, non-ML base price (Spring Boot side); live ML pricing only happens at `/quote` (checkout) — no scenario needs a lightweight pre-cart live-pricing call |
| Quote audit fields: `model_version` + `was_clamped` persisted by Spring Boot; `raw_price` deliberately excluded | `raw_price` is redundant whenever `was_clamped=false` (equals `daily_rate`), and even when clamped it's a model-calibration signal better tracked as Haystack-side monitoring than a permanent per-quote-item column in Spring's transactional schema |
| Recommend-price vs. quote-price drift: intentionally not reconciled (open item) | `period_utilization`/`lead_time_days` are live signals by design; re-pricing at quote time is expected to sometimes differ from an earlier recommend-time price — not a bug to eliminate |

**Non-goals**: renter-facing pricing API/UI, real geocoding, `purchaseYear` feature, `booking_month`/seasonality feature, fuel-price feature, Alembic migrations, async DB access, full auth/JWT stack (retrain path and internal quote endpoint should not assume protection until auth exists — restrict at network/ops level interim), `POST /internal/v1/pricing/estimate`.

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
| 2.4.0 | 2026-08-11 (later) | **New capability addition, still pre-implementation:** internal service-to-service `POST /internal/v1/pricing/quote` endpoint added at Spring Boot's request (checkout-time authoritative pricing) — distinct from the existing in-process `predict_price(...)` outcome, not renter-facing, so it does not reverse the "no public `/predict-price` renter route" decision. Added US-4, "Requirement: Internal pricing quote endpoint" + Scenarios, Verification cases, and implementation task `feature/ml-6-internal-pricing-api` with an explicit hard dependency on `feature/ml-3-pricing-service`'s real per-asset guardrail clamping and category-name mapping fix — cannot be built against the `ml-experiments` static-guardrail stand-in. Also locked, from the same discussion: Spring Boot computes/sends `distance_km` directly (no Haystack geocoding, sanity-check vs. training distribution left as an open follow-up); `deposit_rate` stays a fixed, response-only constant, not a request param; dropped `POST /internal/v1/pricing/estimate` (browse/detail shows a flat base price, live pricing only at quote/checkout); quote audit persists `model_version`/`was_clamped`, deliberately excludes `raw_price`; recommend-vs-quote price drift intentionally left unreconciled. Full contract: `design.md` "Internal quote API". |
| 2.5.0 | 2026-08-11 (Phase 2a implemented) | **`feature/ml-3-pricing-service` implemented and verified same-day as 2.2.0-2.4.0's planning.** `app/services/pricing/` built (`model.py`, `train.py`, `feature_schema.py`, `pricing_tables.py`, `category_mapping.py`, `repository.py`, `read_resilience.py`, `artifacts/`); category-name mismatch (2.2.0) fixed via `category_mapping.py`; real per-asset guardrail clamping live (`min_daily_rate`/`max_daily_rate` now required parameters, no static fallback); `app/repositories/pricing_repository.py`/`pricing_read_resilience.py` relocated into the new package (that directory is now empty). Closed an unplanned gap found while removing the static guardrail table: an unrecognized `category` needed an explicit `ValueError` check, since the table lookup's incidental `KeyError` protection no longer exists — without it, a bad category would silently one-hot-encode to an all-zero row rather than fail. 24 new tests, 144 total passing. Live-verified against all 27 real `heavy_rental` assets. `pricing_client.py`'s predict-routing itself (task 2, `feature/ml-4-integration-tests`) is unchanged — still calls the `ml-experiments` prototype; only its imports were updated, mechanically required by the relocation. Updated Status, Feature module, the category-name mismatch note, Scope bullets, Verification, and Implementation task 1 to reflect done-and-verified rather than planned. Full detail: `docs/dynamic-pricing-masterplan.md` change log, 2026-08-11; the guardrail/duration-discount scale-mismatch finding from live verification: `docs/dynamic-pricing-execution-plan.md`'s new Phase 2d entry. |
| 2.6.0 | 2026-08-11 (Phase 2c implemented) | **`feature/ml-6-internal-pricing-api` implemented and verified, resequenced ahead of Phase 2b.** `POST /internal/v1/pricing/quote` (`app/api/internal_pricing.py`) built and registered directly on the app (not `api_router`), with `app/schemas/pricing.py` and a new `repository.py::get_asset_for_pricing()` for server-side asset resolution. Reuses `predict_price(...)` unchanged. Resequenced before task 2 (lean Phase 2b) since it has no dependency on `pricing_client.py`'s pipeline-wiring surface — only on task 1 (Phase 2a), already done; see `docs/dynamic-pricing-masterplan.md` "Phase 2b/2c sequencing and lean 2b scope". `asset_id` resolved as `int` (real `Asset.id` PK type), one deliberate departure from design.md's illustrative string-code example. 5 new tests (`tests/test_internal_pricing_api.py`), 149 total passing. Updated Status, Scope, Verification, and Implementation task 3 to reflect done-and-verified. |
| 2.7.0 | 2026-08-11 (Phase 2b implemented) | **`feature/ml-4-integration-tests` implemented and verified — the last item blocking Phase 2b.** `pricing_client.py`'s `predict_price_for_asset()` now calls `app.services.pricing.model.predict_price(...)` directly; the `_ensure_loaded()`/`_predict_fn` `ml-experiments`-prototype loader and its static `_fallback_daily_rate()` table are removed (no longer needed — `model.py` loads its own artifacts eagerly at import time). `pricing_client.py` is now a thin response-shaping wrapper (currency/`deposit_rate`/`total_price`/explanation/`-degraded` suffix) around `PricePrediction`. `predict_price_for_asset()` and `PredictPriceAdapter.run()` now require/thread `min_daily_rate`/`max_daily_rate` per candidate, matching `predict_price(...)`'s no-static-fallback guardrail requirement — sourced from each seed-fleet asset dict, already present, no new data source needed. Per the trimmed lean scope, only pipeline-integration tests were added: rewrote `tests/test_pricing_client_phase1e.py`, added `tests/test_pricing_phase2b_wiring.py` (2 tests against the real loaded model). 154 total passing (was 149). Updated Status, Scope bullets (in-process function wired, manual retrain endpoint moved out of this task's scope), Verification (new pipeline-integration bullet), and Implementation task 2 to reflect done-and-verified. Full detail: `docs/dynamic-pricing-masterplan.md`/`docs/dynamic-pricing-execution-plan.md` change logs, 2026-08-11. |
| 2.8.0 | 2026-08-12 (Phase 2d-i implemented) | **Real-bound measurement implemented and live-verified.** Added `ml-experiments/guardrail_calibration_check.py`, reusing `SessionLocal`, `resolve_pricing_schema()`, and `to_feature_name()`. Read all 27 `primary_snapshot` assets undegraded, compared real bounds separately against the implied category base and configured min/max ratio bands, and generated the ignored Phase 2d chart. Real-min band hit rate was 0% for all categories; real-max hits were 50%/0%/14.3%/0%. No trained model, baseline CSV, production artifact, or DB row changed; 188 tests passed. |
| 2.9.0 | 2026-08-12 (Phase 6 / S6) | **In-process agent tool `predict_asset_price` (US-5).** `app/agents/tools.py` wraps `pricing_client.predict_price_for_asset` (single SoT with pipeline); golden shape, SoT parity, silent-zero guard, optional `asset_id` echo. Tests: `tests/test_predict_asset_price_tool.py`. Does not wire Phase 7 Pricing Workers graph. Feasibility_Study implementation-plan **3.5.6**; archive `openspec/changes/archive/2026-08-12-s6-predict-asset-price-tool/`. |
| 2.10.0 | 2026-08-13 (Phase 2d-ii implemented) | Recalibrated synthetic anchors (`80/220`, `230/985`, `85/205`, `120/500`), guardrail bands (`0.74–0.88` / `1.12–1.33`), and duration curve (floor/rate `0.84/0.18`) jointly. Generated the ignored 5,000-row `synthetic_pricing_data_v2.csv` and tracked candidate `model_v2.pkl`/`current_v2.json`; strict checks passed with 35.3% generation-time target clipping. Candidate holdout MAE/RMSE/R²: 16.6376/26.1103/0.9866. Serving artifacts stayed unchanged; 2d-iii validation and 2e promotion remain gated. |
| 2.11.0 | 2026-08-13 (Phase 2d-iii implemented) | Added `candidate_validation_check.py` plus 5 focused tests; directly compared current/candidate artifacts over identical production-schema rows for all 27 live assets at 1/7/14/30 days and over the same deterministic v2 holdout. Candidate 7/14-day clamp rates were 25.93%/29.63% vs. current 92.59%/100%; common-holdout MAE/R² were 16.6376/0.9866 vs. 151.2595/0.1165. Every explicit gate passed. Artifact hashes stayed unchanged and no reload/promotion occurred; Phase 2e is unblocked but separate. |
| 2.11.1 | 2026-08-13 (Phase 2d-iii gap audit/final convergence) | Restored the approved Phase 2d-ii calibration constants that were documented and used for candidate generation but missing from tracked `ml-experiments/pricing_tables.py`; fresh seed-42 generation byte-matches the ignored candidate CSV (`sha256=3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05`). Locked artifact/data/input/output identities, added CSV hash/row-count/candidate-metric provenance, actionable missing-data guidance, invalid-guardrail and non-finite-prediction rejection, and expanded focused coverage 5→8. The category heatmap showed improvement everywhere, with excavator retained as the residual watch item. Final verification: 8 focused tests and 391 full-suite tests passed and 5 tests skipped; Ruff and diff hygiene passed. Live gate results and serving artifacts are unchanged. |
| 2.12.0 | 2026-08-17 (Phase 2e implemented) | Promoted the validated v2 candidate to the serving filenames after preserving byte-exact v1 rollback artifacts; retained both versioned generations. Added an identity-checked serving smoke and tests, called `reload_model()`, and verified all 27 undegraded live assets through `predict_price()` at 1/7/14/30 days. Serving clamp rates exactly reproduce the candidate (11.11%/25.93%/29.63%/29.63% overall; 0%/42.86%/57.14%/57.14% for excavator), with model version `prod-2026-08-13`. |

**Design / feature schema / artifacts / Phase 3 cutover:** [`design.md`](./design.md)

# Dynamic Pricing Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, Outcomes, US-1..3, and Requirements.  
Productionize Phase 1 XGBoost model into `app/services/pricing/` for in-process `predict_price(...)`.

## E — Entities

| Concept | Role |
|---------|------|
| Asset (read model) | category, condition, capacity, platform_height, min/max daily rates |
| Booking (read model) | start/end, status for period_utilization overlap |
| Feature row | Encoded model inputs (one-hot category, ordinal condition, numerics) |
| Model artifacts | `model.pkl` + `current.json` |
| Price prediction | Guardrail-clamped `price_per_day` |
| Spec-band | Bucket by capacity (excavator/forklift) or platform_height (scissor/boom) |

## A — Approach

Per masterplan locked decision: `predict_price(...)` is an **in-process Python function call**, not an HTTP endpoint — no auth/serialization/test-client overhead for same-owner pipeline + pricing.

### Architecture

**As-built (2026-08-11)** — the originally-sketched 4-file layout grew two more modules during implementation: `category_mapping.py` (the DB-name fix) and the relocated `repository.py`/`read_resilience.py` (Phase 1e's logic, moved in rather than left at `app/repositories/`, per this doc's own "relocate, don't rebuild" instruction):

```text
app/services/pricing/
├── __init__.py
├── model.py             # load model.pkl + current.json once, expose predict_price(...)
│                         # + reload_model() hot-swap; real per-asset guardrail clamping
├── train.py              # retrain entrypoint (ports ml-experiments/train.py's logic)
│                         # + retrain() for the in-process manual-retrain path (Phase 2b)
├── feature_schema.py     # ports ml-experiments/feature_schema.py near-verbatim
├── pricing_tables.py     # ports ml-experiments/pricing_tables.py near-verbatim
├── category_mapping.py   # NEW 2026-08-11: DB_NAME_TO_FEATURE_NAME / to_db_name() / to_feature_name()
├── repository.py         # relocated from app/repositories/pricing_repository.py (Phase 1e);
│                         # category-name mapping fix applied here (see below)
├── read_resilience.py    # relocated from app/repositories/pricing_read_resilience.py (Phase 1e)
└── artifacts/
    ├── model.pkl          # promoted from ml-experiments/artifacts/ (already-trained Phase 1 model)
    └── current.json
```

`app/repositories/` is now empty (those were its only two files) — left in place (its own `__init__.py` says "Feature SDDs add concrete repositories") for future use, not deleted.

### Consumers (single source of truth)

**As-built (2026-08-12, S6):** every price path funnels through production `predict_price(...)` (or `pricing_client` shaping above it). No second model loader.

```text
PredictPriceAdapter (service recommend / Call 2 MVP)
    → pricing_client.predict_price_for_asset
        → model.predict_price

POST /internal/v1/pricing/quote (US-4)
    → repository.get_asset_for_pricing + model.predict_price
        (response shape in schemas/pricing.py; same model)

predict_asset_price agent tool (US-5 / S6)
    → pricing_client.predict_price_for_asset   # same as pipeline
        → model.predict_price
```

| Consumer | Module | Notes |
|----------|--------|--------|
| Pipeline / Call 2 MVP | `app/pipelines/predict_price_adapter.py` | Per-candidate dict + `item.pricing` |
| Internal quote API | `app/api/internal_pricing.py` | Spring checkout; resolves asset by id |
| Agent tool | `app/agents/tools.py` (`TOOL_PREDICT_ASSET_PRICE`) | Pricing Worker [7] allowlist; Phase 7 graph not yet wired |

Silent zeros: tool raises `ValueError` if `daily_rate <= 0`.

### Feature schema (locked, from Phase 1b + Phase 1d)

Ports `ml-experiments/feature_schema.py` directly — same `CATEGORIES`, `CONDITION_ORDER`, `FEATURE_COLUMNS`, `build_features()`/`get_target()` logic. Adapt input from `pandas.DataFrame` (CSV-sourced in Phase 1) to a single row/dict from ORM objects.

| Feature | Encoding | Notes |
|---|---|---|
| `category` | one-hot, fixed `CATEGORIES` order | via `AssetCategory.name`; never encode the raw FK |
| `condition` | ordinal, `NEEDS_REPAIR=0…EXCELLENT=3`; **falls back to `"GOOD"` when null** | `Asset.condition`; nullable in the real schema — `encode_condition()`'s ordinal cast can't take NaN anyway |
| `duration_days` | numeric passthrough | `Booking.endDate − Booking.startDate` |
| `capacity` | numeric passthrough; **falls back to `pricing_tables.CATEGORY_CAPACITY_KG` per-category midpoint when null** (not NaN — a data gap, not a structural absence like `platform_height`) | `Asset.capacity`; nullable in the real schema, currently unset for non-forklift seed rows |
| `distance_km` | numeric passthrough | Phase 1/2: still a sampled proxy, not geocoded |
| `platform_height` | numeric, **NaN for forklift/excavator** | `Asset.platform_height`; native missing for XGBoost, not imputed |
| `period_utilization` | numeric passthrough, `[0,1]` | Live aggregate over same `category` + spec-band; status `CONFIRMED`/`PENDING`, non-cancelled; at prediction time — **Phase 1d/1e** |
| `lead_time_days` | numeric passthrough | `Booking.startDate − today`; derived — **Phase 1d** |

Target: `price_per_day` (training-time only; not part of the prediction input).

**Spec-band bucketing** (excavator/forklift by `capacity`, scissor/boom lift by `platform_height`) avoids a fully-booked small-excavator fleet making a large excavator look scarce. Fixed constants (`pricing_tables.CAPACITY_BINS`/`HEIGHT_BINS`, no persisted column) — see that file's comments and `feature_schema.spec_band()`.

**Scarcity pricing is intentional, not a bug**: early booking on an unclaimed window legitimately prices lower (airline/hotel-style).

`booking_month`/seasonality: resolved **not added** — `period_utilization` already captures realized seasonality.

### Data access (confirmed against the real schema, 2026-08-09/10)

Pricing needs read access to `asset_categories.name`, `assets.category_id`/`capacity`/`condition`/`platform_height`/`min_daily_rate`/`max_daily_rate`, `bookings.start_date`/`end_date`/`status`, and `booking_items.asset_id`/`booking_id`. **`Booking` has no `asset_id` column in the real schema** — the booking↔asset link exists only via `BookingItem`, so `period_utilization`'s overlap query (below) joins `booking_items → bookings`, not a direct `Booking.asset_id` this design originally assumed. Spring Boot owns schema/migrations; Python maps onto existing tables (no Alembic, no new tables).

### Category name mapping (found 2026-08-11, fixed 2026-08-11)

`AssetCategory.name` in the real DB is the Spring-Boot canonical business name: `Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`. `feature_schema.CATEGORIES` — baked into the trained model's one-hot columns, and used as the `category` string everywhere in pricing code (`pricing_tables.py` keys, `spec_band()`, today's `seed_fleet.py` candidate fixtures) — uses a different convention: `excavator`, `scissor lift`, `boom lift`, `forklift`. These never coincide, not even case-insensitively (`Fork Lift` vs. `forklift` differs by more than case).

**Confirmed live** (2026-08-11, against `postgres-haystack`/`heavy_rental`): `pricing_repository.compute_period_utilization()`'s `.where(AssetCategory.name == category)` join returns zero rows for every real category when called with a `feature_schema`-style `category` string — it silently falls through to `pt.CATEGORY_UTILIZATION.get(category, 0.0)`, the static per-category constant, with no error and no degraded flag. Called with a DB-style name instead, `feature_schema.spec_band()` raises `ValueError` (it only recognizes the `feature_schema.CATEGORIES` spelling). Either direction is broken. `tests/test_pricing_repository.py` didn't catch this because its `_session_returning()` helper mocks `session.execute` directly — the mocked return value never passes through the real `WHERE` clause, so a mismatched filter can't fail a test built that way.

**Fix — implemented 2026-08-11**, as part of the Phase 1e→`app/services/pricing/` relocation, not a separate task: a single shared mapping module, `app/services/pricing/category_mapping.py` —

```python
DB_NAME_TO_FEATURE_NAME = {
    "Excavator": "excavator",
    "Scissors Lift": "scissor lift",
    "Boom Lift": "boom lift",
    "Fork Lift": "forklift",
}
FEATURE_NAME_TO_DB_NAME = {v: k for k, v in DB_NAME_TO_FEATURE_NAME.items()}

def to_feature_name(db_category_name: str) -> str: ...  # KeyError on unrecognized input
def to_db_name(feature_category_name: str) -> str: ...  # KeyError on unrecognized input
```

Every caller of `predict_price(...)`/`repository.py` stays in `feature_schema` convention throughout, exactly as before — the mapping is applied in exactly one place: `repository.py`'s `compute_period_utilization()` calls `category_mapping.to_db_name(category)` to build the `AssetCategory.name ==` filter's right-hand side, since that's the one spot in this package that needs the DB-style name. `spec_band()`, `resolve_effective_capacity()`, `predict_price(...)` itself, and everything else keep using the `feature_schema`-style string unchanged. A future caller that starts from a real `AssetCategory.name` row (e.g. the internal quote endpoint, Phase 2c, resolving `category` from an `asset_id`) calls `to_feature_name()` once before calling `predict_price(...)`. Direction matters: **DB name is the source of truth**, ML slug is the derived form — don't rename `AssetCategory.name` values to match the model; the model's one-hot columns adapt via this mapping, not the other way around.

Test coverage gap this closes: **closed** — `tests/test_pricing_repository.py`'s `test_compute_period_utilization_filters_by_real_db_category_name` and `test_compute_period_utilization_queries_real_asset_and_category_models` compile the actual generated SQL (`literal_binds=True`) and assert on the bound `AssetCategory.name` literal, CI-safe without a live DB. `tests/test_pricing_model.py`'s `test_db_style_category_name_fails_loud_with_a_helpful_hint` covers `model.py`'s own category-validation check (a related but separate gap — see "Guardrail clamping" below).

**Re-verified live** (2026-08-11, post-fix, against `postgres-haystack`/`heavy_rental`): `predict_price(...)` run for all 27 real assets now returns genuinely varied `period_utilization` per category/spec-band (e.g. Excavator's 4-asset main band: 0.75 / 0.25 / 0.0 across three different windows) — the live-query path is actually executing, not silently substituting the static constant.

**Pricing's database access is read-only (2026-08-10, locked 2026-08-11).** This design previously listed "plus write access to `recommendation_items.ml_predicted_price`" here for Phase 2; that write is no longer planned. `predict_price(...)` returns the prediction on the recommendation response instead, and Spring Boot persists it to `RecommendationItem.mlPredictedPrice` — a JPA-mapped field on a Spring Boot entity, in a schema Spring Boot already owns. Now that this is locked, pricing's Postgres role can be granted `SELECT` only; no code path in this service writes to Postgres. Two topology facts make that more than a naming convention: (1) writing `public.recommendation_items` gets overwritten by the sync job's merge-upsert, which sets every shared non-key column to `EXCLUDED` each cycle, including to `NULL`; (2) the `primary_snapshot` foreign tables are writable (`pg_relation_is_updatable = 28`) and point at the Spring Boot production database directly, so a stray SQLAlchemy autoflush on a mutated instance could otherwise write upstream. Full rationale: `docs/dynamic-pricing-masterplan.md` change log, 2026-08-10. Rests on every prediction happening inside a synchronous Spring Boot → Haystack request — re-check if a batch/offline re-pricing path is ever planned.

All open items are resolved:

- **Column names/casing: snake_case throughout**, not camelCase.
- `Asset.platform_height` exists as a real, nullable column. `Asset.min_daily_rate`/`max_daily_rate` are `NOT NULL`.
- `period_utilization`'s status filter counts bookings in `{PENDING_DEPOSIT, PENDING_CONFIRMED, CONFIRMED, MOBILISED}` — excludes `COMPLETED` (already returned) and `CANCELLED` (releases the hold) — overlap is inclusive on both boundaries (matching `BookingAvailabilityFilter`, no same-day turnover).

**Schema targeting**: `postgres-haystack`'s `heavy_rental` database exposes two schemas — `primary_snapshot` (`postgres_fdw` foreign tables reading live from `postgres-primary`'s real `public` schema — the actual Spring-Boot-owned data) and `public` (a separate local table set, merge-upserted from upstream on a periodic external job, so at most one sync cycle stale — not an independently-drifting fork). **All pricing SQLAlchemy models must set `schema="primary_snapshot"`** — SQLAlchemy's default search path resolves to `public`, which would silently read the stale copy otherwise.

Introduce only the minimal SQLAlchemy declarative models pricing actually reads/writes (not a full domain model set).

**Phase 1e — implemented (2026-08-10)** on `HR-87-ml-2-d-production-db-wiring-for-period-utilization`: `app/models/asset_category.py`/`asset.py`/`booking.py`/`booking_item.py` (first-ever read-only SQLAlchemy models), `app/repositories/pricing_repository.py` (`period_utilization`'s live query), `app/repositories/pricing_read_resilience.py` (see below), wired into the existing `pricing_client.py` → `predict_price.py` call path. This package **relocates**, not rebuilds, that logic when Phase 2 is built — the guardrail-bound `Asset` read must go through the same resolver, not a second fallback implementation. Not wired into `app/api/recommendations.py` yet — no route calls `RecommendationService` yet (tests only).

### Read resilience: tiered fallback (2026-08-10)

Every pricing DB read against `primary_snapshot` — guardrail bounds + category join, and `period_utilization`'s overlap query — shares **one** fallback resolution, decided once per `predict_price(...)` call and applied to every read in that call. A single prediction must not mix `primary_snapshot` and `public` across its reads.

Three tiers, attempted in order:

1. **Transient (mid-recreate, seconds-scale).** A read can hit `UndefinedTable` in the narrow window between the sync cycle's `DROP SCHEMA`/`CREATE SCHEMA` committing and its `IMPORT FOREIGN SCHEMA` completing. Catch specifically `UndefinedTable`/relation-missing errors — never a blanket exception — and retry with a short bounded backoff. Most cycles resolve here.
2. **Sustained (a failed cycle).** If tier 1's retries exhaust, re-issue the same read(s) against `public` instead — a real value, at most one sync cycle stale, not a fabricated default. Mark the resulting `PriceResult` as degraded using `pricing_client.py`'s existing "model unavailable" pattern (`model_version`, `explanation`). **Staleness bound corrected 2026-08-11**: this section previously said "hours, up to the ~24h sync interval" — that assumed the sync job's original `SYNC_INTERVAL_SECONDS=86400` (daily) cadence. `Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md` (merged into this branch 2026-08-11, v2.7.1) now documents the target/develop cadence as `SYNC_INTERVAL_SECONDS=60` (near-real-time poll) — so "at most one sync cycle stale" means **at most ~60 seconds**, not up to a day, once that cadence is live. Two things worth noting: (a) confirm which cadence is actually running wherever this reads in practice, since the two docs' histories diverged independently and this repo doesn't own the sync job; (b) a 60s cycle likely means the tier-1 "transient, mid-recreate" window — the gap between `DROP SCHEMA`/`IMPORT FOREIGN SCHEMA` — recurs far more often than a 24h cadence would, so tier 1's retry path is probably exercised routinely, not rarely, once this cadence is confirmed live. No behavior change needed here (the tiered logic doesn't hardcode a duration), just this doc's staleness.
3. **Cold start (neither schema exists).** A container that has never completed a sync. `predict_price(...)` fails loud (raises) rather than returning a fabricated price.

**Implementation shape**: `app/services/pricing/read_resilience.py`'s `resolve_pricing_schema(session) -> PricingSchemaResolution` — called once per `predict_price(...)` call (relocated from `app/repositories/pricing_read_resilience.py` in Phase 2a, 2026-08-11 — see "Architecture" above), its `.execution_options` (SQLAlchemy's `schema_translate_map`, `{}` when reading `primary_snapshot` unmodified) threaded into every subsequent `session.execute(...)` in that call. This avoids declaring a second set of models pointed at `public` — the same `AssetCategory`/`Asset`/`Booking`/`BookingItem` classes (declared with `schema="primary_snapshot"`) serve both tiers; `schema_translate_map` redirects the table name at query time.

### Guardrail clamping — implemented 2026-08-11

```text
predicted = model.predict(features)
clamped = min(max(predicted, asset.minDailyRate), asset.maxDailyRate)
```

Read per-asset at prediction time (admin-editable via asset admin-portal tag) — no separate config table or env var. `model.py`'s `predict_price(...)` takes `min_daily_rate`/`max_daily_rate` as **required** parameters — every caller supplies them: `pricing_client.py`'s `predict_price_for_asset()` (Phase 2b, implemented 2026-08-11 — reads them off each candidate dict, sourced from `seed_fleet.py`) and the internal quote endpoint (Phase 2c, reading a real `Asset` row). No fallback to a static per-category table exists anywhere in this package — that stand-in stays confined to the superseded `ml-experiments/predict_price.py` prototype.

**A related gap found and closed while removing that static table** (2026-08-11): the `ml-experiments` prototype's only protection against an unrecognized `category` was an *incidental* `KeyError` from its `pricing_tables.CATEGORY_BASE_RATE[category]` guardrail lookup — never a deliberate validation check. With that lookup gone (guardrails are now explicit parameters), nothing would have caught a bad `category` string at all: confirmed empirically that `feature_schema.encode_category()`'s `pd.Categorical(..., categories=CATEGORIES)` silently produces an all-zero one-hot row for an out-of-vocabulary value — no error, and the model would predict from that garbage row without complaint. `model.py`'s `predict_price(...)` now raises `ValueError` explicitly for any `category not in feature_schema.CATEGORIES`, with a hint pointing at `category_mapping.to_feature_name()` for the common case of passing a raw `AssetCategory.name` by mistake. `condition` is intentionally left as-is (an unrecognized value still raises pandas' `IntCastingNaNError` — unfriendly but real, matching the corrected prototype docstring from earlier the same day) — only the `category` gap was a genuine regression introduced by dropping the static table, so only it got a deliberate fix.

### Internal quote API (added 2026-08-11, implemented 2026-08-11)

`POST /internal/v1/pricing/quote` — synchronous, service-to-service only (Spring Boot → Haystack), authoritative per-asset quote at checkout. Reuses this package's `predict_price(...)` — no second prediction path. Registered as its own router (`app/api/internal_pricing.py`), included directly on the app in `app/main.py` (**not** via `app.api.api_router`, so it's outside the public `/api/v1` prefix); restrict at network/ops level, same interim posture as the manual retrain path (see Security notes) until real auth exists.

**Dependency (satisfied 2026-08-11)**: required this capability's real per-asset guardrail clamping (`Asset.minDailyRate`/`maxDailyRate`) and the category-name mapping fix above to already be in place — building this against `ml-experiments/predict_price.py`'s static per-category stand-in would have handed Spring Boot the wrong `min_daily_rate`/`max_daily_rate` shape it was already told to expect. Built after `feature/ml-3-pricing-service` landed. **Resequenced ahead of Phase 2b** (lean pipeline wiring) the same day — this endpoint never touches `pricing_client.py`/`predict_price_adapter.py`/`recommendations.py`, so it had no dependency on that work; see `docs/dynamic-pricing-masterplan.md` "Phase 2b/2c sequencing and lean 2b scope" (see Implementation branches).

**Implementation notes (2026-08-11)**:
- New `app/services/pricing/repository.py::get_asset_for_pricing()` (+ `AssetPricingRow` dataclass) resolves category (via `category_mapping.to_feature_name()`)/condition/capacity/platform_height/guardrail bounds from `asset_id` alone, through the same tiered `read_resilience` resolver as every other pricing read — no second fallback implementation for this read either. Returns `None` on an unresolvable `asset_id`; the endpoint turns that into a per-item error (`error: "asset_not_found"`), not a raised exception.
- Each item resolves its own schema **twice**: once for the `get_asset_for_pricing()` guardrail read, once more inside `predict_price(...)` itself (which always does its own resolution when given `db`/`start_date`/`end_date` and has no parameter to accept a precomputed one). Both are real tiered resolutions against the same resolver — not a second implementation — just not collapsed into one call. The item's `degraded` flag ORs both outcomes so it never under-reports. A single `predict_price(...)` call's own internal reads still never mix schemas (unchanged). A `PricingSchemaUnavailable` (cold start) is deliberately **not** caught per-item — it's a systemic condition, not asset-specific, so it propagates to the global exception handler (500) rather than being reported as 1-of-N per-item errors.
- `asset_id` is typed `int` in `app/schemas/pricing.py`, matching the real `Asset.id` primary key (`app/models/asset.py`) — one deliberate resolution of this section's JSON examples below, which use illustrative string codes (the same placeholder convention `app/pipelines/seed_fleet.py` uses for scratch fixtures, not the real schema).
- 5 new tests: `tests/test_internal_pricing_api.py` — multi-item shape, per-item guardrail bounds from real `Asset` rows, per-item `degraded` independence, unresolvable `asset_id` per-item error, route-inventory (via `app.openapi()["paths"]`, not `app.routes` — this FastAPI version wraps `include_router()` results in an internal `_IncludedRouter` with no stable public `.path` to introspect directly).

Request:
```json
{
  "rental_plan_id": "plan_123",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "distance_km": 18.4,
  "items": [
    { "item_id": "item_1", "asset_id": "AST-EXC-004" },
    { "item_id": "item_2", "asset_id": "AST-SL-011" }
  ]
}
```

Response (200):
```json
{
  "rental_plan_id": "plan_123",
  "currency": "SGD",
  "deposit_rate": 0.30,
  "degraded": false,
  "results": [
    {
      "item_id": "item_1",
      "asset_id": "AST-EXC-004",
      "daily_rate": 182.40,
      "total_price": 2189.60,
      "was_clamped": true,
      "min_daily_rate": 120.00,
      "max_daily_rate": 260.00,
      "model_version": "prod-2026-08-01",
      "degraded": false
    },
    {
      "item_id": "item_2",
      "asset_id": "AST-SL-011",
      "daily_rate": 150.00,
      "total_price": 1800.00,
      "was_clamped": false,
      "min_daily_rate": 90.00,
      "max_daily_rate": 220.00,
      "model_version": "prod-2026-08-01",
      "degraded": false
    }
  ],
  "warnings": []
}
```

Notes:
- `category`/`condition`/`capacity`/`platform_height` are never in the request — resolved server-side per `asset_id` through the same `Asset`/`AssetCategory` read + `DB_NAME_TO_FEATURE_NAME` mapping used elsewhere in this package. Spring Boot does not need to know the ML naming convention.
- `distance_km` is a single value applied to the whole request (one delivery site assumed). Spring Boot computes it (postal-code based) and sends it — Haystack does not geocode. Open follow-up: sanity-check real computed values against the synthetic training distribution (`ml-experiments/generate_synthetic_data.py`) before trusting prediction quality, since the model was trained on a sampled proxy, not real distances. Revisit the single-value assumption if a multi-site quote is ever needed.
- Per-item `degraded`/`model_version` are independent, not request-wide — `resolve_pricing_schema()` runs once per item (per `predict_price_for_asset()` call), not once per request, so one item can degrade to `public` while another doesn't. The top-level `degraded` is a convenience OR-of-all-items flag, not a separate resolution.
- `deposit_rate` is a fixed constant (0.30), sourced from one place in this package (e.g. alongside `pricing_tables.py`, not re-hardcoded per consumer) and returned in the response rather than accepted as a request parameter. Downstream (Spring Boot, frontend) should read it from here instead of maintaining independent copies.
- No `raw_price` in the response — deliberately excluded from Spring Boot's audit persistence (see Key decisions in spec.md); `model_version` + `was_clamped` are persisted there, `raw_price` is not.
- No `POST /internal/v1/pricing/estimate` — browse/detail page pricing is a flat, non-ML base price on Spring Boot's side (e.g. `Asset.baseDailyRate`, no Haystack call); live ML pricing only happens at quote/checkout via this endpoint.
- Price consistency between an earlier `recommend`-surfaced price and this endpoint's quote is intentionally **not** reconciled — `period_utilization`/`lead_time_days` are live, so drift is possible and expected; open item, not yet resolved.

### Pipeline wiring (Phase 2b, implemented 2026-08-11)

`app/services/pricing_client.py`'s `predict_price_for_asset()` calls `app.services.pricing.model.predict_price(...)` directly. It no longer lazily loads `ml-experiments/predict_price.py` via `sys.path` (the `_ensure_loaded()`/`_predict_fn` machinery is gone) and no longer has a static `_fallback_daily_rate()` category-table fallback — `model.py` already loads its artifacts eagerly at import time (Phase 2a) and has no "model unavailable" state to fall back from. `pricing_client.py`'s remaining job is response shaping only: `currency`, `deposit_rate`, `total_price = daily_rate × duration_days`, a human-readable `explanation`, and appending a `-degraded` suffix to `model_version`/a note to `explanation` when `PricePrediction.degraded` is set. All guardrail-clamping and live-aggregate logic stays inside `model.py` — not duplicated here, same principle as the internal quote endpoint above.

Because `predict_price(...)` requires real per-asset `min_daily_rate`/`max_daily_rate` (no static fallback, per "Guardrail clamping" above), `pricing_client.predict_price_for_asset()` now requires them too. `app/pipelines/predict_price_adapter.py`'s `PredictPriceAdapter.run()` reads them straight off each candidate dict (`candidate["min_daily_rate"]`/`candidate["max_daily_rate"]`) — every `app/pipelines/seed_fleet.py` asset already carries both fields, so this needed no new data source for the pipeline's current in-memory candidate pool. A future DB-backed candidate source would need to carry the same two fields per candidate (e.g. via `get_asset_for_pricing()`, already built for the internal quote endpoint).

Per the lean Phase 2b scope (2026-08-11 resequencing decision), only pipeline-integration tests were added — not a re-test of guardrail-clamping math or feature-schema transforms, already covered by Phase 2a's 24 tests. `tests/test_pricing_client_phase1e.py` now mocks `app.services.pricing.model.predict_price` (verifying the wrapper threads every argument through and shapes the response correctly) instead of the retired `_predict_fn` prototype hook. New `tests/test_pricing_phase2b_wiring.py` exercises the real loaded model end to end: `PredictPriceAdapter` produces a `prod-`-versioned, guardrail-bounded price for a seed asset, and `RecommendationService.recommend_from_project_spec()` populates `item.pricing.daily_rate` on the full recommend response. 154 total tests passing (was 149).

### Artifact contract

`current.json` shape already implemented and validated in `ml-experiments/artifacts/current.json` — reuse as-is:

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

### Reference metrics (Phase 1d, synthetic data, 8 features)

Offline-only — expect movement once Phase 3 seeds real historical bookings:

| Category | MAE | R² |
|---|---|---|
| scissor lift | 5.09 | 0.971 |
| excavator | 20.54 | 0.941 |
| boom lift | 11.99 | 0.954 |
| forklift | 5.07 | 0.949 |
| **Overall** | **10.68** | **0.974** |

Slightly higher MAE than Phase 1b baseline (9.95) — expected: two new real variance sources (`period_utilization`, `lead_time_days`). SHAP importance: period_utilization/lead_time_days 2.51/3.18 respectively; still well below duration_days (40.3)/capacity (46.8)/condition (14.1) by design.

### Security notes

No auth stack yet (project-setup). Manual retrain path MUST **not** be a public renter route until real auth SDD exists — restrict at network/ops level interim.

### Phase 3 — cold-start bootstrap, blend, per-category cutover (design decision)

A fresh deployment has no real transaction history. `period_utilization`/`lead_time_days` are always live-computable even with few bookings, but the model's learned price-response needs grounded synthetic data until real history exists. Resolution rides on Phase 3 scheduled retrain already scoped in masterplan/execution plan — **not a new mechanism**:

- **Bootstrap (now)**: 100% grounded synthetic data. Guardrail clamping bounds worst-case error.
- **Blend**: extend Phase 3 retrain `train.py` with sample weighting by data source/recency (`model.fit(X, y, sample_weight=...)`) — real data weighted higher as volume grows. **Design decision only — no code until real data exists**.
- **Cutover**: per category, not all at once. Each category drops synthetic rows independently once it clears its own minimum real-sample threshold (exact threshold TBD). Categories graduate at different rates.

Full reasoning: `docs/dynamic-pricing-masterplan.md` Phase 3.

## S — Structure

```text
ml-experiments/                 # Phase 1 scratch (outside SDD)
  feature_schema.py
  predict_price.py              # prototype contract (static guardrails)
  train.py, generate_synthetic_data.py, pricing_tables.py
  artifacts/model.pkl, current.json
  demo_scenarios.py, shap_review.py, category_metrics.py

app/services/pricing/           # Phase 2a — implemented 2026-08-11 (this capability)
  model.py, train.py, feature_schema.py, pricing_tables.py, category_mapping.py,
  repository.py, read_resilience.py, artifacts/model.pkl, artifacts/current.json

app/api/internal_pricing.py     # Phase 2c -- implemented 2026-08-11: POST /internal/v1/pricing/quote
                                 # (service-to-service, registered directly on the app in
                                 # app/main.py, not via api_router / the public /api/v1 prefix;
                                 # reuses app/services/pricing/model.py's predict_price(...) --
                                 # no second prediction path)
app/schemas/pricing.py          # Phase 2c -- request/response models for the endpoint above

app/services/pricing_client.py  # Phase 2b -- implemented 2026-08-11: thin response-shaping
                                 # wrapper around app.services.pricing.model.predict_price(...)
                                 # (currency/deposit_rate/total_price/explanation). The
                                 # ml-experiments-prototype loader and static fallback table
                                 # are gone.
app/models/asset_category.py, asset.py, booking.py, booking_item.py  # Phase 1e read-only models,
                                                                       # unchanged, still here
app/repositories/                                                    # now empty (Phase 1e's two
                                                                       # files relocated into
                                                                       # app/services/pricing/ above)
```

External dependency (different repo, tracked for coordination): `openspec/specs/domain-seed-data/` — Spring Boot seed data richness, not built here. **Executed and verified 2026-08-11** — no longer a pending ask; see that spec's "State after reseed".

## O — Operations

### Verification runbook

```bash
cd haystack-fast-api
# Phase 1 offline (existing)
uv run python ml-experiments/demo_scenarios.py
uv run python ml-experiments/shap_review.py

# Phase 2a (implemented 2026-08-11):
uv run pytest tests/test_pricing_feature_schema.py tests/test_pricing_model.py \
  tests/test_pricing_repository.py -v
# manual retrain: python -c "from app.services.pricing.train import retrain; retrain()"
#   → check artifacts/current.json's trained_at updated, model.py's _model_version changed

# Phase 2b (implemented 2026-08-11):
uv run pytest tests/test_pricing_client_phase1e.py tests/test_pricing_phase2b_wiring.py \
  tests/test_pricing_phase1e_wiring.py -v

# Still pending:
# category metrics regression vs design reference table (not yet re-run against this package)
```

### Phase 2d-i real-bound measurement (implemented 2026-08-12)

`ml-experiments/guardrail_calibration_check.py` is a read-only calibration probe. It uses the production `SessionLocal`, resolves `primary_snapshot`/`public` through `resolve_pricing_schema()`, joins `Asset` to `AssetCategory`, and normalizes names with `to_feature_name()`. For each real asset it mirrors the synthetic generator base-rate calculation, then keeps two comparisons separate: real bounds versus the implied category/size base, and real bound-to-base ratios versus `GUARDRAIL_MIN_RATIO_RANGE`/`GUARDRAIL_MAX_RATIO_RANGE`.

The live run read all 27 assets from `primary_snapshot` with `degraded=false`. No category had a real minimum ratio inside 0.28–0.35; maximum-band hit rates were 50% for forklift, 0% for scissor lift, 14.3% for boom lift, and 0% for excavator. The script prints the table and writes an ignored chart under `ml-experiments/outputs/phase2d/`. It loads no model and mutates no database row, baseline CSV, or production artifact. These results are inputs to Phase 2d-ii, not recalibration changes themselves.

### Phase 2d-ii recalibration and candidate build (implemented 2026-08-13)

Phase 2d-ii jointly recalibrated all scale controls: category anchors are forklift `80/220`, excavator `230/985`, scissor lift `85/205`, and conservative boom lift `120/500`; guardrail ratios are `0.74–0.88` / `1.12–1.33`; the duration curve uses floor `0.84` and rate `0.18` (`m(7)≈0.894`, `m(14)≈0.855`, `m(30)≈0.841`). The conservative boom-lift lower anchor avoids trusting an unstable extrapolation where the live fleet has no asset near the configured 12 m floor.

The generator wrote 5,000 ignored rows to `ml-experiments/data/phase2d/synthetic_pricing_data_v2.csv`. Strict checks passed, including duration anchors and feature directionality, with 35.3% generation-time target clipping. Generator sanity charts live under `ml-experiments/outputs/phase2d/`; `guardrail_calibration_check.png` belongs to Phase 2d-i, and `candidate_validation_check.png` was generated by Phase 2d-iii.

The production trainer wrote the tracked candidate `app/services/pricing/artifacts/model_v2.pkl` and `current_v2.json`. Holdout MAE/RMSE/R² are `16.6376`/`26.1103`/`0.9866`. The serving loader still reads only `model.pkl`/`current.json`, so live predictions are unchanged; Phase 2d-iii validation passed; Phase 2e promotion remains separate.

### Phase 2d-iii candidate validation (implemented 2026-08-13)

`ml-experiments/candidate_validation_check.py` is a read-only, direct-artifact comparison. It validates metadata/model feature compatibility, loads every live asset through the tiered pricing schema resolver, builds one shared production-schema feature matrix for durations 1/7/14/30, and passes that matrix to both `model.pkl` and `model_v2.pkl`. It applies the same `min(max(raw, min_daily_rate), max_daily_rate)` formula as `model.py`; neither model is loaded through the serving singleton.

Accuracy is compared on the exact same deterministic v2 holdout (`seed=42`, `test_size=0.2`). This is the decision input rather than comparing v1/v2 metadata MAEs directly, because those metadata values were measured on differently scaled datasets. The executable gate requires at least a 20 percentage-point clamp-rate reduction and candidate clamp rate ≤50% at both 7/14 days, with candidate MAE no more than 5% worse and R² no more than 0.01 lower on the common holdout.

The formal comparison inputs are fixed: 27 assets; durations 1/7/14/30; `distance_km=20.0`; production category-utilization fallbacks; and `lead_time_days=0.0`. The CLI cannot override the current/candidate artifact identities, candidate-data path, asset count, distance, or output path. Because the v2 CSV is ignored, the command also requires its exact seed-42 SHA-256 (`3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05`), row counts, and recomputed candidate MAE/RMSE/R² to agree with tracked `current_v2.json`. This closes the possibility of gating a candidate against the wrong regenerated data.

The undegraded `primary_snapshot` run evaluated 27 assets. Current→candidate clamp rates were 62.96%→11.11% at 1 day, 92.59%→25.93% at 7 days, 100%→29.63% at 14 days, and 100%→29.63% at 30 days. Common-v2-holdout MAE/RMSE/R² were 151.2595/212.3965/0.1165 for current and 16.6376/26.1103/0.9866 for candidate. Every gate and candidate-data provenance check passed. The script hash-checks all four artifact files before/after, writes only the ignored chart, and never imports/calls `reload_model()`; Phase 2e was not performed.

The generated `candidate_validation_check.png` contains an upper grouped-bar comparison of overall clamp rates and a lower category heatmap of `current − candidate` clamp-rate reduction, where positive/green cells are improvements. At 7/14/30 days the reductions were boom lift `71.43/71.43/71.43` percentage points, excavator `57.14/42.86/42.86`, forklift `83.33/83.33/83.33`, and scissor lift `57.14/85.71/85.71`; no category regressed. Excavator is the residual watch item because candidate clamp rate remains `42.86%` at 7 days and `57.14%` at 14/30 days. Phase 2e must therefore recheck that category through the promoted production path and revisit the seed outlier/rate-card fit if the result persists.

Final verification passed: 8 focused tests, 391 full-suite tests passed and 5 skipped, Ruff, and diff hygiene. The chart is an ignored scratch output; it is the only Phase 2d-iii image and no artifact or database path was written.

Verification:

```bash
uv run python ml-experiments/generate_synthetic_data.py \
  --output ml-experiments/data/phase2d/synthetic_pricing_data_v2.csv \
  --plots-dir ml-experiments/outputs/phase2d --strict
uv run pytest tests/test_candidate_validation_check.py -q
uv run python ml-experiments/candidate_validation_check.py
```

### Phase 2e calibrated-model promotion (implemented 2026-08-17)

The pre-promotion serving pair is retained as `model_v1.pkl`/`current_v1.json`; its SHA-256 identities are `7c8e8d98d6626fa6991c1e7648739700b0bcb60ee557881522311da6dbb0b0fe` and `4c4131c40a1919e468724da7b38e004b1d03a8b91f2011932e5c71b7ad15d0d9`. The reviewed v2 files remain in place, and the literal serving filenames are byte-identical to them (`dd665d21f4f36176a40dca7c831c80c216155cc75f3605cc787d956ddbd29571` for the model and `98a19dcb1f7fe5fe4097f5855202f12e1e5312845d57237f01f3a6131e0cddca` for metadata).

`ml-experiments/phase2e_serving_smoke.py` verifies those identities, calls `reload_model()`, loads all 27 assets from the tiered pricing schema, and calls the production `predict_price()` entrypoint at 1/7/14/30 days with the Phase 2d-iii fixed inputs. The undegraded `primary_snapshot` run reported `prod-2026-08-13` and reproduced aggregate clamp rates of 11.11%/25.93%/29.63%/29.63%. Excavator reproduced 0%/42.86%/57.14%/57.14%, so it remains a monitoring concern rather than a promotion discrepancy.

Rollback copies the v1 pair back onto the literal serving filenames and then performs the same reload and smoke. Phase 3 promotion may replace the serving pair later, but it must preserve its own generation boundary.

Verification:

```bash
uv run pytest tests/test_pricing_phase2e_promotion.py -q
uv run python ml-experiments/phase2e_serving_smoke.py
```

### Implementation branches

| Branch | Scope |
|--------|--------|
| `HR-87-ml-2-d-production-db-wiring-for-period-utilization` | **Done (2026-08-10)** — Phase 1e: read-only models, `pricing_repository.py`, `pricing_read_resilience.py` tiered fallback; 20 new unit tests |
| `feature/ml-3-pricing-service` | **Done (2026-08-11)** — scaffolded package, ported schema, built `model.py`/`train.py`, real per-asset guardrail clamping, relocated Phase 1e's read models/repositories in as `repository.py`/`read_resilience.py`, fixed the category-name mismatch (`category_mapping.py`); 24 new unit tests, 144 total passing, live-verified against all 27 real assets |
| `feature/ml-6-internal-pricing-api` | **Done (2026-08-11)** — `POST /internal/v1/pricing/quote` (`app/api/internal_pricing.py`, `app/schemas/pricing.py`, `repository.py::get_asset_for_pricing()`); 5 new unit tests, 149 total passing. Resequenced ahead of `feature/ml-4-integration-tests` (lean Phase 2b) — see "Internal quote API" above |
| `feature/ml-4-integration-tests` | **Done (2026-08-11)** — pipeline wired (`pricing_client.py` swapped to `app.services.pricing.model.predict_price(...)`, `min_daily_rate`/`max_daily_rate` threaded through `predict_price_adapter.py`); pipeline-integration tests only (guardrail/feature-schema tests already covered) — `tests/test_pricing_client_phase1e.py` rewritten, `tests/test_pricing_phase2b_wiring.py` added (2 new tests); 154 total passing. Manual retrain endpoint stays moved to demo-prep subtask |
| `HR-118-ml-real-bound-measurement` | **Done (2026-08-12)** — Phase 2d-i read-only real-bound measurement; 27 assets loaded undegraded from `primary_snapshot`, two calibration knobs compared, ignored chart generated; no production data/artifact changes; 188 tests passing |
| `HR-141-ml-recalibration-candidate-build` | **Done (2026-08-13)** — Phase 2d-ii joint recalibration and versioned candidate build; strict 5,000-row generation checks passed, candidate MAE 16.64/R² 0.9866; serving artifacts untouched |
| `HR-146-ml-candidate-validation` | **Done (2026-08-13)** — Phase 2d-iii direct-artifact comparison, 8 focused tests, ignored chart, 27-asset multi-duration run, common-v2-holdout accuracy and SHA/metadata provenance comparison; every Phase 2e gate passed; serving artifacts unchanged |
| `2026-08-17-phase2e-model-promotion` | **Done (2026-08-17)** — v1 rollback preservation, v2 serving promotion, artifact identity tests, hot reload, and 27-asset production-path smoke |

## N — Norms

- In-process only for prediction; no public **renter-facing** pricing API. `POST /internal/v1/pricing/quote` is a scoped exception: internal, service-to-service only (Spring Boot → Haystack), never called by a renter client, never mounted under the public `/api/v1` router.
- Guardrails from per-asset rate bounds, not env tables.
- Port feature schema from ml-experiments — do not re-derive.
- Spring owns schema; Python maps only.
- Full decision rationale lives in masterplan; this design restates contract only.

## S — Safeguards

- Do not treat `ml-experiments/predict_price.py` as satisfying production requirements.
- Do not expose `/predict-price` to renters.
- Do not invent `weekly_rate = daily × 7` on recommend surfaces.
- Do not "fix" low period_utilization early-booking prices.
- Do not add booking_month, fuel price, or purchaseYear without a new decision + this capability update.
- Do not register public retrain without auth SDD.
- Do not compare `AssetCategory.name` against `feature_schema.CATEGORIES` (or vice versa) without going through `DB_NAME_TO_FEATURE_NAME` — a silent zero-row match degrades to the static fallback with no error, the exact bug found 2026-08-11.
- Do not "fix" the category mismatch by renaming `asset_categories.name` values in the DB — see "Category name mapping" above for why the mapping lives in Haystack code, not seed data.
- Do not write a test for category-name-dependent code paths using a fully mocked `session.execute()` only — it can't catch a filter-clause mismatch; assert against real DB-shaped names too.
- Do not build `POST /internal/v1/pricing/quote` against `ml-experiments/predict_price.py`'s static per-category guardrail stand-in — it must use `app/services/pricing/model.py`'s real per-asset clamping, or the guardrail bounds returned to Spring Boot are wrong.
- Do not mount `/internal/v1/pricing/quote` under the public `/api/v1` router, and do not call it from any renter-facing client — service-to-service only (Spring Boot).
- Do not add a `POST /internal/v1/pricing/estimate` endpoint without a new decision — dropped in favor of a flat, non-ML base price on Spring Boot's browse/detail page.
- Do not persist `raw_price` per quote item on Spring Boot's side — deliberately excluded from the audit fields (see spec.md Key decisions); track guardrail-clamp magnitude as Haystack-side monitoring instead.

## Key decisions

See [`spec.md`](./spec.md) Key decisions / non-goals table (mirrored here for REASONS completeness).

| Decision | Why |
|---|---|
| In-process function | Same owner; no HTTP overhead |
| Per-asset guardrails | Admin-editable; matches training clamp |
| NaN platform_height | Structurally N/A for non-aerial |
| No Alembic / no new tables | Spring owns schema |
| Sync SQLAlchemy + psycopg | Project default |
| Manual retrain now | Demo safety net; APScheduler Phase 3 |
| Spec-band + period_utilization | Correct scarcity signal |
| booking_month / fuel not added | Superseded / rejected |
| Category-name mapping fixed in code, not DB data | `AssetCategory.name` is Spring-Boot canonical; `feature_schema.CATEGORIES` is the derived ML slug baked into trained artifacts |
| `mlPredictedPrice` non-persistence: **locked**, not pending | Confirmed 2026-08-11 — see spec.md Change control 2.2.0 |
| `/internal/v1/pricing/quote`: new internal HTTP surface, gated on real guardrail clamping | Spring Boot needs synchronous authoritative checkout pricing; still never renter-facing; must not ship against the static-guardrail prototype |
| `distance_km` sent by Spring Boot, not geocoded here | Real geocoding stays a non-goal; Spring Boot already has both addresses |
| `deposit_rate` fixed constant, response-only | Single source of truth; not asset/category-dependent today |
| No `/internal/v1/pricing/estimate` | Flat base price pre-checkout; live pricing only at quote time |
| Quote audit: `model_version`/`was_clamped` persisted, `raw_price` excluded | Redundant when unclamped; a calibration signal, not a per-transaction fact, when clamped |

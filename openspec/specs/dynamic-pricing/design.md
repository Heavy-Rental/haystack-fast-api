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

```text
app/services/pricing/
├── __init__.py
├── model.py           # load current.json + model.pkl once, expose predict_price(...)
├── train.py            # retrain entrypoint (ports ml-experiments/train.py's logic)
├── feature_schema.py   # ports ml-experiments/feature_schema.py near-verbatim
└── artifacts/
    ├── model.pkl
    └── current.json
```

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

### Category name mapping (found + scoped 2026-08-11)

`AssetCategory.name` in the real DB is the Spring-Boot canonical business name: `Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`. `feature_schema.CATEGORIES` — baked into the trained model's one-hot columns, and used as the `category` string everywhere in pricing code (`pricing_tables.py` keys, `spec_band()`, today's `seed_fleet.py` candidate fixtures) — uses a different convention: `excavator`, `scissor lift`, `boom lift`, `forklift`. These never coincide, not even case-insensitively (`Fork Lift` vs. `forklift` differs by more than case).

**Confirmed live** (2026-08-11, against `postgres-haystack`/`heavy_rental`): `pricing_repository.compute_period_utilization()`'s `.where(AssetCategory.name == category)` join returns zero rows for every real category when called with a `feature_schema`-style `category` string — it silently falls through to `pt.CATEGORY_UTILIZATION.get(category, 0.0)`, the static per-category constant, with no error and no degraded flag. Called with a DB-style name instead, `feature_schema.spec_band()` raises `ValueError` (it only recognizes the `feature_schema.CATEGORIES` spelling). Either direction is broken. `tests/test_pricing_repository.py` didn't catch this because its `_session_returning()` helper mocks `session.execute` directly — the mocked return value never passes through the real `WHERE` clause, so a mismatched filter can't fail a test built that way.

**Fix (Phase 2a scope, folded into the Phase 1e→`app/services/pricing/` relocation, not a separate task)**: a single shared mapping, applied once at the read boundary where an `AssetCategory` row's `name` is consumed —

```python
# DB canonical name -> feature_schema.CATEGORIES slug
DB_NAME_TO_FEATURE_NAME = {
    "Excavator": "excavator",
    "Scissors Lift": "scissor lift",
    "Boom Lift": "boom lift",
    "Fork Lift": "forklift",
}
```

Applied where `AssetCategory.name` is read out of a row (so every downstream `category` string — including what's passed into `spec_band()`, `compute_period_utilization()`'s own join, and `resolve_effective_capacity()`) is always in `feature_schema` convention from that point on. The join itself (`AssetCategory.name == category`) still needs the DB-style name on its left side — so `compute_period_utilization()` inverts the mapping (or queries by `category_id` via a small lookup) rather than comparing a `feature_schema`-style string against the DB column directly. Direction matters: **DB name is the source of truth**, ML slug is the derived form — don't rename `AssetCategory.name` values to match the model; the model's one-hot columns adapt via this mapping, not the other way around.

Test coverage gap this closes: at least one test must exercise the real `WHERE` clause with real DB-shaped names (e.g. an in-process test DB, or asserting on the compiled SQL/bound params), not only a fully mocked `session.execute` — see spec.md Verification.

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
2. **Sustained (a failed cycle — hours, up to the ~24h sync interval).** If tier 1's retries exhaust, re-issue the same read(s) against `public` instead — a real value, at most one sync cycle stale, not a fabricated default. Mark the resulting `PriceResult` as degraded using `pricing_client.py`'s existing "model unavailable" pattern (`model_version`, `explanation`).
3. **Cold start (neither schema exists).** A container that has never completed a sync. `predict_price(...)` fails loud (raises) rather than returning a fabricated price.

**Implementation shape**: `app/repositories/pricing_read_resilience.py`'s `resolve_pricing_schema(session) -> PricingSchemaResolution` — called once per `predict_price_for_asset()` call, its `.execution_options` (SQLAlchemy's `schema_translate_map`, `{}` when reading `primary_snapshot` unmodified) threaded into every subsequent `session.execute(...)` in that call. This avoids declaring a second set of models pointed at `public` — the same `AssetCategory`/`Asset`/`Booking`/`BookingItem` classes (declared with `schema="primary_snapshot"`) serve both tiers; `schema_translate_map` redirects the table name at query time.

### Guardrail clamping

```text
predicted = model.predict(features)
clamped = min(max(predicted, asset.minDailyRate), asset.maxDailyRate)
```

Read per-asset at prediction time (admin-editable via asset admin-portal tag) — no separate config table or env var.

### Internal quote API (added 2026-08-11)

`POST /internal/v1/pricing/quote` — synchronous, service-to-service only (Spring Boot → Haystack), authoritative per-asset quote at checkout. Reuses this package's `predict_price(...)` — no second prediction path. Registered as its own router (`app/api/internal_pricing.py`), **not** mounted under the public `/api/v1` prefix; restrict at network/ops level, same interim posture as the manual retrain path (see Security notes) until real auth exists.

**Hard dependency**: requires this capability's real per-asset guardrail clamping (`Asset.minDailyRate`/`maxDailyRate`) and the category-name mapping fix above to already be in place — building this against `ml-experiments/predict_price.py`'s static per-category stand-in would hand Spring Boot the wrong `min_daily_rate`/`max_daily_rate` shape it was already told to expect. Build after `feature/ml-3-pricing-service` lands (see Implementation branches).

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

app/services/pricing/           # Phase 2 target (this capability)
  model.py, train.py, feature_schema.py, artifacts/

app/api/internal_pricing.py     # Phase 2a addition: POST /internal/v1/pricing/quote
                                 # (service-to-service, not under the public /api/v1 router;
                                 # hard-depends on app/services/pricing/model.py's real
                                 # per-asset guardrail clamping + category-name mapping)

app/services/pricing_client.py  # as-built recommend adapter → ml-experiments / future production
app/models/asset_category.py, asset.py, booking.py, booking_item.py  # Phase 1e read-only models
app/repositories/pricing_repository.py         # Phase 1e: live period_utilization query
app/repositories/pricing_read_resilience.py    # Phase 1e: primary_snapshot/public tiered fallback
                                                # Phase 2a also adds: DB_NAME_TO_FEATURE_NAME mapping
                                                # (category name normalization, see "Category name
                                                # mapping" above) — lands in this same repository move
```

External dependency (different repo, tracked for coordination): `openspec/specs/domain-seed-data/` — Spring Boot seed data richness, not built here. **Executed and verified 2026-08-11** — no longer a pending ask; see that spec's "State after reseed".

## O — Operations

### Verification runbook

```bash
cd haystack-fast-api
# Phase 1 offline (existing)
uv run python ml-experiments/demo_scenarios.py
uv run python ml-experiments/shap_review.py

# After Phase 2:
# unit tests for feature schema, guardrails, prediction shape
# manual retrain → check current.json trained_at
# category metrics regression vs design reference table
```

### Implementation branches

| Branch | Scope |
|--------|--------|
| `HR-87-ml-2-d-production-db-wiring-for-period-utilization` | **Done (2026-08-10)** — Phase 1e: read-only models, `pricing_repository.py`, `pricing_read_resilience.py` tiered fallback; 20 new unit tests |
| `feature/ml-3-pricing-service` | Scaffold package, port schema, model/train, guardrails, **relocate** (don't rebuild) Phase 1e's read models/repositories, **fix category-name mismatch** (`DB_NAME_TO_FEATURE_NAME`, found 2026-08-11) |
| `feature/ml-4-integration-tests` | Wire pipeline, unit tests, manual retrain endpoint |
| `feature/ml-6-internal-pricing-api` | `POST /internal/v1/pricing/quote` — hard depends on `feature/ml-3-pricing-service`; can run alongside/after `feature/ml-4-integration-tests` (shares the same production `model.py`) |

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

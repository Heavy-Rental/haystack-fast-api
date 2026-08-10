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
| `condition` | ordinal, `NEEDS_REPAIR=0…EXCELLENT=3` | `Asset.condition` |
| `duration_days` | numeric passthrough | `Booking.endDate − Booking.startDate` |
| `capacity` | numeric passthrough | `Asset.capacity` |
| `distance_km` | numeric passthrough | Phase 1/2: still a sampled proxy, not geocoded |
| `platform_height` | numeric, **NaN for forklift/excavator** | `Asset.platform_height`; native missing for XGBoost, not imputed |
| `period_utilization` | numeric passthrough, `[0,1]` | Live aggregate over same `category` + spec-band; status `CONFIRMED`/`PENDING`, non-cancelled; at prediction time — **Phase 1d/1e** |
| `lead_time_days` | numeric passthrough | `Booking.startDate − today`; derived — **Phase 1d** |

Target: `price_per_day` (training-time only; not part of the prediction input).

**Spec-band bucketing** (excavator/forklift by `capacity`, scissor/boom lift by `platform_height`) avoids a fully-booked small-excavator fleet making a large excavator look scarce. Fixed constants (`pricing_tables.CAPACITY_BINS`/`HEIGHT_BINS`, no persisted column) — see that file's comments and `feature_schema.spec_band()`.

**Scarcity pricing is intentional, not a bug**: early booking on an unclaimed window legitimately prices lower (airline/hotel-style).

`booking_month`/seasonality: resolved **not added** — `period_utilization` already captures realized seasonality.

### Data access (open item — confirm before implementing)

Pricing needs read access to `AssetCategory.name`, `Asset.category_id`/`capacity`/`condition`/`platform_height`/`minDailyRate`/`maxDailyRate`, and `Booking.startDate`/`endDate`/`status`, plus write access to `RecommendationItem.mlPredictedPrice`. **`app/models/` currently has no concrete models** — just a `Base` re-export placeholder. Spring Boot owns schema/migrations; Python maps existing tables (no Alembic, no new tables).

Before implementing `model.py`, confirm against the actual Spring Boot schema:

- Exact table/column names and casing (diagram-sourced camelCase vs real snake_case).
- Whether `Asset.platform_height` exists as a real column yet.
- Whether `BookingStatus` has a `CONFIRMED` member — only `PENDING`/`CANCELLED` named in this repo, but period_utilization requires `CONFIRMED`/`PENDING`, non-cancelled.

Introduce only minimal SQLAlchemy declarative models pricing actually reads/writes.

**Phase 1e**: `period_utilization`'s live query is pulled forward ahead of this package — `app/repositories/pricing_repository.py`, first-ever read-only SQLAlchemy models, wired into existing `pricing_client.py` → `predict_price.py`. This package **relocates**, not rebuilds, that logic when built.

### Guardrail clamping

```text
predicted = model.predict(features)
clamped = min(max(predicted, asset.minDailyRate), asset.maxDailyRate)
```

Read per-asset at prediction time (admin-editable via asset admin-portal tag) — no separate config table or env var.

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

app/services/pricing_client.py  # as-built recommend adapter → ml-experiments / future production
app/repositories/pricing_repository.py  # Phase 1e target for live utilization query
```

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
| `feature/ml-3-pricing-service` | Scaffold package, port schema, model/train, guardrails, minimal ORM |
| `feature/ml-4-integration-tests` | Wire pipeline, unit tests, manual retrain endpoint |

## N — Norms

- In-process only for prediction; no public renter pricing API.
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

# Specification: Dynamic Pricing

| Field | Value |
|-------|--------|
| **Document type** | SDD feature spec |
| **Status** | Draft — Phase 2 (productionize) and Phase 3 (seeding + scheduled retrain) not yet implemented |
| **Feature module** | `app/services/pricing/` (to be created) |
| **Depends on** | [`SPEC-project-setup.md`](./SPEC-project-setup.md) — environment, layering, uv, Postgres (normative) |
| **Related, not specs** | `docs/dynamic-pricing-masterplan.md` (decision log — this spec restates only what Phase 2 needs to build against, not the full reasoning trail) and `docs/dynamic-pricing-execution-plan.md` (day-by-day tasks/branches) |
| **Built on** | `ml-experiments/` — Phase 1 offline experimentation (scratch, outside SDD, no spec). This spec productionizes the model and feature schema already trained and validated there. |
| **Explicitly out of scope here** | `SPEC-domain-seed-data.md` (Phase 3 seed data — not yet written; separate spec since the schema is shared across other features) |

**Read [`SPEC-project.md`](./SPEC-project.md) and [`SPEC-project-setup.md`](./SPEC-project-setup.md) before this document.**

> **Phase 1c note (2026-08-05):** `ml-experiments/predict_price.py` prototypes this spec's `predict_price(...)` contract early — guardrail clamping included — so the in-development agent prototype can call it before Phase 2 (this spec) lands. It remains `ml-experiments/` scratch code, out of SDD scope like the rest of Phase 1, and its guardrail bounds are a **static per-category stand-in** (`pricing_tables.CATEGORY_BASE_RATE`), not the real per-asset `Asset.minDailyRate`/`maxDailyRate` this spec requires (§5.4). It is fully superseded once this spec is implemented — do not treat it as satisfying any requirement in §4.

---

## 1. Purpose

Phase 1 (`ml-experiments/`) produced and validated a baseline XGBoost model that predicts `price_per_day` for equipment rentals from `category`, `condition`, `duration_days`, `capacity`, `distance_km`, and `platform_height`. This spec defines how that model and its feature schema get **productionized** into `app/services/pricing/` so the agentic recommendation pipeline can call it in-process and persist a data-driven price suggestion, without duplicating the decision log in `docs/dynamic-pricing-masterplan.md`.

---

## 2. Outcomes

When this spec is implemented:

- `app.pipelines` (or wherever the agentic recommendation step lives) can call a single in-process function to get a guardrail-clamped price prediction for a given asset/booking combination.
- The result lands on `RecommendationItem.mlPredictedPrice` — never returned to a renter-facing route directly.
- A manual "retrain now" path exists as a demo safety net, without requiring the full APScheduler-based scheduled retrain (Phase 3).
- The feature schema, encoding rules, and artifact format match what Phase 1b already validated — no silent re-derivation of decisions already locked in the masterplan.

---

## 3. Scope

### In scope
- `app/services/pricing/` package: `model.py` (load + predict), `train.py` (retrain), `feature_schema.py` (ported from `ml-experiments/feature_schema.py`), `artifacts/` (`.pkl` + `current.json`).
- Guardrail clamping of the raw model output to `Asset.minDailyRate`/`Asset.maxDailyRate`.
- An in-process `predict_price(...)` function, called directly from the pipeline — not an HTTP route.
- A manual "retrain now" endpoint (internal/ops use, not renter-facing).
- Minimal SQLAlchemy read models for exactly the columns pricing touches (see §5.3) — mapped onto the existing Spring-Boot-owned schema, no new tables, no Alembic.
- Unit tests: feature schema transforms, guardrail clamping, prediction shape.

### Out of scope (this spec)
- `/predict-price` as a public HTTP endpoint (masterplan: resolved as in-process function call).
- Full APScheduler scheduled retrain (Phase 3).
- Real geocoding for `distance_km` (Phase 1 uses a sampled proxy; still true in Phase 2 — no live bookings to geocode against yet).
- `purchaseYear` as a feature (evaluated in Phase 1b, not added — see masterplan).
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

### 5.2 Feature schema (locked, from Phase 1b)

Ports `ml-experiments/feature_schema.py` directly — same `CATEGORIES`, `CONDITION_ORDER`, `FEATURE_COLUMNS`, `build_features()`/`get_target()` logic. No changes expected beyond adapting the input from a `pandas.DataFrame` (CSV-sourced in Phase 1) to a single row/dict sourced from ORM objects (§5.3).

| Feature | Encoding | Notes |
|---|---|---|
| `category` | one-hot, fixed `CATEGORIES` order | via `AssetCategory.name`; never encode the raw FK |
| `condition` | ordinal, `NEEDS_REPAIR=0…EXCELLENT=3` | `Asset.condition` |
| `duration_days` | numeric passthrough | `Booking.endDate − Booking.startDate` |
| `capacity` | numeric passthrough | `Asset.capacity` |
| `distance_km` | numeric passthrough | Phase 1/2: still a sampled proxy, not geocoded (see Scope) |
| `platform_height` | numeric, **NaN for forklift/excavator** | `Asset.platform_height`; left as a native missing value for XGBoost, not imputed — see masterplan for why |

Target: `price_per_day` (training-time only; not part of the prediction input).

**Open decision, not locked: `booking_month`/seasonality.** Not in the table above — Phase 1b's per-`booking_month` MAE/R² breakdown found a mild pattern (January worst: R² 0.928 vs. ~0.98 typical) consistent with the model missing seasonality signal, but small enough that the current lean is against adding it. Decide explicitly before implementation task 1 (§7) finalizes this table — see `docs/dynamic-pricing-masterplan.md`'s open questions. If added: prefer a cyclical encoding (sin/cos of month) over a raw 1-12 ordinal.

### 5.3 Data access (open item — confirm before implementing)

Pricing needs read access to `AssetCategory.name`, `Asset.category_id`/`capacity`/`condition`/`platform_height`/`minDailyRate`/`maxDailyRate`, and `Booking.startDate`/`endDate`, plus write access to `RecommendationItem.mlPredictedPrice`. **`app/models/` currently has no concrete models** — just a `Base` re-export placeholder. Per the masterplan, Spring Boot owns the schema/migrations; Python maps onto the existing tables (no Alembic, no new tables).

Before implementing `model.py`, confirm against the actual Spring Boot schema (not just the ERD/Class Diagram field names referenced in the masterplan):
- Exact table/column names and casing (the masterplan's field list is diagram-sourced, e.g. `purchaseYear`/`baseDailyRate` read as camelCase — confirm whether the real Postgres columns are camelCase or snake_case).
- Whether `Asset.platform_height` exists as a real column yet, or needs to be added by whoever owns that migration.

Introduce only the minimal SQLAlchemy declarative models pricing actually reads/writes (not a full domain model set) — narrow surface, less staleness risk if the shared schema evolves elsewhere.

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

---

## 6. Verification

- Unit tests (new, under `tests/`): feature schema transforms (one-hot columns, ordinal mapping, NaN passthrough for non-aerial `platform_height`), guardrail clamping (below-min, above-max, in-range cases), prediction output shape/type.
- Manual smoke: call `predict_price(...)` for one asset per category (mirroring `ml-experiments/shap_review.py`'s per-category sweeps) and confirm clamped output is within `[minDailyRate, maxDailyRate]`.
- Manual retrain smoke: invoke the retrain path, confirm `artifacts/current.json`'s `trained_at` updates and a subsequent prediction reflects the new model.
- Regression check: re-run `ml-experiments/category_metrics.py`-equivalent logic (or port it) against the productionized model periodically; flag if any category's MAE/R² drifts materially from §5.6.

---

## 7. Implementation tasks

Maps to `docs/dynamic-pricing-execution-plan.md`'s Day 4–5 subtasks:

1. `feature/ml-3-pricing-service` (Day 4): **first, decide the `booking_month`/seasonality open item (§5.2)**; then scaffold `app/services/pricing/`, port `feature_schema.py`, implement `model.py`/`train.py`, guardrail clamping, minimal SQLAlchemy read models (§5.3 — confirm schema first).
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

**Non-goals**: renter-facing pricing API/UI, real geocoding, `purchaseYear` feature, Alembic migrations, async DB access, full auth/JWT stack (blocks nothing here, but the retrain path should not assume it's protected until one exists).

**Open, not a non-goal**: `booking_month`/seasonality as a feature is genuinely undecided (leaning against, not excluded) — see §5.2. Don't treat its absence from the feature table as final until this is explicitly resolved in Phase 2.

---

## 9. Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-04 | Initial draft, written at the Phase 1→2 boundary per the masterplan's phase order. Productionization plan for the Phase 1b-validated model (category/condition/duration_days/capacity/distance_km/platform_height, R²=0.976 overall on synthetic holdout). Not yet implemented — `app/services/pricing/` does not exist yet. |
| 1.1.0 | 2026-08-04 | Added `booking_month`/seasonality as an explicit open decision (§5.2, §8) carried into implementation task 1 (§7) — a per-`booking_month` MAE/R² check in Phase 1b found a mild pattern worth a deliberate call, not locked either way. |
| 1.2.0 | 2026-08-05 | Added Phase 1c disambiguation note (after header table) — `ml-experiments/predict_price.py` prototypes this spec's contract early for the upcoming agent prototype, with static per-category guardrail bounds standing in for the real per-asset clamp this spec requires. No change to scope, requirements, or design — this spec's implementation is still Phase 2, not started. |

# Proposal: Scheduled monthly retrain with validated promotion

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2026-08-15 |
| **Capability** | `dynamic-pricing` |
| **Phase** | 3a–3d (reserved "Phase 3" name — see `spec.md` Status field) |
| **Plan** | [`docs/dynamic-pricing-scheduled-retrain-plan.md`](../../../docs/dynamic-pricing-scheduled-retrain-plan.md) |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

`spec.md`'s "Requirement: Manual retrain path (US-2)" spec'd a "retrain now" HTTP
endpoint as a demo safety net, pending the masterplan's real, always-intended
design: an in-process APScheduler job, interval configurable via env var,
deferred to "Phase 3". The endpoint was descoped repeatedly across Phase 2b's
resequencing and subtask 5 (demo prep) and **never actually built** —
`train.py::train()`/`retrain()` exist and work, but nothing has ever called them
except by hand.

Decision: **scrap the manual endpoint entirely.** The scheduler becomes the
sole retrain trigger, monthly. No HTTP route for on-demand retrain exists or
should be added.

Phase 2d separately found that a naively retrained model can regress badly
against production guardrails (why Phase 2d/2e — one-time recalibration gated
by clamp-rate/MAE/R² checks — exists at all). A monthly *automated* retrain
carries the same risk every cycle, so this change reuses that same
validate-before-promote discipline: train a versioned candidate, compare it
against the currently-serving model on the gate Phase 2d-iii established, and
promote only on a pass.

This is also the right vehicle to finally build the synthetic→real data blend
`design.md`'s "Phase 3 — cold-start bootstrap, blend, per-category cutover"
section sketched but explicitly deferred ("no code until real data exists").
Investigation confirms real per-booking price data (`booking_items.daily_rate`)
now exists in the schema Haystack already reads — so this change builds the
blend/cutover mechanism as part of the same feature, not a separate future ask.

**Originally planned in parallel with Phase 2e**, which completed separately on 2026-08-17. This
change touches an entirely disjoint set of files — new modules, plus additive
changes to `app/config.py`/`app/main.py`/`pyproject.toml`/`.gitignore` — so
there is no merge risk between the two efforts. `openspec/specs/dynamic-pricing/
{spec.md,design.md}` are touched only once, at the end (a later, separate
archival change), to fold in the finished requirement and formally retire
"Manual retrain path (US-2)" — not mid-flight.

## Scope

- New `app/services/pricing/promotion_gate.py`: the comparison/gate logic
  already implemented in `ml-experiments/candidate_validation_check.py`,
  extracted into a canonical, reusable module (that script refactored to
  import from it). `assess_gate` generalized with `expected_asset_count`/
  `min_asset_count` so a recurring job doesn't need a hardcoded fleet size.
- New `ml-experiments/real_training_data_check.py`: live read-only probe
  confirming `booking_items.daily_rate`/`subtotal` are populated/plausible in
  the seeded DB, before anything is built on top of that assumption.
- Real training-data extraction: `daily_rate`/`subtotal` added to
  `app/models/booking_item.py`; `created_at`/`total_amount` added to
  `app/models/booking.py`; new `repository.py::fetch_real_training_rows()`.
- New `app/services/pricing/blend.py`: `build_training_dataset()` — blends
  real training rows with the existing synthetic dataset, weighting real rows
  higher, and drops synthetic rows per category once that category clears a
  configurable minimum real-row count (cutover). `train.py::train()` extended
  with optional `data`/`sample_weight` parameters.
- New `app/services/pricing/retrain_job.py`: `run_scheduled_retrain()` —
  builds the blended dataset, trains a versioned candidate, evaluates it via
  `promotion_gate`, and promotes (backup + swap + `reload_model()`) only on a
  gate pass; never raises, always records an outcome.
- New `app/services/pricing/scheduler.py`: in-process `AsyncIOScheduler`
  wired into `app/main.py`'s `lifespan`, interval configurable via
  `PRICING_RETRAIN_INTERVAL_DAYS` (default 30/monthly), restart-safe via a
  dedicated `retrain_state.json` last-run record.
- New `PRICING_RETRAIN_*` settings in `app/config.py` (default-disabled, so
  the existing test suite's `TestClient(app)` lifespan invocations are
  unaffected), new `apscheduler` dependency, `.gitignore` additions for
  runtime-generated candidate/backup/state artifacts.

## Architecture

Detail sufficient to implement each phase without re-deriving design
decisions. Phase labels match `tasks.md`/`docs/dynamic-pricing-scheduled-retrain-plan.md`.

### Phase 3a — `promotion_gate.py`

Extract from `ml-experiments/candidate_validation_check.py`, unchanged
behavior: `build_validation_rows`, `evaluate_model`, `summarize_predictions`,
`evaluate_common_holdout`, `assess_gate`, `validate_artifact_contract`,
`validate_model_features`, `load_live_assets` — all pure functions
(DataFrame-in/out or `Session`-in). `candidate_validation_check.py` keeps only
what's script-specific: `EXPECTED_CANDIDATE_DATA_SHA256`/
`validate_candidate_data_provenance` (SHA-pinned to one frozen historical
CSV — meaningless for a job retraining from the live data path every month,
so **not** reused by the scheduled job), `render_chart` (no human reviewer
for an automated monthly run, so **not** reused either), `_print_results`,
`main()`.

Required generalization: `assess_gate`'s asset-count check is pinned to
exactly `EXPECTED_ASSET_COUNT = 27` today (correct for a one-time
provenance-checked comparison, wrong for a recurring job against a fleet
that will grow). Add:

```python
def assess_gate(
    summary: pd.DataFrame,
    accuracy: pd.DataFrame,
    *,
    actual_asset_count: int,
    expected_asset_count: int | None = None,  # exact-match mode (script, unchanged)
    min_asset_count: int = 1,  # sanity-floor mode (scheduled job)
) -> GateDecision: ...
```

`candidate_validation_check.py` calls `assess_gate(..., expected_asset_count=EXPECTED_ASSET_COUNT)`
to preserve its exact existing behavior byte-for-byte. The scheduled job
(Phase 3c) calls `assess_gate(..., expected_asset_count=None, min_asset_count=1)`.

`real_training_data_check.py` (also Phase 3a): read-only script, same pattern
as `ml-experiments/guardrail_calibration_check.py` — query all `booking_items`
joined to `bookings`/`assets`/`asset_categories`, report null/zero-rate of
`daily_rate`/`subtotal` per status and per category.

### Phase 3b — real training-row extraction + blend

`app/models/booking_item.py`: add `daily_rate`/`subtotal` (both nullable,
matching `openspec/specs/spring-entity-repository/spec.md` §5.8). `app/models/booking.py`:
add `created_at`/`total_amount` (§5.7).

```python
REALIZED_PRICE_STATUSES = {"CONFIRMED", "MOBILISED", "COMPLETED"}


def fetch_real_training_rows(
    db: Session,
    resolution: PricingSchemaResolution,
    *,
    statuses: set[str] = REALIZED_PRICE_STATUSES,
) -> pd.DataFrame: ...
```

Patterned directly off `compute_period_utilization()`'s `Asset ⋈ AssetCategory`
/ `BookingItem ⋈ Booking` join shape and `resolution.execution_options`
threading. For each `BookingItem` with non-null, positive `daily_rate` whose
parent `Booking.status` is in `statuses` (excludes `PENDING_DEPOSIT`/
`PENDING_CONFIRMED` — no price is final yet — and `CANCELLED`), emit one row:

| Column | Source |
|---|---|
| `category` | `AssetCategory.name` via `category_mapping.to_feature_name()` |
| `condition` | `Asset.condition` |
| `capacity` | `Asset.capacity` |
| `platform_height` | `Asset.platform_height` |
| `duration_days` | `Booking.end_date − Booking.start_date` |
| `distance_km` | **imputed** via `ml-experiments/generate_synthetic_data.py::sample_distance_km(rng, n)` — no real equivalent exists in the schema (open item) |
| `period_utilization` | `compute_period_utilization()` called **as-is**, with that booking's own `start_date`/`end_date` — the function already takes a window parameter rather than assuming "now", so it works unmodified as a point-in-time historical estimate |
| `lead_time_days` | `start_date − created_at.date()`, falling back to `0` when `created_at` is null |
| `price_per_day` (target) | `daily_rate` |

```python
def build_training_dataset(
    real_rows: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    *,
    min_real_rows_per_category: int,
    real_sample_weight: float,
) -> tuple[pd.DataFrame, np.ndarray]: ...
```

Per category: if real row count ≥ `min_real_rows_per_category`, drop synthetic
rows for that category entirely (cutover). Otherwise keep synthetic rows for
that category, blended with whatever real rows exist so far. Returns the
combined DataFrame plus a `sample_weight` array (`real_sample_weight` for real
rows, `1.0` for synthetic) for `model.fit(X, y, sample_weight=...)`. Empty
`real_rows` degrades to pure-synthetic behavior, byte-equivalent to today.

`train.py::train()` extended with two new optional parameters, both
backward-compatible (existing callers — CLI, `retrain()`, Phase 2d's scripts —
pass neither and are unaffected):

```python
def train(
    *,
    data: pd.DataFrame | None = None,  # bypasses pd.read_csv(data_path) when given
    sample_weight: np.ndarray | None = None,  # threaded into model.fit(...)
    data_path: Path = DEFAULT_DATA_PATH,
    seed: int = 42,
    test_size: float = 0.2,
    model_out: Path = DEFAULT_MODEL_PATH,
    meta_out: Path = DEFAULT_META_PATH,
) -> dict[str, Any]: ...
```

### Phase 3c — `retrain_job.py`

```python
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
CANDIDATE_MODEL_PATH = ARTIFACTS_DIR / "model_candidate.pkl"
CANDIDATE_META_PATH = ARTIFACTS_DIR / "current_candidate.json"
PREVIOUS_MODEL_PATH = ARTIFACTS_DIR / "model_previous.pkl"
PREVIOUS_META_PATH = ARTIFACTS_DIR / "current_previous.json"
STATE_PATH = ARTIFACTS_DIR / "retrain_state.json"

Status = Literal["promoted", "gate_failed", "error"]


def run_scheduled_retrain() -> RetrainOutcome: ...  # never raises
def load_state() -> RetrainState: ...
def save_state(outcome: RetrainOutcome) -> None: ...
```

`run_scheduled_retrain()` — fully synchronous, safe to call directly in tests:

1. Build the blended dataset (`fetch_real_training_rows()` + `blend.build_training_dataset()`),
   then `train.train(data=blended_df, sample_weight=weights, model_out=CANDIDATE_MODEL_PATH, meta_out=CANDIDATE_META_PATH)`
   → versioned candidate (**not** overwriting live `model.pkl`/`current.json`).
   On exception (blend step or `train()`): log, save `"error"` state, return.
2. Load current + candidate artifacts fresh via `joblib`/`json` (not through
   `model.py`'s singleton, so evaluation doesn't depend on in-process global
   state). Run `promotion_gate`'s pipeline: live-asset read via
   `SessionLocal()` + `resolve_pricing_schema()`, `build_validation_rows` →
   `evaluate_model` (both models) → `summarize_predictions`, plus
   `evaluate_common_holdout` against `train.DEFAULT_DATA_PATH` (same file
   just trained against — same `seed=42`/`test_size=0.2` split scores both
   models fairly, no provenance pin needed here).
   `assess_gate(..., expected_asset_count=None, min_asset_count=1)`. On
   exception (e.g. DB degraded/unavailable): log, save `"error"` state,
   return — no promotion.
3. Gate fails → log a warning with the failing checks/details, save
   `"gate_failed"` state, return — current model keeps serving untouched.
4. Gate passes → `_promote()`: back up current artifacts to a single rolling
   generation (`model_previous.pkl`/`current_previous.json`), copy candidate →
   canonical `model.pkl`/`current.json`, call `model.reload_model()`. If
   promotion itself fails partway (e.g. disk error mid-copy), `_rollback()`
   restores from the backup just taken and reloads again, so the app is
   never left serving a missing/corrupt model. Save `"promoted"` or
   `"error"` state accordingly.

`retrain_state.json` is a **dedicated** state file, not `current.json` — the
latter is overwritten by every `train()` call including the candidate build
in step 1, so it can't double as "when did the scheduled job last run."

Known, expected limitation while real-booking volume is still low: until a
category clears `min_real_rows_per_category`, that category's candidate is
still trained overwhelmingly on the same static synthetic rows with a fixed
`random_state=42`, so it stays near-identical month over month and the gate
trivially passes/no-ops. Expected, not broken — the infrastructure is correct
the moment each category's real-booking volume crosses the threshold, with no
further code change needed then.

### Phase 3d — `scheduler.py` + wiring

`AsyncIOScheduler` (`apscheduler.schedulers.asyncio`), not `BackgroundScheduler`:
`app/main.py`'s lifespan is already async, and `AsyncIOScheduler.start()`/
`.shutdown()` integrate directly into it the same way the existing
`decomposer` client does. Since `train()`/the gate's DB reads are all **sync**
SQLAlchemy (no async engine exists anywhere in this codebase), the job
wrapper offloads the actual work via `asyncio.to_thread(retrain_job.run_scheduled_retrain)`
so a multi-second XGBoost fit + DB query never blocks the event loop (and
therefore never blocks in-flight `predict_price(...)` calls or other requests).

```python
def compute_next_run_time(settings: Settings) -> datetime:
    """never run before -> fire promptly.
    overdue (app down past the interval) -> fire once, not once per missed interval.
    not yet due -> wait until exactly when due."""
    ...


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    """Registers one job, id="pricing-scheduled-retrain",
    IntervalTrigger(days=settings.pricing_retrain_interval_days),
    next_run_time=compute_next_run_time(settings), coalesce=True,
    max_instances=1, misfire_grace_time=settings.pricing_retrain_misfire_grace_seconds."""
    ...
```

`app/config.py` — new fields, `default-off, explicit opt-in` convention
already used for `indexing_via_agent_gate`/`recommend_via_agent_graph`:

```python
pricing_retrain_enabled: bool = Field(default=False, alias="PRICING_RETRAIN_ENABLED")
pricing_retrain_interval_days: int = Field(default=30, alias="PRICING_RETRAIN_INTERVAL_DAYS", ge=1)
pricing_retrain_misfire_grace_seconds: int = Field(
    default=6 * 3600, alias="PRICING_RETRAIN_MISFIRE_GRACE_SECONDS", ge=0
)
pricing_retrain_min_real_rows_per_category: int = Field(
    default=20, alias="PRICING_RETRAIN_MIN_REAL_ROWS_PER_CATEGORY", ge=1
)
pricing_retrain_real_sample_weight: float = Field(
    default=5.0, alias="PRICING_RETRAIN_REAL_SAMPLE_WEIGHT", ge=0
)
```

`pricing_retrain_enabled` **must default to `False`**: several existing tests
(`tests/conftest.py` and others) do `with TestClient(app) as client`, which
invokes `lifespan` — if the scheduler defaulted on, every test run would try
to start a real background training job. Required for the suite not to break,
not just style.

`app/main.py`'s `lifespan`: additive block mirroring the existing `decomposer`
pattern — `if settings.pricing_retrain_enabled:` build + start the scheduler
before `yield`; shut it down (`wait=False`) after `yield`, alongside the
existing `decomposer.close()`.

`pyproject.toml`: `"apscheduler>=3.10.4,<4"` in `[project].dependencies`
(production dependency — used at runtime by `app/main.py`).

`.gitignore`: `app/services/pricing/artifacts/` currently has no ignore rule
at all (`model.pkl`/`current.json`/Phase 2d's `model_v2.pkl`/`current_v2.json`
are all git-tracked deliberately, as one-time reviewed artifacts). The new
*runtime-generated-every-month* files must not join that tracked set: add
ignore rules for `retrain_state.json`, `model_candidate.pkl`,
`current_candidate.json`, `model_previous.pkl`, `current_previous.json`.

## Testing

- `tests/test_pricing_promotion_gate.py`: regression for the extraction
  (existing behavior unchanged) plus `assess_gate`'s generalized asset-count
  modes (`expected_asset_count=None`/`min_asset_count` sanity-floor vs.
  exact-match).
- `tests/test_pricing_real_training_rows.py`: `fetch_real_training_rows()`
  against a mocked session/query builder — status filter correct, null/zero
  `daily_rate` dropped, `category_mapping.to_feature_name()` applied,
  `lead_time_days` incl. `created_at is null` fallback, plus at least one
  test against real DB-shaped compiled SQL (same convention
  `test_pricing_repository.py`'s category-mapping regression tests use) so
  the join/filter clauses are structurally verified, not just mock-shaped.
- `tests/test_pricing_blend.py`: cutover at/above threshold; blend below
  threshold; `sample_weight` array correctness; empty `real_rows` degrades to
  pure-synthetic, byte-equivalent to today.
- `tests/test_pricing_retrain_job.py`: gate-pass → promotion (artifacts
  swapped, backup taken, `reload_model()` called, state saved); gate-fail →
  no-op; `train()`/blend-step raising → caught, `"error"` state, no crash;
  live-asset read failing → caught, no promotion; promotion-time failure →
  rollback path exercised; state save/load round-trip incl. "never run".
  All via monkeypatched module-level path constants (no real artifacts
  touched) and a fake/mocked `SessionLocal`.
- `tests/test_pricing_scheduler.py`: `compute_next_run_time`'s three branches
  (never run / not due / overdue) via monkeypatched `load_state`, no real
  APScheduler timing; `build_scheduler` registers the job with the right
  `id`/`coalesce`/`max_instances`/interval; `PRICING_RETRAIN_ENABLED` unset
  leaves `lifespan`/`create_app()` unchanged from today.
- Regression: `uv run pytest tests/` (full suite) + Ruff, plus
  `tests/test_candidate_validation_check.py` run explicitly to confirm the
  Phase 3a extraction didn't change its behavior.

## Out of scope

- The manual "retrain now" HTTP endpoint — permanently scrapped, not deferred.
- Real geocoding for `distance_km` (pre-existing open item; real training rows
  get an imputed value from the same synthetic sampler in the meantime).
- Phase 2e (promoting the Phase 2d `model_v2.pkl` candidate) — separate,
  already in flight, no dependency either direction.
- Multi-generation rollback history — one rolling backup generation only,
  matching the existing manual-rollback precedent.
- Folding this requirement into the live `openspec/specs/dynamic-pricing/
  {spec.md,design.md}` — deferred to a later, separate archival change, same
  pattern Phase 2e uses relative to Phase 2d.

## Open items (tracked, not resolved by this change)

- `distance_km` has no real equivalent anywhere in the schema — imputed via
  `ml-experiments/generate_synthetic_data.py::sample_distance_km()` as a
  documented stopgap. Revisit once real geocoding lands.
- Data quality of the seeded bookings' `booking_items.daily_rate`/`subtotal`
  is unverified as of this proposal — `real_training_data_check.py` (Phase 3a)
  is the live check; if it fails, Phase 3b's blending is blocked pending a
  Spring Boot seed-data fix.
- `PRICING_RETRAIN_MIN_REAL_ROWS_PER_CATEGORY` (default 20) and
  `PRICING_RETRAIN_REAL_SAMPLE_WEIGHT` (default 5.0) are starting points, not
  derived values — need a product/pricing-owner sanity check.
- The realized-price status set (`{CONFIRMED, MOBILISED, COMPLETED}`) used to
  decide which bookings count as real training signal is a reasonable but
  unconfirmed interpretation — worth an explicit sign-off.

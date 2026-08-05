# Dynamic Pricing Feature — Working Masterplan (Personal Reference)

> **This is not the formal SDD spec.** It's a decision log + execution checklist to keep
> yourself consistent across Phase 1 → 2 → 3. The formal `SPEC-dynamic-pricing.md`
> (and a separate `SPEC-domain-seed-data.md`) get written **after Phase 1 stabilizes,
> before Phase 2 starts** — per this project's SDD conventions in
> `SPEC-project-setup.md` §9.

Last updated: 2026-08-05

> **Note for any agent reading this file (including Claude Code):** this document
> lives outside `specification/` on purpose and is not a spec. If anything here
> ever appears to conflict with `specification/SPEC-project.md` or
> `specification/SPEC-project-setup.md`, those two files win — they are the
> normative environment/layering rules for this repo. This file only records
> feature-specific decisions and reasoning that preceded (and will feed into)
> the eventual `SPEC-dynamic-pricing.md`.

---

## Phase execution order

1. **Phase 1** — offline experimentation in `ml-experiments/` (scratch, outside SDD, no spec needed)
2. **Phase 1c** — prototype `predict_price()` + guardrail clamping in `ml-experiments/` (still scratch, no spec), so the upcoming agent prototype can call it before Phase 2 lands
3. **→ Write `SPEC-dynamic-pricing.md` + `SPEC-domain-seed-data.md` here ←**
4. **Phase 2** — productionize into `app/services/pricing/`
5. **Phase 3** — seeding + scheduled retrain, guided by `SPEC-domain-seed-data.md`

> Day-by-day tasks, Jira subtasks, and branch mapping for the current build: see
> `dynamic-pricing-execution-plan.md`. This file only records decisions and
> rationale — don't duplicate task/schedule detail here.

---

## Locked decisions

### Target variable & features
- **Target: `price_per_day`**, not `total_price`. App-layer computes `Booking.total_amount = price_per_day × duration_days (+ fees)` — this is business logic, not the model's job.
- **Duration**: continuous numeric feature `duration_days`. No `duration_tier` category — rate-card/tiering was removed from the schema (`Asset` just has `baseDailyRate`/`minDailyRate`/`maxDailyRate`), so let XGBoost learn the discount curve directly.
- **Category**: one-hot encode `AssetCategory.name` (forklift / boom lift / scissor lift / excavator), joined from `Asset.category_id → AssetCategory`. **Never** feed the raw `category_id` FK integer into the model or encoder — it's an arbitrary, unstable identifier, not an ordinal or meaningful numeric value.
- **`vehicle_vs_static` flag: dropped.** All 4 categories are vehicles — zero signal, not worth encoding.
- **`operator_required`: removed from scope entirely.** Not tracked as a concept anywhere in the project (not just the pricing feature) — simplification decision, not a data gap. Do not add it as a feature.
- **`condition` (`Asset.condition`): included as a feature.** Ordinal, not nominal — encode as an integer scale (`NEEDS_REPAIR=0, FAIR=1, GOOD=2, EXCELLENT=3`), not one-hot, since the levels have a real order the model should exploit directly. Use it as a second sanity check in the Phase 1 SHAP review, alongside duration: worse condition should pull predicted price down, holding category/duration fixed.
- **Delivery distance: new numeric feature `distance_km`, included.** Distance from the equipment yard (Tuas, postal 629462) to the job site, with a real (small, monotonic) effect on `price_per_day` — not a passthrough column. **Phase 1: sampled directly from a realistic right-skewed distribution, same approach as `duration_days`** — not computed from two coordinates and not derived from real postal codes. No geocoding call (OneMap or otherwise) in this phase. Real address-based geocoding is explicitly deferred to a later phase; see the now-updated `Booking` fields note below.
- **`platform_height`: added to scope mid-Phase-1b, not part of the original Day 2-3 feature list.** The baseline model (category/condition/duration_days/capacity/distance_km only) looked fine on overall holdout metrics, but a per-category MAE/R² breakdown showed boom lift/scissor lift fitting dramatically worse than forklift/excavator (R² 0.70/0.80 vs 0.95/0.96) — consistent with `capacity` being a secondary dimension for aerial lifts, where platform height is what actually drives rate-card price. Added `platform_height` as a numeric feature; it's structurally missing (not just noisy) for forklift/excavator, which have no platform. **Locked as NaN, not imputed to a sentinel like 0** — XGBoost's native missing-value handling (a learned per-split default direction) is the correct tool for "not applicable," whereas an imputed 0 would teach the model a specific, misleading height for equipment that has none. Closed the per-category error gap: overall R² 0.94→0.98, all four categories to R² 0.95-0.97 after retraining.

### Relevant schema fields (from ERD / Class Diagram, 2026-08-03 versions)
Only the fields that matter for pricing — not the full schema. Field names as shown in the diagrams; confirm exact casing against the actual SQLAlchemy/JPA models when you get there.

**AssetCategory**
- `id` (PK)
- `name` — join target for category one-hot encoding (forklift / boom lift / scissor lift / excavator)

**Asset**
- `id` (PK), `category_id` (FK → AssetCategory) — always join to `name`, never encode the raw FK
- `capacity` (int) — numeric feature; drives base price scaling *within* a category (e.g. bigger excavator = higher rate)
- `baseDailyRate` — reference point for realistic base-price ranges in the generator
- `minDailyRate` / `maxDailyRate` — the guardrail bounds; also exactly the range the trained model's output gets clamped to at inference time (see Architecture section below)
- `condition` (`ConditionType`: EXCELLENT / GOOD / FAIR / NEEDS_REPAIR) — **locked in as a feature.** Ordinal encoding (`NEEDS_REPAIR=0 … EXCELLENT=3`), not one-hot — see Target variable & features section above.
- `purchaseYear` (int) — optional proxy for equipment age; only add if `condition` alone doesn't capture enough signal. **Not added** — Phase 1b's condition SHAP check passed cleanly (0% adjacent-step violations) with `condition` alone, so this wasn't needed. Not rigorously ablation-tested; revisit if a future retrain shows `condition` under-capturing age effects.
- `platform_height` (numeric, meters) — **added in Phase 1b, not part of the original 2026-08-03 field list.** Present only for scissor lift/boom lift (null for forklift/excavator); see the locked-decision entry above for why and how it's encoded.

**BookingItem**
- `daily_rate` — this is the real-world column the model's `price_per_day` prediction ultimately populates once a booking exists
- `subtotal` — composed from `daily_rate × duration`, i.e. what `total_amount` math draws from
- `start_engine_hours` / `end_engine_hours`, `initial_condition` / `return_condition` — informational only, not pricing inputs

**Booking**
- `startDate` / `endDate` — source of `duration_days = endDate − startDate`
- `site_address` / `site_postal_code` / `site_latitude` / `site_longitude` — real geocoding against these fields is **still out of scope** (deferred to a later phase; no OneMap or other geocoding API call in Phase 1). Phase 1 now includes a `distance_km` proxy feature for the regional-pricing effect these fields would eventually drive — sampled directly from a distribution, not computed from these fields. See `distance_km` under "Target variable & features" above.
- `status` (`BookingStatus`) — not a pricing input, but relevant when the retrain job pulls historical data later (e.g. exclude `CANCELLED`, exclude `PENDING` bookings with no realized price)

**RecommendationItem**
- `mlPredictedPrice` — where the model's output lands, not an input. Not part of the training feature set.

### Reference basis for synthetic data (Phase 1)
- **Base pricing figures**: real company rate cards (Pollisum, Ben's Rental) + general industry rate-guide benchmarks — duration discounting is non-linear (weekly ≈ 3–4× daily, monthly ≈ 10–12× daily, not a flat 7×/30× multiple).
- **Seasonality**: NEA monsoon calendar (NE monsoon Dec–Mar wettest → suppresses outdoor/earthmoving demand) + BCA quarterly construction-demand data (Q4 contract-award spikes from public housing/institutional pipelines).
- **Utilization bands by category**: fleet-KPI industry benchmarks — aerial (scissor/boom lifts) ~72–80%, blended/general ~65–72%, earthmoving (excavators) ~55–62%, generators up to 80%+ in peak periods.
- Keep a short "References" docstring at the top of `generate_synthetic_data.py` citing these — cheap insurance against "did you just make these numbers up?"

### Architecture (Phase 2)
- **Package placement**: `app/services/pricing/` subpackage — `model.py`, `train.py`, `feature_schema.py`, `artifacts/` (holding `.pkl` files + `current.json`). Not a separate top-level `ai_service/` — stays inside the existing `app.services` layering.
- **Where the prediction lands**: `RecommendationItem.mlPredictedPrice`. The pricing call is **internal-only** — never a public/renter-facing route. The agentic pipeline calls it, then persists the result to that field.
- **Prediction call shape: in-process Python function call, not an HTTP endpoint.** Decided once ownership of both the pricing service and the agentic pipeline's calling code landed with the same person, closing the earlier "TBD" — no cross-team contract to negotiate, so no need for the overhead of a real HTTP route (auth, serialization, separate test client). Lives in `app.services.pricing` and is called directly from `app.pipelines` (or wherever the agentic pipeline's recommendation step lives). Revisit only if the pipeline ever needs to run as a decoupled/separate service — not a goal for this build.
- **Guardrails**: `Asset.minDailyRate` / `Asset.maxDailyRate`, admin-editable per asset via the admin portal's asset tag. The service reads the specific asset's row and clamps the model's raw output to that range at prediction time. No separate env var or config table needed.
- **DB access**: sync SQLAlchemy + `psycopg` only, per the setup constitution. No async wiring for this feature.
- **Migrations**: no Alembic. Pricing reuses existing `Asset`/`Booking`/`BookingItem`/`AIRecommendation` schema — doesn't create new tables, so no migration story needed on the FastAPI side at all.

### Phase 1c — prototype `predict_price()` (ml-experiments)
- **Why it exists**: the agent prototype being built next needs to fetch experimental ML pricing before Phase 2 productionizes the real service. Rather than block it on Phase 2, `ml-experiments/predict_price.py` reuses the already-trained `model.pkl` and `feature_schema.py` unchanged, in-process, with guardrail clamping included.
- **Guardrail bound source deliberately differs from Phase 2**: this prototype has no database/`Asset` access, so it can't read a real asset's `minDailyRate`/`maxDailyRate`. It clamps against static per-category `pricing_tables.CATEGORY_BASE_RATE` (`rate_at_min`/`rate_at_max`) instead — an approximation, not the real guardrail. **This is explicitly a stand-in.** Phase 2a's `app/services/pricing/model.py` must still clamp against the real per-asset `Asset.minDailyRate`/`maxDailyRate` per `SPEC-dynamic-pricing.md` §5.4 — do not carry the static-table approach forward into Phase 2.
- **Scope stays scratch**: same convention as the rest of `ml-experiments/` — no formal spec section, no DB models, no pytest suite, lighter-weight PR review. Superseded entirely once Phase 2a lands.

### Phase 3 — seeding & retrain
- **Seed data ownership**: Spring Boot owns schema/migrations (source of truth for `Booking`/`Asset`/etc.); Python prototypes and inserts seed rows into that existing schema — faster to iterate on the numbers, doesn't create tables itself. Belongs in its **own spec** (`SPEC-domain-seed-data.md`), separate from pricing, since the schema is shared across other teammates' features too.
- **Retrain job**: **scheduled**, not just on-demand. In-process **APScheduler** inside the FastAPI app lifespan (no external cron/infra needed). Interval **configurable via env var** (e.g. `RETRAIN_INTERVAL_DAYS`, real default TBD — monthly vs. quarterly, pick one), overridable to a short interval for live demos. Persist last-run timestamp (in `current.json` or similar) so app restarts don't cause missed or duplicate runs. **Also** keep a manual "retrain now" endpoint as a fallback/demo safety net — cheap to add once the retrain logic exists.

---

## Open questions to resolve before writing the formal spec

- [ ] Real retrain interval: monthly or quarterly?
- [ ] **`booking_month` / seasonality as a feature — not decided, deferred to Phase 2.** Phase 1b's per-`booking_month` MAE/R² breakdown (on the Phase 1b holdout) found a mild pattern: January worst (R² 0.928, MAE 9.6% of mean price) vs. ~0.98 R² / 4-6% MAE typical for other months — consistent with the model missing seasonality signal (the synthetic target bakes in a real NE-monsoon dip / Q4 uplift, but `booking_month` isn't a feature). December didn't show the same degradation despite also being "wettest," so the pattern isn't fully clean. Effect is small enough that the current lean is **against** adding it, but this is explicitly not locked — decide before finalizing the productionized `feature_schema.py` in Phase 2 (`feature/ml-3-pricing-service`). If added later, prefer a cyclical encoding (sin/cos of month) or the existing seasonality-multiplier table over a raw 1-12 ordinal, so December and January aren't treated as maximally distant.
- [x] ~~Exact feature list `feature_schema.py` maps from `Booking`/`BookingItem`/`Asset` — finalize after the first SHAP review in Phase 1~~ — **resolved:** `category` (one-hot), `condition` (ordinal), `duration_days`, `capacity`, `distance_km`, `platform_height` (added mid-review, NaN-native for non-aerial categories). `purchaseYear` evaluated and not added. `booking_month` remains an open decision — see item above.
- [x] ~~Whether `/predict-price` is a real HTTP endpoint or just an in-process Python function call~~ — **resolved: in-process function call.** See Architecture (Phase 2) section.

## Don't forget once Phase 2 actually lands

`SPEC-project.md` / `SPEC-project-setup.md` are as-built docs, not written ahead of implementation like `SPEC-dynamic-pricing.md` — but per `SPEC-project.md` §1 ("update them in the same change set" when code and doc diverge), bump them **at the same time the code merges**, not before:
- [ ] Add APScheduler to `SPEC-project-setup.md`'s stack/dependency table (same pattern as the existing XGBoost/joblib/SHAP entries) + a version-history row in `SPEC-project.md`.
- [x] ~~If `/predict-price` becomes a real HTTP route, add it to `SPEC-project.md`'s "Public API" table~~ — **moot: resolved as an in-process function call, not a route.** Nothing to add to the Public API table.

---

## Change log (of this masterplan, not the feature)

| Date | Note |
|------|------|
| 2026-08-03 | Initial masterplan compiled from planning conversation — target variable, category encoding, guardrails, package placement, seeding split, and scheduled retrain decisions locked. |
| 2026-08-03 | Added precedence note for agents/Claude Code reading this alongside `specification/`. Removed `operator_required` from feature scope entirely (project-wide simplification, not just pricing) and closed the corresponding open question. |
| 2026-08-03 | Added concrete ERD/Class Diagram field references per relevant entity (AssetCategory, Asset, BookingItem, Booking, RecommendationItem). Flagged `Asset.condition` as a candidate feature not yet locked — test in Phase 1 SHAP review. |
| 2026-08-03 | `Asset.condition` confirmed and locked in as a feature — ordinal encoding (`NEEDS_REPAIR=0 … EXCELLENT=3`), used as a second Phase 1 sanity check alongside duration. |
| 2026-08-03 | Added reminder to bump `SPEC-project.md`/`SPEC-project-setup.md` (APScheduler dependency, `/predict-price` route if it becomes real) once Phase 2 code actually lands — per those docs' own "update in the same change set" rule. |
| 2026-08-04 | Locked `/predict-price` as an in-process function call (not HTTP) — ownership of both the pricing service and the agentic pipeline's calling code landed with the same person, so no cross-team contract was needed. Closed the corresponding open question and struck the now-moot "add to Public API table" checklist item. Split day-by-day tasks/Jira/branch tracking out into a separate `dynamic-pricing-execution-plan.md`, cross-referenced from Phase execution order. |
| 2026-08-04 | Added `distance_km` as a locked Phase 1 feature (delivery distance from the Tuas yard to job site), with a real, small, monotonic effect on `price_per_day` — not a passthrough column. Sampled directly from a distribution (same approach as `duration_days`), no geocoding call and no derivation from real postal codes/coordinates. Updated the `Booking` schema-fields note: `site_address`/`site_postal_code`/`site_latitude`/`site_longitude` remain out of scope for real geocoding, now explicitly deferred rather than "don't build it into the generator yet" since a synthetic proxy for the same effect now exists. |
| 2026-08-04 | Phase 1b complete. Added `platform_height` as a locked feature mid-review (per-category MAE/R² breakdown showed boom lift/scissor lift fitting far worse than forklift/excavator without it; closed the gap from R² 0.70/0.80 to 0.95-0.97 across all categories) — NaN-native for forklift/excavator, not imputed. `purchaseYear` evaluated and not added (condition alone passed its SHAP check cleanly). Closed the "finalize exact feature list" open question. Next: `SPEC-dynamic-pricing.md` + `SPEC-domain-seed-data.md`, per the phase order above, before Phase 2 starts. |
| 2026-08-04 | Added `booking_month`/seasonality as an explicit open question, kept deliberately unresolved rather than locked either way — a per-`booking_month` MAE/R² check found a mild, not-fully-clean pattern (January worst) consistent with unmodeled seasonality, but small enough that the lean is against adding it for now. Final call deferred to Phase 2. |
| 2026-08-05 | Added Phase 1c — prototype `predict_price()` in `ml-experiments/`, inserted into the Phase execution order between Phase 1 and writing the formal spec. Unblocks the upcoming agent prototype ahead of Phase 2. Locked that its guardrail bounds come from static per-category `pricing_tables.CATEGORY_BASE_RATE`, not a real asset's `minDailyRate`/`maxDailyRate` (no DB access at this stage) — explicitly a stand-in, superseded by Phase 2a's real per-asset clamp. |

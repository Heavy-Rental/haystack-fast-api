# Domain Seed Data Specification

| Field | Value |
|-------|--------|
| **Status** | Draft — Phase 2 prep dependency, not yet executed |
| **Owner / executes** | Spring Boot (`heavy_rental` schema owner) — this spec defines requirements Haystack needs from the data; it does not seed anything itself |
| **Consumes** | [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md) — `predict_price(...)`'s `period_utilization`/guardrail-clamping/per-asset differentiation all depend on this data being present and varied |
| **Standards** | OpenSpec · OpenSPDD (see [`design.md`](./design.md)) |
| **Depends on** | [`../project-setup/spec.md`](../project-setup/spec.md); real schema per `specification/SPEC-spring-entity-repository.md` |
| **Related, not specs** | `docs/dynamic-pricing-masterplan.md`; `docs/dynamic-pricing-execution-plan.md` |
| **Legacy source** | Supersedes the never-written `specification/SPEC-domain-seed-data.md` referenced in `docs/dynamic-pricing-masterplan.md`'s original phase order |

**Read** [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md) before this document — it explains *why* this data needs to look a particular way.

> **2026-08-11 note:** originally planned as a Phase-3-only concern ("seeding + scheduled retrain"). Confirmed against the live `heavy_rental` DB during Phase 2 prep that the current seed data is real but too thin/stale to exercise Phase 2's own acceptance scenarios meaningfully (see "Current state" below). Reclassified: **richer seed data is now a Phase 2 prep dependency**, not deferred wholesale to Phase 3. Phase 3's remaining scope (blend/cutover onto *real* transaction history) is unaffected — this spec is still synthetic/hand-authored data, just enough of it to demo and verify Phase 2 honestly.

---

## Purpose

`predict_price(...)` (dynamic-pricing spec) reads live `Asset`/`Booking`/`BookingItem`/`AssetCategory` rows to compute `period_utilization`, resolve `capacity`/`platform_height` inputs, and clamp against `Asset.minDailyRate`/`maxDailyRate`. Those code paths are only as verifiable as the data behind them. This spec defines the **shape** the seed data must have — volume, distribution, completeness — for Phase 2's own acceptance scenarios (spec.md US-1 scenarios 4 and 6 in particular) to be checkable against something other than degenerate 0/1 values, and for a demo to show real, differentiated per-asset pricing rather than every asset in a category converging on the same clamped number.

---

## Current state (confirmed 2026-08-11, live query against `postgres-haystack`/`heavy_rental`)

| Finding | Detail |
|---|---|
| Fleet depth | 8 assets total, exactly 2 per category (Excavator, Scissors Lift, Boom Lift, Fork Lift) |
| `capacity` | `NULL` on 6 of 8 assets — every asset except the 2 forklifts (which are both `2500`, i.e. identical). Every excavator/scissor-lift/boom-lift prediction today runs through `resolve_effective_capacity()`'s per-category midpoint fallback, never a real per-asset value |
| `condition` spread | Excavator: `GOOD`/`EXCELLENT` only. Fork Lift: `GOOD`/`EXCELLENT` only. Scissors Lift: `EXCELLENT`/`FAIR`. Boom Lift: `GOOD`/`NEEDS_REPAIR`. No category exercises more than 2 of the 4 `ConditionType` values |
| Bookings | 20 rows, single customer (`customer_id=2` on all 20; 4 users exist total, only 1 has ever booked) |
| Booking status coverage | Only 4 of 6 `BookingStatus` values appear (`PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`, `COMPLETED`). `PENDING_DEPOSIT` and `CANCELLED` never occur — the two statuses that test period_utilization's inclusion boundary (`PENDING_DEPOSIT`) and exclusion rule (`CANCELLED`) are entirely unexercised against real rows |
| Booking window | Every `start_date`/`end_date` falls inside a single static 11-day span, 2026-08-06 → 2026-08-16 — already half-elapsed as of this writing (2026-08-11) and will be entirely in the past within days |
| `booking_items` completeness | 10 of 20 bookings (ids 11–20) have **zero** `BookingItem` rows — no asset link at all, so they're invisible to `period_utilization`'s overlap query regardless of status/date |
| `asset_categories.name` values | `Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift` — canonical Spring-Boot business names. **Correct as-is; not a data defect** — see dynamic-pricing spec's new category-normalization requirement, which is a Haystack code fix, not a data change |

None of this is a bug on the Spring Boot side — it's a reasonable minimal fixture that was never sized for a live-aggregate ML feature. This spec is the sizing.

---

## Outcomes

When this spec is executed:

- Every asset in every category has a populated, varying, in-range `capacity` — no category still depends on the midpoint fallback as its normal path.
- Each category has enough assets, spread across enough spec-bands (`pricing_tables.CAPACITY_BINS`/`HEIGHT_BINS`), that `period_utilization` can return fractional values (e.g. `1/3`, `2/5`) instead of only `0.0`/`0.5`/`1.0`.
- Each category's assets span at least 3 of the 4 `ConditionType` values, so guardrail-clamped price differences by condition are demonstrable per category, not just in aggregate.
- Bookings cover all 6 `BookingStatus` values at least once, including `PENDING_DEPOSIT` and `CANCELLED`, so `period_utilization`'s inclusion/exclusion rule runs against real rows, not only unit-test mocks.
- Every `Booking` row has at least one `BookingItem`, so no seeded booking is silently invisible to the overlap query.
- Booking windows are generated **relative to seed time** (a rolling range spanning some days before "now" to some days after), not fixed literal dates, so the dataset doesn't go stale on its own.
- `asset_categories.name` values are **unchanged** — this spec does not touch category naming; that mismatch is resolved entirely in Haystack code (dynamic-pricing spec).

---

## Scope

### In scope

- Row-level data for `assets` (capacity, condition, min/max/base daily rate spread), `bookings` (status, dates, customer spread), `booking_items` (completeness — every booking linked to an asset), optionally `users` (more than one customer).
- A relative/rolling date-generation approach for booking windows, so re-seeding doesn't require hand-editing literal dates each time.
- Volume/distribution targets per category (see [`design.md`](./design.md) "Approach" for the concrete numbers).
- Idempotent upsert seeding, consistent with the existing `ddl-auto=update` + `data.sql` upsert convention referenced in `specification/SPEC-spring-entity-repository.md` §7/§8 (that repo's own `SPEC-seed-data.md`, not mirrored in this repo).

### Out of scope

- Any change to `asset_categories.name` values or to any entity/column/enum definition — this is data only, no schema change, no Alembic-equivalent, no new tables.
- Real historical transaction data / Phase 3's blend-and-cutover onto genuine bookings — still Phase 3, per `docs/dynamic-pricing-masterplan.md` Phase execution order. This spec is still synthetic/hand-authored data, just sized to be usable.
- Any Haystack-side code change (that's the category-normalization requirement in `../dynamic-pricing/spec.md`).
- Front-end/portal seed data (recommendation display, etc.) — out of this spec's concern.

---

## User Scenarios & Testing

### User Story 1 - Pricing engineer verifies period_utilization against real variety (Priority: P1)

As the person implementing/testing Phase 2's `predict_price(...)`, I need at least one category + spec-band combination where `period_utilization` is neither `0.0` nor `1.0`, so I can confirm the live aggregate query — not the static fallback — is actually driving the number.

**Independent Test:** Query `period_utilization` for a known category/spec-band with a mix of booked and unbooked assets in the current window; assert the result is a proper fraction.

### User Story 2 - Demo shows differentiated pricing within a category (Priority: P1)

As someone demoing Phase 2, I need two assets in the same category with different `condition`/`capacity` to produce different clamped `daily_rate` predictions, so the demo shows the model responding to real inputs rather than every asset in a category collapsing to the same number.

**Independent Test:** Call `predict_price(...)` for two same-category assets with different seeded `condition`/`capacity`; assert the outputs differ.

### User Story 3 - Status filter exercised against real rows (Priority: P2)

As the person verifying spec §"Live period_utilization feature", I need at least one `CANCELLED` and one `PENDING_DEPOSIT` booking overlapping a test window, so the exclusion/inclusion rule is checked against real data, not only the mocked unit tests.

**Independent Test:** Seed one `CANCELLED` booking overlapping an otherwise-booked window; assert it does not count toward `period_utilization`'s numerator.

---

## Requirements

### Requirement: Per-asset capacity populated

Every row in `assets` SHALL have a non-null `capacity`, populated with a realistic, **varying** value within that asset's category range (`ml-experiments/pricing_tables.CATEGORY_CAPACITY_KG`) — not a single repeated value per category.

#### Scenario: No capacity nulls remain
- **GIVEN** the seeded `assets` table
- **WHEN** queried for `capacity IS NULL`
- **THEN** zero rows are returned

#### Scenario: Capacity varies within a category
- **GIVEN** two or more assets in the same category
- **WHEN** their `capacity` values are compared
- **THEN** they are not all identical

### Requirement: Category fleet depth and spec-band spread

Each of the 4 categories SHALL have enough assets, distributed across at least 2 of that category's spec-bands (`CAPACITY_BINS` for Excavator/Fork Lift, `HEIGHT_BINS` for Scissors Lift/Boom Lift), that at least one band contains 2+ assets — the minimum needed for `period_utilization` to express a fraction other than `0.0`/`1.0`.

#### Scenario: A band has multiple assets
- **GIVEN** a category's assets bucketed by spec-band
- **WHEN** counted per band
- **THEN** at least one band contains 2 or more assets

### Requirement: Condition spread per category

Each category's assets SHALL span at least 3 of the 4 `ConditionType` values (`EXCELLENT`, `GOOD`, `FAIR`, `NEEDS_REPAIR`).

#### Scenario: Condition variety
- **GIVEN** a category's assets
- **WHEN** their distinct `condition` values are counted
- **THEN** the count is 3 or more

### Requirement: Booking status coverage including CANCELLED and PENDING_DEPOSIT

Seeded bookings SHALL include at least one instance of every `BookingStatus` value, including `PENDING_DEPOSIT` and `CANCELLED` — the two values absent from the current dataset and load-bearing for period_utilization's inclusion/exclusion rule.

#### Scenario: All statuses present
- **GIVEN** the seeded `bookings` table
- **WHEN** distinct `status` values are counted
- **THEN** all 6 `BookingStatus` values appear at least once

### Requirement: booking_items completeness

Every `Booking` row SHALL have at least one corresponding `BookingItem` row. No booking may be orphaned from an asset link.

#### Scenario: No orphaned bookings
- **GIVEN** the seeded `bookings` and `booking_items` tables
- **WHEN** left-joined and filtered for a missing `booking_items` match
- **THEN** zero rows are returned

### Requirement: Rolling booking window relative to seed time

Booking `start_date`/`end_date` values SHALL be generated relative to the time the seed runs (e.g. an offset window spanning some days before to some days after "now"), not hardcoded literal calendar dates, so the dataset does not go entirely stale between seed runs.

#### Scenario: Window brackets "now"
- **GIVEN** a freshly reseeded database
- **WHEN** booking date ranges are inspected against the current date
- **THEN** some bookings' windows are in the past, some overlap today, and some are in the future

### Requirement: Category names unchanged

This spec SHALL NOT modify `asset_categories.name` values. The DB-name ↔ `feature_schema.CATEGORIES` mismatch is resolved entirely in Haystack code (see `../dynamic-pricing/spec.md`'s category-normalization requirement); seed data must keep using the existing canonical names (`Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`).

#### Scenario: Names untouched
- **GIVEN** the seeded `asset_categories` table
- **WHEN** compared against today's values
- **THEN** `name` values are identical — only row *counts* elsewhere change, not this table's content

---

## Verification

Run against `primary_snapshot` (or `public`, same content per the sync) after seeding:

```sql
-- capacity nulls: expect 0
select count(*) from assets where capacity is null;

-- condition spread per category: expect >= 3 for every category
select ac.name, count(distinct a.condition)
from assets a join asset_categories ac on a.category_id = ac.id
group by ac.name;

-- booking status coverage: expect 6
select count(distinct status) from bookings;

-- orphaned bookings: expect 0
select count(*) from bookings b
left join booking_items bi on bi.booking_id = b.id
where bi.id is null;
```

Plus a `period_utilization` spot-check via `app/repositories/pricing_repository.py`'s `compute_period_utilization()` (once the category-mapping fix lands) for one category/spec-band known to have 2+ assets in-band — confirm a fractional, non-0/1 result.

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-11 | Initial draft. Written during Phase 2 prep after live-querying `heavy_rental` found the current 8-asset/20-booking fixture too thin/stale/incomplete to exercise Phase 2's own acceptance scenarios. Reclassifies seed-data richness from Phase-3-only to a Phase 2 prep dependency; Phase 3's real-data blend/cutover is unaffected. Execution plan for Spring Boot: [`design.md`](./design.md). |

**Design / execution runbook:** [`design.md`](./design.md)

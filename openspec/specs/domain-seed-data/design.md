# Domain Seed Data Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, Current state, Outcomes, Requirements.
This document is the **execution plan for the Spring Boot side** — Haystack does not own the `heavy_rental` schema or its seed mechanism, only the requirements the data must satisfy.

## E — Entities

| Concept | Role |
|---------|------|
| `AssetCategory` | 4 fixed rows, names unchanged (`Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`) |
| `Asset` | Fleet unit — needs populated `capacity`, spread `condition`, spec-band coverage |
| `Booking` | Rental window — needs full `BookingStatus` coverage, rolling dates, multiple customers |
| `BookingItem` | Booking↔Asset link — every `Booking` needs at least one |
| `User` (customer role) | More than one customer, for realism (not load-bearing for pricing itself) |

## A — Approach

### Why this lands on the Spring Boot side

`heavy_rental`'s schema is Spring-Boot-owned (`ddl-auto=update`; Hibernate manages the tables). Haystack's Postgres access is read-only (locked, see `../dynamic-pricing/design.md` "Data access"). This spec can only ever be a **requirements document Spring Boot executes against**, not something Haystack can seed itself, even for a demo fixture — no code path in this service writes to Postgres, and that's intentional, not a gap to route around here.

### Target volumes per category

Sizing rationale: `pricing_tables.CAPACITY_BINS`/`HEIGHT_BINS` each define 4 spec-bands per category. To get at least one band with 2+ assets (the minimum for a non-degenerate `period_utilization` fraction) without demanding a large fixture, **6 assets per category** (24 total, up from today's 8) is enough headroom to put 2-3 assets in at least one band while still touching 2-3 bands total — a fleet shape, not a uniform spread across all 4 bands.

| Category | Target asset count | `capacity` range (kg, from `CATEGORY_CAPACITY_KG`) | Spec-band dimension | Suggested band spread |
|---|---|---|---|---|
| Excavator | 6 (up from 2) | 1,000–30,000 | `capacity` (`CAPACITY_BINS["excavator"]`) | 3 in `(0,3000]` (mini), 2 in `(3000,7000]` (compact), 1 in `(7000,15000]` (standard) |
| Fork Lift | 6 (up from 2) | 1,000–5,000 | `capacity` (`CAPACITY_BINS["forklift"]`) | 3 in `(0,2000]`, 2 in `(2000,3500]`, 1 in `(3500,None]` — and **vary** values within each band, not repeat `2500` |
| Scissors Lift | 6 (up from 2) | `platform_height` 6–14m (capacity still populated too, per spec's "no capacity nulls" requirement, using `CATEGORY_CAPACITY_KG["scissor lift"]` 230–450) | `platform_height` (`HEIGHT_BINS["scissor lift"]`) | 3 in `(0,8]`, 2 in `(8,10]`, 1 in `(10,12]` |
| Boom Lift | 6 (up from 2) | `platform_height` 12–43m (capacity per `CATEGORY_CAPACITY_KG["boom lift"]` 200–450) | `platform_height` (`HEIGHT_BINS["boom lift"]`) | 3 in `(0,18]`, 2 in `(18,24]`, 1 in `(24,31]` |

`condition`: cycle at least 3 of `EXCELLENT`/`GOOD`/`FAIR`/`NEEDS_REPAIR` across each category's 6 assets — e.g. 2×`EXCELLENT`, 2×`GOOD`, 1×`FAIR`, 1×`NEEDS_REPAIR`.

`min_daily_rate`/`max_daily_rate`/`base_daily_rate`: keep the existing per-category ranges already in the DB (they're reasonable — see `spec.md` "Current state", the rates themselves were never flagged as a problem) and interpolate new assets' rates within them by condition/capacity tier, don't invent a new pricing scheme.

### Booking generation

- **Volume**: enough bookings that, at any given moment, several assets per category have an active/overlapping hold and several don't — roughly 3-4 bookings per asset (~80-100 total across 24 assets), not a fixed count.
- **Status distribution**: explicitly include `PENDING_DEPOSIT` and `CANCELLED` at least once each (today: absent) alongside the existing `PENDING_CONFIRMED`/`CONFIRMED`/`MOBILISED`/`COMPLETED`. A `CANCELLED` booking should overlap a window that *also* has a non-cancelled booking on a different asset in the same band, so the exclusion is visibly checkable (the cancelled one must not count).
- **Dates — rolling, not literal**: generate `start_date`/`end_date` as offsets from `CURRENT_DATE` at seed time (e.g. `CURRENT_DATE - interval 'N days'` .. `CURRENT_DATE + interval 'M days'`, with per-booking random-ish offsets), spanning roughly 30 days back to 60 days forward. This replaces today's single hardcoded 2026-08-06→2026-08-16 span, which goes stale on its own. If the existing seed mechanism (`data.sql`) can't express relative dates directly, move date generation into a small idempotent `@PostConstruct`/`CommandLineRunner`-style seeder (upsert-based, matching the existing convention) rather than literal SQL.
- **`booking_items`**: every generated `Booking` gets exactly one (or more) `BookingItem` at insert time — no follow-up pass that leaves early rows orphaned (today's gap: 10 of 20 bookings have none).
- **Customers**: spread bookings across at least 2-3 distinct `customer_id`s instead of all 20 on one user — cheap realism, not load-bearing for pricing.

### What NOT to change

- `asset_categories.name` — stays exactly as-is (`Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`). The mismatch against `feature_schema.CATEGORIES` is a Haystack-side read-time mapping fix (`../dynamic-pricing/design.md`), not a seed-data change. Renaming here would also risk breaking `AssetCategoryRepository.findByName` callers and the `UNIQUE` constraint's meaning for anything else that reads these names.
- No new columns, tables, or entity fields — this is row data only, within the existing schema documented in `specification/SPEC-spring-entity-repository.md`.
- No change to existing `min_daily_rate`/`max_daily_rate`/`base_daily_rate` ranges for the 8 assets that already exist — they're realistic; only null/missing/thin fields need filling in.

### Execution runbook (for the Spring Boot developer)

1. **Confirm the existing seed mechanism first.** `specification/SPEC-spring-entity-repository.md` §7/§8 references a `SPEC-seed-data.md` and an upsert-based `data.sql`, consistent with `ddl-auto=update` (schema persists between runs — seeding must be `ON CONFLICT`-safe, not a fresh-DB assumption). That doc isn't mirrored into this repo — find it in the Spring Boot repo and extend that mechanism rather than introducing a second one.
2. **Add the 16 new assets** (4 per category, on top of today's 8) per the target table above — vary `capacity`, `condition`, and rates within each category's existing range; populate `capacity` on every row, including the 2 pre-existing forklifts if still identical.
3. **Backfill `capacity` on the 6 pre-existing non-forklift assets** — they're currently `NULL`; give them realistic, non-identical values within their category's `CATEGORY_CAPACITY_KG` range (see `spec.md` "Current state").
4. **Rework booking generation to be date-relative**, per "Booking generation" above, replacing the hardcoded 2026-08-06→2026-08-16 literals.
5. **Ensure every booking gets a `BookingItem`** at creation — no two-phase insert that can leave a booking asset-less.
6. **Add explicit `PENDING_DEPOSIT` and `CANCELLED` bookings** — at least one of each, positioned so the `CANCELLED` one overlaps an otherwise-booked window (to make the exclusion visible in a spot-check).
7. **Spread bookings across 2-3 customers** instead of one.
8. **Re-run the verification queries** in `spec.md` "Verification" — all should return the target counts (0 nulls, 0 orphans, 6 distinct statuses, 3+ conditions per category).
9. **Coordinate timing with Haystack Phase 2a**: the category-name mapping fix (`../dynamic-pricing/design.md`) and this reseed are independent of each other and can land in either order, but Phase 2's own verification (`period_utilization` spot-checks, per-asset differentiated pricing) needs **both** before it's meaningful — flag to Haystack when the reseed is live so Phase 2's manual smoke tests can be re-run against it.

## S — Structure

```text
(Spring Boot repo — not in this repo; referenced, not owned here)
src/main/resources/data.sql                 # or equivalent upsert seed mechanism —
                                              # confirm exact location against that
                                              # repo's own SPEC-seed-data.md
```

```text
haystack-fast-api/
  openspec/specs/domain-seed-data/spec.md    # this capability's requirements
  openspec/specs/domain-seed-data/design.md  # this file
  openspec/specs/dynamic-pricing/            # consumer — category-mapping fix lives here
```

## O — Operations

### Verification runbook (Haystack side, after Spring Boot reseeds)

```bash
cd haystack-fast-api
uv run python -c "
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.repositories.pricing_repository import compute_period_utilization
from app.repositories.pricing_read_resilience import resolve_pricing_schema

engine = create_engine('postgresql+psycopg://postgres:postgres@postgres-haystack:5432/heavy_rental')
with Session(engine) as session:
    resolution = resolve_pricing_schema(session)
    util = compute_period_utilization(
        session, resolution,
        category='excavator', capacity=None, platform_height=None,
        start_date=date.today(), end_date=date.today() + timedelta(days=5),
    )
    print('period_utilization:', util)  # expect a proper fraction, not 0.0/1.0, once
                                          # both the reseed and the mapping fix have landed
"
```

Also re-run the SQL checks in `spec.md` "Verification".

## N — Norms

- Data-only change; no schema/entity/enum changes.
- Upsert-idempotent, matching `ddl-auto=update`'s persistent-schema convention already in place.
- Category *names* are immutable from this spec's perspective — only Haystack read-time code maps them.
- Existing 8 assets' rate ranges are not touched, only their gaps (`capacity`) filled and their peers added.

## S — Safeguards

- Do not rename or restructure `asset_categories.name` — that breaks the `UNIQUE` constraint's meaning for other consumers and is explicitly out of scope.
- Do not introduce a second seeding mechanism alongside the existing `data.sql`/upsert convention — extend it.
- Do not hardcode booking dates as literals again — the whole point is a rolling window that doesn't go stale.
- Do not leave any new booking without a `BookingItem`.
- Do not fabricate rate ranges outside each category's existing `min_daily_rate`/`max_daily_rate` spread.

## Key decisions

| Decision | Why |
|---|---|
| 6 assets/category (24 total), not more | Enough for 2+ assets in at least one spec-band per category without over-building a fixture; matches the minimal-fixture spirit of the existing 8 |
| Capacity backfilled on existing assets, not just new ones | The 6 pre-existing non-forklift assets are the ones actually used in demos/tests today; leaving them null while only new assets get real values would still hide the fallback path most of the time |
| Rolling dates over literal dates | Static 2026-08-06→2026-08-16 window already half-elapsed at spec-writing time; a fixture that self-invalidates within days isn't a fixture worth having |
| Category names untouched | Mismatch is a Haystack read-time concern (ML feature naming vs. business naming), not a data defect — see `../dynamic-pricing/design.md` |
| Extend existing `data.sql`/upsert mechanism, don't replace it | `ddl-auto=update` means schema and data persist between runs; a second seeding path risks conflicting with the upsert convention already documented in Spring Boot's `SPEC-seed-data.md` |

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

### Target volumes per category — as originally drafted, then as actually executed

Sizing rationale: `pricing_tables.CAPACITY_BINS`/`HEIGHT_BINS` each define 4 spec-bands per category (3 for forklift). To get at least one band with 2+ assets (the minimum for a non-degenerate `period_utilization` fraction), this section originally suggested **6 assets per category** (24 total) spread 3/2/1 across three bands.

**What Spring Boot actually built (executed + verified 2026-08-11) is better, and is the version to treat as canonical going forward**: instead of spreading assets thinly across multiple bands, every category got **exactly one 4-asset "main" band and exactly 1 asset in every other band** — 27 assets total (7/7/7/6, forklift having only 3 bands). One guaranteed-non-degenerate band per category is simpler to point a demo or a `period_utilization` spot-check at than a signal split across two thin bands, and it's what the confirmed live simulation (`../domain-seed-data/spec.md` "State after reseed") validated: `0.75`/`0.25`/`0.0` across three windows on Excavator's main band.

| Category | Assets (actual) | Main band (4 assets) | Other bands (1 asset each) |
|---|---|---|---|
| Excavator | 7 | `(3000,7000]` — compact | `(0,3000]`, `(7000,15000]`, `(15000,None]` |
| Fork Lift | 6 | `(2000,3500]` | `(0,2000]`, `(3500,None]` |
| Scissors Lift | 7 | `(0,8]` | `(8,10]`, `(10,12]`, `(12,None]` |
| Boom Lift | 7 | `(0,18]` | `(18,24]`, `(24,31]`, `(31,None]` |

`condition`: actual result exceeds the ≥3-of-4 requirement — all 4 `ConditionType` values present in every category.

`min_daily_rate`/`max_daily_rate`/`base_daily_rate`: keep the existing per-category ranges already in the DB (they're reasonable — see `spec.md` "Current state", the rates themselves were never flagged as a problem) and interpolate new assets' rates within them by condition/capacity tier, don't invent a new pricing scheme.

### Booking generation

- **Volume**: enough bookings that, at any given moment, several assets per category have an active/overlapping hold and several don't — roughly 3-4 bookings per asset, not a fixed count. **Actual: 90 bookings** across 27 assets (20 original + 70 new), within this range.
- **Status distribution**: explicitly include `PENDING_DEPOSIT` and `CANCELLED` at least once each (was: absent) alongside the existing `PENDING_CONFIRMED`/`CONFIRMED`/`MOBILISED`/`COMPLETED`. A `CANCELLED` booking should overlap a window that *also* has a non-cancelled booking on a different asset in the same band, so the exclusion is visibly checkable. **Actual: all 6 statuses present** (`PENDING_DEPOSIT`: 4, `CANCELLED`: 7, `PENDING_CONFIRMED`: 15, `CONFIRMED`: 22, `MOBILISED`: 14, `COMPLETED`: 28).
- **Dates — rolling, not literal**: generate `start_date`/`end_date` as offsets from `CURRENT_DATE` at seed time, spanning roughly 30 days back to 60 days forward. This replaces the original single hardcoded 2026-08-06→2026-08-16 span, which went stale on its own. **Actual: 2026-06-22 → 2026-09-24**, confirmed spanning well before/around/after "today" (2026-08-11). Whether the mechanism is genuinely date-relative or a wide static range wasn't confirmed either way — worth asking Spring Boot directly before the *next* reseed, since a wide static range will eventually go stale the same way the original one did, just later.
- **`booking_items`**: every generated `Booking` gets exactly one (or more) `BookingItem` at insert time — no follow-up pass that leaves early rows orphaned. **Actual: 0 orphaned bookings** — the 10 originally-orphaned bookings (ids 11-20) were backfilled too, beyond what this design asked for (it only required this for *new* bookings).
- **Customers**: spread bookings across at least 2-3 distinct `customer_id`s instead of all 20 on one user — cheap realism, not load-bearing for pricing. **Actual: 3 distinct customers** (2 new users added: Mei Ling, Farid Rahman, with real BCrypt hashes).

**Bonus, not asked for but a legitimate catch**: Spring Boot's execution added a programmatic status-vs-child-row consistency validation pass, which found and fixed 3 pre-existing status errors on the *original* 20 bookings (ids 2, 6, 7 — statuses inconsistent with their already-existing payment/delivery/return records). Not something this design anticipated; recorded here so the reasoning behind those 3 corrections isn't lost.

### What NOT to change

- `asset_categories.name` — stays exactly as-is (`Excavator`, `Scissors Lift`, `Boom Lift`, `Fork Lift`). The mismatch against `feature_schema.CATEGORIES` is a Haystack-side read-time mapping fix (`../dynamic-pricing/design.md`), not a seed-data change. Renaming here would also risk breaking `AssetCategoryRepository.findByName` callers and the `UNIQUE` constraint's meaning for anything else that reads these names.
- No new columns, tables, or entity fields — this is row data only, within the existing schema documented in [`../spring-entity-repository/spec.md`](../spring-entity-repository/spec.md).
- No change to existing `min_daily_rate`/`max_daily_rate`/`base_daily_rate` ranges for the 8 assets that already exist — they're realistic; only null/missing/thin fields need filling in.

### Execution runbook (for the Spring Boot developer) — completed 2026-08-11

Kept below as the record of what was asked for and as a template for any future reseed; steps 1-8 are done and independently verified (see `../domain-seed-data/spec.md` "Execution result"/"State after reseed"). Step 9 (coordinate with Haystack) is what triggered this update.

1. **Confirm the existing seed mechanism first.** [`../spring-entity-repository/spec.md`](../spring-entity-repository/spec.md) §7/§8 references a `SPEC-seed-data.md` and an upsert-based `data.sql`, consistent with `ddl-auto=update` (schema persists between runs — seeding must be `ON CONFLICT`-safe, not a fresh-DB assumption). That doc isn't mirrored into this repo — find it in the Spring Boot repo and extend that mechanism rather than introducing a second one.
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

**Status (2026-08-11): reseed confirmed, code fix still pending.** The script below calls `compute_period_utilization()` as it exists today — which still has the category-name mismatch bug (`../dynamic-pricing/design.md` "Category name mapping"), so running it right now with `category='excavator'` will silently return the static fallback constant, **not** reflect this reseed. To confirm the *data* independent of that still-open code fix, the check was instead run directly against the raw tables with the real DB category name substituted by hand: querying Excavator's 4-asset main band (`(3000,7000]`, asset ids 1/2/9/10) returned **0.75**, **0.25**, **0.0** across three different windows — confirming the reseed itself is solid. Re-run the script below for real, unmodified, once Phase 2a's mapping fix lands — it should then reproduce a similar non-degenerate result through the actual function.

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
| 6 assets/category (24 total) originally suggested, **27 actually built** — 4-in-one-band + 1-in-each-other-band, not a 3/2/1 spread | Executed version is cleaner: one guaranteed-non-degenerate band per category to point a demo/spot-check at, instead of splitting the signal across two thinner bands. Confirmed via live simulation (0.75/0.25/0.0 across three windows) — see spec.md "State after reseed" |
| Capacity backfilled on existing assets, not just new ones | The 6 pre-existing non-forklift assets are the ones actually used in demos/tests today; leaving them null while only new assets get real values would still hide the fallback path most of the time |
| Rolling dates over literal dates | Static 2026-08-06→2026-08-16 window already half-elapsed at spec-writing time; a fixture that self-invalidates within days isn't a fixture worth having |
| Category names untouched | Mismatch is a Haystack read-time concern (ML feature naming vs. business naming), not a data defect — see `../dynamic-pricing/design.md` |
| Extend existing `data.sql`/upsert mechanism, don't replace it | `ddl-auto=update` means schema and data persist between runs; a second seeding path risks conflicting with the upsert convention already documented in Spring Boot's `SPEC-seed-data.md` |

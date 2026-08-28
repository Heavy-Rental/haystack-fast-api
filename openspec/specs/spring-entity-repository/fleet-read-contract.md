# D0 — Fleet read contract (S4 app)

| Field | Value |
|-------|--------|
| **Status** | **As-built (2026-08-13)** — haystack recommend tools |
| **Stage** | S4 / Phase 4 app half |
| **Parent** | [`spec.md`](./spec.md) (Spring JPA schema) |
| **Runtime** | `app/repositories/fleet_repository.py` · `LiveSqlFleetBackend` |

This is the **versioned D0 map** from Spring tables on **Postgres-Haystack** to recommend fleet DTOs.

**Schema (`PRICING_SCHEMA`):** ORM models stay mapped to `primary_snapshot`. Live may set `PRICING_SCHEMA=public`; that value is applied with SQLAlchemy `schema_translate_map` for **fleet + pricing reads only**. It does **not** remap KG-1 / pgvector. Pytest forces `primary_snapshot`. Default in `app/config.py` is `primary_snapshot`.

**Config T0–T2 (as-built):** 60s `postgres-haystack-sync`, `SYNC_TABLE_ALLOWLIST`, per-cycle METRICS. Local/devcontainer: [Haystack-Fast-API pack](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API). Academy/paid: this repo vendors `sync-from-primary.sh` in `deploy-pipeline/ansible/roles/haystack/files/` (**ADR-0012**). Consumer contract: pack `specs/001-haystack-postgres-merge-sync/contracts/schema-contract.md` (v1.0).

**Alignment:** pack D0 v1.0 allowlist is singular `asset,booking,category`. This contract (and `FleetRepository`) reads plural `assets`, `asset_categories`, `bookings`, `booking_items` (Spring JPA `spec.md`). Resolve in the **config pack / vendored sync script** if merge does not land those physical names.

## Table allowlist

| Table | Use |
|-------|-----|
| `asset_categories` | Category display name → feature slug |
| `assets` | Fleet rows |
| `bookings` | Rental window + status |
| `booking_items` | Booking → asset link |
| `return_records` | Proof of return; `returned_at` ends a live-hold |

No free-form SQL. Queries are SQLAlchemy `select` only.

## Asset DTO

| DTO | Column | Notes |
|-----|--------|--------|
| `asset_id` | `assets.name` (UNIQUE) | Never invent |
| `equipment_type` | `asset_categories.name` | Approved display (`Boom Lift`, …) |
| `category` | mapped feature name | `scissor lift`, `excavator`, … |
| `condition` | `assets.condition` | |
| `capacity` | `assets.capacity` | Quote `equipment.capacity` |
| `platform_height` | `assets.platform_height` | |
| `min_daily_rate` / `max_daily_rate` | `assets.min_daily_rate` / `assets.max_daily_rate` | |
| `description` | `assets.description` | Quote `equipment.desc` |
| `purchase_year` | `assets.purchase_year` | Quote `equipment.purchaseYear` |
| `location` | `assets.location` | Optional; omitted when the mirror has no column |

Unknown / unapproved category or blank `name` → row skipped.

## Quote mapping (Call 2 `equipment`)

Internal DTO `asset_id` stays `assets.name`. The HTTP quote remaps so Spring can FK `recommendation_items.asset_id`:

| Quote field | Column / rule |
|-------------|----------------|
| `equipment.id` | `assets.id` (string PK) when the row resolves |
| `equipment.name` | `assets.name` |
| `equipment.category` | `asset_categories.name` |
| `equipment.capacity` | `assets.capacity` |
| `equipment.purchaseYear` | `assets.purchase_year` |
| `equipment.location` | `assets.location` when the column exists |
| `equipment.desc` | `assets.description` |
| `equipment.available` | `false` when a live-hold booking overlaps the rental window after applying `return_records.returned_at`; also `false` when collapsed quote `quantity > 1` (one PK cannot fulfill N units) |
| `equipment.platformHeight` | `assets.platform_height` for Scissors Lift / Boom Lift only; omitted otherwise |
| `equipment.img` | **Not emitted** — Haystack does not read `asset_images` |

`FLEET_BACKEND=fake` (CI) keeps seed `equipment.id` = catalog `asset_id` (`AST-*`). Live SQL with a missing row **omits** the item (warning) instead of emitting a seed id.

## Booking DTO

| DTO | Source |
|-----|--------|
| `booking_id` | `bookings.id` |
| `asset_id` | parent `assets.name` via `booking_items` |
| `start_date` / `end_date` | `bookings.*` |
| `status` | `bookings.status` |

Only **live-hold** statuses count as busy (same as pricing): `PENDING_DEPOSIT`, `PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`. `CANCELLED` / `COMPLETED` ignored.

Quote `equipment.available` is false when a live-hold `bookings` row for that `assets.id` overlaps the rental window (today when dates are missing), unless `return_records.returned_at` ends the hold on or before the overlap. Collapsed Call 2 lines with `quantity > 1` are always `available: false` — one physical machine cannot fulfill N concurrent units. Live reads use `PRICING_SCHEMA=public` → `heavy_rental.public`.

## Runtime flag

`FLEET_BACKEND=fake` (default, CI) \| `sql` (`LiveSqlFleetBackend` + `SessionLocal`). Empty / missing schema → `[]`, no invent.

`PRICING_SCHEMA=primary_snapshot` (default, CI) \| `public` (live translate). Fleet and pricing share this flag.

# D0 — Fleet read contract (S4 app)

| Field | Value |
|-------|--------|
| **Status** | **As-built (2026-08-13)** — haystack recommend tools |
| **Stage** | S4 / Phase 4 app half |
| **Parent** | [`spec.md`](./spec.md) (Spring JPA schema) |
| **Runtime** | `app/repositories/fleet_repository.py` · `LiveSqlFleetBackend` |

This is the **versioned D0 map** from Spring tables on **Postgres-Haystack** (`primary_snapshot`, degrade to `public`) to recommend fleet DTOs.

**Config T0–T2 (as-built):** [Haystack-Fast-API pack](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API) — 60s `postgres-haystack-sync`, `SYNC_TABLE_ALLOWLIST`, per-cycle METRICS. Consumer contract: `specs/001-haystack-postgres-merge-sync/contracts/schema-contract.md` (pack v1.0).

**Alignment:** pack D0 v1.0 allowlist is singular `asset,booking,category`. This contract (and `FleetRepository`) reads plural `assets`, `asset_categories`, `bookings`, `booking_items` (Spring JPA `spec.md`). Resolve in the **config** pack if merge does not land those physical names.

## Table allowlist

| Table | Use |
|-------|-----|
| `asset_categories` | Category display name → feature slug |
| `assets` | Fleet rows |
| `bookings` | Rental window + status |
| `booking_items` | Booking → asset link |

No free-form SQL. Queries are SQLAlchemy `select` only.

## Asset DTO

| DTO | Column | Notes |
|-----|--------|--------|
| `asset_id` | `assets.name` (UNIQUE) | Never invent |
| `equipment_type` | `asset_categories.name` | Approved display (`Boom Lift`, …) |
| `category` | mapped feature name | `scissor lift`, `excavator`, … |
| `condition` | `assets.condition` | |
| `capacity` | `assets.capacity` | |
| `platform_height` | `assets.platform_height` | |
| `min_daily_rate` / `max_daily_rate` | `assets.min_daily_rate` / `max_daily_rate` | |

Unknown / unapproved category or blank `name` → row skipped.

## Booking DTO

| DTO | Source |
|-----|--------|
| `booking_id` | `bookings.id` |
| `asset_id` | parent `assets.name` via `booking_items` |
| `start_date` / `end_date` | `bookings.*` |
| `status` | `bookings.status` |

Only **live-hold** statuses count as busy (same as pricing): `PENDING_DEPOSIT`, `PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`. `CANCELLED` / `COMPLETED` ignored.

## Runtime flag

`FLEET_BACKEND=fake` (default, CI) \| `sql` (`LiveSqlFleetBackend` + `SessionLocal`). Empty / missing schema → `[]`, no invent.

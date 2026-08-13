# Proposal: S4 app + live SQL fleet backend

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S4 app + config T0–T2 stamp) |
| **Date** | 2026-08-13 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 4 + S7.1 live ORM leftover |
| **Study** | [`Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md`](../../../../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md) D0 / Track D |
| **Tasks** | [`./tasks.md`](./tasks.md) |

## Why

S7.1 `backend="sql"` only accepted injected DTOs. Recommend fleet tools could not read the Postgres-Haystack mirror. This change freezes **D0** and wires allowlisted ORM reads. Config-repo **T0–T2** is already shipped on pack `develop` (60s poll, allowlist, METRICS) — stamped as-built here; table-name alignment remains a config follow-up.

## What shipped

| Item | Behaviour |
|------|-----------|
| D0 contract | `openspec/specs/spring-entity-repository/fleet-read-contract.md` |
| `FleetRepository` | Allowlisted `assets` ⨝ `asset_categories`, `bookings` ⨝ `booking_items` |
| `asset_id` | `assets.name` (UNIQUE); never invent |
| `LiveSqlFleetBackend` | `FleetBackend` over the repository |
| `FLEET_BACKEND` | `fake` (default) \| `sql` |
| Live-hold bookings | Same statuses as pricing; `CANCELLED` ignored |
| Schema resilience | Reuse pricing `primary_snapshot` → `public` |

## Config T0–T2 (as-built, not in this repo)

[Haystack-Fast-API pack](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API): T0 skip/sleep; T1 60s + METRICS; T2 `SYNC_TABLE_ALLOWLIST`.

## Out of scope

- Align pack singular table names with haystack plural ORM (config follow-up)
- MVP `RecommendationService` seed path
- S8 Neo4j populate
- Production default flip of `RECOMMEND_VIA_AGENT_GRAPH`

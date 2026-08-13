# Proposal: S8.1 T3 Neo4j populate (config pack as-built stamp)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (config pack — not this app) |
| **Date** | 2026-08-13 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 8 / **8.1 T3** |
| **Verified** | [Haystack-Fast-API pack `develop`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API) |
| **Pack spec** | `specs/005-haystack-neo4j-populate/` (Status: Implemented) |
| **Tasks** | [`./tasks.md`](./tasks.md) |

## Why

PR-L / 8.1 asked for `populate-neo4j-from-haystack` (SQL → Cypher MERGE; fleet labels isolated from DocumentStore). That job now ships in the **config pack**, not haystack-fast-api. This archive stamps haystack docs so S8.1 is not treated as remaining work.

## What was verified

| Item | Pack artifact |
|------|----------------|
| Compose service | `neo4j-populate` |
| Scripts | `.devcontainer/scripts/populate-neo4j-from-haystack.sh`, `populate_neo4j.py` |
| MERGE | Parameterized Cypher keyed by node `id` |
| Isolation | `:Asset` / `:Booking` / `:Category` only; `:Document` untouched; rebuild label-scoped |
| Interval | `POPULATE_INTERVAL_SECONDS=60` (poll; not T4 sync-hook) |

## Out of scope (still open)

- **S8.2 T4** — trigger on successful `postgres-haystack-sync` merge or admin HTTP
- **S8.3** — real `neo4j_cypher_read` / `trigger_neo4j_populate` in this app (S7.2 stays fake/no-op)

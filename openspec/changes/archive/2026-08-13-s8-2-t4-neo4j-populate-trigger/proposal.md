# Proposal: S8.2 T4 Neo4j populate trigger (config pack as-built stamp)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (config pack — not this app) |
| **Date** | 2026-08-13 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 8 / **8.2 T4** |
| **Verified** | [Haystack-Fast-API pack `develop`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API) |
| **Pack spec** | `specs/005-haystack-neo4j-populate/` (T3 + **T4** Implemented) |
| **Tasks** | [`./tasks.md`](./tasks.md) |

## Why

PR-M / 8.2 required trigger-after-successful-sync **or** admin HTTP, label-scoped delete, never drop KG-1. The pack previously only polled every 60s (T3). `develop` now documents post-sync HTTP + admin `:8089`.

## What was verified

| T4 requirement | Pack evidence |
|----------------|---------------|
| After successful sync | Sync POSTs populate URL (best-effort) |
| Admin HTTP | host **8089** — `POST /v1/populate`, `GET /health` |
| Scoped delete | Fleet labels only |
| Never drop KG-1 | `:Document` never written or deleted |
| 60s poll | T3 safety-net, not a substitute for T4 |

## Out of scope (still open)

- **S8.3** — app live `neo4j_cypher_read` / `trigger_neo4j_populate` (may call this HTTP)

# PostgreSQL hostname is `postgres-haystack`, not `db`

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-10 |
| **Deciders** | haystack-fast-api maintainers |
| **Trace** | `openspec/specs/project-setup/spec.md` |

## Context and Problem Statement

Which hostname should the FastAPI service use for PostgreSQL on the compose/devcontainer network? Short alias `db` is convenient but ambiguous.

## Considered Options

* Hostname `db` (generic Docker alias)
* Hostname `postgres-haystack` (hyphen; DNS-confirmed 2026-08-10)
* Hostname `postgres_haystack` (underscore)

## Decision Outcome

Chosen option: **`postgres-haystack`**. Default database `heavy_rental`. Sync SQLAlchemy + **psycopg** v3 (`postgresql+psycopg://`).

Hostname `db` MUST NOT be used: on this Docker network it can resolve to either `postgres-haystack` or the Spring Boot primary. Underscore `postgres_haystack` is the wrong DNS name.

### Consequences

* Good: fleet/pricing reads hit the haystack mirror, not the Spring write SoT by accident.
* Bad / accepted: docs and older feasibility text that say `db` or `postgres_haystack` are wrong until stamped.

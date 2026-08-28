# `INDEXING_DOCUMENT_STORE` memory default vs pgvector

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | haystack-fast-api |
| **Trace** | FR-IX-027 / FR-IX-028 |

## Context and Problem Statement

Call 1 must write project chunks somewhere retrieval tools can filter by `user_id` + `ingest_id`. A shared pgvector table is the production shape; CI cannot require Postgres pgvector.

## Considered Options

* Always InMemory (lost on process restart; no I2 path)
* Always pgvector (CI depends on extra infra)
* Factory: `memory` default, `pgvector` opt-in; I2 production default later

## Decision Outcome

Chosen option: **`build_document_store()` / `create_session_document_store()`**. Default `memory` = fresh InMemory per ingest. `pgvector` = shared table with tenant filters. Optional `INDEXING_CHUNK_TTL_SECONDS` + delete helpers. Dual-mode tests: default CI memory; `@pytest.mark.pgvector`.

Target later: production default `pgvector` (I2).

### Consequences

* Good: default pytest needs no pgvector; live retrieval is tenant-scoped.
* Bad / accepted: memory sessions die with the process; I2 is still a target, not as-built.

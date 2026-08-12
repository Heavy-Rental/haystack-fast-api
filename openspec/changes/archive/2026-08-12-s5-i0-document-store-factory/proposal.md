# Proposal: DocumentStore factory + INDEXING_DOCUMENT_STORE (S5-I0 / Phase 5.2)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S5-I0) |
| **Date** | 2026-08-12 |
| **Trace** | FR-IX-027 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 5 / step **5.2 I0** |
| **Study** | [`Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md`](../../../../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md) §4.5 / Track I |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

Multi-replica Call 1→2 and durable multi-user project chunks need a **PgvectorDocumentStore** path on Postgres-Haystack. Safe rollout starts with a **config flag + factory** (I0) while CI and default ingest stay on process-local **InMemory**.

## What shipped

| Item | Behaviour |
|------|-----------|
| Env `INDEXING_DOCUMENT_STORE` | `memory` (default) \| `pgvector` |
| `build_document_store()` | Returns `InMemoryDocumentStore` or `PgvectorDocumentStore` from mode/settings |
| Invalid mode | `ValueError` with allowed values |
| `get_document_store` / `reset_document_store` | Remain process-local **InMemory** singleton (no accidental host `pgvector` before I1) |
| Dependency | `pgvector-haystack` (lazy import on pgvector branch) |
| Ingest pipeline | **Unchanged** — still InMemory until **I1** |

## Spec / design

- `openspec/specs/indexing/spec.md` — FR-IX-027 + scenarios + change control **0.9.0**
- `openspec/specs/indexing/design.md` — modules, config, test runbook
- `openspec/specs/project-setup/spec.md` — env/stack note
- `openspec/TRACEABILITY.md` — FR-IX-027 map
- `openspec/AGENTS.md` / `project.md` — as-built note
- `specification/SPEC-indexing-file-type-router.md` — pointer
- Feasibility_Study implementation-plan **3.5.4** · dual-plane study **2.7.6**

## Code

- `app/config.py` — `indexing_document_store`
- `app/pipelines/indexing/document_store.py` — `build_document_store`, `normalize_document_store_mode`
- `.env.example` — documented flag
- `pyproject.toml` — `pgvector-haystack`
- `tests/test_document_store_factory.py` — S5-I0 pack
- `tests/test_config.py` — default memory

## Out of scope (follow-up)

- I1: wire factory into pipeline writer + session registry — **done** (see S5-I1 archive)
- I1: tenant isolation retrieval tests / TTL job / dual-mode CI markers — **done** (S5-I1)
- I2: production default `pgvector`

# Proposal: DocumentStore pipeline wire + tenant isolation + TTL (S5-I1 / Phase 5.3–5.6)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S5-I1) |
| **Date** | 2026-08-12 |
| **Trace** | FR-IX-028 (builds on FR-IX-027 / I0) |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 5 / steps **5.3–5.6** |
| **Study** | [`Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md`](../../../../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md) §4.5 / Track I |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

Multi-replica Call 1→2 and durable multi-user project chunks need the indexing **writer** and **session registry** on the same DocumentStore backend selected by `INDEXING_DOCUMENT_STORE`, with **hard tenant filters** on retrieval and optional **TTL/delete** for temporary project files.

## What shipped

| Item | Behaviour |
|------|-----------|
| `create_session_document_store()` | `memory` → fresh InMemory per ingest; `pgvector` → shared table `indexing_project_chunks` |
| `IndexingIngestService` | Uses factory when no test store/pipeline injected; session holds writer store |
| Retrieval filters | `run_vector_search` / `project_vector_search` filter `user_id` + `ingest_id`; post-filter safety net |
| Backend retrievers | InMemoryEmbeddingRetriever or PgvectorEmbeddingRetriever |
| TTL / delete | `INDEXING_CHUNK_TTL_SECONDS`; `delete_ingest_chunks`; `purge_expired_chunks`; `discard_project_knowledge_session` |
| Dual-mode tests | Default CI isolation/TTL packs; `@pytest.mark.pgvector` optional (`RUN_PGVECTOR_TESTS=1`) |
| Default mode | Still **`memory`** (CI-safe); I2 production default pgvector remains TARGET |

## Spec / design

- `openspec/specs/indexing/spec.md` — FR-IX-028 + scenarios + change control **0.10.0**
- `openspec/specs/indexing/design.md` — modules, config, test runbook
- `openspec/TRACEABILITY.md` — FR-IX-028 map
- `openspec/project.md` — as-built I1 note
- `specification/SPEC-indexing-file-type-router.md` — pointer
- Feasibility_Study implementation-plan **3.5.5** · dual-plane study **2.7.7**

## Code

- `app/config.py` — `indexing_chunk_ttl_seconds`
- `app/pipelines/indexing/document_store.py` — session factory + delete
- `app/pipelines/indexing/retrieval.py` — tenant filters + backend dispatch
- `app/services/indexing.py` — I1 wire + optional `expires_at` stamp
- `app/services/project_chunk_cleanup.py` — purge + discard
- `app/services/project_knowledge_session.py` — generic store type
- `app/agents/tools.py` — session-scoped filters
- `.env.example` · `pyproject.toml` marker
- Tests: `test_tenant_vector_isolation.py`, `test_project_chunk_cleanup.py`, `test_pgvector_isolation.py`

## Out of scope (follow-up)

- I2: production default `INDEXING_DOCUMENT_STORE=pgvector`
- Multi-replica shared idempotency store
- Admin HTTP for purge (helpers only)

# Tasks: DocumentStore pipeline wire + isolation + TTL (S5-I1 / Phase 5.3–5.6)

| Field | Value |
|-------|--------|
| **Status** | **Complete / as-built** |
| **Date** | 2026-08-12 |
| **Proposal** | [`./proposal.md`](./proposal.md) |
| **Process** | TDD red→green→refactor · BDD G/W/T in isolation/cleanup packs |

## Spec / design first

- [x] OpenSpec FR-IX-028 + scenarios in `specs/indexing/spec.md`
- [x] Design modules + config + test table in `specs/indexing/design.md`
- [x] TRACEABILITY + project.md as-built notes
- [x] Feasibility_Study implementation-plan Phase 5.3–5.6 + dual-plane Track I1
- [x] specification pointer `SPEC-indexing-file-type-router.md`
- [x] Archive this change set

## Implementation

- [x] Config `INDEXING_CHUNK_TTL_SECONDS` default `0` + `.env.example`
- [x] `create_session_document_store()` (memory fresh / pgvector shared)
- [x] Wire factory into `IndexingIngestService` + session registry
- [x] Stable pgvector table `indexing_project_chunks`
- [x] Tenant filters on `run_vector_search` + tool always passes session keys
- [x] Backend-aware retriever (InMemory / Pgvector)
- [x] `delete_ingest_chunks` + `purge_expired_chunks` + `discard_project_knowledge_session`
- [x] Optional `expires_at` stamp when TTL > 0
- [x] `@pytest.mark.pgvector` registered; skip unless `RUN_PGVECTOR_TESTS=1`

## Test pack (S5-I1)

- [x] Shared-store isolation two users (`test_tenant_vector_isolation.py`)
- [x] Ingest writes `user_id`/`ingest_id` meta on store
- [x] Tool scopes to session tenant
- [x] Delete one ingest leaves others
- [x] TTL purge only expired
- [x] Discard session registry + chunks
- [x] Factory session helper + table name
- [x] Optional live pgvector pack (skip by default)
- [x] Full default suite regression green

## How to re-run tests (instructions)

```bash
cd haystack-fast-api
uv run pytest tests/test_document_store_factory.py tests/test_tenant_vector_isolation.py \
  tests/test_project_chunk_cleanup.py -q
uv run pytest tests/ -q
# Optional:
RUN_PGVECTOR_TESTS=1 uv run pytest -m pgvector -q
```

Canonical: [`openspec/specs/indexing/spec.md` — How to test FR-IX-028](../../../specs/indexing/spec.md#how-to-test-fr-ix-028--s5-i1--verification-instructions) · [`design.md` runbook](../../../specs/indexing/design.md#how-to-test-this-capability-runbook)

## Explicitly not done (follow-up I2+)

- [ ] Production default `INDEXING_DOCUMENT_STORE=pgvector` (I2)
- [ ] Shared multi-replica idempotency
- [ ] Public admin purge HTTP

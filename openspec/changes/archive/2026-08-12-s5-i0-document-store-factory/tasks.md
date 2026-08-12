# Tasks: DocumentStore factory + INDEXING_DOCUMENT_STORE (S5-I0 / Phase 5.2)

| Field | Value |
|-------|--------|
| **Status** | **Complete / as-built** |
| **Date** | 2026-08-12 |
| **Proposal** | [`./proposal.md`](./proposal.md) |
| **Process** | TDD red→green→refactor · BDD G/W/T in `tests/test_document_store_factory.py` |

## Spec / design first

- [x] OpenSpec FR-IX-027 + scenarios in `specs/indexing/spec.md`
- [x] Design modules + config + test table in `specs/indexing/design.md`
- [x] Project-setup env/stack note
- [x] TRACEABILITY + AGENTS + project.md as-built notes
- [x] Feasibility_Study implementation-plan Phase 5.2 + dual-plane Track I0
- [x] specification pointer `SPEC-indexing-file-type-router.md`
- [x] Archive this change set

## Implementation

- [x] Config `INDEXING_DOCUMENT_STORE` default `memory` + `.env.example`
- [x] `build_document_store()` / `normalize_document_store_mode()`
- [x] `pgvector` branch lazy-imports `PgvectorDocumentStore` (connection + dim)
- [x] Invalid mode → `ValueError`
- [x] Singleton `get_document_store` stays InMemory (no I1 wire)
- [x] Dependency `pgvector-haystack` in `pyproject.toml`

## Test pack (S5-I0)

- [x] Factory memory default / explicit memory
- [x] Settings default is memory
- [x] Invalid flag errors
- [x] Case/whitespace normalization
- [x] `pgvector` with mocked constructor (no live Postgres)
- [x] ImportError path message when integration missing
- [x] Empty connection string error path
- [x] Singleton stays InMemory
- [x] Full default suite regression green

## How to re-run tests (instructions)

```bash
cd haystack-fast-api
uv run pytest tests/test_document_store_factory.py -q   # S5-I0 pack
uv run pytest tests/ -q                                  # full regression
```

Canonical: [`openspec/specs/indexing/spec.md` — How to test FR-IX-027](../../../specs/indexing/spec.md#how-to-test-fr-ix-027--s5-i0--verification-instructions) · [`design.md` runbook](../../../specs/indexing/design.md#how-to-test-this-capability-runbook)

## Explicitly not done (follow-up I1+)

- [x] Wire factory into `IndexingIngestService` / session registry → **done in S5-I1** (archive `../2026-08-12-s5-i1-document-store-pipeline-wire/`)
- [x] Tenant isolation retrieval tests + TTL job → **done in S5-I1**
- [x] `@pytest.mark.pgvector` dual-mode pack → **done in S5-I1** (optional `RUN_PGVECTOR_TESTS=1`)
- [ ] Production default `INDEXING_DOCUMENT_STORE=pgvector` (I2)

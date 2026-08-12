# Changelog

## Unreleased

### Added (S5-I1 / Phase 5.3–5.6 — 2026-08-12)

- **FR-IX-028** — Call 1 wires `create_session_document_store()` (`INDEXING_DOCUMENT_STORE`: `memory` = fresh InMemory per ingest; `pgvector` = shared table `indexing_project_chunks`).
- Tenant isolation: `project_vector_search` / `run_vector_search` always filter `user_id` + `ingest_id` (InMemory or Pgvector retriever).
- Optional chunk TTL: `INDEXING_CHUNK_TTL_SECONDS` stamps `meta.expires_at`; helpers `delete_ingest_chunks`, `purge_expired_chunks`, `discard_project_knowledge_session`.
- Dual-mode tests: default CI isolation/TTL packs; optional `@pytest.mark.pgvector` (`RUN_PGVECTOR_TESTS=1`).
- OpenSpec archive: `openspec/changes/archive/2026-08-12-s5-i1-document-store-pipeline-wire/`.

### Added (S2a / resilience C1 — 2026-08-12)

- **FR-IX-024** — Optional `Idempotency-Key` on Call 1 ingest (`POST .../submitprojectspecification`). Successful lean **200** bodies are stored process-locally (scoped by `user_id` + key) and replayed on retry with the same `ingest_id`. Failed 4xx/5xx are not cached. Single-flight for concurrent same-key POSTs. TTL via `IDEMPOTENCY_TTL_SECONDS` (default 24h). **Not multi-replica shared.**
- **FR-IX-025** — Optional `X-Correlation-Id` / W3C `traceparent`; server mints correlation id when missing; logs bind id; responses **echo** `X-Correlation-Id`.
- OpenSpec: indexing contract/spec/design + TRACEABILITY; Postman resilience headers; tests in `tests/test_ingest_idempotency.py` and `tests/test_correlation_middleware.py`.

## v1.0.0

### Added or Changed
- Added this changelog :)
- Fixed typos in both templates
- Back to top links
- Added more "Built With" frameworks/libraries
- Changed table of contents to start collapsed
- Added checkboxes for major features on roadmap

### Removed

- Some packages/libraries from acknowledgements I no longer use
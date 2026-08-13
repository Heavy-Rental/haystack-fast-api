# Changelog

## Unreleased

### Added (S7.7 / Phase 7 — 2026-08-13)

- Isolated recommend A–L prompt contracts in `app/agents/recommend_prompts.py` (Coordinator [8], Delegator, Workers [5][6][7]). Stage-1 Q&A `app/agents/prompts.py` unchanged.
- Tool DI runtime: `build_recommend_runtime`, `ALLOWED_WORKER_KINDS`, `validate_work_plan` (`UnknownWorkerKindError`). Delegator + `execute_needs` fail closed on unknown `worker_kind`.
- Stub rationale helper keeps golden merge text; LLM payloads can rewrite rationale only (`apply_rationale_only`).
- Tests: `tests/test_recommend_prompts.py`, `tests/test_agent_tool_di.py`.
- OpenSpec archive: `openspec/changes/archive/2026-08-13-s7-7-prompts-a-l-tool-di/`.

### Changed (specification/ removal — 2026-08-13)

- Relocated the only unique spec, Spring JPA catalog, to `openspec/specs/spring-entity-repository/spec.md`.
- Retargeted live code/docs/OpenSpec pointers. Deleted the legacy `specification/` stub tree.

### Added (S7.5 + S7.6 / Phase 7 — 2026-08-12)

- Call 2 `getassetrecommendations` can run the C/W/D recommend graph behind `RECOMMEND_VIA_AGENT_GRAPH` (default **false**). Same quote DTO (`quoteRef`, `items[]`); gate refuse → 400; traces stay off the body.
- G-1 `tool_traces` contract: `role`, `node`, `need_id` on fan-out, `duration_ms >= 0` on terminal spans (`app/agents/recommend_traces.py`).
- Tests: `tests/test_recommend_http_call2.py`, `tests/test_tool_traces.py`.
- OpenSpec archive: `openspec/changes/archive/2026-08-12-s7-5-s7-6-call2-enrich-traces/`.

### Added (S7.3 + S7.4 / Phase 7 — 2026-08-12)

- Recommend LangGraph DAG (`app/agents/recommend_graph.py` / `recommend_nodes.py`): `check_gate → project_worker → delegator → execute_needs → synthesis`. Must-seq fleet→price within need; `RECOMMEND_FANOUT_CAP` (default 4) batches across needs. Gate false skips fleet/price tools.
- Tool-free Coordinator stub synthesis (`app/agents/recommend_synthesis.py`): merge `fleet_by_need` + `prices_by_need` → `results_by_need`; empty fleet / missing prices → `item: null` + warning; no invent; F-2 on apply.
- Isolated from Stage-1 Q&A (`app/agents/graph.py`). Call 2 HTTP enrich landed in S7.5.
- Tests: `tests/test_recommend_graph_order.py`, `test_recommend_fanout.py`, `test_recommend_synthesis.py`.
- OpenSpec archive: `openspec/changes/archive/2026-08-12-s7-3-s7-4-recommend-graph-synthesis/`.

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
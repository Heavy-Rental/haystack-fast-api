# Changelog

## Unreleased

### Changed (docs — HR-244 / ADR-0012 deploy workers, 2026-08-28)

- Academy/paid compose vendors pack `postgres-haystack-sync` and `neo4j-populate` scripts (`deploy-pipeline/ansible/roles/haystack/files/`). Sidecars use `postgres:17` and `python:3.12-slim`, not `python -m` from the uvicorn image.
- OpenSpec: FR-PDH-010, project-setup, FR-KG-011, equipment-recommendation, fleet-read-contract; **ADR-0012**. Archive `openspec/changes/archive/2026-08-28-hr-244-deploy-pipeline-sync-workers/`.
- FastAPI `app/` is still a client: `trigger_neo4j_populate` POSTs `NEO4J_POPULATE_URL`; request handlers do not run ETL. Local/devcontainer compose remains the config pack.
- Feasibility_Study implementation-plan **3.20.0**; dual-plane **2.8.5**.

### Changed (docs — OpenSpec / OpenSPDD / MADR sync, 2026-08-27)

- Added MADR log `openspec/adrs/` (ADR-0001…0011) and OpenSPDD canvas index `openspec/spdd/README.md`.
- Folded Phase 3b–3d into live `openspec/specs/dynamic-pricing/` **3.1.0** (ADR-0005); archived `2026-08-15-scheduled-model-retrain`.
- Archived shipped OpenSpec changes (Call 1 summary, Call 2/3 numbering, superseded dual-hop docs, FR-P-013, FR-P-014).
- Constitution / `project.md` / `AGENTS.md` Path C: Call 2 quote is live HTTP; host is `postgres-haystack` (not `db`).
- Replaced template root `README.md` with product + spec-standard entry points.
- Portal dual-hop OpenSPDD `design.md`; removed duplicate indexing FR-IX-024/025; intake live pointer matches lean FR-IX-023.

### Added (docs)

- `QUICKSTART.md` at the uv project root: install, two `.env` profiles (fake vs live compose), pytest, Call 1 → Call 2 curl smoke.

### Changed (docs — spec sync)

- OpenSpec + `Feasibility_Study/` + `Feasibility_Study_Spring/` aligned to as-built Call 1 / Call 2.
- Call 2 quote identity: live SQL `equipment.id` = `assets.id`; internal DTO `asset_id` remains `assets.name`. Seed `AST-*` is CI/`fake` only.
- Quote fields (`capacity`, `purchaseYear`, `location`, `available`, `desc`, aerial-only `platformHeight`, no `img`) and evidence `confidenceScore` / `matchScore` / `reason` documented on the Call 2 contract and Spring mapping.
- Call 1: file-before-text, ignore placeholder caption, multi-need hint split, expanded date/budget patterns.
- `PRICING_SCHEMA` + pytest `NEED_DECOMPOSER=stub` / `PRICING_SCHEMA=primary_snapshot` documented in project-setup.

### Changed (SQL read schema)

- `PRICING_SCHEMA=public` | `primary_snapshot` selects which Postgres schema fleet and pricing agents read. ORM tables stay mapped to `primary_snapshot`; `public` is applied with `schema_translate_map`. Default remains `primary_snapshot`.

### Changed (Call 2 equipment.platformHeight)

- Quote `equipment.platformHeight` is `assets.platform_height` only for Scissors Lift / Boom Lift (`category_id` 2 or 3, or name/type containing scissor/boom). Omitted for forklift/excavator and when height is null. Also set from the selected candidate if the second assets lookup is skipped.

### Changed (Call 1 expected_budget patterns)

- Budget extract accepts `SGD8000`, `SGD 8k`, `1.5m SGD`, spoken currency, `RM`, yen, cue + bare number (`budget of 8000`), spaced thousands, and `$8000` / `$12,500` without a cue when the figure looks like money.
- Still not a budget: words only (`tight budget`), `$10` room-size, `8m` / `20 ton`.

### Changed (Call 2 matchScore + reason)

- `matchScore` is a 0..1 evidence score (category, height cue, available, priced), not `1/rank`.
- `reason` is a factual match sentence (hints, category, availability, daily_rate). Removed `Stub merge:`.
- Fleet filter uses `equipment_hints` only when present so a forklift need cannot pick a scissor lift from a shared description.

### Changed (Call 2 confidenceScore + Call 1 named dates)

- `confidenceScore` is an evidence-weighted score (need coverage, matchScore, live `assets.id`, availability, priced lines, rental dates), not `0.55 + 0.08 × n`.
- Call 1 date extract now accepts English months (`1 Sep 2026 to 30 Sep 2026`, `Sep 1, 2026`, `between 1 September 2026 and 30 September 2026`), ordinals (`1st of September 2026`), hyphenated names (`1-Sep-2026`), two-digit years (`1 Sep 26`), dotted/slashed numerics, ISO datetimes, compact `YYYYMMDD`, quarters (`Q3 2026`), month-only (`Sep 2026`), `end/start of September`, and `this/next month`. Heights like `8m` are not dates.

### Changed (Call 2 quote: drop equipment.img)

- Removed `equipment.img` from the Call 2 quote DTO and stopped reading `asset_images`.

### Changed (Call 1 needs_summary multi-need)

- Ingest source merges extracted file text **before** `project_text` and ignores the placeholder caption `"Optional caption alongside file"`.
- Stub / LLM-empty fallback splits one need per approved type (`forklift`, `scissor lift`, …) with `equipment_hints`.
- LLM prompt requires one JSON object per distinct equipment type. Local `.env` uses `NEED_DECOMPOSER=llm`; pytest forces stub.

### Changed (Call 2 quote equipment catalog fields)

- Quote `equipment` now exposes top-level `capacity`, `purchaseYear`, `location`, `available`, `desc`, `tags` from the assets table (Spring portal DTO). `capacity` is no longer extra-only.
- `purchaseYear` / `desc` from `assets.purchase_year` / `assets.description`. `location` from `assets.location` when that column exists.
- `available` is false when a live-hold booking (`booking_items` + `bookings`) overlaps the rental window; missing dates use today. Unreadable bookings → null, no invent.

### Changed (Call 2 equipment from assets table)

- Call 2 MVP (`RecommendationService`) honors `FLEET_BACKEND=sql` and reads candidates from the `assets` table via `FleetRepository` (no silent seed fallback).
- Quote `equipment.id` is `assets.id` (PK) when the row resolves; `equipment.name` is `assets.name`. Seed-only picks still use the catalog `asset_id`.
- Live SQL quotes omit the item (warning) instead of emitting seed `AST-*` ids when the assets row is missing.
- `FLEET_BACKEND` normalizes `=sql` / `SQL` so a dotenv `FLEET_BACKEND==sql` typo still selects the live backend.
- `FleetRepository.get_asset` looks up by numeric `assets.id` or `assets.name` so Spring can FK `recommendation_items.asset_id`.

### Changed (Call 2 predicted price on each item)

- Call 2 quote items now include `mlPredictedPrice` (production `pricing_client` / `predict_price` daily rate). Same value as `equipment.baseDailyRate`. `was_clamped` / `explanation` pass through `equipment.extra`.
- Pricing Worker [7] forwards a live SQL session to `predict_asset_price` when `FLEET_BACKEND=sql`.
- Docs stamp: OpenSpec Call 2 contract + equipment-recommendation 1.9.1; Feasibility_Study implementation-plan **3.17.1**.

### Added (S7.8 / Worker [5] KG-1 — 2026-08-13)

- Project Worker [5] calls session-bound `project_vector_search` and `project_kg_query` before `decompose_project_needs`.
- Writes `project.research_notes` / `project.graph_notes` (explicit empty or skip when tools missing or fail). Decompose still runs; no invented `asset_id`.
- Catalog registers KG-1 tools when a `ProjectKnowledgeSession` is passed; Call 2 graph path supplies the session.
- Tests: `tests/test_recommend_project_worker.py`. Implementation-plan **3.17.0**. Archive `openspec/changes/archive/2026-08-13-s7-8-worker5-kg1-live/`.

### Added (S8.3 / Phase 8 app — 2026-08-13)

- Live KG-2 tools behind `NEO4J_BACKEND=bolt` (default **fake**): `BoltNeo4jBackend` reads fleet labels only (`:Asset` / `:Booking` / `:Category` / `:Attachment`); never `:Document`.
- `trigger_neo4j_populate` POSTs `NEO4J_POPULATE_URL` (ops admin `:8089`) and returns immediately; transport errors → `status=unavailable`. Fake path stays `noop` / `queued`.
- K-3: empty **or** Bolt-unavailable backends skip `neo4j_cypher_read`; SQL fleet tools still run.
- Optional `@pytest.mark.neo4j` (`RUN_NEO4J_TESTS=1`); extra `uv sync --extra neo4j`.
- FR-KG-011 marked as-built (persist = pack S8.1–S8.2; load = app S8.3).
- Tests: `tests/test_neo4j_tools.py` (HTTP stub, mapper, K-3 unavailable); `tests/test_neo4j_tools_integration.py`.
- Feasibility_Study implementation-plan **3.16.0**; dual-plane **2.8.3**. Archive `openspec/changes/archive/2026-08-13-s8-3-live-neo4j-tools/`.

### Changed (S8.2 / T4 config — 2026-08-13)

- Stamped Phase 8 **8.2 T4** as-built from the [Haystack-Fast-API pack](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API): post-sync populate trigger, admin HTTP `:8089` (`POST /v1/populate`), scoped fleet delete, KG-1 `:Document` never dropped.
- 60s populate poll remains the T3 safety-net. **S8.3** app live Neo4j tools remain.
- Feasibility_Study implementation-plan **3.15.0**; dual-plane **2.8.2**. Archive `openspec/changes/archive/2026-08-13-s8-2-t4-neo4j-populate-trigger/`.

### Changed (S2b / Phase 2 Spring — 2026-08-13)

- Stamped **S2b as-built** from [heavy-rental-spring-rest-api `develop`](https://github.com/Heavy-Rental/heavy-rental-spring-rest-api): `HaystackRecommenderClient`, Resilience4j, `RecommenderSagaService`, WireMock pack (canonical plan **v2.1.1**).
- Haystack Feasibility_Study implementation-plan **3.14.0**. Archive `openspec/changes/archive/2026-08-13-s2b-spring-resilience-stamp/`.
- Still open: multi-replica S2a store; Spring prod ingest retry flag; C2 `202`/SSE.

### Changed (S8.1 / T3 config — 2026-08-13)

- Stamped Phase 8 **8.1 T3** as-built from the [Haystack-Fast-API pack](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API): Compose `neo4j-populate`, SQL → Cypher MERGE, fleet labels isolated from DocumentStore.
- **S8.2 T4** (trigger-on-sync) and **S8.3** (app live Neo4j tools) remain.
- Feasibility_Study implementation-plan **3.13.0**; dual-plane **2.8.1**. Archive `openspec/changes/archive/2026-08-13-s8-1-t3-neo4j-populate/`.

### Changed (S4 / Phase 4 config T0–T2 — 2026-08-13)

- Documented config-repo T0–T2 as **as-built** on [Haystack-Fast-API pack `develop`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API): 60s `postgres-haystack-sync`, `SYNC_TABLE_ALLOWLIST`, per-cycle METRICS.
- Recorded table-name alignment follow-up: pack D0 `asset,booking,category` vs haystack ORM `assets` / `bookings` / `booking_items` / `asset_categories`.
- Feasibility_Study implementation-plan **3.12.0**; dual-plane **2.8.0**.

### Added (S4 / Phase 4 app — 2026-08-13)

- Live SQL fleet backend: `FleetRepository` + `LiveSqlFleetBackend` behind `FLEET_BACKEND=sql` (default **fake**). `asset_id` is `assets.name`; live-hold bookings only; empty/unknown category → `[]`.
- D0 contract: `openspec/specs/spring-entity-repository/fleet-read-contract.md`.
- `run_recommend_graph` opens a `SessionLocal` when the flag is `sql` and no catalog is injected. Config-repo T0–T2 sync is unchanged.
- Tests: `tests/test_fleet_repository.py`.
- OpenSpec archive: `openspec/changes/archive/2026-08-13-s4-live-sql-fleet-backend/`.

### Added (S7.2 / Phase 7 — 2026-08-13)

- Allowlisted in-process KG-2 tools in `app/agents/neo4j_tools.py`: `neo4j_cypher_read` (templates only) and `trigger_neo4j_populate` (non-blocking `job_id` / no-op).
- `FakeNeo4jBackend` default is empty; fixture inject for template tests. Free-form Cypher/SQL kwargs raise `FreeFormCypherRejected`; unknown templates raise `UnknownNeo4jTemplateError`.
- Delegator K-3 skip: empty graph omits `neo4j_cypher_read` from fleet allowlist (`skip_tools`). Recommend is not blocked. Fleet worker attaches optional `graph_notes` when a fixture graph is present.
- Tests: `tests/test_neo4j_tools.py`, fixture `tests/fixtures/recommend/neo4j_graph.json`.
- OpenSpec archive: `openspec/changes/archive/2026-08-13-s7-2-neo4j-tools/`.

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
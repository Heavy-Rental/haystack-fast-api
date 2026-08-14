# Portal Dual-Hop Specification (Call 1 Ingest → Call 2 Recommend)

| Field | Value |
|-------|--------|
| **Status** | **as-built** |
| **Capability** | `portal-dual-hop` |
| **Feature id** | `portal-call1-call2-process` |
| **Standards** | OpenSpec · GitHub Spec-kit · OpenSPDD |
| **Audience** | Engineers, coding agents, Spring integrators |
| **Agent map** | [`../../AGENTS.md`](../../AGENTS.md) runtime flow |
| **Env** | [`../../../.env.example`](../../../.env.example) · live [`.env`](../../../.env) |
| **Postman** | [`../../../postman/README.md`](../../../postman/README.md) |
| **Spring mapping** | [`../../../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../../../Feasibility_Study_Spring/portal-to-haystack-mapping.md) |

**Spec-kit phases:** Specify (this file) → Plan → Tasks → Implement → Converge.

When behaviour here and the codebase diverge, update them in the **same change set**.

### Document roles & conflict rule

| Document | Owns |
|----------|------|
| **This capability** | End-to-end Call 1 → Call 2 process, dual-plane data rules, operational checklist |
| [`../indexing/spec.md`](../indexing/spec.md) + [`../indexing/contracts/ingest-from-project-spec.md`](../indexing/contracts/ingest-from-project-spec.md) | Call 1 field list, MIME map, FR-IX-023 lean body, S2a/S3 |
| [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) | Mandatory KG-1 after joiner; Call 3 Q&A tools |
| [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md) + [`../recommendation-pipeline/contracts/get-asset-recommendations.md`](../recommendation-pipeline/contracts/get-asset-recommendations.md) | Call 2 quote DTO, scores, fleet identity |
| [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) | Parent product vision |

**Conflict rule:** Field-level HTTP contracts → **child contract wins**. Cross-call saga, data-plane boundaries, and step order → **this capability**.

---

## Purpose

Document the **as-built** haystack-fast-api multi-call journey:

1. **Call 1** — ingest project specification (file and/or text) into DocumentStore + mandatory KG-1; return lean summary + `ingest_id`.
2. **Call 2** — recommend / quote equipment for that session using project knowledge first, then fleet (SQL ± Neo4j) and pricing.

Call 3 (chatbot Q&A) is out of primary scope here; it is noted only for orientation.

---

## Outcomes

- Portal / Spring can run **Call 1 then Call 2** and return a quote without re-ingesting on Call 2 failure.
- Call 1 SHALL write **project-only** knowledge (vectors + KG-1), never fleet table dumps into pgvector.
- Call 2 SHALL load session `(user_id, ingest_id)`, MUST NOT invent `equipment.id` or rates, and MAY use Neo4j KG-2 only as optional fleet graph context.
- Engineers have a single OpenSpec entry for process order, stores, env flags, errors, and ops checklist.

---

## Scope

### In scope

| Area | Notes |
|------|--------|
| Call 1 HTTP process | Index + KG-1 + session + lean FR-IX-023 body |
| Call 2 HTTP process | MVP service path + optional agent graph path |
| Dual data planes | Plane B project vs Plane A fleet |
| Env flags that change path | `INDEXING_*`, `FLEET_*`, `NEO4J_*`, `RECOMMEND_VIA_AGENT_GRAPH` |
| Ops note | `neo4j-populate` lives in config pack; app is client/reader |

### Out of scope

| Area | Notes |
|------|--------|
| Call 3 chatbot field contract | [`../knowledge-graph/contracts/project-knowledge-query.md`](../knowledge-graph/contracts/project-knowledge-query.md) |
| Spring Resilience4j implementation | Spring repo / Feasibility_Study_Spring |
| neo4j-populate SQL→Cypher ETL source | Config pack, not this app |

---

## Runtime overview

### Portal dual-hop

```text
React  POST /api/recommendations/project-spec
         │
         ▼
Spring Boot (orchestrator / booking SoT)
         │
         ├─ Call 1  POST /internal/v1/recommendations/submitprojectspecification
         │            → index project + KG-1 + session
         │            → lean summary + ingest_id
         │
         ├─ persist user_id + ingest_id
         │
         └─ Call 2  POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
                      → quote / items[]  (primary body back to React)
```

### Call ownership

| | **Call 1 — Ingest** | **Call 2 — Recommend / quote** |
|--|---------------------|--------------------------------|
| **Route** | `POST /internal/v1/recommendations/submitprojectspecification` | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Input** | Project file and/or `project_text` + `user_id` | `user_id` + `ingest_id` (+ optional `query`) |
| **Output** | Lean summary + `ingest_id` | Quote envelope (`quoteRef`, `items[]`) |
| **Stores written** | DocumentStore (memory/pgvector), KG-1 JSON, session registry | None (reads only) |
| **Fleet** | Not used | Postgres SQL and/or Neo4j KG-2 |
| **Pricing** | Not used | `predict_price` / pricing client |
| **Idempotency** | Optional `Idempotency-Key` | No — do **not** re-run Call 1 on Call 2 failure |

### Data planes (MUST NOT conflate)

```text
Plane B — project (Call 1 writes; Call 2/3 read)
  project file/text
    → chunks → DocumentStore (memory | pgvector table indexing_project_chunks)
    → KG-1 Ragas graph → artifacts/kg/{user_id}/kg_{ingest_id}.json
    → ProjectKnowledgeSession (user_id, ingest_id)

Plane A — fleet (Call 2 reads; not from Call 1)
  Postgres assets/bookings/...  → SQL fleet tools (primary)
  neo4j-populate (ops)         → Neo4j :Asset/:Booking/:Category (optional)
```

---

## Requirements

### Requirement: FR-PDH-001 Portal dual-hop order

The portal project-spec submit path SHALL run **Call 1 before Call 2**. Spring MUST persist Call 1 `user_id` and `ingest_id` and pass them to Call 2. On Call 2 failure, the client MUST NOT re-ingest by default (retry Call 2 only).

#### Scenario: Happy dual-hop

- **GIVEN** a valid project-spec payload and a running haystack instance
- **WHEN** Spring issues Call 1 then Call 2 with the returned `ingest_id`
- **THEN** Call 1 returns HTTP 200 lean body including `ingest_id`
- **AND** Call 2 returns HTTP 200 quote envelope with `quoteRef` and `items[]` (possibly empty with warnings)

#### Scenario: Call 2 without Call 1 session

- **GIVEN** no process-local session for `(user_id, ingest_id)`
- **WHEN** a client POSTs Call 2
- **THEN** the service returns HTTP **404**

---

### Requirement: FR-PDH-002 Call 1 project-only indexing

Call 1 SHALL index **project specification** content only (multipart file and/or `project_text`). Call 1 MUST NOT embed or write Postgres fleet tables (`assets`, `bookings`, …) into the DocumentStore or KG-1.

#### Scenario: Project text ingest

- **GIVEN** JSON body with `user_id` and non-empty `project_text`
- **WHEN** Call 1 succeeds
- **THEN** chunks are written to the session DocumentStore with meta `user_id` + `ingest_id`
- **AND** KG-1 is built and persisted under `{KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json`
- **AND** a `ProjectKnowledgeSession` is registered for Call 2

#### Scenario: Unsupported MIME hard-fail

- **GIVEN** an unsupported or unclassified file type
- **WHEN** Call 1 runs
- **THEN** the service returns HTTP **400** and does not register a successful session

---

### Requirement: FR-PDH-003 Call 1 mandatory KG-1

After successful chunk production at `final_doc_joiner`, Call 1 SHALL build KG-1. KG failure MUST hard-fail the request (HTTP 400). Full Ragas transforms run only when `KG_APPLY_TRANSFORMS=true`.

#### Scenario: KG failure fails ingest

- **GIVEN** indexing produced writable chunks
- **WHEN** KG-1 build fails
- **THEN** Call 1 returns HTTP **400**
- **AND** the public lean success body is not returned

---

### Requirement: FR-PDH-004 Call 1 lean public body

Call 1 public success body SHALL be the lean FR-IX-023 envelope (`ingest_id`, `user_id`, `user_requirement_summary`, `tentative_*`, `needs_summary[]`, `expected_budget` | null, `warnings[]`). Technical chunk/KG counts MUST remain internal (session meta).

#### Scenario: Lean body fields present

- **GIVEN** a successful Call 1
- **WHEN** the client reads the 200 JSON body
- **THEN** `ingest_id` starts with `ing_`
- **AND** `user_id` echoes the request
- **AND** `user_requirement_summary` is non-empty
- **AND** public body does not require `documents[]` or `kg_*` fields

---

### Requirement: FR-PDH-005 Call 1 idempotency and correlation

Call 1 MAY accept `Idempotency-Key`. When present, successful 200 lean bodies SHALL be replayed for the same `user_id` + key (process-local store). Failed 4xx/5xx MUST NOT be cached. `X-Correlation-Id` SHALL be logged and echoed (minted if omitted).

#### Scenario: Retry same key

- **GIVEN** a successful Call 1 with `Idempotency-Key=K` for `user_id=U`
- **WHEN** the client retries Call 1 with the same `U` and `K`
- **THEN** the response is the same lean body including the same `ingest_id`
- **AND** a second logical index is not performed

---

### Requirement: FR-PDH-006 Call 2 session prerequisite

Call 2 SHALL require a prior successful Call 1 session for the same process-local `(user_id, ingest_id)` unless a future durable session path is explicitly implemented.

#### Scenario: Same-process handoff

- **GIVEN** Call 1 just succeeded on uvicorn process P
- **WHEN** Call 2 is issued to process P with that `user_id` and `ingest_id`
- **THEN** the session is found and recommend proceeds

#### Scenario: Process restart

- **GIVEN** Call 1 completed, then the process restarted (InMemory session lost)
- **WHEN** Call 2 uses the old `ingest_id`
- **THEN** the service returns HTTP **404** until re-ingest (memory DocumentStore path)

---

### Requirement: FR-PDH-007 Call 2 project knowledge before fleet

When `RECOMMEND_VIA_AGENT_GRAPH=true`, Call 2 SHALL run project tools before fleet/pricing workers:

`check_gate → project_worker → delegator → execute_needs → synthesis`.

`project_worker` SHALL use project DocumentStore + KG-1 (and need decompose). Fleet SQL and optional Neo4j SHALL run only after needs exist (and after gate pass).

#### Scenario: Agent graph order

- **GIVEN** `RECOMMEND_VIA_AGENT_GRAPH=true` and a valid session with `indexing_ok=true`
- **WHEN** Call 2 runs
- **THEN** project_vector_search and/or project_kg_query run in the project worker phase
- **AND** fleet retrieval and pricing run per need after the delegator plan
- **AND** synthesis MUST NOT invent `asset_id` or rates

#### Scenario: Gate refuse

- **GIVEN** session meta `indexing_ok=false` and agent graph enabled
- **WHEN** Call 2 runs
- **THEN** the service returns HTTP **400**
- **AND** fleet/pricing tools are not used to invent a quote

---

### Requirement: FR-PDH-008 Call 2 fleet and pricing sources

Call 2 fleet candidates SHALL come from allowlisted tools only:

| Backend | Source |
|---------|--------|
| `FLEET_BACKEND=sql` | Postgres `assets` / bookings (live; quote `equipment.id` = `assets.id`) |
| `FLEET_BACKEND=fake` | Seed catalog (CI; may use `AST-*`) |

Rates SHALL come from `pricing_client` / `predict_price` (or agent tool `predict_asset_price`). Neo4j KG-2 is optional context (`NEO4J_BACKEND=bolt`); empty/unavailable graph MUST skip Neo4j tools without inventing relationships.

#### Scenario: Live SQL identity

- **GIVEN** `FLEET_BACKEND=sql` and a matching `assets` row
- **WHEN** Call 2 returns an item
- **THEN** `items[].equipment.id` is `str(assets.id)`
- **AND** `items[].equipment.name` is `assets.name`
- **AND** `items[].mlPredictedPrice` is the predicted daily rate when the item is returned

#### Scenario: Missing assets row on SQL path

- **GIVEN** `FLEET_BACKEND=sql` and no resolvable assets row for a candidate
- **WHEN** Call 2 assembles the quote
- **THEN** that item is omitted
- **AND** a warning is included
- **AND** seed `AST-*` ids are not emitted

#### Scenario: Neo4j empty does not block quote

- **GIVEN** `NEO4J_BACKEND=bolt` but the fleet graph is empty or unavailable
- **WHEN** Call 2 agent path runs
- **THEN** Neo4j tools are skipped (K-3)
- **AND** SQL fleet + pricing may still produce a quote

---

### Requirement: FR-PDH-009 DocumentStore backends for project chunks

Project chunks SHALL be written by Call 1 via `create_session_document_store()`:

| `INDEXING_DOCUMENT_STORE` | Behaviour |
|---------------------------|-----------|
| `memory` (default) | Fresh InMemory store per ingest (process-local) |
| `pgvector` | Shared table `indexing_project_chunks`; tenant filters on `user_id` + `ingest_id` |

`PRICING_SCHEMA` MUST remap fleet/pricing SQL only; it MUST NOT remap KG-1 or pgvector.

#### Scenario: Memory default

- **GIVEN** `INDEXING_DOCUMENT_STORE=memory`
- **WHEN** Call 1 succeeds
- **THEN** project vectors are process-local
- **AND** Call 2 on another process cannot see them without re-ingest

---

### Requirement: FR-PDH-010 Neo4j populate is ops plane

Postgres → Neo4j fleet projection SHALL be performed by the **config pack** service `neo4j-populate` (SQL → Cypher MERGE), not by Call 1/2 request handlers. This app MAY enqueue populate via `trigger_neo4j_populate` (non-blocking) and MAY read via `neo4j_cypher_read` templates only.

#### Scenario: Populate not on recommend hot path

- **GIVEN** Call 2 recommend is running
- **WHEN** fleet graph is stale
- **THEN** recommend MUST NOT block on a full Neo4j rebuild
- **AND** tools may read whatever graph is already projected

---

### Requirement: FR-PDH-011 No invent

Call 1 MUST NOT invent budgets or dates when not confidently extracted. Call 2 MUST NOT invent `equipment.id`, catalog membership, or rates. Empty matches SHALL return `items: []` (or omit items) with warnings.

#### Scenario: Empty fleet match

- **GIVEN** needs that match no available catalog assets
- **WHEN** Call 2 completes
- **THEN** `items` is empty or contains no invented equipment
- **AND** `warnings` explains the soft failure
- **AND** `confidenceScore` is null when there are no items

---

## Call 1 process (detail)

### Endpoint

| Item | Value |
|------|--------|
| **Method / path** | `POST /internal/v1/recommendations/submitprojectspecification` |
| **Handler** | `app/api/recommendations.py` → `recommend_from_project_spec` |
| **Service** | `IndexingIngestService.ingest_from_project_spec` (default) |
| **Optional gate** | `INDEXING_VIA_AGENT_GATE=true` → LangGraph `START→index_gate→END` → same service |
| **Response model** | `IngestFromProjectSpecResponse` (`app/schemas/indexing.py`) |
| **Contract** | [`../indexing/contracts/ingest-from-project-spec.md`](../indexing/contracts/ingest-from-project-spec.md) |

### Headers

| Header | Required | Behaviour |
|--------|----------|-----------|
| `Content-Type` | yes | `application/json` **or** `multipart/form-data` |
| `Idempotency-Key` | no | Same `user_id` + key → replay same **200** lean body / `ingest_id` |
| `X-Correlation-Id` | no | Logged + echoed; server mints UUID if missing |
| `traceparent` | no | Optional W3C trace; logged |

### Request fields

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant; scopes session + idempotency |
| `user_name` | no | Audit only |
| `project_text` | one of text/file | Free-text brief |
| `file` | one of text/file | Multipart upload |
| `start_date` / `end_date` | no | ISO; if both set, `end >= start` |
| `include_pricing` / `options` | no | Accepted; not a budget amount |

**Source merge:** extracted **file text first**, then `project_text`. Placeholder caption `"Optional caption alongside file"` is ignored.

**Supported types:** unstructured `.txt` `.md` `.pdf` `.docx` `.html`; structured `.csv` `.json` `.xlsx`.

### Internal steps

```text
[1] HTTP accept — parse JSON/multipart; validate; optional idempotency hit
[2] Allocate ingest_id = "ing_" + uuid.hex; create_session_document_store()
[3] Package ByteStreams with meta user_id, ingest_id, optional TTL
[4] Indexing pipeline — FileTypeRouter dual-branch → convert → clean/split
    → final_doc_joiner → embed → DocumentWriter
[5] Hard checks — MIME / empty convert / zero chunks → 400
[6] Mandatory KG-1 — hard-fail on failure; artifact under KG_ARTIFACT_DIR
[7] Lean extract — summary, needs_summary, dates, expected_budget
[8] Register ProjectKnowledgeSession(user_id, ingest_id)
[9] Return lean 200 body
```

### Success body (lean FR-IX-023)

| Field | Type | Meaning |
|-------|------|---------|
| `ingest_id` | string | Handle for Call 2 / Call 3 |
| `user_id` | string | Echo |
| `user_requirement_summary` | string | Deterministic summary |
| `tentative_start_date` | date \| null | Rental start |
| `tentative_end_date` | date \| null | Rental end |
| `needs_summary[]` | array | Structured needs |
| `expected_budget` | object \| null | Extract-only when confident |
| `warnings` | string[] | Soft issues |

### Call 1 errors

| Status | When |
|--------|------|
| **400** | Missing `user_id`; empty source; bad dates; unsupported MIME; empty index; **KG fail** |
| **5xx** | Unexpected error (client MAY retry same `Idempotency-Key`) |

### Call 1 env

| Variable | Role |
|----------|------|
| `INDEXING_DOCUMENT_STORE` | `memory` \| `pgvector` |
| `INDEXING_EMBEDDER` / `INDEXING_EMBEDDING_DIM` | Embed path |
| `INDEXING_VIA_AGENT_GATE` | Direct service vs gate [4] |
| `NEED_DECOMPOSER` / `LLM_*` | `needs_summary` |
| `KG_ARTIFACT_DIR` / `KG_APPLY_TRANSFORMS` | KG-1 |
| `IDEMPOTENCY_TTL_SECONDS` | Idempotency cache TTL |

### Call 1 example

```bash
curl -sS -X POST http://localhost:8000/internal/v1/recommendations/submitprojectspecification \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: demo-call1' \
  -H 'Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000' \
  -d '{
    "user_id": "user_demo",
    "project_text": "Need a forklift and a scissors lift for indoor work ~8m. Budget SGD 15000. From 1 Sep 2026 to 30 Sep 2026."
  }'
```

---

## Call 2 process (detail)

### Endpoint

| Item | Value |
|------|--------|
| **Method / path** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Handler** | `get_asset_recommendations` |
| **Service** | `SessionRecommendService.recommend` |
| **Default path** | `RecommendationService` MVP |
| **Agent path** | `RECOMMEND_VIA_AGENT_GRAPH=true` → `run_recommend_graph` (same quote DTO) |
| **Response model** | `AssetRecommendResponse` (`app/schemas/recommend_quote.py`) |
| **Contract** | [`../recommendation-pipeline/contracts/get-asset-recommendations.md`](../recommendation-pipeline/contracts/get-asset-recommendations.md) |

### Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Same as Call 1 |
| `ingest_id` | **yes** | From Call 1 |
| `query` | no | Optional focus |
| `top_k` | no | Cap items (1–50) |

### Paths

#### MVP (`RECOMMEND_VIA_AGENT_GRAPH=false`)

```text
[1] Load session → 404 if missing
[2] Decompose needs from session text
[3] Per unit-need: fleet filter → availability → predict_price → rank
[4] Map to quote DTO; confidenceScore; return 200
```

#### Agent graph (`RECOMMEND_VIA_AGENT_GRAPH=true`)

```text
START → check_gate
      → project_worker   (project_vector_search → project_kg_query → decompose)
      → delegator
      → execute_needs    (fleet then price per need; optional neo4j_cypher_read)
      → synthesis        (no invent) → END → HTTP quote
```

### Call 2 reads

| Source | Content |
|--------|---------|
| Session DocumentStore | Project-spec vectors (Call 1) |
| KG-1 | Project graph (Call 1) |
| Postgres | Fleet tables when `FLEET_BACKEND=sql` |
| Neo4j KG-2 | Optional fleet graph when `NEO4J_BACKEND=bolt` |
| Pricing model | Daily rates |

**MUST NOT** treat pgvector as “vectorized whole Postgres DB.” pgvector holds **project chunks** only.

### Quote response (summary)

| Field | Meaning |
|-------|---------|
| `quoteRef` | Server `QUO-…` |
| `confidenceScore` | Evidence-based; null if no items |
| `items[]` | Ranked equipment lines |
| `items[].mlPredictedPrice` | Predicted daily rate |
| `items[].equipment.id` | `assets.id` (SQL) or seed id (fake) |
| `warnings` | Soft issues |

**confidenceScore weights:** 0.30 need coverage + 0.20 mean matchScore + 0.20 live digit id + 0.15 available + 0.10 priced + 0.05 dates (cap 0.99).

**matchScore weights:** 0.50 category + 0.20 height cue + 0.15 available + 0.15 priced.

### Call 2 errors

| Status | When |
|--------|------|
| **404** | Session missing |
| **400** | Validation; agent gate refuse |

### Call 2 env

| Variable | Role |
|----------|------|
| `RECOMMEND_VIA_AGENT_GRAPH` | MVP vs multi-agent |
| `FLEET_BACKEND` | `sql` \| `fake` |
| `PRICING_SCHEMA` | `public` \| `primary_snapshot` (fleet/pricing SQL only) |
| `NEO4J_BACKEND` / `NEO4J_*` | Optional KG-2 |
| `RECOMMEND_FANOUT_CAP` | Parallel needs (default 4) |

### Call 2 example

```bash
curl -sS -X POST http://localhost:8000/internal/v1/recommendations/project-knowledge/getassetrecommendations \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: demo-call2' \
  -d '{
    "user_id": "user_demo",
    "ingest_id": "ing_PASTE_FROM_CALL_1",
    "query": "Need scissors lift"
  }'
```

---

## Call 3 (orientation only)

| Item | Value |
|------|--------|
| Route | `POST .../project-knowledge/query` |
| Role | Chatbot Q&A over **project** store + KG-1 |
| Not | Quote / fleet recommend |
| Needs | Same `user_id` + `ingest_id` |
| Contract | [`../knowledge-graph/contracts/project-knowledge-query.md`](../knowledge-graph/contracts/project-knowledge-query.md) |

---

## Implementation map

| Concern | Location |
|---------|----------|
| Routes | `app/api/recommendations.py` |
| Call 1 service | `app/services/indexing.py` |
| Call 1 schemas | `app/schemas/indexing.py` |
| DocumentStore factory | `app/pipelines/indexing/document_store.py` |
| Indexing pipeline | `app/pipelines/indexing/pipeline.py` |
| KG-1 | `app/pipelines/kg/*` |
| Session registry | `app/services/project_knowledge_session.py` |
| Idempotency | `app/services/ingest_idempotency.py` |
| Call 2 session service | `app/services/session_recommend.py` |
| Call 2 MVP | `app/services/recommendations.py` |
| Call 2 agent graph | `app/agents/recommend_graph.py`, `recommend_nodes.py` |
| Fleet SQL tools | `app/agents/fleet_tools.py`, `app/repositories/fleet_repository.py` |
| Neo4j tools | `app/agents/neo4j_tools.py` |
| Quote DTO | `app/schemas/recommend_quote.py` |
| Config | `app/config.py` |

---

## Operational checklist

### Before Call 1

- [ ] API up (`uvicorn`)
- [ ] Embedder keys if not `mock`
- [ ] If `pgvector`: Postgres up + embedding dim matches column

### After Call 1

- [ ] HTTP 200 + `ingest_id`
- [ ] Session registered on same process
- [ ] Optional: KG artifact `artifacts/kg/{user_id}/kg_{ingest_id}.json`

### Before Call 2 (live quote)

- [ ] Same process as Call 1 (or durable project store)
- [ ] `FLEET_BACKEND=sql` and `postgres-haystack` has `assets`
- [ ] Optional: Neo4j populated (config pack `neo4j-populate`)
- [ ] App `NEO4J_PASSWORD` matches pack (often `heavyrental`)

### On Call 2 failure

- [ ] Retry **Call 2 only** (do not re-ingest by default)
- [ ] HTTP 404 → re-run Call 1 (session lost)

---

## Related reading

| Doc | When |
|-----|------|
| [`../../AGENTS.md`](../../AGENTS.md) | Runtime map Paths A–D |
| [`../indexing/contracts/ingest-from-project-spec.md`](../indexing/contracts/ingest-from-project-spec.md) | Call 1 fields |
| [`../recommendation-pipeline/contracts/get-asset-recommendations.md`](../recommendation-pipeline/contracts/get-asset-recommendations.md) | Call 2 quote |
| [`../../../QUICKSTART.md`](../../../QUICKSTART.md) | Smoke curls |
| [`../../../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../../../Feasibility_Study_Spring/portal-to-haystack-mapping.md) | Spring dual-hop |
| [`../../../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md`](../../../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md) | Dual-plane architecture |

---

## One-sentence summary

**Call 1** turns a project file/text into indexed project knowledge (vectors + KG-1) and a lean summary/`ingest_id`.  
**Call 2** loads that session, grounds needs in project knowledge, matches live fleet (SQL ± Neo4j), prices candidates, and returns a quote — without inventing equipment ids or rates.

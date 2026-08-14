# Call 1 & Call 2 Endpoint Process Guide

| Field | Value |
|-------|--------|
| **Status** | As-built (haystack-fast-api) |
| **Audience** | Engineers, Spring integrators, operators |
| **Date** | 2026-08-14 |
| **OpenSpec twin** | [`../openspec/specs/portal-dual-hop/spec.md`](../openspec/specs/portal-dual-hop/spec.md) |
| **Call 1 contract** | [`../openspec/specs/indexing/contracts/ingest-from-project-spec.md`](../openspec/specs/indexing/contracts/ingest-from-project-spec.md) |
| **Call 2 contract** | [`../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`](../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md) |
| **Spring mapping** | [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) |
| **Smoke curls** | [`../QUICKSTART.md`](../QUICKSTART.md) |
| **Postman** | [`../postman/README.md`](../postman/README.md) |

This document describes the **full as-built process** for:

1. **Call 1** — ingest project specification (file and/or text)  
2. **Call 2** — recommend / quote equipment for that ingest session  

Call 3 (chatbot Q&A) is noted only for orientation.

### Contents

1. [Big picture](#1-big-picture)
2. [Call 1 — Submit project specification](#2-call-1--submit-project-specification)
3. [Call 2 — Get asset recommendations (quote)](#3-call-2--get-asset-recommendations-quote)
4. [End-to-end sequence](#4-end-to-end-sequence-live-oriented-profile)
5. [Side-by-side comparison](#5-side-by-side-comparison)
6. [Call 3 (orientation only)](#6-call-3-orientation-only)
7. [Implementation map](#7-implementation-map-code)
8. [Operational checklist](#8-operational-checklist)
9. [Related reading](#9-related-reading)
10. [One-sentence summary](#10-one-sentence-summary)
11. **[Evaluation & performance tests (predicted vs actual)](#11-evaluation--performance-tests-predicted-vs-actual)** ← metrics, confidenceScore, test `.env` isolation

Jump to evaluation subsections:

- [11.1 Design principles](#111-design-principles)
- [11.2 Configuration used for these tests (`.env` vs pytest)](#112-configuration-used-for-these-tests-env-vs-pytest-isolation)
- [11.3 Call 1 metrics](#113-call-1-metrics-predicted-vs-gold)
- [11.4 Call 2 metrics](#114-call-2-metrics-predicted-vs-gold)
- [11.5 Fixtures layout & case schema](#115-fixtures-layout--case-schema)
- [11.6 CI thresholds](#116-ci-acceptance-thresholds)
- [11.7 How to run + HTML report](#117-how-to-run--html-report)
- [11.8 Sample results (scoreboard)](#118-sample-results-scoreboard)
- [11.9 Interpreting failures](#119-interpreting-failures)
- [11.10 Out of scope](#1110-out-of-scope)

---

## 1. Big picture

### 1.1 Portal dual-hop (product path)

```text
React  POST /api/recommendations/project-spec
         │
         ▼
Spring Boot (orchestrator / SoT for bookings)
         │
         ├─ Call 1  POST .../submitprojectspecification
         │            → index project + KG-1 + session
         │            → lean summary + ingest_id
         │
         ├─ persist user_id + ingest_id
         │
         └─ Call 2  POST .../project-knowledge/getassetrecommendations
                      → quote / items[]  (primary body back to React)
```

### 1.2 What each call owns

| | **Call 1 — Ingest** | **Call 2 — Recommend / quote** |
|--|---------------------|--------------------------------|
| **Route** | `POST /internal/v1/recommendations/submitprojectspecification` | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Input** | Project file and/or `project_text` + `user_id` | `user_id` + `ingest_id` from Call 1 (+ optional `query`) |
| **Output** | Lean summary + `ingest_id` | Quote envelope (`quoteRef`, `items[]`) |
| **Stores written** | DocumentStore (memory/pgvector), KG-1 JSON, session registry | None (reads only) |
| **Fleet** | Not used | Postgres SQL and/or Neo4j KG-2 |
| **Pricing** | Not used | `predict_price` / pricing client |
| **Idempotency** | Optional `Idempotency-Key` | No (do **not** re-run Call 1 on Call 2 failure) |

### 1.3 Data planes (do not mix)

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

| Store | Holds | Written by | Read by Call 2? |
|-------|--------|------------|-----------------|
| DocumentStore / pgvector | **Project-spec** embeddings only | Call 1 | Yes (`project_vector_search`) |
| KG-1 JSON | **Project** knowledge graph | Call 1 | Yes (`project_kg_query`) |
| Postgres fleet tables | Assets, bookings, categories | Spring / domain | Yes (`FLEET_BACKEND=sql`) |
| Neo4j KG-2 | Fleet graph projection | Config pack `neo4j-populate` | Optional (`NEO4J_BACKEND=bolt`) |

**Important:** pgvector does **not** store vectorized fleet rows from Postgres. It stores project-spec chunks from Call 1 only (when `INDEXING_DOCUMENT_STORE=pgvector`).

---

## 2. Call 1 — Submit project specification

### 2.1 Endpoint

| Item | Value |
|------|--------|
| **Method / path** | `POST /internal/v1/recommendations/submitprojectspecification` |
| **Handler** | `app/api/recommendations.py` → `recommend_from_project_spec` |
| **Service** | `IndexingIngestService.ingest_from_project_spec` (default) |
| **Optional gate** | `INDEXING_VIA_AGENT_GATE=true` → LangGraph `START→index_gate→END` → same service |
| **Response model** | `IngestFromProjectSpecResponse` (`app/schemas/indexing.py`) |

### 2.2 Headers

| Header | Required | Behaviour |
|--------|----------|-----------|
| `Content-Type` | yes | `application/json` **or** `multipart/form-data` |
| `Idempotency-Key` | no | Same `user_id` + key → replay same **200** lean body / `ingest_id` (process-local; TTL `IDEMPOTENCY_TTL_SECONDS`) |
| `X-Correlation-Id` | no | Logged + echoed; server mints UUID if missing |
| `traceparent` | no | Optional W3C trace; logged |

**Idempotency rules**

1. Only successful HTTP **200** lean bodies are cached.  
2. Scope = `user_id` + `Idempotency-Key`.  
3. Failed **4xx/5xx** are **not** cached.  
4. Concurrent same key uses single-flight (no double logical index).  
5. Store is **process-local** (not multi-replica shared).  
6. Clients MAY retry **5xx** / timeouts with the **same** key.

### 2.3 Request body

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant; scopes session + idempotency |
| `user_name` | no | Audit only (not on lean response) |
| `project_text` | one of text/file | Free-text project brief |
| `file` | one of text/file | Multipart upload |
| `start_date` / `end_date` | no | ISO dates; if both set, `end >= start` |
| `include_pricing` / `options` | no | Accepted; **not** a budget amount |

**Source merge rule:** extracted **file text first**, then `project_text`. Placeholder caption `"Optional caption alongside file"` is ignored.

**Supported file types**

| Kind | Extensions |
|------|------------|
| Unstructured | `.txt` `.md` `.pdf` `.docx` `.html` |
| Structured | `.csv` `.json` `.xlsx` |

### 2.4 Step-by-step process (internal)

```text
[1] HTTP accept
    • Parse JSON or multipart
    • Validate user_id, non-empty source, date window
    • Optional Idempotency-Key lookup → maybe return cached lean body

[2] Allocate session identity
    • ingest_id = "ing_" + uuid.hex
    • create_session_document_store()
        INDEXING_DOCUMENT_STORE=memory  → fresh InMemoryDocumentStore
        INDEXING_DOCUMENT_STORE=pgvector → shared table indexing_project_chunks
    • Stamp meta: user_id, ingest_id, optional user_name, expires_at (TTL)

[3] Package sources
    • File → Haystack ByteStream (MIME from filename)
    • project_text → text/plain ByteStream
    • Meta stamped on each stream

[4] Indexing pipeline (Haystack dual-branch)
    FileTypeRouter by MIME
      Branch A (unstructured): convert → clean → split → embed → DocumentWriter
      Branch B (structured):   convert → (path) → embed → DocumentWriter
    final_doc_joiner merges post-split docs for KG input
    Embedder: INDEXING_EMBEDDER (mock | openai | sentence-transformers)
    Dim: INDEXING_EMBEDDING_DIM (must match pgvector column if used)

[5] Hard checks
    • Unsupported MIME → 400
    • No documents after convert → 400
    • Zero chunks / zero writes → 400

[6] Mandatory KG-1 (hard-fail on failure)
    • Input: post-joiner documents
    • KnowledgeGraphGenerator
        KG_APPLY_TRANSFORMS=false → document nodes only
        true → full Ragas transforms (LLM cost)
    • Save: {KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json
    • Failure → 400 (request fails; no silent skip)

[7] Lean summary extraction (public response)
    • user_requirement_summary from file extract + project_text
    • needs_summary[] via NEED_DECOMPOSER (stub | llm)
    • tentative_start/end: request dates preferred, else free-text extract
    • expected_budget: extract only when confident (never invent)

[8] Register ProjectKnowledgeSession
    Key: (user_id, ingest_id)
    Holds: document store handle, KG path/object, meta
      (summary, needs, dates, indexing_ok, kg_*, …)
    Process-local registry (lost on uvicorn restart unless durable store + reload)

[9] Return lean 200 body
    Technical chunk/KG counts stay internal (session meta only)
```

### 2.5 Success response (lean FR-IX-023)

| Field | Type | Meaning |
|-------|------|---------|
| `ingest_id` | string | Handle for Call 2 / Call 3 (`ing_` + hex) |
| `user_id` | string | Echo |
| `user_requirement_summary` | string | Deterministic summary of brief |
| `tentative_start_date` | date \| null | Rental start |
| `tentative_end_date` | date \| null | Rental end |
| `needs_summary[]` | array | Structured equipment needs |
| `needs_summary[].need_id` | string \| null | e.g. `need_1` |
| `needs_summary[].description` | string | Human need text |
| `needs_summary[].equipment_hints` | string[] | Category/type hints |
| `needs_summary[].quantity` | int \| null | When known |
| `expected_budget` | object \| null | `{amount, currency, source}` if extracted |
| `warnings` | string[] | Soft issues |

**Example**

```json
{
  "ingest_id": "ing_a1b2c3d4e5f6…",
  "user_id": "user_demo",
  "user_requirement_summary": "Need a forklift and a scissors lift…",
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-30",
  "needs_summary": [
    {
      "need_id": "need_1",
      "description": "Need a forklift",
      "equipment_hints": ["forklift"],
      "quantity": 1
    },
    {
      "need_id": "need_2",
      "description": "Need a scissors lift for indoor work ~8m",
      "equipment_hints": ["scissor lift"],
      "quantity": 1
    }
  ],
  "expected_budget": {
    "amount": 15000,
    "currency": "SGD",
    "source": "extracted"
  },
  "warnings": []
}
```

**Not on public body (still executed internally)**

| Concern | Where |
|---------|--------|
| Chunk previews, counts, MIME/filenames | Indexing pipeline + session `meta` |
| `kg_built`, node/rel counts, artifact path | KG runner + session registry |
| Session DocumentStore + KG object | `ProjectKnowledgeSession` for Call 2 |

### 2.6 Errors (Call 1)

| Status | When |
|--------|------|
| **400** | Missing `user_id`; empty source; bad dates; unsupported MIME; convert/index empty; **KG fail** |
| **5xx** | Unexpected server error (client may retry **same** `Idempotency-Key`) |

### 2.7 Env that shapes Call 1

| Variable | Role |
|----------|------|
| `INDEXING_DOCUMENT_STORE` | `memory` (default) \| `pgvector` |
| `INDEXING_EMBEDDER` / `INDEXING_EMBEDDING_DIM` | How chunks are embedded |
| `INDEXING_VIA_AGENT_GATE` | false = direct service; true = gate [4] |
| `NEED_DECOMPOSER` / `LLM_*` | How `needs_summary` is built |
| `KG_ARTIFACT_DIR` / `KG_APPLY_TRANSFORMS` | KG-1 path + transform depth |
| `IDEMPOTENCY_TTL_SECONDS` | Cache TTL for Idempotency-Key |
| `POSTGRES_*` | Required for **pgvector** path (and unrelated fleet later) |

### 2.8 Curl example

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

**Multipart (file) sketch**

```bash
curl -sS -X POST http://localhost:8000/internal/v1/recommendations/submitprojectspecification \
  -H 'X-Correlation-Id: demo-call1-file' \
  -F 'user_id=user_demo' \
  -F 'file=@postman/fixtures/project.txt;type=text/plain'
```

---

## 3. Call 2 — Get asset recommendations (quote)

### 3.1 Endpoint

| Item | Value |
|------|--------|
| **Method / path** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Handler** | `get_asset_recommendations` |
| **Service** | `SessionRecommendService.recommend` |
| **Default path** | `RecommendationService` MVP (fleet filter → availability → price → rank) |
| **Agent path** | `RECOMMEND_VIA_AGENT_GRAPH=true` → `run_recommend_graph` (same quote DTO) |
| **Response model** | `AssetRecommendResponse` (`app/schemas/recommend_quote.py`) |

### 3.2 Prerequisite

Successful **Call 1** on the **same process** for the same `(user_id, ingest_id)`.

| Situation | Result |
|-----------|--------|
| Session missing | **404** |
| Agent graph + `indexing_ok=false` | **400** (gate refuse) |
| Uvicorn restarted (memory sessions) | Call 2 **404** until re-ingest |

### 3.3 Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Same as Call 1 |
| `ingest_id` | **yes** | From Call 1 |
| `query` | no | Optional focus text |
| `top_k` | no | Cap on returned items (1–50) |

Headers: optional `X-Correlation-Id`, `traceparent`. **No** `Idempotency-Key` on Call 2.

### 3.4 Step-by-step process

#### A) Common entry

```text
[1] Load ProjectKnowledgeSession(user_id, ingest_id)
    • Not found → 404
[2] Branch on RECOMMEND_VIA_AGENT_GRAPH
```

#### B) Default MVP path (`RECOMMEND_VIA_AGENT_GRAPH=false`)

```text
[3] Need decomposition from session summary / text
[4] For each unit-need:
      • Filter fleet candidates
          FLEET_BACKEND=sql  → LiveSqlFleetBackend (assets table)
          FLEET_BACKEND=fake → seed catalog (CI)
      • Filter by booking availability window
      • predict_price (ML) for candidates
      • Rank + rationale
[5] Map to quote DTO
      equipment.id   = str(assets.id) when SQL
      equipment.name = assets.name
      mlPredictedPrice = predicted daily rate
[6] confidenceScore from evidence weights
[7] Return AssetRecommendResponse
```

#### C) Agent graph path (`RECOMMEND_VIA_AGENT_GRAPH=true`)

```text
START
  │
  ▼
check_gate
  • indexing_ok from session meta
  • false → synthesis refuse → 400
  │
  ▼
project_worker   ← PROJECT KNOWLEDGE FIRST
  1) project_vector_search  → Call 1 chunks (memory or pgvector)
  2) project_kg_query       → Call 1 KG-1
  3) decompose_project_needs → unit needs[]
  │
  ▼
delegator
  • Build work_plan per need
  • Fleet tools + optional neo4j_cypher_read
  • Pricing tools if include_pricing
  • Skip Neo4j if empty/unavailable (K-3)
  │
  ▼
execute_needs   (fan-out, RECOMMEND_FANOUT_CAP)
  Per need, must-seq:
    [6] fleet_worker
          retrieve_fleet_assets  → Postgres SQL (primary)
          neo4j_cypher_read      → Neo4j templates (optional context)
    [7] pricing_worker
          predict_asset_price    → ML model
  │
  ▼
synthesis [8]
  • Merge tool outputs only
  • NEVER invent asset_id or rates
  • Map results_by_need → quote items[]
  │
  ▼
END → HTTP 200 quote (tool_traces stay internal, not on HTTP body)
```

### 3.5 What Call 2 reads (and does not)

| Source | Content | When |
|--------|---------|------|
| Session DocumentStore | **Project-spec** vectors | Always (if session alive) |
| KG-1 artifact | **Project** graph | Agent path / tools |
| Postgres `assets` / bookings | **Fleet** | `FLEET_BACKEND=sql` |
| Neo4j KG-2 | **Fleet** graph projection | `NEO4J_BACKEND=bolt` + graph populated |
| Pricing model | Daily rates | Pricing worker / MVP price step |

**Incorrect model:** Call 2 reads pgvector that contains the whole Postgres DB + Neo4j.  
**Correct model:** project knowledge from Call 1 first; fleet from live SQL; Neo4j optional fleet graph.

### 3.6 Success response (quote)

| Field | Meaning |
|-------|---------|
| `user_id`, `ingest_id`, `query` | Echo |
| `quoteRef` | Server `QUO-…` (Spring may overwrite commercially) |
| `confidenceScore` | Evidence score (null if no items) |
| `days` | From session tentative dates |
| `estimatedTotal` | Sum of line totals when priced |
| `specSummary` | Call 1 `user_requirement_summary` |
| `rationale` | Joined item reasons |
| `items[]` | Ranked equipment lines |
| `items[].matchScore` | Category / height / available / priced signals |
| `items[].reason` | Factual sentence |
| `items[].mlPredictedPrice` | Predicted **daily** rate |
| `items[].equipment.*` | See table below |
| `warnings` | Soft issues / no-match |
| `recommendationId` | Optional rec id |

**`equipment` fields (live SQL)**

| Field | Source |
|-------|--------|
| `id` | `assets.id` (string) |
| `name` | `assets.name` |
| `category` | category name |
| `baseDailyRate` | same as `mlPredictedPrice` |
| `capacity`, `purchaseYear`, `location`, `desc` | assets columns |
| `available` | booking overlap / live-hold |
| `platformHeight` | only Scissors / Boom Lift |
| `tags` | often `[]` |

**Safeguards**

- Do not invent `equipment.id` or rates  
- Missing assets row on SQL path → **omit item + warning** (never emit seed `AST-*`)  
- Empty match → `items: []` + warning  
- No chatbot `answer` on this route (that is Call 3)

### 3.7 Confidence & match scores

**confidenceScore** (quote-level, cap 0.99):

| Weight | Signal |
|--------|--------|
| 0.30 | Need coverage (items / needs) |
| 0.20 | Mean `matchScore` |
| 0.20 | Live digit `equipment.id` (`assets.id`) |
| 0.15 | `available is True` |
| 0.10 | `mlPredictedPrice > 0` |
| 0.05 | Both rental dates known |

**matchScore** (item-level): 0.50 category + 0.20 height cue + 0.15 available + 0.15 priced.

### 3.8 Errors (Call 2)

| Status | When |
|--------|------|
| **404** | No session for `(user_id, ingest_id)` |
| **400** | Validation; agent gate refuse (`indexing_ok=false`) |

### 3.9 Env that shapes Call 2

| Variable | Role |
|----------|------|
| `RECOMMEND_VIA_AGENT_GRAPH` | false = MVP service; **true** = multi-agent graph |
| `FLEET_BACKEND` | `sql` live assets \| `fake` seed |
| `PRICING_SCHEMA` | `public` \| `primary_snapshot` (fleet/pricing SQL only) |
| `NEO4J_BACKEND` | `bolt` \| `fake` |
| `NEO4J_URI` / `USER` / `PASSWORD` | Bolt (pack default password often `heavyrental`) |
| `NEO4J_POPULATE_URL` | Ops trigger only; not required mid-quote |
| `RECOMMEND_FANOUT_CAP` | Parallel needs (default 4) |
| `INDEXING_DOCUMENT_STORE` | Where project vectors live for project_worker |

### 3.10 Curl example

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

## 4. End-to-end sequence (live-oriented profile)

Typical live flags:

- `NEED_DECOMPOSER=llm`
- `INDEXING_EMBEDDER=openai` (or ST)
- `FLEET_BACKEND=sql`
- `NEO4J_BACKEND=bolt`
- `RECOMMEND_VIA_AGENT_GRAPH=true`
- `INDEXING_DOCUMENT_STORE=memory` or `pgvector`

```text
Client/Spring
    │
    │  Call 1
    ▼
FastAPI submitprojectspecification
    │  embed + write DocumentStore (project only)
    │  build KG-1 → artifacts/kg/...
    │  register session(user_id, ingest_id)
    │  return lean summary + ingest_id
    │
    │  Call 2 (same process)
    ▼
FastAPI getassetrecommendations
    │  load session
    │  project_worker: vector + KG-1 + needs
    │  fleet SQL ← postgres-haystack.assets
    │  neo4j templates ← KG-2 (if populated)
    │  predict_price
    │  synthesize quote
    ▼
200 { quoteRef, items[], confidenceScore, … }
```

### Ops plane for Neo4j (outside Call 1/2 request body)

```text
postgres-haystack fleet tables
    → neo4j-populate (POST /v1/populate or post-sync)
    → Neo4j :Asset / :Booking / :Category (+ IN_CATEGORY, FOR_ASSET)
```

- Implemented in the **config pack**, not in this app’s request handlers.  
- App may `POST` `NEO4J_POPULATE_URL` via `trigger_neo4j_populate` (non-blocking).  
- If Neo4j is empty, Call 2 still quotes from **SQL**; graph tools are skipped.

**Pack table-name note:** populate defaults to singular SQL names `asset`, `booking`, `category`. Live Spring tables are often plural (`assets`, `bookings`, `asset_categories`). Compatibility views or `FLEET_TABLE_ALLOWLIST` alignment may be required for `tables_ok > 0`.

---

## 5. Side-by-side comparison

| Topic | Call 1 | Call 2 |
|-------|--------|--------|
| Purpose | Ingest + summarize project | Recommend equipment quote |
| Writes vectors | Yes (project chunks) | No |
| Writes KG-1 | Yes (mandatory) | No (reads) |
| Reads Postgres fleet | No | Yes (`FLEET_BACKEND=sql`) |
| Reads Neo4j | No | Optional (KG-2) |
| Pricing | No | Yes |
| Public body | Lean summary | Commercial quote |
| Session | Creates | Requires |
| Retry key | `Idempotency-Key` | N/A — retry Call 2 only |

---

## 6. Call 3 (orientation only)

| Item | Value |
|------|--------|
| Route | `POST /internal/v1/recommendations/project-knowledge/query` |
| Role | Chatbot Q&A over **project** store + KG-1 |
| Not | Quote / fleet recommend |
| Needs | Same `user_id` + `ingest_id` |
| Contract | [`../openspec/specs/knowledge-graph/contracts/project-knowledge-query.md`](../openspec/specs/knowledge-graph/contracts/project-knowledge-query.md) |

---

## 7. Implementation map (code)

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
| Call 2 MVP recommend | `app/services/recommendations.py` |
| Call 2 agent graph | `app/agents/recommend_graph.py`, `recommend_nodes.py` |
| Fleet SQL tools | `app/agents/fleet_tools.py`, `app/repositories/fleet_repository.py` |
| Neo4j tools | `app/agents/neo4j_tools.py` |
| Quote DTO | `app/schemas/recommend_quote.py` |
| Config | `app/config.py`, `.env` |

---

## 8. Operational checklist

### Before Call 1

- [ ] API up (`uvicorn`)
- [ ] Embedder keys if not `mock`
- [ ] If `pgvector`: Postgres up + embedding dim matches column

### After Call 1

- [ ] HTTP `200` + `ingest_id`
- [ ] Session registered (same process)
- [ ] Optional: `artifacts/kg/{user_id}/kg_{ingest_id}.json` exists

### Before Call 2 (live quote)

- [ ] Same process as Call 1 (or durable project store)
- [ ] `FLEET_BACKEND=sql` + `postgres-haystack` has `assets`
- [ ] Optional: Neo4j populated (`GET http://neo4j-populate:8089/v1/status` → `tables_ok > 0`)
- [ ] App `NEO4J_PASSWORD` matches pack (often `heavyrental`, not `neo4j`)

### On Call 2 failure

- [ ] Retry **Call 2 only** — do **not** re-ingest unless product policy says so  
- [ ] `404` → Call 1 session lost; re-run Call 1

### Trigger Neo4j populate (ops)

```bash
curl -sS -X POST http://neo4j-populate:8089/v1/populate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"merge"}'

curl -sS http://neo4j-populate:8089/v1/status
```

---

## 9. Related reading

| Doc | When |
|-----|------|
| [`../openspec/specs/portal-dual-hop/spec.md`](../openspec/specs/portal-dual-hop/spec.md) | OpenSpec FR-PDH requirements + scenarios |
| [`../openspec/AGENTS.md`](../openspec/AGENTS.md) | Runtime map Paths A–D |
| [`../openspec/specs/indexing/contracts/ingest-from-project-spec.md`](../openspec/specs/indexing/contracts/ingest-from-project-spec.md) | Call 1 fields |
| [`../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`](../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md) | Call 2 quote + identity |
| [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) | Spring dual-hop |
| [`../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md`](../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md) | Dual-plane architecture |
| [`../QUICKSTART.md`](../QUICKSTART.md) | Fast smoke |
| [`../postman/README.md`](../postman/README.md) | Full collection |
| [`testing/recommendation-pipeline-testing-guide.md`](./testing/recommendation-pipeline-testing-guide.md) | Pipeline tests |
| §11 below | Evaluation metrics, fixtures, scoreboard, HTML report, **test `.env` isolation** |
| [`eval/call1-call2-eval-results.md`](./eval/call1-call2-eval-results.md) | **Committed** scoreboard snapshot |
| [`eval/call1-call2-test-data-and-predictions.json`](./eval/call1-call2-test-data-and-predictions.json) | Inputs + gold + predicted Call 1/2 |
| [`eval/README.md`](./eval/README.md) | Eval docs index + export command |
| [`../tests/fixtures/eval/README.md`](../tests/fixtures/eval/README.md) | Eval fixture seed / regenerate notes |
| [`multi-agent-architecture.md`](./multi-agent-architecture.md) | Multi-agent graphs (gate, Call 3, Call 2 C/W/D) |
| [`README.md`](./README.md) | Docs index |
| [`integrations/spring-boot-api-contract.md`](./integrations/spring-boot-api-contract.md) | Spring wire notes |

---

## 10. One-sentence summary

**Call 1** turns a project file/text into indexed project knowledge (vectors + KG-1) and a lean summary/`ingest_id`.  
**Call 2** loads that session, grounds needs in project knowledge, matches live fleet (SQL ± Neo4j), prices candidates, and returns a quote — without inventing equipment ids or rates.

---

## 11. Evaluation & performance tests (predicted vs actual)

This section defines how to **measure recommender quality** for Call 1 and Call 2: compare **system outputs (predicted)** to **labeled expected outcomes (actual/gold)** using **`confidenceScore`**, **`matchScore`**, and supporting offline metrics.

| Artifact | Path |
|----------|------|
| **Committed results (static)** | [`eval/call1-call2-eval-results.md`](./eval/call1-call2-eval-results.md) · [`eval/call1-call2-eval-results.json`](./eval/call1-call2-eval-results.json) |
| **Test data + predictions export** | [`eval/call1-call2-test-data-and-predictions.json`](./eval/call1-call2-test-data-and-predictions.json) · [`eval/call1-call2-test-data.md`](./eval/call1-call2-test-data.md) · [`eval/test-data/`](./eval/test-data/) |
| **Export script** | `scripts/export_eval_test_data.py` |
| Metrics helpers | `tests/eval/metrics.py` |
| Seeded case pack | `tests/fixtures/eval/call1_call2_cases.json` (`eval_seed: 42`) |
| Eval fleet | `tests/fixtures/eval/eval_fleet.json` |
| Fixture notes | `tests/fixtures/eval/README.md` |
| Unit metric tests | `tests/test_eval_metrics.py` |
| Pack runner | `tests/test_call1_call2_eval_pack.py` |
| Confidence formula unit tests | `tests/test_confidence_score.py` |
| HTML report (local) | `reports/pytest-report.html` (gitignored) |

### 11.1 Design principles

1. **Deterministic “random” data** — synthetic cases are generated/committed with fixed `EVAL_SEED=42`. Pytest does **not** re-sample randomly each run.
2. **Labeled gold** — every case has `call1_expected` and `call2_expected`.
3. **CI-safe** — default pack uses mock embedder, stub/fixed need decomposer for Call 2, fake fleet, fixed price adapter (`daily_rate=185`). No live LLM or Neo4j required.
4. **No invent** — empty matches → `items: []` and `confidenceScore: null` are valid; inventing budget when gold is null fails the case.
5. **Call 1 has no `confidenceScore`** — Call 1 uses need/date/budget metrics; Call 2 uses confidence + ranking metrics.

### 11.2 Configuration used for these tests (`.env` vs pytest isolation)

Evaluation tests **do not rely on your live host `.env` for fleet/LLM/Neo4j**.  
`tests/conftest.py` **autouse** forces CI-safe values so a live compose profile cannot break the pack:

| Variable | Forced by `tests/conftest.py` | Why for eval |
|----------|-------------------------------|--------------|
| `INDEXING_EMBEDDER` | `mock` | No OpenAI/network; stable chunks |
| `INDEXING_EMBEDDING_DIM` | `384` | Matches mock embedder |
| `INDEXING_DOCUMENT_STORE` | `memory` | No Postgres/pgvector required |
| `NEED_DECOMPOSER` | `stub` | Call 1 need extract without LLM |
| `FLEET_BACKEND` | `fake` | Seed/injected fleet (pack injects `eval_fleet.json`) |
| `PRICING_SCHEMA` | `primary_snapshot` | Unused on fake path; avoids public remap |
| `NEO4J_BACKEND` | `fake` | Pack does not need live KG-2 |
| `RECOMMEND_VIA_AGENT_GRAPH` | `false` | **MVP** Call 2 path for pack stability |
| `PROJECT_AGENT_MODE` | `stub` | Call 3 not under test |
| `KG_ARTIFACT_DIR` | temp dir per test | Keeps KG writes out of repo tree |

**Also forced at pack runtime (code, not `.env`):**

| Setting | Value in eval pack |
|---------|-------------------|
| Call 2 path | `SessionRecommendService(via_agent_graph=False)` |
| Fleet assets/bookings | `tests/fixtures/eval/eval_fleet.json` via `AssetCandidateFilter` / `BookingAvailabilityFilter` |
| Call 2 needs | Injected `_FixedDecomposer` from case `gold_by_need` (decouples LLM) |
| Prices | `_FixedPriceAdapter(daily_rate=185.0)` for MAPE ≈ 0 |
| Session meta `needs_summary` | Aligned to gold need count so `confidenceScore` need_count matches formula |

**Live `.env` profile (not used by default eval pack)** — example of what operators use for manual dual-hop, for contrast only:

```env
# Live-oriented example (manual smoke / compose) — NOT what pytest eval forces
NEED_DECOMPOSER=llm
LLM_BASE_URL=https://inference.do-ai.run/v1
LLM_API_KEY=...
LLM_MODEL=router:heavy-rental
INDEXING_EMBEDDER=openai
INDEXING_EMBEDDING_DIM=384
INDEXING_DOCUMENT_STORE=memory   # or pgvector when durable chunks are required
INDEXING_VIA_AGENT_GATE=false
FLEET_BACKEND=sql
PRICING_SCHEMA=public
NEO4J_BACKEND=bolt
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=heavyrental
NEO4J_POPULATE_URL=http://neo4j-populate:8089/v1/populate
RECOMMEND_VIA_AGENT_GRAPH=true
KG_APPLY_TRANSFORMS=false
KG_ARTIFACT_DIR=artifacts/kg
```

| Concern | Eval pack (pytest) | Live `.env` example |
|---------|--------------------|---------------------|
| Embeddings | mock | openai / ST |
| DocumentStore | memory | memory or pgvector |
| Needs | stub + fixed Call 2 decomposer | llm |
| Fleet | fake + `eval_fleet.json` | sql → Postgres `assets` |
| Neo4j | fake (unused) | bolt + populate |
| Call 2 graph | off (MVP) | often `true` |
| Prices | fixed 185 fixture | `predict_price` model |

Optional future live eval (not default CI): set `RUN_EVAL_LIVE=1` and relax conftest only in a marked suite — **not implemented** in the default pack.

### 11.3 Call 1 metrics (predicted vs gold)

| Predicted (system) | Expected (label) | Metric |
|--------------------|------------------|--------|
| `needs_summary` hints/descriptions | `call1_expected.equipment_types` | **Need type Precision / Recall / F1** (canonical categories) |
| `tentative_start_date` / `end_date` | gold dates or null | **Date exact-match** |
| `expected_budget.amount` | gold amount or null | **Budget match**; **invent rate** when gold is null |
| `user_requirement_summary` | non-empty brief | **Summary completeness** |
| HTTP success + `ingest_id` | success | **Ingest success rate** |

Helpers: `need_set_prf`, `date_exact_match`, `budget_match` in `tests/eval/metrics.py`.

### 11.4 Call 2 metrics (predicted vs gold)

| Predicted (system) | Expected (label) | Metric |
|--------------------|------------------|--------|
| Top / listed `equipment.id` or category | `gold_asset_ids` / `gold_categories` | **Hit@1** (and Hit@k over returned items) |
| Ordered items | graded relevance (id=1.0, category=0.5) | **nDCG@k** |
| `len(items)` vs need count | `need_count` | **Coverage** |
| `matchScore` | — | **Mean matchScore** (internal quality signal) |
| `confidenceScore` | formula + band | **Consistency** vs recomputed formula; **confidence_min** band |
| `mlPredictedPrice` | `price_daily` in gold | **MAPE** (≈ 0 with fixed price adapter) |
| Empty items on no-match | `expect_empty_items: true` | items empty + confidence **null** |

#### `confidenceScore` formula (as-built)

From `compute_confidence_score` in `app/services/session_recommend.py` (cap **0.99**):

| Weight | Signal |
|--------|--------|
| 0.30 | Need coverage (`\|items\| / need_count`) |
| 0.20 | Mean item `matchScore` |
| 0.20 | Live digit `equipment.id` (`assets.id` on SQL path; seed `AST-*` scores 0 here) |
| 0.15 | `equipment.available is True` |
| 0.10 | `mlPredictedPrice > 0` |
| 0.05 | Both rental dates known |

**Eval checks:**

1. **Consistency** — recompute from returned items + session need_count/dates; must equal `quote.confidenceScore`.
2. **Band** — happy cases assert `confidence >= confidence_min` (typically 0.50–0.55).
3. **Calibration-lite** — pack report bins confidence (`none` / `low` / `medium` / `high`) and Hit@1 rate per bin; high bin must not underperform empty/none on this synthetic pack.

### 11.5 Fixtures layout & case schema

Canonical fixture notes also live in [`../tests/fixtures/eval/README.md`](../tests/fixtures/eval/README.md).

#### Directory map

| Field | Value |
|-------|--------|
| **Seed** | `EVAL_SEED=42` (deterministic pack; **not** re-randomized each pytest run) |
| **Cases** | [`tests/fixtures/eval/call1_call2_cases.json`](../tests/fixtures/eval/call1_call2_cases.json) |
| **Fleet** | [`tests/fixtures/eval/eval_fleet.json`](../tests/fixtures/eval/eval_fleet.json) — extends recommend seed with Boom / Fork for pack coverage |
| **Runner** | [`tests/test_call1_call2_eval_pack.py`](../tests/test_call1_call2_eval_pack.py) |
| **Metrics** | [`tests/eval/metrics.py`](../tests/eval/metrics.py) |
| **Fixture README** | [`tests/fixtures/eval/README.md`](../tests/fixtures/eval/README.md) |
| **This section** | `docs/call1-call2-endpoint-process.md` §11 |

#### Eval fleet inventory (`eval_fleet.json`)

| asset_id | equipment_type | Notes |
|----------|----------------|--------|
| `AST-SL-001` | Scissors Lift | platform_height 10 m |
| `AST-SL-002` | Scissors Lift | platform_height 12 m |
| `AST-EX-001` | Excavator | preferred when EX-002 booked |
| `AST-EX-002` | Excavator | booked 2026-09-01..2026-09-30 in fixture |
| `AST-FL-001` | Fork Lift | pack-only vs default seed |
| `AST-BL-001` | Boom Lift | pack-only vs default seed |

#### What each case contains

| Field | Role |
|-------|------|
| `case_id` | Stable id (parametrized pytest name) |
| `kind` | `happy` or `no_match` (macro gates split on this) |
| `project_text` | Synthetic brief fed to Call 1 |
| `call1_expected` | Gold equipment types, dates, budget (or null + `must_not_invent_budget`) |
| `call2_expected` | Gold asset ids / categories, `confidence_min`, `hit_at_1_required`, optional `expect_empty_items` |
| `call2_expected.gold_by_need[]` | Injected Call 2 needs (`need_id`, hints, `price_daily`, optional `prefer_not_asset_ids`) |

#### Case schema example

```json
{
  "case_id": "happy_scissors",
  "kind": "happy",
  "project_text": "Need one scissors lift … Budget SGD 12000.",
  "call1_expected": {
    "equipment_types": ["scissor lift"],
    "start_date": "2026-09-01",
    "end_date": "2026-09-14",
    "budget_amount": 12000,
    "budget_currency": "SGD",
    "must_not_invent_budget": false
  },
  "call2_expected": {
    "need_count": 1,
    "gold_by_need": [
      {
        "need_id": "need_1",
        "equipment_hints": ["scissor lift"],
        "gold_asset_ids": ["AST-SL-001", "AST-SL-002"],
        "gold_categories": ["Scissors Lift"],
        "price_daily": 185.0
      }
    ],
    "confidence_min": 0.55,
    "hit_at_1_required": true,
    "expect_empty_items": false
  }
}
```

#### Pack case catalog (12 cases)

| case_id | kind | What it stresses |
|---------|------|------------------|
| `happy_scissors` | happy | Single scissors + dates + budget |
| `happy_excavator` | happy | Single excavator |
| `happy_forklift` | happy | Fork Lift (eval fleet only) |
| `happy_boom` | happy | Boom Lift (eval fleet only) |
| `multi_scissors_excavator` | happy | Two needs, two items |
| `multi_fork_boom` | happy | Fork + boom multi-need |
| `no_dates_scissors` | happy | Missing rental dates (lower confidence band ok) |
| `no_budget_forklift` | happy | Budget null + `must_not_invent_budget` |
| `excavator_prefers_available` | happy | Avoid booked `AST-EX-002` |
| `happy_scissors_short_window` | happy | Short date window |
| `no_match_submarine` | no_match | Empty items + null confidence |
| `no_match_helicopter` | no_match | Empty items (avoid catalog keyword traps like `aerial`) |

#### Regenerating fixtures

- Edit `call1_call2_cases.json` / `eval_fleet.json` by hand, **or** re-run a local generator with a **fixed seed**.
- **Commit** the JSON so CI stays reproducible.
- Do **not** regenerate randomly inside default pytest (pack must be stable).

### 11.6 CI acceptance thresholds

| Metric | Happy cases | No-match cases |
|--------|-------------|----------------|
| Ingest success | 100% | 100% |
| Need type F1 (macro) | ≥ **0.85** | n/a |
| Budget invent (when forbidden) | **0** | **0** |
| Hit@1 rate | ≥ **0.85** | empty items |
| Confidence consistency | **100%** | null confidence |
| Mean confidence | ≥ **0.50** | null |
| Price MAPE (fixture rates) | ≤ **0.01** | n/a |

Constants live in `tests/test_call1_call2_eval_pack.py` (`HAPPY_NEED_F1_MIN`, etc.).

### 11.7 How to run + HTML report

```bash
cd haystack-fast-api
uv sync --group dev   # includes pytest-html

# Metrics unit tests
uv run pytest tests/test_eval_metrics.py -v

# Confidence formula + quote recompute
uv run pytest tests/test_confidence_score.py -v

# Full seeded Call 1 → Call 2 eval pack (per-case + macro gates)
uv run pytest tests/test_call1_call2_eval_pack.py -v

# All evaluation-related tests (28 cases as of 2026-08-14)
uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q
```

#### HTML report (pytest-html)

The suite is configured in `pyproject.toml` → `[tool.pytest.ini_options] addopts` to always write a **self-contained** HTML report:

| Item | Value |
|------|--------|
| Plugin | `pytest-html` (dev dependency group) |
| Default path | **`reports/pytest-report.html`** |
| Style | `--self-contained-html` (CSS/JS embedded; one file to open in a browser) |
| Git | `reports/` is **gitignored** — regenerate locally or attach as CI artifact |

```bash
# Any pytest run regenerates the report
uv run pytest tests/ -q
# open: reports/pytest-report.html

# Eval pack only → same default report path (overwritten each run)
uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q

# Custom report path
uv run pytest tests/ -q --html=reports/eval-only.html --self-contained-html

# Disable HTML for one run
uv run pytest tests/ -q -p no:html -o addopts=
```

### 11.8 Sample results (scoreboard)

**Committed static artifacts (open without re-running pytest):**

- Scoreboard markdown: [`eval/call1-call2-eval-results.md`](./eval/call1-call2-eval-results.md)
- Metrics JSON: [`eval/call1-call2-eval-results.json`](./eval/call1-call2-eval-results.json)
- **Full test data + predictions:** [`eval/call1-call2-test-data-and-predictions.json`](./eval/call1-call2-test-data-and-predictions.json)
- Case index: [`eval/call1-call2-test-data.md`](./eval/call1-call2-test-data.md)
- Fixture copies: [`eval/test-data/`](./eval/test-data/)

Refresh export:

```bash
uv run python scripts/export_eval_test_data.py
```

Also available after a local run:

1. **pytest** pass/fail  
2. **`reports/pytest-report.html`** (pytest-html; gitignored)

**Latest committed snapshot (2026-08-14T02:28:12Z, eval pack isolation):**  
`28 passed` for `test_eval_metrics` + `test_confidence_score` + `test_call1_call2_eval_pack`.

| case_id | kind | need F1 | Hit@1 | coverage | confidence | nDCG | MAPE | items |
|---------|------|---------|-------|----------|------------|------|------|-------|
| happy_scissors | happy | 1.00 | 1.00 | 1.00 | **0.80** | 1.00 | 0 | 1 |
| happy_excavator | happy | 1.00 | 1.00 | 1.00 | **0.76** | 1.00 | 0 | 1 |
| happy_forklift | happy | 1.00 | 1.00 | 1.00 | **0.76** | 1.00 | 0 | 1 |
| happy_boom | happy | 0.67 | 1.00 | 1.00 | **0.76** | 1.00 | 0 | 1 |
| multi_scissors_excavator | happy | 1.00 | 1.00 | 1.00 | **0.78** | 0.82 | 0 | 2 |
| multi_fork_boom | happy | 1.00 | 1.00 | 1.00 | **0.76** | 0.82 | 0 | 2 |
| no_dates_scissors | happy | 1.00 | 1.00 | 1.00 | **0.71** | 1.00 | 0 | 1 |
| no_budget_forklift | happy | 1.00 | 1.00 | 1.00 | **0.76** | 1.00 | 0 | 1 |
| excavator_prefers_available | happy | 1.00 | 1.00 | 1.00 | **0.76** | 1.00 | 0 | 1 |
| happy_scissors_short_window | happy | 1.00 | 1.00 | 1.00 | **0.80** | 1.00 | 0 | 1 |
| no_match_submarine | no_match | 1.00 | n/a* | 0 | **null** | 1.00* | n/a | 0 |
| no_match_helicopter | no_match | 1.00 | n/a* | 0 | **null** | 1.00* | n/a | 0 |

\*No-match: empty `items` is success; pack treats “correct empty” as hit/nDCG success for that case.

**Macro (same run)**

| Metric | Value |
|--------|--------|
| mean need F1 | **0.97** |
| mean Hit@1 | **1.00** |
| mean confidence (cases with a score) | **~0.77** |
| mean matchScore | **0.85** |
| mean nDCG | **0.97** |
| mean price MAPE | **0.00** (fixed fixture rate 185) |
| budget invent rate | **0** |
| confidence consistency | **100%** |

**Why confidence is not 0.99 on happy fake-fleet cases:** seed ids are `AST-*`, not digit `assets.id`, so the **0.20 live-id** term in `confidenceScore` is 0. On live SQL (`equipment.id` = `assets.id`) that term can raise the score.

Re-run the pack anytime:

```bash
uv run pytest tests/test_call1_call2_eval_pack.py -v
# then open reports/pytest-report.html
```

### 11.9 Interpreting failures

| Failure | Likely cause |
|---------|----------------|
| Need F1 below gate | Stub/Call 1 extract missed catalog keywords in `project_text` |
| Hit@1 failed | Ranker/filter picked wrong type; gold ids not in `eval_fleet.json` |
| Confidence inconsistent | Session `needs_summary` length or dates disagree with formula inputs |
| Confidence below min | Low matchScore, missing prices, or seed ids (no live digit credit) |
| Budget invented | Extracted amount when gold required null |
| No-match returned items | Gold description/hints accidentally contain catalog keywords (e.g. `aerial` → boom) |

### 11.10 Out of scope

- Online A/B or production dashboards  
- Live LLM eval without labels in default CI  
- Treating `confidenceScore` as a calibrated probability from a trained model  
- Changing formula weights (would be a separate product change)  
- Committing `reports/*.html` by default (gitignored; attach in CI if needed)

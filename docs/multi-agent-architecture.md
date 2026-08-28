# Multi-Agent Architecture (haystack-fast-api)

| Field | Value |
|-------|--------|
| **Status** | As-built |
| **Audience** | Engineers, coding agents, Spring integrators |
| **Date** | 2026-08-27 |
| **Runtime package** | `app/agents/` |
| **Framework** | LangGraph (state graphs) + in-process tools (Haystack / SQL / Neo4j / ML) |
| **OpenSpec map** | [`../openspec/AGENTS.md`](../openspec/AGENTS.md) · knowledge-graph · equipment-recommendation |
| **C/W/D study** | [`../Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) |
| **Call 1 / Call 2 process** | [`call1-call2-endpoint-process.md`](./call1-call2-endpoint-process.md) |
| **OpenSPDD prompts** | [`../openspec/spdd/prompts/`](../openspec/spdd/prompts/) |
| **ADRs** | [`../openspec/adrs/`](../openspec/adrs/) (0003 dual-hop, 0008 graph flag, 0009 Neo4j) |

This document describes **all multi-agent (and agent-adjacent LangGraph) systems** in this service: roles, topologies, tools, state partitions, configuration, and how they bind to Call 1 / 2 / 3.

OpenSpec remains the **normative behaviour SoT**. This guide is the readable architecture map.

---

## Contents

1. [Overview & hard rules](#1-overview--hard-rules)
2. [Where agents sit in the product journey](#2-where-agents-sit-in-the-product-journey)
3. [Path A — Indexing Coordinator gate [4]](#3-path-a--indexing-coordinator-gate-4)
4. [Path B — Project-knowledge Q&A (Call 3)](#4-path-b--project-knowledge-qa-call-3)
5. [Path C — Recommend C/W/D (Call 2 multi-agent)](#5-path-c--recommend-cwd-call-2-multi-agent)
6. [Shared tool layer](#6-shared-tool-layer)
7. [State, partitions, and tool_traces](#7-state-partitions-and-tool_traces)
8. [Configuration (env)](#8-configuration-env)
9. [Code map (`app/agents/`)](#9-code-map-appagents)
10. [How to test](#10-how-to-test)
11. [Related reading](#11-related-reading)

---

## 1. Overview & hard rules

### 1.1 Why multi-agent here

The product needs **grounded** equipment recommendations and project Q&A without stuffing raw files into an LLM or inventing catalog IDs:

| Concern | Owner |
|---------|--------|
| Project-spec chunks + KG-1 | Call 1 indexing (+ optional agent gate) |
| Chatbot answers over project only | Call 3 Stage-1 graph |
| Needs → fleet → price → quote | Call 2 MVP **or** recommend C/W/D graph |
| Fleet SQL / Neo4j / pricing math | **Tools**, not free-form agent code |

**Coordinator / Worker / Delegator (C/W/D)** is the role vocabulary used for recommend-mode (Phase 7). Stage-1 Q&A uses a simpler sequential research → graph → synthesis chain.

### 1.2 Hard architectural rules (do not violate)

| Rule | Meaning |
|------|---------|
| **In-process tools only** | No MCP / FastMCP tool server. LangGraph nodes call Python tools in-process. |
| **No free-form SQL/Cypher** | Fleet and Neo4j tools use allowlisted templates / ORM helpers only. |
| **No invent** | Synthesis and workers must not invent `asset_id` / `equipment.id` or rates. Empty fleet → null item + warning. |
| **Indexing gate is non-LLM** | Coordinator [4] always calls `run_indexing_from_request`; no tool-calling LLM. |
| **Files never enter LLM as raw bytes** | Agents use DocumentStore / KG-1 / summaries after index. |
| **Dual plane** | Project knowledge (vectors + KG-1) ≠ fleet (Postgres SQL ± Neo4j KG-2). |
| **Traces stay off public quote DTO** | `tool_traces` live on graph state (S7.6); Call 2 HTTP body is the quote only. |

### 1.3 Three graphs at a glance

| Path | Graph | HTTP | Default |
|------|-------|------|---------|
| **A. Indexing gate [4]** | `START → index_gate → END` | Call 1 when `INDEXING_VIA_AGENT_GATE=true` | **off** |
| **B. Project knowledge** | `research → graph → synthesis` | Call 3 always | **on** for Call 3 |
| **C. Recommend C/W/D** | `check_gate → project_worker → delegator → execute_needs → synthesis` | Call 2 when `RECOMMEND_VIA_AGENT_GRAPH=true` | **off** (live `.env` may set `true`) |

---

## 2. Where agents sit in the product journey

```text
React  POST /api/recommendations/project-spec
         │
         ▼
Spring Boot saga
         │
         ├─ Call 1  POST .../submitprojectspecification
         │            default: IndexingIngestService (direct)
         │            optional: INDEXING_VIA_AGENT_GATE → indexing_gate graph [4]
         │            → DocumentStore + KG-1 + ProjectKnowledgeSession
         │            → lean FR-IX-023 body (ingest_id, …)
         │
         ├─ Call 2  POST .../project-knowledge/getassetrecommendations
         │            default: SessionRecommendService → RecommendationService MVP
         │            optional: RECOMMEND_VIA_AGENT_GRAPH → run_recommend_graph C/W/D
         │            → quote (quoteRef, items[], confidenceScore, …)
         │
         └─ Call 3  POST .../project-knowledge/query  (optional chatbot)
                      always: run_project_knowledge_agents
                      → answer + hits / sources
```

| Call | Multi-agent? | Notes |
|------|--------------|--------|
| **1** | Optional gate only | Indexing itself is Haystack pipeline + mandatory KG, not a free agent loop |
| **2** | Optional C/W/D graph | Same public quote DTO as MVP |
| **3** | Yes (Stage 1) | Project sources only — no fleet inventory tools |

Detail for dual-hop HTTP: [`call1-call2-endpoint-process.md`](./call1-call2-endpoint-process.md).

---

## 3. Path A — Indexing Coordinator gate [4]

### 3.1 Purpose

Expose Call 1 indexing as a **forced non-LLM Coordinator tool edge** so later multi-agent recommend can treat “index succeeded” as a gate (`indexing_ok`), without making indexing an LLM Worker.

### 3.2 Topology

```text
START → index_gate → END
```

| Item | Value |
|------|--------|
| Module | `app/agents/indexing_gate.py` |
| Tool | `run_indexing_from_request` (`app/agents/tools.py`) |
| Service | Same `IndexingIngestService` as direct Call 1 |
| State | `IndexingGateState` (`user_id`, sources, `indexing_ok`, `ingest_id`, `response`, `tool_traces`, …) |

### 3.3 Does the gate use the indexing pipeline?

**Yes — indirectly.** `indexing_gate.py` does **not** import Haystack’s indexing pipeline itself. It always goes through the **same service path** as normal Call 1 (`INDEXING_VIA_AGENT_GATE=false`).

#### Call chain

```text
indexing_gate (LangGraph node in indexing_gate.py)
  → run_indexing_from_request          # app/agents/tools.py
      → IndexingIngestService.ingest_from_project_spec
          → create_session_document_store() / _build_pipeline_for_store()
          → build_indexing_pipeline / injected pipeline
          → run_indexing_pipeline(pipeline, sources=…)
               # app/pipelines/indexing/pipeline.py
               # FileTypeRouter → convert → clean/split → embed → DocumentWriter
          → mandatory KG-1 (hard-fail) + ProjectKnowledgeSession register
          → lean FR-IX-023 IngestFromProjectSpecResponse
```

From the gate node (forced tool call, no LLM):

```text
response = run_indexing_from_request(
    user_id=...,
    user_name=...,
    project_text=...,
    file_sources=...,
    start_date=...,
    end_date=...,
    service=service,   # optional injected IndexingIngestService
)
```

From `IndexingIngestService` (after packaging `ByteStream` sources):

```text
out = run_indexing_pipeline(pipeline, sources=sources)
```

#### Layer responsibilities

| Layer | Role |
|-------|------|
| **`app/agents/indexing_gate.py`** | Forced non-LLM Coordinator edge: call the indexing tool, set `indexing_ok`, attach lean response or error |
| **`run_indexing_from_request`** (`tools.py`) | Thin wrapper around `IndexingIngestService.ingest_from_project_spec` |
| **`IndexingIngestService`** (`services/indexing.py`) | Owns dual-branch **indexing pipeline**, mandatory KG-1, lean summary, session registry |
| **`app/pipelines/indexing/pipeline.py`** | Actual Haystack graph: FileTypeRouter → convert → split → embed → write |

#### Implications

| Question | Answer |
|----------|--------|
| Same pipeline as direct Call 1? | **Yes** — gate only changes *who invokes* the service, not *which* pipeline runs |
| Does the gate reimplement convert/embed/write? | **No** |
| Does the gate skip KG-1? | **No** — still mandatory hard-fail inside the service |
| Public body different? | **No** — identical lean FR-IX-023 DTO |
| Can tests inject a fake service? | **Yes** — `make_index_gate_node(service=...)` / `run_indexing_from_request(service=...)` |

### 3.4 Behaviour

1. Always invoke the indexing tool (no LLM tool selection).  
2. On success: `indexing_ok=true`, lean `IngestFromProjectSpecResponse` attached.  
3. On failure: `indexing_ok=false`, error message; HTTP still surfaces as Call 1 4xx via the API layer.  
4. Public body shape is **identical** to direct `IndexingIngestService` (FR-IX-023 lean).  
5. After success, the same session + DocumentStore + KG-1 are available for Call 2 / Call 3 tools.

### 3.5 Configuration

| Env | Default | Effect |
|-----|---------|--------|
| `INDEXING_VIA_AGENT_GATE` | `false` | `true` → Call 1 goes through the gate graph |

When the flag is **false**, the API calls `IndexingIngestService` **directly** (no LangGraph). When **true**, the API calls `run_indexing_gate` → same service → same pipeline.

---

## 4. Path B — Project-knowledge Q&A (Call 3)

### 4.1 Purpose

Answer free-form questions about the **uploaded project specification** using:

1. Dense retrieval over session DocumentStore chunks  
2. KG-1 (Ragas project graph) query  
3. Synthesis (stub or LLM)

**No fleet / booking / pricing tools** on this path (Stage 1).

### 4.2 Topology

```text
START → research_agent → graph_agent → synthesis_agent → END
```

| Item | Value |
|------|--------|
| Modules | `app/agents/graph.py`, `nodes.py`, `state.py`, `prompts.py`, `tools.py` |
| Entry | `run_project_knowledge_agents` ← `ProjectKnowledgeQAService` |
| Route | `POST /internal/v1/recommendations/project-knowledge/query` |
| Prerequisite | Successful Call 1 session `(user_id, ingest_id)` |

### 4.3 Nodes & tools

| Node | Role | Tool |
|------|------|------|
| `research_agent` | Research | `project_vector_search` |
| `graph_agent` | Graph | `project_kg_query` |
| `synthesis_agent` | Synthesis | **none** (stub or LLM over notes/hits) |

### 4.4 State (`ProjectKnowledgeAgentState`)

Defined in `app/agents/state.py`:

| Field | Meaning |
|-------|---------|
| `user_id`, `ingest_id` | Session key |
| `query`, `top_k` | User question |
| `research_notes`, `research_hits` | Vector retrieval |
| `graph_notes`, `graph_hits` | KG-1 hits |
| `final_answer` | Synthesized answer |
| `sources_used` | Which tools contributed |
| `tool_traces` | Audit spans |

### 4.5 Configuration

| Env | Default | Effect |
|-----|---------|--------|
| `PROJECT_AGENT_MODE` | `stub` | `stub` = deterministic synthesis; `llm` = OpenAI-compatible chat |
| `PROJECT_AGENT_TOP_K` | `5` | Vector top-k |
| Embedder settings | same as indexing | Query embedder mode/dim **must** match store |

### 4.6 OpenSPDD

- Prompts: `app/agents/prompts.py`  
- Index: [`../openspec/spdd/prompts/project-knowledge-agents.md`](../openspec/spdd/prompts/project-knowledge-agents.md)  
- Rule: when Q&A behaviour is wrong, **edit prompts/spec first**, then code.

### 4.7 Testing

- `tests/test_project_knowledge_agents.py`  
- `tests/test_project_knowledge_api.py`  
- `tests/test_project_vector_tool.py`, `tests/test_project_kg_query_tool.py`  
- Guide: [`testing/knowledge-graph-testing-guide.md`](./testing/knowledge-graph-testing-guide.md)

---

## 5. Path C — Recommend C/W/D (Call 2 multi-agent)

### 5.1 Purpose

Produce the **same Call 2 quote DTO** as the MVP `RecommendationService`, but via an isolated LangGraph DAG with explicit roles:

- Ground project context (Worker [5])  
- Plan work (Delegator)  
- Per-need fleet then price (Workers [6]/[7])  
- Merge without inventing IDs/rates (Coordinator [8])

### 5.2 Topology

```text
START
  → check_gate
       │ indexing_ok == false ──► synthesis (refuse) → END  → HTTP 400
       │ indexing_ok == true
       ▼
    project_worker [5]
       │  project_vector_search → project_kg_query → decompose_project_needs
       ▼
    delegator
       │  emit work_plan[] (fleet_worker / pricing_worker per need)
       ▼
    execute_needs
       │  batches of RECOMMEND_FANOUT_CAP
       │  per need: MUST fleet [6] then price [7]
       ▼
    synthesis [8]  (no tools)
       ▼
    END → map to quote DTO (quoteRef, items[], confidenceScore, …)
```

| Item | Value |
|------|--------|
| Build | `build_recommend_graph` / `run_recommend_graph` in `recommend_graph.py` |
| HTTP wire | `SessionRecommendService` when `RECOMMEND_VIA_AGENT_GRAPH=true` (S7.5) |
| Isolated from | Stage-1 Q&A graph (`app.agents.graph`) |

### 5.3 Roles (C/W/D)

| Role | Graph node | Write partition(s) | Tools |
|------|------------|--------------------|-------|
| **Coordinator** (gate) | `check_gate` | `run` (via traces); gate refuse path | none |
| **Project Worker [5]** | `project_worker` | `project` | `project_vector_search`, `project_kg_query`, `decompose_project_needs` |
| **Delegator** | `delegator` | `work_plan` | **none** (policy only) |
| **Fleet Worker [6]** | inside `execute_needs` | `fleet_by_need[need_id]` | `retrieve_fleet_assets`, `filter_fleet_candidates`, `check_booking_availability`, optional `neo4j_cypher_read` |
| **Pricing Worker [7]** | inside `execute_needs` | `prices_by_need[need_id]` | `predict_asset_price` only |
| **Coordinator [8]** | `synthesis` | `recommendation` | **none** |

Partition enforcement: `validate_state_transition` / `apply_partition_write` in `recommend_state.py` (**F-2**). Illegal writes raise `StateTransitionError` (no partial corrupt write).

### 5.4 Project Worker [5] detail (S7.8)

Order inside `project_worker`:

1. `project_vector_search` — passages from Call 1 DocumentStore  
2. `project_kg_query` — KG-1 facts  
3. `decompose_project_needs` — unit needs for fan-out  

Outputs: `project.needs`, `research_notes` / `graph_notes`, optional hits.

### 5.5 Delegator

- Builds `work_plan[]` entries with `worker_kind` ∈ {`fleet_worker`, `pricing_worker`} and `need_id`.  
- Adds Neo4j to fleet allowlist only if `neo4j_available(catalog)` (K-3).  
- Otherwise sets `skip_tools: [neo4j_cypher_read]`.  
- Does **not** run tools itself.

### 5.6 execute_needs (fan-out scheduler)

| Rule | Detail |
|------|--------|
| Within need | **Must-seq**: fleet complete before pricing |
| Across needs | Batches of size `RECOMMEND_FANOUT_CAP` (default **4**, min 1) |
| Cap = 1 | Serialize each need pipeline |
| Workers | Do **not** spawn sibling needs |

### 5.7 Synthesis [8]

- Module: `recommend_synthesis.py` (+ prompt intents in `recommend_prompts.py`)  
- Merges `fleet_by_need` + `prices_by_need` → `results_by_need`  
- Copy `asset_id` / rates from tool output only  
- Empty fleet → `item: null` + warning  
- Optional LLM may rewrite **rationale only** (`apply_rationale_only`); invented IDs/rates discarded  

### 5.8 Neo4j (KG-2) tools (S7.2 / S8.3)

| Tool | Behaviour |
|------|-----------|
| `neo4j_cypher_read` | Allowlisted templates only (`asset_neighbors`, `assets_by_category`, `compatible_attachments`) |
| `trigger_neo4j_populate` | Non-blocking HTTP enqueue to ops admin URL (`NEO4J_POPULATE_URL`); **not** on recommend hot path |

- Labels: fleet only (`Asset`, `Booking`, `Category`, `Attachment`) — never `:Document` (KG-1)  
- `NEO4J_BACKEND=fake` (default) vs `bolt`  
- Empty/unavailable → K-3 skip; quote still from SQL/fake fleet  

### 5.9 HTTP binding & DTO

| Item | Detail |
|------|--------|
| Flag | `RECOMMEND_VIA_AGENT_GRAPH` (default `false`) |
| Public body | Same as MVP: `AssetRecommendResponse` |
| Gate refuse | `indexing_ok=false` → **400** |
| Not on body | `tool_traces`, chatbot `answer` |

### 5.10 OpenSPDD (recommend)

| Resource | Path |
|----------|------|
| Runtime prompts | `app/agents/recommend_prompts.py` |
| Prompt index | [`../openspec/spdd/prompts/recommend-agents.md`](../openspec/spdd/prompts/recommend-agents.md) |
| Templates A–L | Feasibility_Study multi-agent C/W/D §10 |

**Rule:** When recommend-agent behaviour is wrong, edit **recommend** prompts first — do not rewrite Stage-1 `prompts.py`.

### 5.11 Testing

| Area | Tests |
|------|--------|
| Graph order / gate | `tests/test_recommend_graph_order.py` |
| Fan-out | `tests/test_recommend_fanout.py` |
| State partitions | `tests/test_recommend_agent_state.py` |
| Project worker | `tests/test_recommend_project_worker.py` |
| Synthesis | `tests/test_recommend_synthesis.py` |
| HTTP Call 2 flag | `tests/test_recommend_http_call2.py` |
| Tools / DI | `tests/test_tool_factory.py`, `tests/test_fleet_tools.py`, `tests/test_neo4j_tools.py` |
| Eval pack (MVP default) | `tests/test_call1_call2_eval_pack.py` · [`eval/`](./eval/) |

---

## 6. Shared tool layer

### 6.1 Principle

Tools are **stable name contracts** used in traces and Delegator allowlists. Implementations live under `app/agents/` and call app services / repositories.

### 6.2 Tool catalog (by path)

#### Project / session (Call 3 + recommend [5])

| Name | Purpose |
|------|---------|
| `project_vector_search` | Dense search over project chunks (`user_id` + `ingest_id` filters) |
| `project_kg_query` | KG-1 node/rel search |
| `decompose_project_needs` | Text → structured needs (stub or LLM decomposer) |

#### Indexing (Call 1 gate)

| Name | Purpose |
|------|---------|
| `run_indexing_from_request` | Full index + KG-1 + session register |

#### Fleet (recommend [6])

| Name | Purpose |
|------|---------|
| `retrieve_fleet_assets` | List/read fleet (fake seed or SQL) |
| `filter_fleet_candidates` | Match unit-need to catalog |
| `check_booking_availability` | Drop overlapping bookings |

#### Pricing (recommend [7])

| Name | Purpose |
|------|---------|
| `predict_asset_price` | In-process ML daily rate + clamp metadata |

#### Neo4j KG-2 (optional [6] / ops)

| Name | Purpose |
|------|---------|
| `neo4j_cypher_read` | Template graph reads |
| `trigger_neo4j_populate` | Async populate enqueue |

### 6.3 Factory & backends

| Module | Role |
|--------|------|
| `tool_factory.py` | `build_recommend_tool_catalog`, `build_recommend_runtime`, allowlists, `neo4j_available` |
| `fleet_tools.py` | Fake / DTO SQL / `LiveSqlFleetBackend` |
| `neo4j_tools.py` | Fake / Bolt backends |
| `tools.py` | Stage-1 session tools + indexing + pricing entrypoints |

Worker-kind allowlists (`WORKER_TOOL_ALLOWLISTS`):

| worker_kind | Tools |
|-------------|--------|
| `fleet_worker` | retrieve, filter, availability (+ neo4j when available) |
| `pricing_worker` | `predict_asset_price` |

Unknown tool / worker_kind → `UnknownToolError` / `UnknownWorkerKindError`.

### 6.4 Backend selection

| Env | Values | Effect |
|-----|--------|--------|
| `FLEET_BACKEND` | `fake` (default) \| `sql` | Seed vs Postgres `assets` / bookings |
| `NEO4J_BACKEND` | `fake` (default) \| `bolt` | Fixture graph vs live Bolt |
| `PRICING_SCHEMA` | `primary_snapshot` \| `public` | SQL schema map for fleet/pricing only (not KG-1/pgvector) |

---

## 7. State, partitions, and tool_traces

### 7.1 Recommend state top-level keys

From `recommend_state.py`:

| Key | Owner role(s) |
|-----|----------------|
| `run` | Coordinator / init (`indexing_ok`, user/ingest, dates, …) |
| `project` | Project worker |
| `work_plan` | Delegator |
| `fleet_by_need` | Fleet workers (keyed by `need_id`) |
| `prices_by_need` | Pricing workers |
| `recommendation` | Coordinator synthesis |
| `tool_traces` | Shared audit bus (all roles append) |
| `persistence` | Coordinator (reserved) |

### 7.2 tool_traces contract (S7.6)

Helpers: `recommend_traces.py` (`append_tool_trace`, `now`, `elapsed_ms`).

| Field | Required | Notes |
|-------|----------|--------|
| `role` | yes | `coordinator` / `delegator` / `project_worker` / `fleet_worker` / `pricing_worker` |
| `node` | yes | Graph node name |
| `status` | yes | e.g. `start`, `ok`, `completed`, `error`, `refused` |
| `need_id` | fan-out | Present on per-need workers |
| `tool` | when tool ran | Stable tool name |
| `duration_ms` | terminal spans | Non-negative ms |

**Not** returned on Call 2 HTTP quote body.

### 7.3 Stage-1 traces

Call 3 also records `tool_traces` / `sources_used` on `ProjectKnowledgeAgentState` (and may surface differently on the Q&A response — see knowledge-graph contract).

---

## 8. Configuration (env)

### 8.1 Agent path flags

| Variable | Default | Path |
|----------|---------|------|
| `INDEXING_VIA_AGENT_GATE` | `false` | Call 1 gate [4] |
| `RECOMMEND_VIA_AGENT_GRAPH` | `false` | Call 2 C/W/D |
| `RECOMMEND_FANOUT_CAP` | `4` | Call 2 need parallelism |
| `PROJECT_AGENT_MODE` | `stub` | Call 3 synthesis (+ recommend rationale stub/llm) |
| `PROJECT_AGENT_TOP_K` | `5` | Call 3 vector top-k |

### 8.2 Data backends (agents consume)

| Variable | Default | Used by |
|----------|---------|---------|
| `FLEET_BACKEND` | `fake` | Fleet tools / recommend |
| `PRICING_SCHEMA` | `primary_snapshot` | Live SQL fleet/pricing |
| `NEO4J_BACKEND` | `fake` | Neo4j tools |
| `NEO4J_URI` / `USER` / `PASSWORD` | bolt defaults | Bolt client |
| `NEO4J_POPULATE_URL` | pack `:8089` | Populate enqueue |
| `INDEXING_EMBEDDER` / `DIM` | `mock` / `384` | Vector tools + Call 1 |
| `INDEXING_DOCUMENT_STORE` | `memory` | Project chunks |
| `NEED_DECOMPOSER` / `LLM_*` | `stub` | Decompose needs |
| `KG_*` | artifact dir, transforms | KG-1 build (Call 1) |

### 8.3 Pytest isolation

`tests/conftest.py` forces fake/stub/mock/memory and `RECOMMEND_VIA_AGENT_GRAPH=false` so host live `.env` does not break CI. See project-setup OpenSpec + Call 1/2 process §11.2.

### 8.4 Example live profile (agents on)

```env
# Call 2 multi-agent quote
RECOMMEND_VIA_AGENT_GRAPH=true
RECOMMEND_FANOUT_CAP=4
FLEET_BACKEND=sql
PRICING_SCHEMA=public
NEO4J_BACKEND=bolt
NEO4J_PASSWORD=heavyrental

# Call 3 synthesis
PROJECT_AGENT_MODE=stub   # or llm with LLM_* keys

# Call 1 usually direct
INDEXING_VIA_AGENT_GATE=false
```

---

## 9. Code map (`app/agents/`)

| File | Responsibility |
|------|----------------|
| `__init__.py` | Public exports |
| `state.py` | Stage-1 `ProjectKnowledgeAgentState` |
| `graph.py` | Build/run Call 3 graph |
| `nodes.py` | Research / graph / synthesis nodes (Call 3) |
| `prompts.py` | Stage-1 OpenSPDD prompts |
| `tools.py` | Project tools, indexing tool, pricing tool wrappers |
| `indexing_gate.py` | Coordinator [4] gate graph |
| `recommend_state.py` | Recommend STM + F-2 partitions |
| `recommend_graph.py` | Build/run recommend DAG |
| `recommend_nodes.py` | Gate, project worker, delegator, execute_needs, synthesis node |
| `recommend_synthesis.py` | Tool-free merge [8] |
| `recommend_traces.py` | G-1 tool_traces helpers |
| `recommend_prompts.py` | Recommend A–L system/intent prompts |
| `tool_factory.py` | Catalog DI, allowlists, runtime |
| `fleet_tools.py` | Fleet read tools + backends |
| `neo4j_tools.py` | KG-2 tools + backends |

Services that **invoke** agents:

| Service | Graph |
|---------|--------|
| `IndexingIngestService` / API | Optional gate |
| `SessionRecommendService` | Optional recommend graph |
| `ProjectKnowledgeQAService` | Always Stage-1 graph |

---

## 10. How to test

```bash
cd haystack-fast-api

# Stage-1 Q&A agents
uv run pytest tests/test_project_knowledge_agents.py tests/test_project_knowledge_api.py -q

# Recommend graph / state / HTTP
uv run pytest tests/test_recommend_graph_order.py tests/test_recommend_fanout.py \
  tests/test_recommend_agent_state.py tests/test_recommend_http_call2.py -q

# Tools
uv run pytest tests/test_tool_factory.py tests/test_fleet_tools.py tests/test_neo4j_tools.py -q

# Offline dual-hop eval (MVP path by default)
uv run pytest tests/test_call1_call2_eval_pack.py -q

# HTML report (self-contained)
# → reports/pytest-report.html
```

Optional live:

```bash
RUN_NEO4J_TESTS=1 uv run pytest tests/ -q -m neo4j
```

Eval scoreboard / fixtures: [`eval/`](./eval/).

---

## 11. Related reading

| Doc | When |
|-----|------|
| [`call1-call2-endpoint-process.md`](./call1-call2-endpoint-process.md) | HTTP Call 1/2 process + eval §11 |
| [`eval/README.md`](./eval/README.md) | Committed eval results + test-data export |
| [`testing/knowledge-graph-testing-guide.md`](./testing/knowledge-graph-testing-guide.md) | KG + Call 3 testing |
| [`testing/recommendation-pipeline-testing-guide.md`](./testing/recommendation-pipeline-testing-guide.md) | FR-010 + Call 2 tests |
| [`../openspec/AGENTS.md`](../openspec/AGENTS.md) | SDD map + runtime flow |
| [`../openspec/spdd/prompts/project-knowledge-agents.md`](../openspec/spdd/prompts/project-knowledge-agents.md) | Call 3 prompts |
| [`../openspec/spdd/prompts/recommend-agents.md`](../openspec/spdd/prompts/recommend-agents.md) | Call 2 agent prompts |
| [`../openspec/specs/knowledge-graph/spec.md`](../openspec/specs/knowledge-graph/spec.md) | KG-1 / multi-agent Q&A requirements |
| [`../openspec/specs/equipment-recommendation/spec.md`](../openspec/specs/equipment-recommendation/spec.md) | Parent product + Phase 7 FRs |
| [`../Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) | C/W/D templates A–L |
| [`../Feasibility_Study/multi-agent-synthesis-recommend-output.md`](../Feasibility_Study/multi-agent-synthesis-recommend-output.md) | Synthesis / quote mapping |

---

## One-sentence summary

**Multi-agent in this project is three LangGraph paths—optional non-LLM indexing gate, Stage-1 project Q&A, and optional recommend C/W/D—all sharing in-process allowlisted tools, hard no-invent rules, and clear separation between project knowledge (Call 1) and fleet/pricing (Call 2).**

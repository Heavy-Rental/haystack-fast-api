# Feasibility Study: Postgres–Haystack Sync, Neo4j, Multi-Agent Request Workflow

| Field | Value |
|-------|--------|
| **Document type** | Architecture / infrastructure feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 2.7.1 |
| **Application** | `haystack-fast-api` |
| **Related specs** | `openspec/specs/project-setup/`, `indexing/`, `knowledge-graph/`, `recommendation-pipeline/`, `dynamic-pricing/`, `equipment-recommendation/` |
| **Related studies** | [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) · [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) · [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) · [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) · [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) · [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) |
| **Cloud focus** | DigitalOcean |

---

## 1. Executive summary

This study covers **two complementary planes**:

| Plane | Description |
|-------|-------------|
| **Fleet / data platform** | Spring **Postgres-primary** → real-time sync → **Postgres-Haystack** → **Neo4j** graph projection (KG-2) |
| **Request / agent path** | Spring → **FastAPI** → **Multi-Agent Orchestrator** (LangGraph) → **[4] Indexing tool** → then agents invoke **in-process tools** (project store/Pgvector, Postgres-Haystack fleet SQL, Neo4j KG-2, **ML pricing**) → **synthesize recommendation** |
| **Indexing DocumentStore cutover** | **As-built:** `InMemoryDocumentStore`. **Target:** Indexing Pipeline writes **`PgvectorDocumentStore`** on Postgres-Haystack (multi-user, multi-instance, optional TTL “temporary” project files). |

### Verdicts

| Question | Result |
|----------|--------|
| Fleet real-time sync primary → Postgres-Haystack? | **Yes**, with CDC/outbox/logical replication constraints |
| Neo4j from synced Postgres-Haystack? | **Yes as graph projection**, not native PG replication |
| Spring → FastAPI with project file? | **Yes** (matches as-built route shape) |
| Multi-Agent first, indexing as tool? | **Yes** — force index tool **[4]** early; do not put files in LLM context |
| **Recommend after [4] via agents + in-process tools?** | **Yes** — orchestrator calls tools only; taps **Postgres-Haystack**, **Neo4j**, **ML pricing**, project context; synthesizes recommendation (§4.1) |
| Indexing → InMemoryDocumentStore + KG-1? | **Yes — as-built today** |
| **Indexing Pipeline cutover InMemory → PgvectorDocumentStore?** | **Yes — feasible and recommended** for multi-user project files (see §4.5) |
| In-process tools after Pgvector cutover? | **GO for vector** (tenant filters); **conditional for KG-1** until shared load path |
| Neo4j populate from Postgres-Haystack? | **Yes as async job** on discovery of new primary data (Track D/T) |
| DigitalOcean hosts this? | **Yes** for Postgres (+ pgvector), apps, optional Kafka; **Neo4j DIY or Aura** |
| Ship everything at once? | **No** — dual-track phases (see §10); agent-index can stay InMemory until phase **I1** |

**Overall:** Architecture is **viable**. Keep **eventual consistency**, ship **agent-fronted indexing** without waiting for Kafka/Neo4j, plan **Pgvector** for project vectors, and target a **Multi-Agent Orchestrator** that **after step [4]** **runs in-process tools** (fleet SQL, Neo4j graph, ML pricing, project context) to **produce recommendations**. A separate MCP/FastMCP tool server is **not** in scope.

---

## 2. Combined target architecture

```text
                    ┌──────────────────────────────────────┐
                    │  Spring Boot REST API                │
                    │  • Writes Postgres-primary (OLTP)    │
                    │  • HTTP client → haystack-fast-api   │
                    └───────────┬──────────────┬───────────┘
           domain writes        │              │ project-spec request
           (Asset/Booking/…)    │              │ (file / project_text + user_id)
                                ▼              ▼
              ┌─────────────────────┐   ┌─────────────────────────────────────┐
              │ Postgres-primary    │   │ FastAPI (haystack-fast-api)         │
              └──────────┬──────────┘   │ validate + package ByteStreams      │
                         │              └──────────────────┬──────────────────┘
           real-time sync│                                 │
           (CDC/outbox)  │                                 ▼
                         │              ┌─────────────────────────────────────┐
                         │              │ Multi-Agent Orchestrator (LangGraph)│
                         │              │  policy + tool calls only (no SoT) │
                         │              │  [4] tool: run_indexing_pipeline   │
                         │              │  AFTER [4] agents → in-process tools: │
                         │              │   · project context (Pgvector/KG-1)│
                         │              │   · fleet SQL (Postgres-Haystack)  │
                         │              │   · graph context (Neo4j KG-2)     │
                         │              │   · predict_asset_price (ML, in-process)│
                         │              │  → synthesize **recommendation**   │
                         │              └───────┬─────────────┬───────────────┘
                         │                      │             │
                         ▼                      ▼             ▼
              ┌─────────────────────┐  ┌──────────────────┐  ┌──────────────────┐
              │ Postgres-Haystack   │  │ Indexing write:  │  │ In-process tools │
              │ • mirrored fleet    │◄─│ DocumentStore    │  │ (same app process)│
              │ • **pgvector docs** │  │ as-built: InMem  │  │ SQL / Neo4j /    │
              │   (project chunks)  │  │ **target: Pgvector**│ pricing        │
              └──────────┬──────────┘  │ + KG-1           │  └────────┬─────────┘
                         │             └──────────────────┘           │
                         │  graph projection (fleet)                  │
                         ▼                                            │
              ┌─────────────────────┐                                 │
              │ Neo4j (KG-2 fleet)  │◄────────────────────────────────┘
              └─────────────────────┘
              (+ ML pricing via app pricing_client / model artifacts)
```

**Rule:** Project-file path and fleet-sync path meet at **Postgres-Haystack / Neo4j / agents**, but they are **not one pipeline**.

**DocumentStore cutover:** Indexing Pipeline **Branch A** target changes from process-local **InMemoryDocumentStore** to shared **PgvectorDocumentStore** on Postgres-Haystack (flagged cutover; see §4.5).

### 2.1 Spring multi-call journey (equipment recommender)

haystack-fast-api is the **recommender / project-knowledge feature** next to Spring’s domain API. Spring typically issues **multiple sequential calls** (a saga), not a single mega-request. This subsection is aligned with [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) §2 (wire resilience, SSE, 202 jobs are detailed there).

```text
Portal / user
    │
    ▼
Spring Boot REST API          (auth, booking SoT, multi-call orchestration)
    │  call 1: ingest project file
    │  call 2: project-knowledge Q&A (0..N)
    │  call 3: recommend / rank+price (later reattach)
    ▼
haystack-fast-api             (Haystack pipelines, agents, DocumentStore, KG)
```

| Call | Typical route / payload | Latency profile (today / target) | Uses which plane? |
|------|---------------------------|----------------------------------|-------------------|
| **1. Ingest** | `POST /from-project-spec` — multipart file or JSON text + `user_id` | Seconds–tens of seconds (index + KG + optional agent orchestration) | **Plane B** (§4): indexing → DocumentStore + KG-1; **as-built** technical body; **TARGET** + needs/dates/budget summary (FR-IX-023) — see [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) |
| **2. Q&A** | `POST /project-knowledge/query` — `user_id`, `ingest_id`, `query` | Seconds if LLM; fast if stub | **Plane B** session tools over store + KG-1 from call 1 |
| **3. Recommend** | Future HTTP — needs, dates, options (or continue after ingest) | Seconds–tens; multi unit-need loop | **Plane B orchestrator after [4]** + **in-process tools** → Plane A fleet/Neo4j + **ML pricing** + project context |
| **Health** | `GET /health` | Milliseconds | Ops / resilience probes |

**How this fits the dual-plane architecture**

```text
         Spring multi-call journey (§2.1)
    ┌──────────────────────────────────────────┐
    │ 1 ingest → 2 Q&A → 3 recommend           │
    └─────┬──────────┬─────────────┬───────────┘
          │          │             │
          ▼          ▼             ▼
     Plane B [1–4]  Plane B [5]   Plane B [8] recommend
     index+KG-1     project Q&A   Multi-Agent → in-process tools:
     + Pgvector I1  (optional)    fleet SQL + Neo4j + pricing
                                  + project context  (§4.1)
```

| Implication | Guidance |
|-------------|----------|
| One HTTP protocol for all four calls? | **No** — design **per interaction type** (see resilience study: REST for upload; SSE/poll for long ingest progress) |
| Call 2 without call 1 | **Invalid** — needs `ingest_id` / session from successful ingest |
| Call 3 without Track D mirror | Falls back to **seed fleet** today; production recommend needs **Plane A** Asset/Booking data |
| Sticky sessions | Required for process-local InMemory across call 1→2 **or** use **Pgvector I1** + shared session semantics |

**Wire robustness** (timeouts, idempotency, circuit breaker, 202 jobs, SSE progress):  
[`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) — Track C1–C3. Do **not** use SSE as the project-file **upload** channel.

---

## 3. Plane A — Fleet data platform (Postgres → Haystack PG → Neo4j)

### 3.1 Proposal

1. **Postgres-primary** (Spring Boot) is source of truth for fleet/catalog/booking.  
2. **Postgres-Haystack** receives near-real-time sync for AI/read models (+ later vectors).  
3. **Neo4j** is populated from Postgres-Haystack as a **graph projection** (equipment KG-2).

### 3.2 Three data planes inside “sync” (do not conflate)

| Plane | Content | Sync meaning | SQL replication alone? |
|-------|---------|--------------|------------------------|
| **Relational domain** | Asset, Booking, rates | Row CDC / logical rep / outbox | **Yes** (table subset) |
| **Vector / document** | Chunks, embeddings | Transform + embed pipeline | **No** |
| **Graph (Neo4j)** | Entities, relationships | Cypher projection / ETL | **No** |

### 3.3 Sync patterns (summary)

| Pattern | Lag | Domain tables | Vectors | Recommendation |
|---------|-----|---------------|---------|----------------|
| Logical replication | Seconds | High | Poor alone | Good if DO privileges allow |
| CDC + Kafka | Seconds | High | Events → reembed jobs | High scale / multi-sink |
| Spring outbox → worker | Seconds | High | Explicit hooks | **Often best control** |
| Poll ETL | Min–hours | Medium | Batch OK | **Best Phase D1** |
| Dual-write | “Instant” if lucky | Risky | Avoid | **Do not** |

### 3.4 Consistency

Use **eventual consistency** with lag SLOs (`primary_to_haystack_seconds`, `haystack_to_neo4j_seconds`). Do **not** block Spring writes on Neo4j.

---

## 4. Plane B — Request workflow (Spring → Agent → Index → tools → stores/Neo4j)

### 4.1 End-to-end sequence (proposed)

```text
[1] Spring Boot REST API
      builds multipart/JSON: user_id, user_name?, project_text? | file (project spec)
      POST → haystack-fast-api /api/v1/recommendations/from-project-spec
                    (or future /agent/ingest)
      # Wire resilience / SSE progress / 202 jobs:
      # see spring-boot-fastapi-integration-resilience.md

[2] FastAPI endpoint
      • Validate user_id, non-empty source, date window if present
      • Package file bytes → Haystack ByteStream (MIME from extension)
      • run_in_threadpool( MultiAgentOrchestrator.run(payload, file_sources) )

[3] Multi-Agent Orchestrator invoked (LangGraph)  — **Coordinator** role
      Role: **policy, gates, state, synthesis only** — does not own SQL/Cypher/pricing math
      state = { request_payload, file_sources, ingest_id?, session?, tool_traces[], recommendation? }
      Tool backend (target): **in-process tool module** (LangGraph nodes call Python tools directly)
      Role vocabulary: [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md)

[4] FORCED NON-AGENT TOOL EDGE (Coordinator gate — **not** an LLM Worker)
      Tool: run_indexing_pipeline / run_indexing_from_request
            (pass request body fields + file_sources)
      • FileTypeRouter dual-branch (structured vs unstructured by type)
      • convert → clean/split → final_doc_joiner
      • Branch A: embed → write → DocumentStore
            as-built:  InMemoryDocumentStore (process-local)
            **target:  PgvectorDocumentStore on Postgres-Haystack**
            meta: user_id, ingest_id (multi-user isolation)
      • Branch B: mandatory KG-1 (+ JSON artifact) + ProjectKnowledgeSession
      • return ingest_id, kg_*, documents_written
      **Gate:** no recommend / fleet tools until [4] succeeds; no raw files in LLM context

### After step [4] — Multi-Agent uses in-process tools to recommend

Target model: **Workers** **only invoke allowlisted in-process tools** (shared tool module). They **do not** embed ad-hoc SQL/Cypher or pricing weights inside node code — tools own those backends. An explicit **Delegator** (router node) sequences Workers and expands **per-need fan-out** — not free ReAct.

[5] Project-context Worker (optional Q&A or recommend prep) — AFTER [4]
      role=worker  (shared / once per run)
      In-process tools:
        • project_vector_search   → Pgvector (I1) / session store
        • project_kg_query        → KG-1 (session / shared load path)
        • decompose_project_needs → unit needs[] for fan-out
      Output: needs, constraints, site/project facts for ranking

[5b] Delegator (explicit router node) — AFTER needs known
      role=delegator
      • Allowlisted branches only (not free-form planner)
      • Expand work items per need_id for [6] and [7]
      • May skip optional backends (e.g. Neo4j empty → no graph tool)

[6] Fleet + graph Workers — AFTER [4] (and Plane A data available)
      role=worker  **fan-out per need_id** ([6]×N)
      In-process tools:
        • retrieve_fleet_assets / filter_fleet_candidates  → **Postgres-Haystack**
        • check_booking_availability                      → **Postgres-Haystack** bookings
        • neo4j_cypher_read                               → **Neo4j KG-2** fleet relationships
        • trigger_neo4j_populate (ops)                    → **job** from Postgres-Haystack (async)
      Output: candidate assets, graph-neighbor context, availability (per need)

[7] Pricing Workers — AFTER candidates exist for that need
      role=worker  **fan-out per need_id** ([7]×N); within need: after [6]
      In-process tool:
        • predict_asset_price  → **ML pricing model** (`predict_price_for_asset` / model artifacts)
      Feature row (from docs/dynamic-pricing + fleet tools):
        category name, condition, duration_days, capacity, distance_km,
        platform_height (NaN if N/A), optional period_utilization + lead_time_days
      Output: **price_per_day** (clamped) + metadata; total = rate × days
      Fallback: category table if model missing — never silent zeros
      Full contract: [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md)

[8] Recommendation synthesis (Coordinator — not a tool, not a Worker)
      role=coordinator.synthesis
      • Merge: project context [5] + fleet/Neo4j [6]×N + prices [7]×N
      • Output: **recommended assets** + **predicted rent prices** (structured DTO)
        — align `results_by_need` / `RecommendationItem` / `PricingPayload`
      • Synthesis is **tool-free**: must not invent asset_id or daily_rate
      • Project-spec grounds needs via [4]+[5]; fleet+price tools ground offers
      • As-built Stage-1 synthesis is Q&A-only — target extend for recommend
      • Full study: [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md)
      • Record tool_traces (tool name, args summary, hit counts, **role**, **need_id**)

[9] HTTP response to Spring
      • Ingest-only path: return after [4] (ingest_id, kg_*, documents_written)
      • Recommend path (same request or Spring call 3): return after [8]
      • Neo4j full rebuild: prefer async job ids; do not block recommend on full rebuild
      • Long runs: 202 + job status / SSE progress (resilience study)

Spring multi-call alignment (§2.1):
  • call 1 ≈ [1]–[4] ingest
  • call 2 ≈ [5] Q&A tools
  • call 3 ≈ [5]–[8] recommend (or combined graph after [4] when product allows)
  • Production accuracy needs Track D fleet mirror + T3 Neo4j + pricing model deploy
```

### 4.1.1 Multi-Agent Orchestrator vs tools (recommend-ready target)

**Role vocabulary (alias layer):** Coordinator / Worker / Delegator map onto this orchestrator design without changing tool ownership — see [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md). In that vocabulary: **[4]** is a **forced non-agent tool edge** under the Coordinator (not a Worker); domain steps **[5]–[7]** are Workers (fleet/pricing **fan-out per need**); routing is an **explicit Delegator** node; synthesis **[8]** stays Coordinator-owned and tool-free. **Agent instruction templates** (**A–L**, incl. **sequential/parallel processing**) for every agent role: C/W/D **§10**. Must-seq gate & fleet→price; may-par across needs; fleet LTM = **`postgres_haystack`←`postgres-primary`** — C/W/D §10.0.1–§10.0.11.

| Layer | Responsibility | Does **not** |
|-------|----------------|--------------|
| **Multi-Agent Orchestrator** (LangGraph in app) | Choose agents/order; call tools; synthesize recommendation text/JSON | Own fleet DB as SoT; run free SQL/Cypher; train models |
| **In-process tool module** | Host allowlisted tools; connect to Pgvector, Postgres-Haystack, Neo4j, pricing | Replace Spring portal API |
| **Postgres-Haystack** | Fleet mirror + project Pgvector chunks | Write primary OLTP |
| **Neo4j KG-2** | Fleet graph context for agents | Project-file SoT (KG-1 is separate) |
| **ML pricing model** | Price predictions via `predict_asset_price` tool | Ranking policy (orchestrator) |

```text
┌─────────────────────────────────────────────────────────────┐
│ Multi-Agent Orchestrator (LangGraph)                        │
│  Coordinator: policy · [4] gate · state · synthesis [8]     │
│                                                             │
│  [4] forced non-agent index tool edge  (not a Worker)       │
│       │ success only                                        │
│       ▼                                                     │
│  Worker [5] project / needs                                 │
│       │                                                     │
│       ▼                                                     │
│  Delegator (explicit router) → work items per need_id       │
│       │                                                     │
│       ├─ Worker [6]×N fleet / Neo4j   ─┐                    │
│       └─ Worker [7]×N pricing         ─┤ in-process tools   │
│                                         ▼                   │
│  Tool module (in-process)                                    │
│    ├─ project_*     → Pgvector / KG-1                       │
│    ├─ retrieve_*    → Postgres-Haystack (fleet)             │
│    ├─ neo4j_*       → Neo4j KG-2                            │
│    └─ predict_*     → ML pricing model                      │
│       │                                                     │
│       ▼                                                     │
│  Coordinator synthesis [8] → Recommendation response        │
└─────────────────────────────────────────────────────────────┘
```

**Feasibility verdict for post-[4] recommend via in-process tools:** **GO** with prerequisites **I1** (Pgvector), **D1+/T1** (fleet SQL), **T3** (Neo4j projection), and pricing model available in-app (`pricing_client`).

### 4.2 Step-by-step feasibility

| Step | Feasible? | Notes |
|------|-----------|--------|
| **1. Spring → FastAPI** project file body | **GO** | Same contract as as-built ingest route; Spring is HTTP client |
| **2. FastAPI validate + ByteStreams** | **GO** | Keep parsing **out of** the LLM; thin router + service |
| **3. Multi-Agent Orchestrator** | **GO*** | *Policy + tool calls; stub mode without LLM for CI |
| **4. Indexing tool from request body** | **GO** | Body → adapter → `IndexingIngestService` / pipeline (not raw `pipeline.run(http_body)`) |
| **4e. Indexing Pipeline as SuperComponent** | **GO** | Optional packaging: `@super_component` wraps dual-branch graph; **KG stays outside**; see [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) |
| **4b. File-type processing** | **GO** | Inside `FileTypeRouter`; agent does not choose converters |
| **4c. InMemoryDocumentStore + KG-1** | **GO** | **As-built** today after successful ingest |
| **4d. Indexing cutover → PgvectorDocumentStore + KG-1** | **GO** | Same pipeline; swap store backend; multi-user via meta; see **§4.5** |
| **5. Project tools after [4]** | **GO** | Q&A or recommend prep; Pgvector after I1 for multi-instance |
| **6. Fleet SQL + Neo4j tools** | **GO** | After Plane A mirror + T3; in-process tools |
| **7. ML pricing tool** | **GO** | In-process; see [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) |
| **8. Recommendation synthesis in orchestrator** | **GO** | Assets + prices from tool hits; structured DTO; see synthesis study |
| **9. Single HTTP does all of [4]–[8] sync** | **RISKY** | Prefer split ingest vs recommend or 202 jobs; see resilience study |

### 4.3 “Pass request body to indexing pipeline” (precise meaning)

| Level | What is passed | Recommended? |
|-------|----------------|--------------|
| L1 | Validated fields + `file_sources: list[ByteStream]` | **Yes** |
| L2 | Full Pydantic/dict body + files | **Yes** |
| L3 | Raw multipart stream into agent/LLM | **No** |

Haystack pipeline inputs remain **`sources`**, not FastAPI JSON. The agent tool must include the same adapter as `IndexingIngestService` today.

### 4.4 Indexing outputs (as-built alignment)

On successful tool run, the system already can produce:

| Output | Role |
|--------|------|
| **InMemoryDocumentStore** (as-built) | Process-local, ingest-scoped chunks + embeddings |
| **KG-1 Knowledge Graph** | Document nodes (+ optional Ragas transforms); in-memory for agents |
| **JSON artifact** | `{KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json` |
| **ProjectKnowledgeSession** | Registry key `(user_id, ingest_id)` for later tools |

This matches the online session plane today. **Target** replaces the DocumentStore backend in the indexing write path (next section) without changing MIME routing or KG-1 assembly semantics.

### 4.5 Indexing Pipeline DocumentStore cutover: InMemory → PgvectorDocumentStore

This is an **explicit feasibility item**: change the Indexing Pipeline’s **Branch A** writer target from `InMemoryDocumentStore` to Haystack **`PgvectorDocumentStore`** (PostgreSQL + **pgvector** extension), typically on **Postgres-Haystack**.

#### 4.5.1 What changes vs what stays

| Stays the same | Changes |
|----------------|---------|
| FastAPI / agent tool entry | DocumentStore implementation |
| FileTypeRouter dual-branch by MIME | `DocumentWriter` → Pgvector tables |
| convert → clean/split → join → embed | Connection string / pool to Postgres-Haystack |
| Mandatory KG-1 after post-join chunks | Session registry holds Pgvector-backed store (or connection factory) |
| HTTP ingest response shape | Config flag + ops (backups, TTL jobs) |
| Meta stamping `user_id`, `ingest_id` | Retrieval filters **must** enforce tenant isolation |

```text
  final_doc_joiner
       │
       ├─► doc_embedder → DocumentWriter → DocumentStore
       │                      as-built: InMemoryDocumentStore
       │                      **target:  PgvectorDocumentStore**
       │
       └─► KG-1 generator → JSON artifact + session
              session.document_store = same store used by writer
```

**Protocol note:** Both stores implement Haystack’s DocumentStore API, so the pipeline graph shape is a **backend swap**, not a redesign of indexing. It is **not** a free rename: persistence, multi-instance sharing, and operational concerns differ.

#### 4.5.2 Why cut over (especially multi-user project files)

| Need | InMemory | PgvectorDocumentStore |
|------|----------|------------------------|
| Multiple users’ project requirement files | Awkward across processes | **Yes** — one store, isolate with `user_id` / `ingest_id` meta |
| Multiple FastAPI replicas | Each process has private store | **Shared** Postgres |
| Survive process restart | **No** | **Yes** |
| Temporary retention | Accidental (process death) | **Policy** — TTL / delete job |
| Align with Postgres-Haystack platform | No | **Yes** |

**Multi-user temporary storage model (recommended):**

1. All users write into the **same** Pgvector document table(s).  
2. Every chunk carries **`user_id`** + **`ingest_id`** (and optional `expires_at`).  
3. All retrieval tools **filter** by current `user_id` (and usually `ingest_id`).  
4. A cleanup job deletes expired or discarded ingests — that is how “temporary project requirement files” work on Postgres.

Without filters, tenants can see each other’s chunks — isolation is an **application invariant**, not automatic.

#### 4.5.3 Feasibility verdict for the cutover

| Criterion | Verdict |
|-----------|---------|
| Technically possible with Haystack 2.x | **Yes** (`pgvector-haystack` / `PgvectorDocumentStore`) |
| Compatible with current dual-branch indexing | **Yes** — only writer/store wiring |
| Compatible with mandatory KG-1 | **Yes** — KG remains sibling path; input still post-join chunks |
| Multi-user project files | **Yes** — meta + filtered retrieval + TTL |
| DigitalOcean Managed PG + pgvector | **Yes** — enable `vector` extension on Postgres-Haystack |
| CI without real Postgres | **Keep InMemory** (or Testcontainers) via flag |
| Drop-in with zero config change | **No** — needs DB, dim match, env, migrations |

**Overall cutover: GO — recommended production DocumentStore for the Indexing Pipeline.**

#### 4.5.4 Migration pattern (safe rollout)

| Step | Action |
|------|--------|
| 1 | Config: e.g. `INDEXING_DOCUMENT_STORE=memory\|pgvector` (default `memory` until ready) |
| 2 | Factory: `build_document_store()` returns InMemory or Pgvector from settings |
| 3 | Wire factory into `build_indexing_pipeline` / `IndexingIngestService` |
| 4 | Session registry uses the same store instance (or reconnection for Pgvector) |
| 5 | `project_vector_search` uses embedder + retriever against that store |
| 6 | Tests: default memory; one integration suite against Pgvector |
| 7 | Optional dual-write period (memory + pgvector) only if debugging — usually unnecessary |
| 8 | Production default → `pgvector`; memory for local/CI |

**Embedder constraint:** `INDEXING_EMBEDDING_DIM` (and model) must match the Pgvector column dimension used at table create time.

**Promotion vs write-at-index:**  
**Preferred target:** Indexing Pipeline **writes Pgvector directly** so durable multi-user storage is not an extra hop. The only DocumentStore backends in scope are **InMemory** (as-built/CI) and **Pgvector** (target).

#### 4.5.5 Comparison: InMemory vs Pgvector (indexing write target)

| Store | Multi-user shared API | Durable | DO fit | Role after this study |
|-------|----------------------|---------|--------|------------------------|
| **InMemoryDocumentStore** | Per process only | No | N/A | **As-built / CI / flag off** |
| **PgvectorDocumentStore** | **Yes** | **Yes** | Managed PG + pgvector | **Target Indexing Pipeline writer (only durable path)** |

### 4.6 In-process multi-agent tool layer

#### 4.6.1 Role

| Tools are | Tools are not |
|-----------|---------------|
| Allowlisted callables invoked by LangGraph agents | Source of truth for fleet or prices |
| How agents read Postgres-Haystack, Neo4j, pricing model | How Spring calls the recommender (Spring stays on **HTTP REST** to FastAPI) |
| Shared module next to Stage-1 `app/agents/tools.py` | A separate FastMCP/MCP server process |

**Decision:** A separate **MCP/FastMCP tool server is out of scope**. Multi-agent works by **invoking tools directly in-process** (including PostgreSQL access).

#### 4.6.2 Recommended stack

```text
Spring ──REST──► FastAPI
                    │
                    ▼
              LangGraph multi-agent
                    │  in-process tool calls
                    ▼
              Tool module (app/agents/tools + shared core)
                    ├─► Postgres-Haystack (fleet SQL + Pgvector)
                    ├─► Neo4j (constrained read / graph context)
                    ├─► ML pricing (pricing_client / predict_price)
                    └─► trigger neo4j-populate job (async enqueue)
```

| Side | Component | Responsibility |
|------|-----------|----------------|
| **Tools** | Python functions / `ProjectTool`-style wrappers | SQL, KG query, pricing, job triggers |
| **Orchestration** | LangGraph multi-agent | Policy, sequencing, synthesis — no embedded fleet SQL |

#### 4.6.3 Tool catalog (recommend-capable)

Tools the **Multi-Agent Orchestrator** invokes **after [4]**. Orchestrator **synthesizes**; tools **execute**.

| Tool name | Action | Backend |
|-----------|--------|---------|
| `run_indexing_from_request` | Indexing gate **[4]** | Pipeline → Pgvector (I1) |
| `project_vector_search` | Project chunk context | InMemory / **Pgvector** |
| `project_kg_query` | Project KG-1 facts | Session / artifact |
| `decompose_project_needs` | Spec → unit needs | Need decomposer / LLM |
| `retrieve_fleet_assets` | Candidate equipment | **Postgres-Haystack** SQL (read-only allowlist) |
| `filter_fleet_candidates` | Category/size filter | Postgres-Haystack |
| `check_booking_availability` | Availability window | **Postgres-Haystack** bookings |
| `neo4j_cypher_read` | Fleet graph context | **Neo4j KG-2** (templates) |
| `trigger_neo4j_populate` | Refresh fleet graph | Async job from Haystack PG |
| `predict_asset_price` | **ML pricing** | In-process model — [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) |
| `generate_rank_rationale` | Explain ranks | LLM (optional) |

**Orchestrator-owned (not tools):** recommendation merge/rank policy, final JSON for Spring, LangGraph edges.

**Do not** invent one mega-tool `recommend_everything` — keep narrow tools after [4].

#### 4.6.4 Phasing (recommend via in-process tools after [4])

- **Now / R1–R2:** Stage-1 Q&A tools in-process; recommend still service/seed path.  
- **I1:** Indexing → **Pgvector**.  
- **D1+/T1/T3:** fleet SQL + Neo4j projection ready for tools.  
- **R5 / recommend agents:** after **[4]** gate, Coordinator runs **[5]** → **Delegator** → **[6]×N / [7]×N** Workers (fan-out per need) with in-process tools including **`predict_asset_price`** + Postgres-Haystack + Neo4j → Coordinator **[8]** recommendation.

#### 4.6.5 Feasibility summary

| Verdict | Detail |
|---------|--------|
| **GO** | In-process tool catalog; orchestrator keeps synthesis |
| **Post-[4] recommend** | **GO** — agents call tools; merge in [8] |
| **PostgreSQL tools** | **GO** — read-only allowlisted SQL on Postgres-Haystack |
| **Pgvector (I1)** | Multi-instance project vector tools |
| **No FastMCP** | Not required; not in architecture |

### 4.7 Neo4j population trigger (request path)

```text
Postgres-Haystack (already synced from primary)
        │
        ▼
Tool / worker: trigger_neo4j_populate
        │
        ▼
Worker: SQL → graph mapping → Cypher MERGE (KG-2)
        │
        ▼
Neo4j available to multi-agent fleet tools
```

| Mode | Use |
|------|-----|
| **Async job** on trigger (recommended for full rebuild) | Return `job_id` to Spring |
| **Incremental upsert** on domain CDC | Background; no per-request full rebuild |
| **Inline on every project upload** | Only if graph is tiny; usually **too slow** |

**KG-1 (project file)** and **KG-2 (fleet Neo4j)** remain **two planes**. Project indexing does not replace fleet Neo4j load.

### 4.8 Sequencing safeguards (OpenSPDD-style)

**Norms**

- Orchestrator **must** complete **[4] indexing successfully** before project vector/KG, fleet, Neo4j-read, or pricing tools used for **recommend**.  
- **After [4]**, recommend path agents invoke **allowlisted in-process tools** only.  
- Request body files → tool args only; never full binary into LLM prompts.  
- Record `tool_traces` for Spring/debug (every tool call).  
- Recommendation = **orchestrator synthesis** over tool outputs — not a hidden side effect of one tool.

**Safeguards**

- Do not skip mandatory KG-1 hard-fail path on ingest.  
- Do not invent fleet inventory from project KG-1 alone — use **Postgres-Haystack** + **Neo4j**.  
- Do not block ingest or recommend on full Neo4j rebuild; use `trigger_neo4j_populate` async + read what is already projected.  
- Do not treat agent tools as authoritative over Spring Postgres-primary.  
- Pricing tool failures: fallback policy documented (e.g. table rates) — do not silent-zero prices.  
- Stub/CI path: agent graph runs with zero LLM keys; pricing stub OK.  
- After Pgvector cutover: **never** retrieve project chunks without `user_id` (and usually `ingest_id`) filters.

### 4.9 As-built vs proposed (request path)

| Concern | As-built today | Proposed (target) |
|---------|----------------|-------------------|
| Who calls indexing? | FastAPI → `IndexingIngestService` directly | Multi-Agent **Coordinator gate [4]** (flag; forced non-agent tool); then recommend Workers |
| Indexing graph packaging | `build_indexing_pipeline` + `run_*` | Optional **SuperComponent** wrapper (no KG inside) |
| Orchestrator role | Stage-1 Q&A graph only | **Recommend orchestrator**: Coordinator + Delegator + Workers + in-process tools after [4] |
| Role vocabulary | Informal agent names | **Coordinator / Worker / Delegator** alias layer (dedicated study) |
| **[4] as LLM Worker?** | N/A (service path) | **No** — forced non-agent tool edge |
| Delegator | Fixed sequential edges only | **Explicit router node** (allowlisted branches) |
| Multi-need recommend | N/A / service loop | **Fan-out Workers per need** for fleet **[6]** and pricing **[7]** |
| Tool host | In-process `ProjectTool` | Expanded **in-process** tool module (fleet, Neo4j, pricing) |
| When do agents run? | **After** ingest, Q&A route | After **[4]** for Q&A **and** recommend (**[5]–[8]**) |
| DocumentStore | InMemory session | **Pgvector** (I1) on Postgres-Haystack |
| Fleet / Neo4j / price | Seed fleet; service pricing path | In-process tools: SQL + Neo4j + **`predict_asset_price`** |
| Observability | Basic tool_traces | tool_traces + **`role`** + **`need_id`** on fan-out |
| Spring caller | HTTP multi-call | Same REST; call 3 = recommend graph |

---

## 5. Current repository baseline

| Area | As-built | Implication |
|------|----------|-------------|
| App Postgres | Host `postgres_haystack`; SQLAlchemy sync | Can grow into Postgres-Haystack client |
| DocumentStore | **InMemoryDocumentStore** | **Target cutover:** Indexing → **PgvectorDocumentStore** (§4.5) |
| KG-1 | Ragas + JSON + session | Matches indexing outputs in §4.4 |
| Agents | Fixed sequential Q&A **after** ingest | Target: Coordinator + Delegator + Workers **after [4]**; fan-out per need; **in-process** tools |
| Tool packaging | In-process Stage-1 tools | Expand tool module (no separate MCP server) |
| Pricing | Service / seed path | In-process `predict_asset_price` for recommend agents |
| Asset/Booking | Seed fleet | Needs Track D for production accuracy |
| Neo4j / KG-2 | Stage 2 backlog | Track D3 + T3; Neo4j tools for recommend context |

---

## 6. DigitalOcean fit (summary)

| Component | DO fit | How |
|-----------|--------|-----|
| Postgres-primary | Strong | Managed PostgreSQL |
| Postgres-Haystack + pgvector | Strong | Managed PG + vector extensions ([docs](https://docs.digitalocean.com/products/vector-databases/postgresql/)) |
| FastAPI + Spring | Strong | App Platform / Droplets / DOKS |
| Multi-Agent + workers | Strong | Same compute; keep long jobs off request workers |
| Kafka (optional CDC) | Good | Managed Kafka |
| Neo4j | DIY / external | **No Managed Neo4j**; Droplet/DOKS or Aura |

**Replication caveat:** Validate logical replication / slots on chosen Managed PG plan; Spring **outbox** is the reliable fallback.

### Example VPC layout

```text
DigitalOcean VPC
├── Managed PG A — primary (Spring)
├── Managed PG B — Haystack (pgvector + mirrors)
├── Managed Kafka (optional)
├── Spring Boot service
├── haystack-fast-api (+ LangGraph)
├── CDC / ETL / Neo4j populate workers
├── Neo4j (Droplet/DOKS)
└── Spaces (artifacts, dumps)
```

---

## 7. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Schema drift Spring ↔ mirror | High | Contract tests; versioned schema |
| SQL-only fleet “vector sync” (no embed) | High | Project vectors come from **Indexing Pipeline** (I1 Pgvector write), not CDC of Spring rows |
| Neo4j as second SoT | High | Document projection-only |
| Agent free-form skips index | High | Forced graph edge to indexing tool |
| Over-permissioned tool SQL/Cypher | High | Allowlist tools; read-mostly; audited writes |
| One request = index + Neo4j rebuild | High | Async jobs; timeouts |
| DO replication privileges | Medium | Spike; outbox fallback |
| InMemory loss on restart | Medium | **I1:** Indexing writes **PgvectorDocumentStore** |
| Missing `user_id` filter on Pgvector retrieve | **High** | Enforce tenant filters in all tools/retrievers |
| Embedding dim ≠ Pgvector column | **High** | Single config source; migrate table on dim change |
| Pgvector table growth (no TTL) | Medium | Expiry job for temporary project ingests |
| Connection pool exhaustion under index load | Medium | Pool size, threadpool limits |
| Dual-cluster + Neo4j + Kafka cost | Medium | Dual-track; delay Kafka |

---

## 8. Feasibility verdict matrix (combined)

| Question | Verdict |
|----------|---------|
| Primary → Postgres-Haystack near-real-time (domain) | **Feasible** |
| Haystack SQL read models on that PG | **Feasible** |
| Pgvector documents on that PG | **Feasible** — preferably via **Indexing Pipeline write (I1)**, not only post-hoc promote |
| Neo4j projection from Haystack PG | **Feasible** |
| Native PG → Neo4j storage replication | **Not feasible** |
| Spring → FastAPI project file | **Feasible** |
| Multi-Agent first + indexing tool | **Feasible** (forced tool) |
| Indexing → InMemory + KG-1 | **Feasible (as-built)** |
| **Indexing Pipeline cutover → PgvectorDocumentStore + KG-1** | **Feasible (recommended target)** — §4.5 |
| Multi-user temporary project files on Pgvector | **Feasible** (meta `user_id`/`ingest_id` + TTL delete) |
| In-process retrieve tools | **GO** (InMemory or Pgvector) |
| Trigger Neo4j populate | **Feasible** (job; needs Track D) |
| Entire stack on DigitalOcean | **Feasible** (Neo4j self-managed; pgvector on Managed PG) |
| All-at-once day one | **Not recommended** |

---

## 9. Looking at the original phase list

### Original spine

> schema contract → poll ETL mirror → CDC/outbox → Neo4j projection → Pgvector cutover  
> — not all-at-once Kafka + Neo4j + dual-PG day one

### Assessment

| Phase | Still valid? | Comment |
|-------|--------------|---------|
| Schema contract | **Yes — keep first for fleet** | Unblocks recommend/pricing/graph mapping |
| Poll ETL mirror | **Yes — best first sync** | Proves value before CDC/Kafka |
| CDC/outbox | **Yes when lag SLA needs it** | Outbox often simpler than Kafka initially |
| Neo4j projection | **Yes after mirror exists** | Batch job before continuous |
| Pgvector cutover | **Yes — and tie to Indexing Pipeline** | Platform prep (**D4**) + **I1** makes Indexing **write** Pgvector (§4.5); multi-user project files |
| “Not all-at-once” | **Yes — reaffirmed** | Extended by dual-track below |

**Gap in original list alone:** it only covers the **fleet data platform**. It does **not** schedule:

- Multi-Agent as ingest orchestrator  
- Expanded in-process tool module (fleet/Neo4j/pricing)  
- **Explicit Indexing Pipeline DocumentStore cutover** (InMemory → Pgvector)  

Those belong on **Track R / Track I**, which can start **without** waiting for D3 (Neo4j). Pgvector cutover **does** need a usable Postgres-Haystack (D1-level cluster or dedicated vector DB).

---

## 10. Dual-track phased roadmap (recommended)

### Track D — Data platform (fleet)

| Phase | Name | Outcome |
|-------|------|---------|
| **D0** | Schema contract | Spring tables/columns/enums for Asset, Booking, … documented |
| **D1** | Poll ETL mirror + Haystack PG ready | Primary → Postgres-Haystack domain tables; cluster usable for app |
| **D2** | CDC / outbox | Near-real-time domain mirror |
| **D3** | Neo4j projection | Batch then continuous graph load from Haystack PG |
| **D4** | Pgvector platform ready | Extension, dims, pooling, backups for vector tables (enables I1) |

### Track I — Indexing DocumentStore cutover (project requirements)

| Phase | Name | Outcome |
|-------|------|---------|
| **I0** | Store factory + flag | `INDEXING_DOCUMENT_STORE=memory\|pgvector`; tests default memory |
| **I1** | **Indexing Pipeline writes PgvectorDocumentStore** | Branch A writer + session registry + vector tools use Pgvector; multi-user meta + optional TTL job |
| **I2** | Production default pgvector | Memory only for CI/local; monitoring + retention SLOs |

### Track R — Request / agent / tools (project specification)

| Phase | Name | Outcome |
|-------|------|---------|
| **R0** | Contract parity | Spring→FastAPI ingest contract stable |
| **R1** | Agent invokes indexing tool | Multi-Agent forced tool; store = whatever flag says (memory first OK) |
| **R2** | Session Q&A | research→graph→synthesis over session DocumentStore + KG-1 |
| **R4** | Expand tool module | Fleet SQL, Neo4j read, `trigger_neo4j_populate`, pricing tools |
| **R5** | Cross-plane agent | Project + fleet/Neo4j/pricing tools under Safeguards |

### Dependencies

```text
R0 ──────────────────────────────► R1 ► R2
                                      │
D0 ► D1 ──► D4 ──► I0 ► I1 ► I2 ─────┘   (Indexing→Pgvector; multi-user project files)
              │
D1 ► D2 ──────► D3 ──────────────────────► R4 / R5   (fleet Neo4j tools after D3)
```

| Can ship early without Kafka/Neo4j? | Yes |
|-------------------------------------|-----|
| **R1–R2** | Agent-fronted indexing + Q&A on **InMemory** (as-built store) |
| **D0–D1** | Schema + poll mirror for real Asset/Booking reads |
| **I1** | Needs Postgres-Haystack + pgvector (**D1/D4**); **does not need Neo4j or Kafka** |
| Needs D2+ | Tight fleet lag SLAs |
| Needs D3 | Meaningful fleet Neo4j + populate job |
| After I1 | Multi-user durable/TTL project requirement chunks in Indexing Pipeline |

### First-ship order (practical)

1. **R1** — Agent tool wraps indexing (flag); keep direct service path; **still InMemory OK**.  
2. **D0–D1** — Schema contract + poll ETL mirror + Haystack PG available.  
3. **I0–I1** — **Indexing Pipeline DocumentStore cutover to PgvectorDocumentStore** (multi-user project files).  
4. **D2** — Outbox/CDC when lag demands it.  
5. **D3** — Neo4j projection worker (admin/API trigger first).  
6. **R4–R5** — expand in-process tools + multi-agent fleet tools.

**Still true:** do **not** start with Kafka + Neo4j + dual PG + Pgvector + free ReAct on day one — but **do schedule I1** once Haystack Postgres exists, without waiting for Neo4j.

---

## 11. Devcontainer transition plan (Heavy-Rental Haystack-Fast-API)

This section maps the dual-plane **Track D** roadmap onto the **actual** local stack used for this project.

**Config repo (source of truth for compose):**  
[Heavy-Rental/heavy-rental-devcontainer-configuration — `develop` / `Haystack-Fast-API`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)

Key paths:

| Path | Role |
|------|------|
| `.devcontainer/docker-compose.yml` | Services: app, `postgres_haystack`, `postgres_haystack_sync`, `neo4j` |
| `.devcontainer/devcontainer.json` | Ports 5434 / 7474 / 7687; PG connection profiles; postCreate (uv, neo4j-haystack) |
| `.devcontainer/scripts/sync-from-primary.sh` | FDW + merge-upsert from `postgres-primary` → `postgres_haystack` |
| `specs/001-haystack-postgres-merge-sync/` | Merge-sync contract |
| `specs/002-haystack-neo4j/` | Neo4j DocumentStore path |

### 11.1 Current topology (as of `develop`)

```text
Docker network: heavy-rental-network  (external: true)
────────────────────────────────────────────────────
  postgres-primary          ◄── Spring / REST API stack (other compose)
  (host name on shared network)
           │
           │  service postgres_haystack_sync  (sync worker → postgres_haystack)
           │  scripts/sync-from-primary.sh
           │  SYNC_INTERVAL_SECONDS=60  (near-RT poll — NOT CDC)
           │  SYNC_MODE=merge  (FDW staging → UPSERT by PK/unique)
           │  restart: unless-stopped
           │  HALT_ON_PRIMARY_UNAVAILABLE=false  (skip+sleep if primary missing)
           ▼
  postgres_haystack  (compose service / DNS host; app POSTGRES_HOSTNAME)
  image: postgres:17
  DB: heavy_rental   host port 5434→5432
           ▲
           │  POSTGRES_HOSTNAME=postgres_haystack / DATABASE_URL → postgres_haystack
  haystack-fast-api  (dev workspace, sleep infinity)

  neo4j  (container_name: neo4j-haystack)
  image: neo4j:5   Browser :7474  Bolt :7687
  NEO4J_* env for neo4j-haystack DocumentStore
  ⚠ no job yet that populates fleet graph FROM postgres_haystack after sync
```

**Naming note:** This study uses underscore service keys (`postgres_haystack`, `postgres_haystack_sync`) aligned with app `POSTGRES_HOSTNAME` / OpenSpec. The config-repo compose on `develop` currently uses hyphenated keys (`postgres-haystack`, `postgres-haystack-sync`) with the same roles — treat them as the same services when operating compose.

**VS Code profiles already distinguish:**

| Profile | Host | Meaning |
|---------|------|---------|
| Haystack Local (R/W) | `postgres_haystack` | Postgres-Haystack |
| REST API Primary (source) | `postgres-primary` | Spring / primary OLTP |

### 11.2 Gap analysis vs this feasibility study

| Study target | Current devcontainer | Gap |
|--------------|----------------------|-----|
| **D1** Poll ETL primary → Haystack PG | **`postgres_haystack_sync` + FDW merge** | **Done** |
| **D2** Near-real-time sync | Interval **60s**; `restart: unless-stopped` (config repo `develop`) | **Mostly done** (poll near-RT); true CDC/outbox still optional |
| **D3** Neo4j projection from Haystack PG | Neo4j **service exists**; env for DocumentStore | **No populate-from-`postgres_haystack` job** |
| **D4 / I1** pgvector for indexing | Plain `postgres:17` | **No vector extension bootstrap** |
| External primary | Assumed on `heavy-rental-network` | Ops: ensure REST API compose attaches primary |

**Important:** Config-repo compose on `develop` already runs **60s poll merge** (**D1 + T1-ish**). Calling that “CDC real-time” would still be incorrect — it is **poll ETL**, not logical replication or Debezium.

### 11.3 Target topology (local after transition)

```text
heavy-rental-network
  postgres-primary
        │
        │  near-real-time domain sync
        │  (short-interval merge and/or logical rep / outbox)
        ▼
  postgres_haystack  [optional: pgvector image + CREATE EXTENSION vector]
        │
        │  after successful sync (or on trigger)
        │  neo4j-populate: SQL domain tables → Cypher MERGE
        ▼
  neo4j (neo4j-haystack)
        ├── :Asset / :Booking / …   (fleet KG-2 projection)
        └── (optional) DocumentStore labels — keep namespaced

  haystack-fast-api → reads/writes postgres_haystack; Bolt to neo4j as needed
```

### 11.4 Transition phases (T0–T5)

| Phase | Name | Devcontainer / script changes | Maps to | Exit criteria |
|-------|------|------------------------------|---------|---------------|
| **T0** | Baseline & docs | Confirm `postgres-primary` on shared network; document runbook; one successful merge when primary up; skip/sleep when down (`HALT_ON_PRIMARY_UNAVAILABLE=false` in current compose) | **D1** as-is | Logs show merge success; local tables updated |
| **T1** | Near-real-time domain sync | **Largely done on `develop`:** `SYNC_INTERVAL_SECONDS=60`, `postgres_haystack_sync` `restart: unless-stopped`; remaining: lag logging/metrics, optional healthcheck | **D1→D2** | With primary online, changes appear on `postgres_haystack` within ~60s SLA |
| **T2** | Sync hardening | Table **allowlist** (Asset, Booking, …) if full public merge is heavy; document `merge` vs `mirror`; optional logical replication design; fail cycle alerts | **D2** | Deterministic table set; predictable lag metrics |
| **T3** | Neo4j populate from Haystack PG | **New** script `populate-neo4j-from-haystack.sh` (or Python job) + Compose service `neo4j-populate`; read from `TARGET_HOST=postgres_haystack`; MERGE fleet nodes/rels; **namespace labels** vs DocumentStore | **D3** | After write on primary + sync, Neo4j Browser shows fleet graph |
| **T4** | Triggered populate | On **successful** `run_merge` in `sync-from-primary.sh`, invoke populate (or compose `depends_on` + shared volume signal); later: admin HTTP | **D3 continuous** | Each successful sync refreshes graph (or incremental upsert) |
| **T5** | pgvector (parallel) | Switch `postgres_haystack` image to **`pgvector/pgvector:pg17`** (or init container `CREATE EXTENSION vector`); app env for `PgvectorDocumentStore` | **D4 / I1** | Extension present; indexing smoke write |

### 11.5 Real-time options ranked for *this* compose

| Option | How it fits current `postgres_haystack_sync` | Effort | Recommendation |
|--------|------------------------------|--------|-----------------|
| **A. Shorten poll interval** | Change `SYNC_INTERVAL_SECONDS` only; reuse FDW merge script | **Low** | **T1 default** |
| **B. Manual / one-shot trigger** | `docker compose run postgres_haystack_sync` after Spring seed | Low | Dev convenience |
| **C. Logical replication** primary→`postgres_haystack` | Needs `wal_level`, publication on primary; subscription on haystack | Medium | When FDW lag/load insufficient |
| **D. Spring outbox + consumer container** | New service; prod-like | Medium–High | Best long-term fidelity |
| **E. Debezium + Kafka in devcontainer** | Extra brokers/connectors | High | **Avoid** for local unless platform-standard |

**Transition recommendation:** **T1 = Option A** (e.g. 60s) before investing in Kafka. Design **T2/C or D** when SLA or correctness requires it.

### 11.6 Neo4j: DocumentStore vs fleet projection (same instance)

Current comments wire Neo4j for **neo4j-haystack DocumentStore**. Fleet population from Postgres-Haystack is a **different product concern** (KG-2).

| Use | Labels / isolation | Writer |
|-----|-------------------|--------|
| Project / doc graph (optional DocumentStore) | e.g. `:Document`, store-specific props | haystack app / neo4j-haystack |
| Fleet projection from `postgres_haystack` | e.g. `:Asset`, `:Booking`, `:Category` | **`neo4j-populate` job only** |

**Do not** drop entire Neo4j database on each populate if DocumentStore data must survive. Prefer:

- Label-scoped `MATCH (n:Asset) DETACH DELETE n` before reload, or  
- Incremental `MERGE` by business key, or  
- Neo4j 5 **separate database** (`fleet` vs `documents`) if isolation is hard.

### 11.7 Concrete checklist (config repo PRs)

| File | Actions |
|------|---------|
| `.devcontainer/docker-compose.yml` | (T1) `SYNC_INTERVAL_SECONDS`, `restart: unless-stopped` on `postgres_haystack_sync`; (T3) add `neo4j-populate` service; (T5) optional pgvector image for `postgres_haystack` |
| `.devcontainer/scripts/sync-from-primary.sh` | (T1) lag logging; (T4) call populate on success |
| `.devcontainer/scripts/populate-neo4j-from-haystack.sh` | **New (T3)** — env: `PGHOST=postgres_haystack`, `NEO4J_URI=bolt://neo4j:7687`, table→graph mapping |
| `.devcontainer/devcontainer.json` | Document sync SLA; Neo4j UI connection remains bolt://neo4j:7687 |
| `specs/001-haystack-postgres-merge-sync/` | Amend: near-real-time interval options; allowlist |
| `specs/002-haystack-neo4j/` | Split DocumentStore vs **fleet projection** requirements |

**Example env deltas (illustrative — not applied here):**

```yaml
# postgres_haystack_sync (near-real-time poll — matches config repo develop)
SYNC_INTERVAL_SECONDS: "60"
HALT_ON_PRIMARY_UNAVAILABLE: "false"  # skip+sleep when primary missing
restart: unless-stopped
TARGET_HOST: postgres_haystack
SOURCE_HOST: postgres-primary

# neo4j-populate (new service sketch)
# image: postgres:17 or python:3.12-slim + neo4j driver
# depends_on: [postgres_haystack, neo4j]
# NEO4J_URI: bolt://neo4j:7687
# PGHOST: postgres_haystack
```

### 11.8 Prerequisites & runbook notes

1. Create/use external network: `docker network create heavy-rental-network` (if missing).  
2. Start **REST API / Spring** stack so **`postgres-primary`** is resolvable on that network.  
3. Start Haystack-Fast-API devcontainer compose (`postgres_haystack`, `neo4j`, app; then `postgres_haystack_sync`).  
4. Verify: VS Code “REST API Primary” vs “Haystack Local”; Neo4j Browser `http://localhost:7474`.  
5. With primary down, current compose uses **`HALT_ON_PRIMARY_UNAVAILABLE=false`**: skip cycle + sleep (no wipe of local tables). Prefer this over halt+restart storms under `unless-stopped`.

### 11.9 Risks specific to this transition

| Risk | Mitigation |
|------|------------|
| Treating poll sync as CDC real-time | Publish lag SLA; keep poll vs CDC distinction |
| FDW full-public merge expensive | T2 allowlist high-value tables |
| Populate overwrites DocumentStore graph | Label/database isolation (§11.6) |
| Halt+restart storms when primary down | Prefer `HALT_ON_PRIMARY_UNAVAILABLE=false` + skip/sleep under `unless-stopped` |
| Primary not on network | Document dependency on Spring compose |
| App writes OLTP to primary | Keep FastAPI on **`postgres_haystack` only** for domain R/W sandbox |
| Extra local ANN packages in config repo | Not part of target architecture; durable vectors = Pgvector only |

### 11.10 Mapping T-phases → study Track D / first-ship

| First-ship / Track D | Devcontainer transition |
|----------------------|-------------------------|
| D1 poll ETL | **Already T0** (`postgres_haystack_sync` + script) |
| D2 near-real-time | **T1 largely done** (60s + `unless-stopped` on `develop`); **T2** hardening |
| D3 Neo4j from Haystack PG | **T3–T4** |
| D4 / I1 pgvector | **T5** (parallel once `postgres_haystack` stable) |
| R1 agent indexing | App code; uses `postgres_haystack` when I1 done — independent of T3 |

**Suggested local order:** **T0 → T1 → T3 → T4 → T2 (as needed) → T5**.

### 11.11 What stays out of the app repo vs config repo

| Concern | Where to change |
|---------|-----------------|
| Compose services, sync interval, neo4j-populate container | **heavy-rental-devcontainer-configuration** |
| Haystack pipelines, PgvectorDocumentStore wiring, agent tools | **haystack-fast-api** application |
| Spring outbox / primary WAL | **Spring / REST API** stack + primary PG settings |
| Optional compose services (populate job) | **Config repo** (+ app client flag); see §11.12 |


## 12. Suggested spikes (pre-implementation)

### Fleet (Track D) / DigitalOcean

1. Inventory minimal Spring columns for recommend + pricing + graph.  
2. Managed PG: publication/slot vs outbox spike.  
3. Second PG + `CREATE EXTENSION vector` + Pgvector smoke test.  
4. Neo4j Droplet: load 1k Assets from mirror SQL.  
5. Lag metrics dashboard.

### Devcontainer (Track T — §11)

1. With primary online: one merge cycle; compare row counts primary vs `postgres_haystack`.  
2. Set `SYNC_INTERVAL_SECONDS=60`; change a row on primary; measure time-to-visible on `postgres_haystack`.  
3. Prototype `populate-neo4j-from-haystack.sh` for one table (e.g. Asset) → Neo4j Browser.  
4. Confirm DocumentStore nodes (if any) are not deleted by fleet reload.  
5. Optional: `pgvector/pgvector:pg17` image swap + `CREATE EXTENSION vector`.  
6. Optional: in-process fleet tool stub against `postgres_haystack`.

### Request / agent (Track R)

1. LangGraph `START → index_tool → END`; parity with existing ingest tests.  
2. Latency: direct service vs agent tool (stub).  
3. One read tool + one `trigger_neo4j_populate` no-op/job enqueue.  
4. Failure: unsupported MIME / KG hard-fail still 400.

### Indexing DocumentStore cutover (Track I)

1. `CREATE EXTENSION vector` on Postgres-Haystack; PgvectorDocumentStore smoke write/read.  
2. Indexing pipeline flag `pgvector`: two `user_id`s, prove retrieval isolation.  
3. TTL/delete job deletes one ingest without affecting the other user.  
4. Embed dim mismatch fails fast with clear error.  
5. Regression: full ingest pytest suite with memory flag still green.

---

## 13. Open questions

### Fleet / DO

1. Where does Postgres-primary live (DO / other / on-prem)?  
2. Max lag SLA for availability/pricing?  
3. Neo4j: Droplet Community, Enterprise, or Aura?  
4. Sync table allowlist?  
5. Kafka standard vs outbox-only?  

### Request / agent / tools

6. Must **every** Spring call go through Multi-Agent, or feature-flag subset?  
7. Default durable store: **Pgvector in Indexing Pipeline (I1)** only?  
8. Project chunk **TTL** (e.g. 24h / 7d / until user deletes session)?  
9. Should Neo4j populate run **on each project upload**, on **schedule**, or **admin-only**?  
10. Who owns long-running Neo4j populate workers (app vs sidecar job)?  
11. Auth between Spring and FastAPI (mTLS, API key, mesh)?  
12. After I1, is **InMemory** allowed only in CI, or also single-node demos?

---

## 14. References

### Product / repo

- `openspec/AGENTS.md` — live flow map  
- `openspec/specs/indexing/` — FileTypeRouter ingest, InMemory default  
- `openspec/specs/knowledge-graph/` — KG-1 + Stage-1 agents; KG-2 Neo4j backlog  
- `openspec/specs/equipment-recommendation/` — DocumentStore choices  
- `openspec/specs/project-setup/` — Postgres, layering  
- [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) — Spring multi-call wire  

### Devcontainer (Heavy-Rental)

- [Haystack-Fast-API on `develop`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)  
- `.devcontainer/docker-compose.yml` — `postgres_haystack`, `postgres_haystack_sync`, `neo4j`  
- `.devcontainer/scripts/sync-from-primary.sh` — FDW merge (default **60s** poll on config-repo `develop`)  
- `specs/001-haystack-postgres-merge-sync`, `002-haystack-neo4j`  

### DigitalOcean

- [Managed PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/)  
- [PostgreSQL vector search (pgvector)](https://docs.digitalocean.com/products/vector-databases/postgresql/)  
- [Migrate / continuous migration](https://docs.digitalocean.com/products/databases/postgresql/how-to/migrate/)  
- [Managed Kafka](https://docs.digitalocean.com/products/databases/kafka/)  

### Haystack / Neo4j

- [PgvectorDocumentStore](https://docs.haystack.deepset.ai/docs/pgvectordocumentstore)  
- In-repo: [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) (ML pricing) · [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md)  
- Decision log: [`docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md) · [`docs/dynamic-pricing-execution-plan.md`](../docs/dynamic-pricing-execution-plan.md)  
- [PgvectorDocumentStore](https://docs.haystack.deepset.ai/docs/pgvectordocumentstore)  

---

## 15. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Fleet sync + Neo4j + DigitalOcean |
| **1.1.0** | 2026-08-10 | Spring→Agent→Indexing→MCP→stores/Neo4j workflow; dual-track phases; original phase list reviewed |
| **1.2.0** | 2026-08-10 | **Indexing Pipeline DocumentStore cutover** InMemory → **PgvectorDocumentStore** (§4.5); Track I; multi-user TTL project files |
| **1.3.0** | 2026-08-10 | **§2.1 Spring multi-call journey** (ingest → Q&A → recommend) from resilience study; map to Plane A/B; §4.1 cross-link |
| **1.4.0** | 2026-08-10 | **§11 Devcontainer transition plan** for Heavy-Rental Haystack-Fast-API (primary→haystack sync + Neo4j populate) |
| **1.5.0** | 2026-08-10 | **§11.12 MCP** optional compose profile after T4; link MCP multi-agent feasibility study |
| **1.6.0** | 2026-08-10 | Target DocumentStore path = **InMemory → Pgvector only** (no secondary ANN store in product plan) |
| **1.7.0** | 2026-08-10 | **§4.6 / §11.12:** MCP stack = **FastMCP server + mcp-haystack client**; LangGraph wiring + env |
| **1.8.0** | 2026-08-10 | **§4.6.5** FastMCP **tool consolidation** GO (constraints); link dedicated consolidation study |
| **1.9.0** | 2026-08-10 | **Pgvector I1** strengthens MCP vector **GO**; expanded §4.6.3 catalog; unlisted pipeline tools pointer |
| **2.0.0** | 2026-08-10 | **Post-[4] recommend:** Multi-Agent Orchestrator + FastMCP tools (Postgres-Haystack, Neo4j, ML pricing); steps [5]–[8] |
| **2.1.0** | 2026-08-10 | Link **ML pricing feasibility** (features, guardrails, Phase 1e/2a); expand [7] feature row |
| **2.2.0** | 2026-08-10 | **§4.2 4e:** Indexing Pipeline as **SuperComponent** GO; link study |
| **2.3.0** | 2026-08-10 | **[8] synthesis** assets+prices; link synthesis + MCP server/pyproject/config-repo studies |
| **2.4.0** | 2026-08-10 | Call 1 **TARGET** simplified response (needs/dates/budget); link FR-IX-023 study |
| **2.5.0** | 2026-08-10 | **Remove FastMCP/MCP server** from architecture; in-process tools only |
| **2.5.1** | 2026-08-10 | Align Haystack Postgres **service hostname** to **`postgres_haystack`** (match app `POSTGRES_HOSTNAME` / OpenSpec project-setup); was documented as compose `db` / `postgres-haystack` |
| **2.5.2** | 2026-08-10 | Rename sync service **`db-sync` → `postgres_haystack_sync`**; align §11 with config-repo compose (`SYNC_INTERVAL_SECONDS=60`, `unless-stopped`) |
| **2.5.3** | 2026-08-11 | §4.1.1 cross-link **Coordinator / Worker / Delegator** vocabulary study |
| **2.6.0** | 2026-08-11 | Folder alignment: §4.1 roles ([4] non-agent gate, Delegator, fan-out ×N); diagram; §4.9/§5/§16 C/W/D rows |
| **2.6.1** | 2026-08-11 | §4.1.1 pointer to C/W/D §10 agent A/B instruction templates |
| **2.6.2** | 2026-08-11 | §4.1.1: agent A+B+C + `heavy_rental` table contextual awareness pointer |
| **2.6.3** | 2026-08-11 | §4.1.1: agent A+B+C+D state space pointer |
| **2.6.4** | 2026-08-11 | §4.1.1: agent A+B+C+D+E environment modeling pointer |
| **2.6.5** | 2026-08-11 | §4.1.1: agent A–F integration patterns (events + validation) pointer |
| **2.6.6** | 2026-08-11 | §4.1.1: agent A–G monitoring and adaptation pointer |
| **2.6.7** | 2026-08-11 | §4.1.1: agent A–H memory; fleet LTM = haystack←primary sync |
| **2.6.8** | 2026-08-11 | §4.1.1: agent A–I context management pointer |
| **2.6.9** | 2026-08-11 | §4.1.1: agent A–J decision integration pointer |
| **2.7.0** | 2026-08-11 | §4.1.1: agent A–K workflow optimization pointer |
| **2.7.1** | 2026-08-11 | §4.1.1: agent A–L sequential/parallel processing pointer |

---

## 16. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Build fleet sync + Neo4j? | **Yes, Track D phased** |
| Build agent-first indexing? | **Yes, Track R1** (flag; forced index tool **[4]**) |
| **[4] as LLM Worker agent?** | **No** — **Coordinator gate** (forced non-agent tool edge) |
| Coordinator / Worker / Delegator vocabulary? | **Yes** — alias layer; see C/W/D study |
| Delegator shape | **Explicit router** (allowlisted); not free ReAct |
| Fleet / pricing multi-need | **Fan-out Workers per need** ([6]×N / [7]×N) |
| C/W/D labels in logs / tool_traces? | **Yes** (`role`, `need_id`) |
| Indexing as Haystack **SuperComponent**? | **GO** optional — wrap dual-branch pipeline; KG remains service-side ([study](./indexing-pipeline-supercomponent.md)) |
| Indexing outputs (as-built) | **InMemory + KG-1** |
| **Indexing DocumentStore cutover** | **Yes — I1: pipeline writes PgvectorDocumentStore** |
| Multi-user project files | **Pgvector + user_id/ingest_id filters + TTL** |
| Durable store default | **Pgvector in Indexing Pipeline only** (InMemory for CI) |
| **Call 1 simplified body (needs/dates/budget)?** | **GO (TARGET)** — FR-IX-023; keep `ingest_id`; not Call 3 recommend |
| **Multi-Agent after [4]** | **GO** — Coordinator + Delegator + Workers run **in-process tools**; Coordinator synthesizes |
| **Synthesis outputs assets + rent price?** | **GO (target)** — merge only; see [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) |
| Recommend data sources via tools | **Postgres-Haystack** + **Neo4j KG-2** + **ML pricing** + project Pgvector/KG-1 |
| **ML pricing detail** | See [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md); `price_per_day` + clamp; not public HTTP |
| Tool packaging | **In-process** tool module (no FastMCP/MCP server) |
| Recommend tools | Postgres-Haystack SQL + Neo4j + `predict_asset_price` after [4] |
| Neo4j populate | **Job trigger** after D3/T3 on new primary data; not per-request full rebuild by default |
| DigitalOcean | **Suitable**; Neo4j self-managed or Aura; pgvector on Managed PG |
| **Devcontainer today** | **D1 + ~60s poll** (`postgres_haystack_sync` FDW merge); Neo4j up but **no fleet populate from `postgres_haystack`** |
| **Devcontainer next** | **T2** allowlist/metrics if needed; **T3–T4** neo4j-populate from Haystack PG; CDC only if poll SLA insufficient |
| Original phase spine | **Keep** as Track D; parallel **Track I** + Track R + **Track T** (§11) |
| First ship | **R1 + D0–D1**, then **I1**; local: **T0→T1→T3→T4**; not Kafka + free ReAct all at once |
| Avoid | Dual-write; Neo4j as SoT; SQL-only fleet “vector sync”; free agent MIME routing; blocking ingest on Neo4j; unfiltered multi-tenant retrieve; wiping DocumentStore graph on fleet reload; secondary ANN stores outside Pgvector |

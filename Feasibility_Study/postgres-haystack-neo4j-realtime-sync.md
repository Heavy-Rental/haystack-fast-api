# Feasibility Study: Postgres–Haystack Sync, Neo4j, Agent/MCP Request Workflow

| Field | Value |
|-------|--------|
| **Document type** | Architecture / infrastructure feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.6.0 |
| **Application** | `haystack-fast-api` |
| **Related specs** | `openspec/specs/project-setup/`, `indexing/`, `knowledge-graph/`, `recommendation-pipeline/`, `dynamic-pricing/`, `equipment-recommendation/` |
| **Related studies** | [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) · [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md) |
| **Cloud focus** | DigitalOcean |

---

## 1. Executive summary

This study covers **two complementary planes**:

| Plane | Description |
|-------|-------------|
| **Fleet / data platform** | Spring **Postgres-primary** → real-time sync → **Postgres-Haystack** → **Neo4j** graph projection (KG-2) |
| **Request / agent path** | Spring Boot calls **FastAPI** with a **project specification file** → **Multi-Agent** handles the request → **Indexing Pipeline tool** → write **DocumentStore + Knowledge Graph (KG-1)** → optional **MCP** tools and **Neo4j populate** triggers |
| **Indexing DocumentStore cutover** | **As-built:** `InMemoryDocumentStore`. **Target:** Indexing Pipeline writes **`PgvectorDocumentStore`** on Postgres-Haystack (multi-user, multi-instance, optional TTL “temporary” project files). |

### Verdicts

| Question | Result |
|----------|--------|
| Fleet real-time sync primary → Postgres-Haystack? | **Yes**, with CDC/outbox/logical replication constraints |
| Neo4j from synced Postgres-Haystack? | **Yes as graph projection**, not native PG replication |
| Spring → FastAPI with project file? | **Yes** (matches as-built route shape) |
| Multi-Agent first, indexing as tool? | **Yes** — force index tool early; do not put files in LLM context |
| Indexing → InMemoryDocumentStore + KG-1? | **Yes — as-built today** |
| **Indexing Pipeline cutover InMemory → PgvectorDocumentStore?** | **Yes — feasible and recommended** for multi-user project files (see §4.5) |
| MCP retrieve tools after Pgvector cutover? | **Conditional GO** — later packaging (R4); primary durable write is Indexing → Pgvector |
| MCP triggers Neo4j from Postgres-Haystack? | **Yes as job trigger** — depends on fleet sync plane readiness |
| DigitalOcean hosts this? | **Yes** for Postgres (+ pgvector), apps, optional Kafka; **Neo4j DIY or Aura** |
| Ship everything at once? | **No** — dual-track phases (see §10); agent-index can stay InMemory until phase **I1** |

**Overall:** Architecture is **viable**. Keep **eventual consistency**, treat **MCP as tool transport (not source of truth)**, ship **agent-fronted indexing** without waiting for Kafka/Neo4j, and plan an explicit **Indexing Pipeline DocumentStore cutover** to **PgvectorDocumentStore** for multi-user durable (or TTL-temporary) project requirements.

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
                         │              │ Multi-Agent (LangGraph orchestrator)│
                         │              │  1) tool: run_indexing_pipeline     │
                         │              │  2) tools: session Q&A (optional)   │
                         │              │  3) MCP tools: retrieve / promote   │
                         │              │  4) MCP: trigger_neo4j_populate     │
                         │              └───────┬─────────────┬───────────────┘
                         │                      │             │
                         ▼                      ▼             ▼
              ┌─────────────────────┐  ┌──────────────────┐  ┌──────────────────┐
              │ Postgres-Haystack   │  │ Indexing write:  │  │ MCP server       │
              │ • mirrored domain   │◄─│ DocumentStore    │  │ configured tools │
              │ • **pgvector docs** │  │ as-built: InMem  │  │ (retrieve, …)    │
              │   (project chunks)  │  │ **target: PgvectorDocumentStore**     │
              └──────────┬──────────┘  │ + KG-1 session   │  └────────┬─────────┘
                         │             └──────────────────┘           │
                         │  graph projection (fleet)                  │
                         ▼                                            │
              ┌─────────────────────┐                                 │
              │ Neo4j (KG-2 fleet)  │◄────────────────────────────────┘
              └─────────────────────┘
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
| **1. Ingest** | `POST /from-project-spec` — multipart file or JSON text + `user_id` | Seconds–tens of seconds (index + KG + optional agent orchestration) | **Plane B** (§4): agent → indexing → DocumentStore + KG-1 |
| **2. Q&A** | `POST /project-knowledge/query` — `user_id`, `ingest_id`, `query` | Seconds if LLM; fast if stub | **Plane B** session tools over store + KG-1 from call 1 |
| **3. Recommend** | Future / service FR-010 — needs, dates, options | Seconds; multi unit-need loop | **Plane A** mirrored Asset/Booking (+ pricing); not the project-file index alone |
| **Health** | `GET /health` | Milliseconds | Ops / resilience probes |

**How this fits the dual-plane architecture**

```text
         Spring multi-call journey (§2.1)
    ┌──────────────────────────────────────────┐
    │ 1 ingest → 2 Q&A → 3 recommend           │
    └─────┬──────────┬─────────────┬───────────┘
          │          │             │
          ▼          ▼             ▼
     Plane B §4  Plane B §4[5]  Plane A §3
     ingest+KG-1 project Q&A    fleet mirror
     + Pgvector I1              + optional Neo4j KG-2
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

## 4. Plane B — Request workflow (Spring → Agent → Index → MCP → stores/Neo4j)

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

[3] Multi-Agent invoked FIRST (request handler)
      state = { request_payload, file_sources, ingest_id?, session?, traces[] }

[4] Tool: run_indexing_pipeline  (pass request body fields + file_sources)
      • FileTypeRouter dual-branch (structured vs unstructured by type)
      • convert → clean/split → final_doc_joiner
      • Branch A: embed → write → DocumentStore
            as-built:  InMemoryDocumentStore (process-local)
            **target:  PgvectorDocumentStore on Postgres-Haystack**
            meta: user_id, ingest_id (multi-user isolation)
      • Branch B: mandatory KG-1 (+ JSON artifact) + ProjectKnowledgeSession
            session holds handle to the same DocumentStore used in Branch A
      • return IngestFromProjectSpecResponse-like result

[5] (Optional same graph) session tools
      project_vector_search / project_kg_query / synthesis  — only AFTER [4] succeeds
      (vector search reads the DocumentStore — InMemory today, Pgvector after cutover)

[6] MCP server tools (later phase)
      • retrieve data using configured tools (fleet read models, docs, ops APIs)
      • **after Indexing→Pgvector cutover, primary durable write is already in the pipeline**
        • no secondary vector store (Pgvector is the durable DocumentStore)
      • trigger_neo4j_populate(from=Postgres-Haystack)  — fleet graph job

[7] HTTP response to Spring
      • Prefer: return when [4] complete (ingest_id, kg_*, documents_written)
      • Neo4j full rebuild: async job ids / status, unless product forces sync wait

Further Spring calls (not expanded as steps [8]… here):
  • call 2 Q&A / call 3 recommend — multi-call journey in §2.1
  • call 3 production accuracy depends on Track D fleet mirror (Plane A), not only on this ingest
  • wire resilience / SSE progress / 202 jobs — spring-boot-fastapi-integration-resilience.md
```

### 4.2 Step-by-step feasibility

| Step | Feasible? | Notes |
|------|-----------|--------|
| **1. Spring → FastAPI** project file body | **GO** | Same contract as as-built ingest route; Spring is HTTP client |
| **2. FastAPI validate + ByteStreams** | **GO** | Keep parsing **out of** the LLM; thin router + service |
| **3. Multi-Agent first** | **GO*** | *Force indexing tool as first edge; stub mode without LLM for CI |
| **4. Indexing tool from request body** | **GO** | Body → adapter → `IndexingIngestService` / pipeline (not raw `pipeline.run(http_body)`) |
| **4b. File-type processing** | **GO** | Inside `FileTypeRouter`; agent does not choose converters |
| **4c. InMemoryDocumentStore + KG-1** | **GO** | **As-built** today after successful ingest |
| **4d. Indexing cutover → PgvectorDocumentStore + KG-1** | **GO** | Same pipeline; swap store backend; multi-user via meta; see **§4.5** |
| **5. Session multi-agent Q&A** | **GO** | As-built Stage-1 graph; requires session from [4]; retriever must use same store |
| **6a. MCP retrieve tools** | **CONDITIONAL GO** | Haystack `mcp-haystack`; Neo4j MCP servers exist; ops + auth |
| **6b. Postgres/Pgvector as primary write** | **GO (preferred)** | **Prefer write-at-index** via §4.5 cutover; only DocumentStore path besides InMemory |
| **6d. MCP trigger Neo4j from Postgres-Haystack** | **GO as job** | Requires Track D sync; prefer async; not full DB binary copy |
| **7. Single HTTP does all of 4–6d sync** | **RISKY** | Latency/timeouts; split ingest response vs background jobs |

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

### 4.6 MCP server role

| MCP is | MCP is not |
|--------|------------|
| Tool transport for agents (retrieve, write, trigger jobs) | Source of truth for fleet or prices |
| A way to expose Neo4j Cypher / GraphRAG / ops actions | A substitute for CDC from Spring primary |
| Optional packaging for LangGraph tools | Required for first agent-indexing milestone |

**Industry fit:** Haystack MCP integration (`mcp-haystack`); Neo4j publishes MCP servers (Cypher / GraphRAG). Product specs already mark Hayhooks/MCP as **optional**, not a second SoT.

**Suggested MCP tool catalog (illustrative)**

| Tool name | Action |
|-----------|--------|
| `run_indexing_from_request` | May stay in-process LangGraph tool (not only MCP); writes DocumentStore per flag (memory/pgvector) |
| `retrieve_project_chunks` | Read project chunks (filter `user_id` / `ingest_id`) from active DocumentStore |
| `retrieve_fleet_assets` | Read Postgres-Haystack mirror |
| `trigger_neo4j_populate` | Enqueue graph projection from Postgres-Haystack |
| `neo4j_cypher_read` | Constrained read queries (KG-2) |

### 4.7 Neo4j population trigger (request path)

```text
Postgres-Haystack (already synced from primary)
        │
        ▼
MCP tool trigger_neo4j_populate
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
| **Incremental upsert** on domain CDC | Background; no per-request MCP |
| **Inline on every project upload** | Only if graph is tiny; usually **too slow** |

**KG-1 (project file)** and **KG-2 (fleet Neo4j)** remain **two planes**. Project indexing does not replace fleet Neo4j load.

### 4.8 Sequencing safeguards (OpenSPDD-style)

**Norms**

- Orchestrator **must** call indexing tool successfully before project vector/KG tools.  
- Request body files → tool args only; never full binary into LLM prompts.  
- Record `tool_traces` for Spring/debug.

**Safeguards**

- Do not skip mandatory KG-1 hard-fail path.  
- Do not invent fleet inventory from project KG-1 alone.  
- Do not block ingest HTTP on full Neo4j rebuild by default.  
- Do not treat MCP as authoritative over Spring Postgres-primary.  
- Stub/CI path: agent graph runs with zero LLM keys.  
- After Pgvector cutover: **never** retrieve project chunks without `user_id` (and usually `ingest_id`) filters.

### 4.9 As-built vs proposed (request path)

| Concern | As-built today | Proposed |
|---------|----------------|----------|
| Who calls indexing? | FastAPI → `IndexingIngestService` directly | Multi-Agent tool (optional flag) |
| When do agents run? | **After** ingest, on Q&A route | **First** as ingest orchestrator; Q&A still after index |
| DocumentStore | InMemory session (as-built) | **Target:** Indexing Pipeline → **PgvectorDocumentStore** (I1); memory via flag for CI |
| Neo4j | Not implemented | MCP/job from Postgres-Haystack |
| Spring caller | Possible client of same HTTP | Explicit system integration |

---

## 5. Current repository baseline

| Area | As-built | Implication |
|------|----------|-------------|
| App Postgres | Host `db`; SQLAlchemy sync | Can grow into Postgres-Haystack client |
| DocumentStore | **InMemoryDocumentStore** | **Target cutover:** Indexing → **PgvectorDocumentStore** (§4.5) |
| KG-1 | Ragas + JSON + session | Matches indexing outputs in §4.4 |
| Agents | Fixed sequential Q&A **after** ingest | R1 adds orchestrator around indexing |
| MCP | Spec optional only | R4 packaging |
| Asset/Booking | Seed fleet | Needs Track D for production accuracy |
| Neo4j / KG-2 | Stage 2 backlog | Track D3 + R4/R5 |

---

## 6. DigitalOcean fit (summary)

| Component | DO fit | How |
|-----------|--------|-----|
| Postgres-primary | Strong | Managed PostgreSQL |
| Postgres-Haystack + pgvector | Strong | Managed PG + vector extensions ([docs](https://docs.digitalocean.com/products/vector-databases/postgresql/)) |
| FastAPI + Spring | Strong | App Platform / Droplets / DOKS |
| Multi-Agent + workers | Strong | Same compute; keep long jobs off request workers |
| Kafka (optional CDC) | Good | Managed Kafka |
| MCP server process | DIY | Droplet/DOKS sidecar next to API |
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
├── MCP server process (optional sidecar)
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
| MCP as SoT / over-permissioned writes | High | Allowlist tools; read-mostly; audited writes |
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
| MCP retrieve packaging | **Conditional GO** (later R4; tools hit InMemory or Pgvector only) |
| MCP trigger Neo4j populate | **Feasible** (job; needs Track D) |
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
- MCP packaging  
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

### Track R — Request / agent / MCP (project specification)

| Phase | Name | Outcome |
|-------|------|---------|
| **R0** | Contract parity | Spring→FastAPI ingest contract stable |
| **R1** | Agent invokes indexing tool | Multi-Agent forced tool; store = whatever flag says (memory first OK) |
| **R2** | Session Q&A | research→graph→synthesis over session DocumentStore + KG-1 |
| **R4** | MCP tool layer | MCP exposes retrieve, `trigger_neo4j_populate`, etc. |
| **R5** | Cross-plane agent | Project tools + fleet/Neo4j MCP tools under Safeguards |

### Dependencies

```text
R0 ──────────────────────────────► R1 ► R2
                                      │
D0 ► D1 ──► D4 ──► I0 ► I1 ► I2 ─────┘   (Indexing→Pgvector; multi-user project files)
              │
D1 ► D2 ──────► D3 ──────────────────────► R4 / R5   (Neo4j MCP useful after D3)
```

| Can ship early without Kafka/Neo4j? | Yes |
|-------------------------------------|-----|
| **R1–R2** | Agent-fronted indexing + Q&A on **InMemory** (as-built store) |
| **D0–D1** | Schema + poll mirror for real Asset/Booking reads |
| **I1** | Needs Postgres-Haystack + pgvector (**D1/D4**); **does not need Neo4j or Kafka** |
| Needs D2+ | Tight fleet lag SLAs |
| Needs D3 | Meaningful fleet Neo4j + MCP populate |
| After I1 | Multi-user durable/TTL project requirement chunks in Indexing Pipeline |

### First-ship order (practical)

1. **R1** — Agent tool wraps indexing (flag); keep direct service path; **still InMemory OK**.  
2. **D0–D1** — Schema contract + poll ETL mirror + Haystack PG available.  
3. **I0–I1** — **Indexing Pipeline DocumentStore cutover to PgvectorDocumentStore** (multi-user project files).  
4. **D2** — Outbox/CDC when lag demands it.  
5. **D3** — Neo4j projection worker (admin/API trigger first).  
6. **R4–R5** — MCP packaging + multi-agent fleet tools.

**Still true:** do **not** start with Kafka + Neo4j + dual PG + Pgvector + MCP + free ReAct on day one — but **do schedule I1** once Haystack Postgres exists, without waiting for Neo4j.

---

## 11. Devcontainer transition plan (Heavy-Rental Haystack-Fast-API)

This section maps the dual-plane **Track D** roadmap onto the **actual** local stack used for this project.

**Config repo (source of truth for compose):**  
[Heavy-Rental/heavy-rental-devcontainer-configuration — `develop` / `Haystack-Fast-API`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)

Key paths:

| Path | Role |
|------|------|
| `.devcontainer/docker-compose.yml` | Services: app, `db` (postgres-haystack), `db-sync`, `neo4j` |
| `.devcontainer/devcontainer.json` | Ports 5434 / 7474 / 7687; PG connection profiles; postCreate (uv, neo4j-haystack) |
| `.devcontainer/scripts/sync-from-primary.sh` | FDW + merge-upsert from `postgres-primary` → `db` |
| `specs/001-haystack-postgres-merge-sync/` | Merge-sync contract |
| `specs/002-haystack-neo4j/` | Neo4j DocumentStore path |

### 11.1 Current topology (as of `develop`)

```text
Docker network: heavy-rental-network  (external: true)
────────────────────────────────────────────────────
  postgres-primary          ◄── Spring / REST API stack (other compose)
  (host name on shared network)
           │
           │  service db-sync  (postgres-haystack-sync)
           │  scripts/sync-from-primary.sh
           │  SYNC_INTERVAL_SECONDS=86400  (daily — NOT real-time)
           │  SYNC_MODE=merge  (FDW staging → UPSERT by PK/unique)
           │  restart: "no"   (halt if primary missing)
           ▼
  db  (container_name: postgres-haystack)
  image: postgres:17
  DB: heavy_rental   host port 5434→5432
           ▲
           │  POSTGRES_HOSTNAME=db / DATABASE_URL → db
  haystack-fast-api  (dev workspace, sleep infinity)

  neo4j  (container_name: neo4j-haystack)
  image: neo4j:5   Browser :7474  Bolt :7687
  NEO4J_* env for neo4j-haystack DocumentStore
  ⚠ no job yet that populates fleet graph FROM db after sync
```

**VS Code profiles already distinguish:**

| Profile | Host | Meaning |
|---------|------|---------|
| Haystack Local (R/W) | `db` | Postgres-Haystack |
| REST API Primary (source) | `postgres-primary` | Spring / primary OLTP |

### 11.2 Gap analysis vs this feasibility study

| Study target | Current devcontainer | Gap |
|--------------|----------------------|-----|
| **D1** Poll ETL primary → Haystack PG | **`db-sync` + FDW merge** | **Done** (interval is 24h) |
| **D2** Near-real-time sync | Interval **86400s**; one-shot-friendly `restart: "no"` | **Need shorter cycle or true CDC** |
| **D3** Neo4j projection from Haystack PG | Neo4j **service exists**; env for DocumentStore | **No populate-from-`db` job** |
| **D4 / I1** pgvector for indexing | Plain `postgres:17` | **No vector extension bootstrap** |
| External primary | Assumed on `heavy-rental-network` | Ops: ensure REST API compose attaches primary |

**Important:** Daily merge is a solid **D1** implementation. Calling it “real-time” without changing interval/mechanism would be incorrect.

### 11.3 Target topology (local after transition)

```text
heavy-rental-network
  postgres-primary
        │
        │  near-real-time domain sync
        │  (short-interval merge and/or logical rep / outbox)
        ▼
  db (postgres-haystack)  [optional: pgvector image + CREATE EXTENSION vector]
        │
        │  after successful sync (or on trigger)
        │  neo4j-populate: SQL domain tables → Cypher MERGE
        ▼
  neo4j (neo4j-haystack)
        ├── :Asset / :Booking / …   (fleet KG-2 projection)
        └── (optional) DocumentStore labels — keep namespaced

  haystack-fast-api → reads/writes db; Bolt to neo4j as needed
```

### 11.4 Transition phases (T0–T5)

| Phase | Name | Devcontainer / script changes | Maps to | Exit criteria |
|-------|------|------------------------------|---------|---------------|
| **T0** | Baseline & docs | Confirm `postgres-primary` on shared network; document runbook; one successful merge when primary up; halt when down (`HALT_ON_PRIMARY_UNAVAILABLE=true`) | **D1** as-is | Logs show merge success; local tables updated |
| **T1** | Near-real-time domain sync | Set `SYNC_INTERVAL_SECONDS` to **30–120** (dev SLA); set `db-sync` **`restart: unless-stopped`**; log cycle lag; optional healthcheck | **D1→D2** | With primary online, changes appear on `db` within chosen SLA |
| **T2** | Sync hardening | Table **allowlist** (Asset, Booking, …) if full public merge is heavy; document `merge` vs `mirror`; optional logical replication design; fail cycle alerts | **D2** | Deterministic table set; predictable lag metrics |
| **T3** | Neo4j populate from Haystack PG | **New** script `populate-neo4j-from-haystack.sh` (or Python job) + Compose service `neo4j-populate`; read from `TARGET_HOST=db`; MERGE fleet nodes/rels; **namespace labels** vs DocumentStore | **D3** | After write on primary + sync, Neo4j Browser shows fleet graph |
| **T4** | Triggered populate | On **successful** `run_merge` in `sync-from-primary.sh`, invoke populate (or compose `depends_on` + shared volume signal); later: MCP/admin HTTP | **D3 continuous** | Each successful sync refreshes graph (or incremental upsert) |
| **T5** | pgvector (parallel) | Switch `db` image to **`pgvector/pgvector:pg17`** (or init container `CREATE EXTENSION vector`); app env for `PgvectorDocumentStore` | **D4 / I1** | Extension present; indexing smoke write |

### 11.5 Real-time options ranked for *this* compose

| Option | How it fits current `db-sync` | Effort | Recommendation |
|--------|------------------------------|--------|-----------------|
| **A. Shorten poll interval** | Change `SYNC_INTERVAL_SECONDS` only; reuse FDW merge script | **Low** | **T1 default** |
| **B. Manual / one-shot trigger** | `docker compose run db-sync` after Spring seed | Low | Dev convenience |
| **C. Logical replication** primary→`db` | Needs `wal_level`, publication on primary; subscription on haystack | Medium | When FDW lag/load insufficient |
| **D. Spring outbox + consumer container** | New service; prod-like | Medium–High | Best long-term fidelity |
| **E. Debezium + Kafka in devcontainer** | Extra brokers/connectors | High | **Avoid** for local unless platform-standard |

**Transition recommendation:** **T1 = Option A** (e.g. 60s) before investing in Kafka. Design **T2/C or D** when SLA or correctness requires it.

### 11.6 Neo4j: DocumentStore vs fleet projection (same instance)

Current comments wire Neo4j for **neo4j-haystack DocumentStore**. Fleet population from Postgres-Haystack is a **different product concern** (KG-2).

| Use | Labels / isolation | Writer |
|-----|-------------------|--------|
| Project / doc graph (optional DocumentStore) | e.g. `:Document`, store-specific props | haystack app / neo4j-haystack |
| Fleet projection from `db` | e.g. `:Asset`, `:Booking`, `:Category` | **`neo4j-populate` job only** |

**Do not** drop entire Neo4j database on each populate if DocumentStore data must survive. Prefer:

- Label-scoped `MATCH (n:Asset) DETACH DELETE n` before reload, or  
- Incremental `MERGE` by business key, or  
- Neo4j 5 **separate database** (`fleet` vs `documents`) if isolation is hard.

### 11.7 Concrete checklist (config repo PRs)

| File | Actions |
|------|---------|
| `.devcontainer/docker-compose.yml` | (T1) `SYNC_INTERVAL_SECONDS`, `restart: unless-stopped` on `db-sync`; (T3) add `neo4j-populate` service; (T5) optional pgvector image for `db` |
| `.devcontainer/scripts/sync-from-primary.sh` | (T1) lag logging; (T4) call populate on success |
| `.devcontainer/scripts/populate-neo4j-from-haystack.sh` | **New (T3)** — env: `PGHOST=db`, `NEO4J_URI=bolt://neo4j:7687`, table→graph mapping |
| `.devcontainer/devcontainer.json` | Document sync SLA; Neo4j UI connection remains bolt://neo4j:7687 |
| `specs/001-haystack-postgres-merge-sync/` | Amend: near-real-time interval options; allowlist |
| `specs/002-haystack-neo4j/` | Split DocumentStore vs **fleet projection** requirements |

**Example env deltas (illustrative — not applied here):**

```yaml
# db-sync (near-real-time poll)
SYNC_INTERVAL_SECONDS: "60"
HALT_ON_PRIMARY_UNAVAILABLE: "true"
restart: unless-stopped

# neo4j-populate (new service sketch)
# image: postgres:17 or python:3.12-slim + neo4j driver
# depends_on: [db, neo4j]
# NEO4J_URI: bolt://neo4j:7687
# PGHOST: db
```

### 11.8 Prerequisites & runbook notes

1. Create/use external network: `docker network create heavy-rental-network` (if missing).  
2. Start **REST API / Spring** stack so **`postgres-primary`** is resolvable on that network.  
3. Start Haystack-Fast-API devcontainer compose (`db`, `neo4j`, app; then `db-sync`).  
4. Verify: VS Code “REST API Primary” vs “Haystack Local”; Neo4j Browser `http://localhost:7474`.  
5. With primary down, current script **halts without mutating local tables** — keep that safety during T1 unless intentionally changed.

### 11.9 Risks specific to this transition

| Risk | Mitigation |
|------|------------|
| Treating 24h sync as real-time | Publish SLA; implement T1 |
| FDW full-public merge expensive | T2 allowlist high-value tables |
| Populate overwrites DocumentStore graph | Label/database isolation (§11.6) |
| `restart: "no"` stops continuous cycles | T1 → `unless-stopped` |
| Primary not on network | Document dependency on Spring compose |
| App writes OLTP to primary | Keep FastAPI on **`db` only** for domain R/W sandbox |
| Extra local ANN packages in config repo | Not part of target architecture; durable vectors = Pgvector only |

### 11.10 Mapping T-phases → study Track D / first-ship

| First-ship / Track D | Devcontainer transition |
|----------------------|-------------------------|
| D1 poll ETL | **Already T0** (`db-sync` + script) |
| D2 near-real-time | **T1–T2** |
| D3 Neo4j from Haystack PG | **T3–T4** |
| D4 / I1 pgvector | **T5** (parallel once `db` stable) |
| R1 agent indexing | App code; uses `db` when I1 done — independent of T3 |

**Suggested local order:** **T0 → T1 → T3 → T4 → T2 (as needed) → T5**.

### 11.11 What stays out of the app repo vs config repo

| Concern | Where to change |
|---------|-----------------|
| Compose services, sync interval, neo4j-populate container | **heavy-rental-devcontainer-configuration** |
| Haystack pipelines, PgvectorDocumentStore wiring, agent tools | **haystack-fast-api** application |
| Spring outbox / primary WAL | **Spring / REST API** stack + primary PG settings |
| Optional MCP Compose service / profile | **Config repo** (+ app client flag); see §11.12 |

### 11.12 MCP server in devcontainer (optional, after T4)

**MCP is not on the T0–T5 critical path** for primary→haystack sync or Neo4j populate. Multi-agent Stage 1 can keep **in-process** tools (`app/agents/tools.py`).

| When | What |
|------|------|
| After **T0–T1** (and ideally **T3–T4**) | Optional Compose service **`mcp-haystack`** (HTTP/streamable MCP) on `heavy-rental-network` |
| Compose | Prefer **`profiles: ["mcp"]`** so default `up` stays light |
| Env | `PGHOST=db`, `NEO4J_URI=bolt://neo4j:7687`; app `MCP_SERVER_URL=http://mcp-haystack:8100/...` |
| Tools | Retrieve project/fleet (tenant-scoped); `trigger_neo4j_populate` only after T3 exists |
| Order | **T0 → T1 → T3 → T4**, then MCP phases **M1–M4** |

**Illustrative service (not applied — study only):**

```yaml
  # docker compose --profile mcp up -d
  mcp-haystack:
    # build/image: FastMCP + allowlisted tools
    restart: unless-stopped
    environment:
      PGHOST: db
      NEO4J_URI: bolt://neo4j:7687
      MCP_PORT: "8100"
    ports:
      - "8100:8100"   # local dev only
    depends_on:
      db:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    networks:
      - heavy-rental-network
    profiles: ["mcp"]
```

**Full feasibility (options, security, DigitalOcean sidecar, M0–M5):**  
[`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md)

**Do not** expose MCP publicly on DigitalOcean without auth; Spring portal traffic remains **FastAPI REST**, not MCP.

---

## 12. Suggested spikes (pre-implementation)

### Fleet (Track D) / DigitalOcean

1. Inventory minimal Spring columns for recommend + pricing + graph.  
2. Managed PG: publication/slot vs outbox spike.  
3. Second PG + `CREATE EXTENSION vector` + Pgvector smoke test.  
4. Neo4j Droplet: load 1k Assets from mirror SQL.  
5. Lag metrics dashboard.

### Devcontainer (Track T — §11)

1. With primary online: one merge cycle; compare row counts primary vs `db`.  
2. Set `SYNC_INTERVAL_SECONDS=60`; change a row on primary; measure time-to-visible on `db`.  
3. Prototype `populate-neo4j-from-haystack.sh` for one table (e.g. Asset) → Neo4j Browser.  
4. Confirm DocumentStore nodes (if any) are not deleted by fleet reload.  
5. Optional: `pgvector/pgvector:pg17` image swap + `CREATE EXTENSION vector`.  
6. Optional (§11.12 / MCP study): FastMCP “ping” on profile `mcp`; invoke from app container.

### Request / agent (Track R)

1. LangGraph `START → index_tool → END`; parity with existing ingest tests.  
2. Latency: direct service vs agent tool (stub).  
3. MCP sidecar: one read tool + one `trigger_neo4j_populate` no-op/job enqueue.  
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

### Request / agent / MCP

6. Must **every** Spring call go through Multi-Agent, or feature-flag subset?  
7. Default durable store: **Pgvector in Indexing Pipeline (I1)** only?  
8. Project chunk **TTL** (e.g. 24h / 7d / until user deletes session)?  
9. Should Neo4j populate run **on each project upload**, on **schedule**, or **admin-only**?  
10. Who owns the MCP server process (same deploy as FastAPI vs sidecar)?  
11. Auth between Spring and FastAPI (mTLS, API key, mesh)?  
12. After I1, is **InMemory** allowed only in CI, or also single-node demos?

---

## 14. References

### Product / repo

- `openspec/AGENTS.md` — live flow map  
- `openspec/specs/indexing/` — FileTypeRouter ingest, InMemory default  
- `openspec/specs/knowledge-graph/` — KG-1 + Stage-1 agents; KG-2 Neo4j backlog  
- `openspec/specs/equipment-recommendation/` — optional MCP; DocumentStore choices  
- `openspec/specs/project-setup/` — Postgres, layering  
- [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) — Spring multi-call wire  

### Devcontainer (Heavy-Rental)

- [Haystack-Fast-API on `develop`](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)  
- `.devcontainer/docker-compose.yml` — `db` (postgres-haystack), `db-sync`, `neo4j`  
- `.devcontainer/scripts/sync-from-primary.sh` — FDW merge (default 24h)  
- `specs/001-haystack-postgres-merge-sync`, `002-haystack-neo4j`  

### DigitalOcean

- [Managed PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/)  
- [PostgreSQL vector search (pgvector)](https://docs.digitalocean.com/products/vector-databases/postgresql/)  
- [Migrate / continuous migration](https://docs.digitalocean.com/products/databases/postgresql/how-to/migrate/)  
- [Managed Kafka](https://docs.digitalocean.com/products/databases/kafka/)  

### Haystack / MCP / Neo4j

- [PgvectorDocumentStore](https://docs.haystack.deepset.ai/docs/pgvectordocumentstore)  
- [Haystack MCP integration](https://haystack.deepset.ai/integrations/mcp)  
- [Neo4j MCP / GenAI ecosystem](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)  

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

---

## 16. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Build fleet sync + Neo4j? | **Yes, Track D phased** |
| Build agent-first indexing? | **Yes, Track R1** (flag; forced index tool) |
| Indexing outputs (as-built) | **InMemory + KG-1** |
| **Indexing DocumentStore cutover** | **Yes — I1: pipeline writes PgvectorDocumentStore** |
| Multi-user project files | **Pgvector + user_id/ingest_id filters + TTL** |
| Durable store default | **Pgvector in Indexing Pipeline only** (InMemory for CI) |
| MCP | **Later (R4 / M\*)**; tool transport only; see MCP study + §11.12 |
| MCP in compose | Optional service + **profile `mcp`** after T4; not T0–T5 critical path |
| Neo4j populate via MCP | **Job trigger** after D3/T3; not per-request full rebuild by default |
| DigitalOcean | **Suitable**; Neo4j self-managed or Aura; pgvector on Managed PG |
| **Devcontainer today** | **D1 done** (`db-sync` 24h FDW merge); Neo4j up but **no fleet populate from `db`** |
| **Devcontainer next** | **T1** shorten sync interval + restart policy; **T3–T4** neo4j-populate from Haystack PG |
| Original phase spine | **Keep** as Track D; parallel **Track I** + Track R + **Track T** (§11) |
| First ship | **R1 + D0–D1**, then **I1**; local: **T0→T1→T3→T4**; not Kafka+MCP all at once |
| Avoid | Dual-write; Neo4j as SoT; SQL-only fleet “vector sync”; free agent MIME routing; blocking ingest on Neo4j; unfiltered multi-tenant retrieve; wiping DocumentStore graph on fleet reload; secondary ANN stores outside Pgvector |

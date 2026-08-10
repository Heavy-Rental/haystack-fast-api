# Feasibility Study: FastMCP Tool Consolidation for Multi-Agent Orchestration

| Field | Value |
|-------|--------|
| **Document type** | Architecture / integration feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.3.0 |
| **Application** | `haystack-fast-api` |
| **Question** | Can a **FastMCP server** **consolidate** multi-agent tools so LangGraph orchestration stays in the app and tools live on (or behind) FastMCP? |
| **DocumentStore target** | **InMemoryDocumentStore (as-built CI) → PgvectorDocumentStore (product target, phase I1)** |
| **Related studies** | [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md) · [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4.5–§4.6 · [`ml-pricing-multi-agent-fastmcp.md`](./ml-pricing-multi-agent-fastmcp.md) · [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) |
| **As-built code** | `app/agents/tools.py`, `app/agents/graph.py`, `app/agents/nodes.py`, `app/services/project_knowledge_session.py`, `app/pipelines/*`, `app/services/*` |

---

## 1. Executive summary

### Question

In the multi-agent orchestration context of **haystack-fast-api**, can tools currently bound in-process to LangGraph be **consolidated onto a FastMCP server**, so agents invoke a single tool catalog via MCP (Haystack **`mcp-haystack`** client) rather than importing session-local Python callables?

### Verdicts

| Question | Result |
|----------|--------|
| **Logical consolidation** (one allowlisted catalog, stable tool names, shared implementations)? | **GO** |
| **Orchestration stays in LangGraph** (research → graph → synthesis)? | **GO** — FastMCP does **not** replace multi-agent |
| **InMemory → Pgvector cutover (I1) still feasible?** | **GO** — dual-plane §4.5; **recommended product path** |
| **`project_vector_search` on separate FastMCP after I1?** | **GO** — Pgvector is network-visible; filter `user_id` + `ingest_id` |
| **`project_kg_query` on separate FastMCP?** | **CONDITIONAL GO** — needs **shared KG-1 load path** (artifact volume / durable store); not fixed by Pgvector alone |
| **Physical consolidation into a separate Docker container while still on InMemory only?** | **NO** for project vector — process-local store invisible to sidecar |
| **In-process FastMCP mount** (same process as FastAPI; no extra container)? | **GO** for early tool surface (optional bridge before I1) |
| **Fleet tools** on separate FastMCP? | **GO** (once `db` / Neo4j / T3 exist) |
| **Other pipeline capabilities as MCP tools?** | **Selective GO** — fleet, Neo4j, **pricing** for recommend; not full recommend monolith |
| **Recommend after step [4] via FastMCP tools?** | **GO** — orchestrator agents call tools only; synthesize ranks in LangGraph |
| Required for Stage-1 Q&A **now**? | **No** — keep `build_session_tools` until I1 + MCP phases |

**Overall:** **GO — stronger with Pgvector.** Replacing **InMemoryDocumentStore** with **PgvectorDocumentStore** removes the main blocker for consolidating **vector** tools onto a **sidecar FastMCP** server. Consolidation is **tool-hosting** only: the **Multi-Agent Orchestrator** sequences agents that **invoke FastMCP tools** (project context, **Postgres-Haystack** fleet, **Neo4j** graph, **ML pricing**) and **synthesizes the recommendation** after indexing step **[4]**.

| State plane | After I1 (Pgvector target) | Sidecar FastMCP |
|-------------|----------------------------|-----------------|
| Project vectors | Shared Postgres-Haystack + pgvector | **Yes** — open store by connection + tenant filters |
| KG-1 | Still often process/artifact-local today | **Only if** artifact path or durable graph is shared |
| Fleet SQL / Neo4j | Already network services | **Yes** after T\* |

---

## 2. What “consolidate to FastMCP” means

| Meaning | In scope? | Notes |
|---------|-----------|--------|
| **Single tool catalog** registered on FastMCP (`project_*`, fleet_*, ops_*) | **Yes** | Allowlist + schemas + tenant args |
| **Shared implementation module** used by both in-process and MCP wrappers | **Yes** | Avoid dual-path drift |
| **LangGraph calls tools by name** via MCP client when `AGENT_TOOLS=mcp` | **Yes** | `mcp-haystack` `MCPTool` + HTTP |
| **Move multi-agent graph / LLM synthesis into FastMCP** | **No** | Orchestration + **recommendation synthesis** stay in app |
| **Replace Spring → FastAPI REST with MCP** | **No** | Spring stays on REST |
| **FastMCP becomes source of truth for fleet/prices** | **No** | Transport only; model is a tool backend |
| **Recommend after [4] by agents calling FastMCP tools** | **Yes** | Postgres-Haystack + Neo4j + ML pricing + project context |

```text
BEFORE (as-built / pre-I1)
  LangGraph ──► ProjectTool(func closes over session) ──► InMemory DS / KG-1
  Recommend path ──► RecommendationService (seed fleet + pricing client) — not MCP

AFTER I1 + consolidated MCP (target recommend path)
  [4] Indexing ──write──► PgvectorDocumentStore (Postgres-Haystack)
  Multi-Agent Orchestrator (after [4] succeeds)
       │  agents only invoke tools
       ▼
  mcp-haystack client ──HTTP──► FastMCP
                                  ├─ project_*     → Pgvector / KG-1
                                  ├─ retrieve_*    → Postgres-Haystack fleet
                                  ├─ neo4j_*       → Neo4j KG-2 context
                                  └─ predict_*     → ML pricing model
       │
       ▼
  synthesis / rank → Recommendation response (orchestrator, not FastMCP)
```

---

## 3. As-built multi-agent tool model (evidence)

### 3.1 Orchestration (unchanged under consolidation)

| Piece | Location | Behaviour |
|-------|----------|-----------|
| Graph | `app/agents/graph.py` | Fixed: `research_agent` → `graph_agent` → `synthesis_agent` |
| Nodes | `app/agents/nodes.py` | Explicit tool calls (not free-form ReAct); stable traces |
| Q&A facade | `app/services/project_knowledge_qa.py` | Resolve session → `run_project_knowledge_agents` |

### 3.2 Tools today (only LangGraph-registered tools)

| Tool name | Builder | Backing (as-built) | Target backing | Binding style |
|-----------|---------|--------------------|----------------|---------------|
| `project_vector_search` | `build_project_vector_search_tool` | `session.document_store` (**InMemoryDocumentStore**) | **PgvectorDocumentStore** on Postgres-Haystack (I1) | **Closure** today → **tenant lookup** after I1 |
| `project_kg_query` | `build_project_kg_query_tool` | `session.knowledge_graph` (Ragas KG-1) | Same + optional shared artifact/durable load | **Closure** today → **load by ingest** for MCP |

Source: `app/agents/tools.py` — `build_session_tools(session)` returns a `dict[str, ProjectTool]`.

**These are the only two first-class agent tools in code today.** Other pipelines/services are **capabilities** (see §5.1), not registered LangGraph tools yet.

### 3.3 Session locality vs Pgvector cutover

`ProjectKnowledgeSessionRegistry` is **process-local** (`app/services/project_knowledge_session.py`):

| Field | As-built | After I1 (target) |
|-------|----------|-------------------|
| Key | `(user_id, ingest_id)` | Same |
| Document store | Ingest-scoped **InMemory** (or process singleton) | **PgvectorDocumentStore** connection / factory; chunks filtered by meta |
| KG-1 | In-memory Ragas graph + optional JSON artifact | Still need **shared load** for multi-process MCP |
| Visible to sidecar? | **No** (InMemory) | **Vector: Yes** · **KG: only with shared path** |

**Implication:**

- **With InMemory only:** FastMCP sidecar **cannot** serve `project_vector_search` against the API’s RAM store.  
- **With Pgvector (I1):** FastMCP sidecar **can** open the same DB and run dense retrieve with `user_id` + `ingest_id` filters — **this is the intended consolidation path**.  
- **KG-1** is **not** solved by Pgvector alone; keep hybrid or shared artifact until a durable project-graph path exists.

---

## 4. Feasibility by consolidation mode

### Mode A — Shared library + dual wrappers (recommended engineering pattern)

| Aspect | Assessment |
|--------|------------|
| Idea | Extract pure functions e.g. `run_project_vector_search(store, query, …)` / `run_project_kg_query(kg, query, …)` (partially already via `run_vector_search`, `query_knowledge_graph`). Thin **ProjectTool** and **FastMCP `@tool`** wrappers both call them. |
| Feasibility | **GO** immediately |
| Extra container? | **No** (library only) |
| Benefit | Single implementation; tests target pure functions; MCP is packaging |

### Mode B — In-process FastMCP (same container as FastAPI)

| Aspect | Assessment |
|--------|------------|
| Idea | Run FastMCP (or MCP-over-HTTP ASGI) **in the same process/image** as the app; register tools that resolve session from the **same** registry. LangGraph uses mcp-haystack client to `http://127.0.0.1:8100` **or** in-process client if supported. |
| Feasibility | **GO** for **tool-surface consolidation** without externalizing stores |
| Extra container? | **No** |
| Pros | Full access to session registry; proves MCP allowlist/schemas early |
| Cons | Not true process isolation; multi-replica session stickiness still hard; less ideal as long-term DO sidecar story |

### Mode C — Separate FastMCP container (Compose profile `mcp` / DO sidecar)

| Aspect | Assessment |
|--------|------------|
| Idea | Long-lived FastMCP service on `heavy-rental-network`; app holds **mcp-haystack** client (`MCP_SERVER_URL=http://mcp-haystack:8100/mcp`). |
| Feasibility **before** I1 (InMemory only) | **NO** for project vector — sidecar cannot read API RAM store |
| Feasibility **after I1 (Pgvector target)** for **`project_vector_search`** | **GO** — same Postgres-Haystack + pgvector; require `user_id` + `ingest_id` (+ embedding dim parity) |
| Feasibility for **`project_kg_query`** after I1 | **CONDITIONAL** — still needs shared KG-1 artifact/load; hybrid OK |
| Feasibility for **fleet** tools | **GO** after T1/T3 (SQL + bolt + populate job) |
| Extra container? | **Yes** (optional profile) |

**Prerequisites for Mode C project vector (with Pgvector as target):**

1. **I1 complete:** Indexing Pipeline writes **PgvectorDocumentStore** on Postgres-Haystack (dual-plane §4.5).  
2. **Tenant meta** on every document (`user_id`, `ingest_id`) and filters on retrieve.  
3. **Embedder parity:** same `INDEXING_EMBEDDING_DIM` / model on app and MCP server.  
4. **DB connectivity** from MCP service to `db` (not only from FastAPI).  
5. **Session addressability:** tools take **`user_id` + `ingest_id`** — no Python session object.  
6. **KG-1 (if on MCP):** shared artifact volume / object store / durable graph — **independent** of Pgvector.  
7. **Auth + allowlist** on MCP (especially DO).

### Mode D — Hybrid catalog (recommended **product** path under Pgvector)

| Tool class | Host after I1 | Notes |
|------------|---------------|--------|
| `project_vector_search` | **Mode C FastMCP** (preferred) or in-process via same Pgvector factory | Pgvector enables true consolidation |
| `project_kg_query` | **hybrid** until shared KG load | In-process OK; MCP when artifacts shared |
| Fleet SQL / Neo4j / populate | Mode C when T* ready | Network backends already |
| Indexing / full recommend pipeline | **FastAPI** (or async job) | Not first-class MCP day one |

`AGENT_TOOLS=inprocess|mcp|hybrid` remains the switch (see MCP study §3.1).

---

## 5. Tool-by-tool consolidation matrix (catalog tools)

| Tool | As-built | After I1 | Consolidate to FastMCP? | Conditions |
|------|----------|----------|-------------------------|------------|
| `project_vector_search` | Session InMemory | **Pgvector** | **Yes — GO** | Mode C after I1 + tenant filters + embedder parity |
| `project_kg_query` | Session KG-1 | KG-1 + optional shared artifact | **Yes — conditional** | Mode C after shared KG load; hybrid until then |
| `retrieve_fleet_assets` | Not as-built | SQL on `db` | **Yes** | T1+; read-only allowlist |
| `neo4j_cypher_read` | Not as-built | Neo4j | **Yes** | Constrained templates; T3 data present |
| `trigger_neo4j_populate` | Not as-built | Job enqueue | **Yes** | T3; returns `job_id` |
| `run_indexing_from_request` | FastAPI ingest | Same; writer → Pgvector | **Partial** | Prefer FastAPI for Spring multipart; MCP only external hosts |
| Synthesis / LLM | `make_synthesis_node` | Same | **No** | Stays in LangGraph |

Stable names (`project_vector_search`, `project_kg_query`) stay identical across in-process and MCP.

### 5.1 Inventory: capabilities **not** previously listed as MCP tools

Codebase scan of `app/agents`, `app/pipelines`, `app/services` (beyond the catalog above).  
**Verdict key:** **GO** = good FastMCP candidate · **CONDITIONAL** = later / narrow · **NO** = keep FastAPI/pipeline · **INTERNAL** = library only, not a public MCP tool.

| Capability (code) | Role today | FastMCP? | Rationale |
|-------------------|------------|----------|-----------|
| `run_vector_search` (`pipelines/indexing/retrieval.py`) | Core of vector tool | **INTERNAL** | Implement shared core; expose only as `project_vector_search` |
| `query_knowledge_graph` (`pipelines/kg/query.py`) | Core of KG tool | **INTERNAL** | Same → `project_kg_query` |
| `run_indexing_pipeline` / `IndexingIngestService.ingest_from_project_spec` | Spring/multipart ingest | **CONDITIONAL** | Prefer REST; optional MCP for external agents; after I1 writes Pgvector; graph may be **SuperComponent** ([study](./indexing-pipeline-supercomponent.md)) — **not** including KG |
| `run_knowledge_graph` (`pipelines/kg/runner.py`) | Build KG-1 after index | **CONDITIONAL** | Heavy / LLM; keep on ingest path; MCP only if external agent triggers rebuild |
| `load_knowledge_graph_from_artifact` | Session hydrate | **GO** as helper | Server-side load for `project_kg_query`; not necessarily a separate agent tool |
| `ProjectKnowledgeSessionRegistry` put/get/delete | Process session map | **NO** | Not an agent tool; after Pgvector, registry is thinner (connection + meta) |
| `ProjectKnowledgeQAService.ask` / `run_project_knowledge_agents` | Multi-agent orchestration | **NO** | Orchestration stays in app; not an MCP tool |
| `RecommendationService.recommend_from_project_spec` | Full recommend saga | **NO** as one MCP tool | Too large; Spring stays on REST |
| `run_intake_front` | Need → units front | **NO** / later **CONDITIONAL** | Pipeline stage; optional future `decompose_project_needs` |
| Need decomposer (`StubNeedDecomposer` / `LlmNeedDecomposer`) | Text → needs | **CONDITIONAL** | Good future agent tool **after** Stage-1; needs LLM secrets on server |
| `source_text_resolver` | Resolve text input | **INTERNAL** | Ingest helper |
| `asset_candidate_filter` | Fleet candidate filter | **CONDITIONAL** | After fleet SQL on MCP/`db`; maps near `retrieve_fleet_assets` |
| `booking_availability_filter` | Availability | **CONDITIONAL** | Needs booking data on Postgres-Haystack mirror |
| `expand_quantity` | Qty expansion | **CONDITIONAL** | Pure/local logic; low priority for MCP |
| `catalog` / `seed_fleet` | Catalog seed helpers | **NO** (ops) | Dev/seed; not multi-agent prod tools |
| `predict_price_for_asset` / `predict_price_adapter` | Dynamic pricing | **GO** as FastMCP tool | Feature contract + guardrails: [`ml-pricing-multi-agent-fastmcp.md`](./ml-pricing-multi-agent-fastmcp.md); package model; fallback if pkl missing |
| `rank_rationale_generator` | Rank explanations | **CONDITIONAL** | LLM; optional after core recommend tools |
| Health (`/health`) | Liveness | **NO** / optional ping | Compose healthcheck; MCP already has hello “ping” in M1 |
| Pricing tables / ML train scripts (`ml-experiments/`) | Offline | **NO** | Not runtime agent tools |
| `RecommendationService.recommend_*` merge loop | Full recommend saga | **NO as MCP** | Becomes orchestrator graph **[5]–[8]** calling narrow tools |

#### 5.1.1 Recommend-path MCP tool names (post-[4] catalog)

| MCP name | Backed by | Role in recommend |
|----------|-----------|-------------------|
| `project_vector_search` / `project_kg_query` | Pgvector / KG-1 | Project context after [4] |
| `decompose_project_needs` | Need decomposer | Spec → unit needs |
| `retrieve_fleet_assets` | Postgres-Haystack SQL | Candidate pool |
| `filter_fleet_candidates` | `asset_candidate_filter` + SQL | Narrow candidates |
| `check_booking_availability` | booking filter + mirror | Availability |
| `neo4j_cypher_read` | Neo4j KG-2 | Graph neighborhood / fleet relationships |
| `predict_asset_price` | ML pricing model | Price each candidate |
| `generate_rank_rationale` | rank rationale generator | Optional explanation |
| `load_project_kg_artifact` | shared KG load helper | Enable MCP KG tool |

**Orchestrator-owned (not MCP):** final ranking policy, packaging Spring response, LangGraph edges.

**Do not** expose as MCP without allowlist review: free SQL, free Cypher write, shell, primary-DB write, full recommend monolith, model training.

### 5.3 Multi-Agent Orchestrator pattern (post-[4] recommend) — feasibility

| Claim | Feasible? | Notes |
|-------|-----------|--------|
| Orchestrator is “just agents calling FastMCP tools” | **GO** (target) | Plus **synthesis** node; tools never own final recommend |
| Recommend **only after [4]** indexing succeeds | **GO** | Hard gate in graph |
| Context from **Neo4j** + **Postgres-Haystack** + **pricing model** | **GO** | Separate tools; compose in agents |
| ML features from fleet rows | **GO** | category, condition, capacity, height, duration, distance |
| Live `period_utilization` in tool | **CONDITIONAL** | Phase **1e** + booking mirror; defaults until then |
| Neo4j as XGBoost features | **NO** without retrain | Graph = agent rank/explain context only |
| Stage-1 as-built already does this | **No** | Today: Q&A tools only; recommend is service/seed path |
| Prerequisites | I1, D1+/T1, T3, model package, M4 client | Hybrid until all ready; pricing detail study |

### 5.2 Pgvector cutover impact on consolidation (re-check)

| Claim | Feasible? |
|-------|-----------|
| Indexing Pipeline target = **PgvectorDocumentStore** | **Yes** (dual-plane §4.5) |
| Multi-user project files via meta + TTL | **Yes** |
| FastMCP sidecar reads same Pgvector as writers | **Yes** — same DSN, filters, embedder dim |
| Multi-replica API + multi-replica MCP without sticky sessions | **Yes** for **vector** after I1 |
| InMemory remains for CI / flag-off | **Yes** — MCP Mode C project vector tests need Pgvector (or Testcontainers) |
| Full dual-tool Mode C (`vector` + `kg`) without any shared volume | **No** — KG still needs a load path |

---

## 6. Target architecture (consolidated)

```text
Spring ──REST──► haystack-fast-api
                    │
                    │  ingest (in-process indexing preferred)
                    │  Q&A → LangGraph multi-agent (orchestration)
                    │
                    │  AGENT_TOOLS=mcp | hybrid | inprocess
                    ▼
              ┌─ inprocess: ProjectTool → shared lib → session store
              │
              └─ mcp/hybrid: mcp-haystack client
                              │
                              │ streamable HTTP MCP
                              ▼
                         FastMCP server (tool consolidation host)
                              ├─ project_vector_search → Pgvector (I1 required)
                              ├─ project_kg_query → shared KG load (conditional)
                              ├─ retrieve_fleet_* / filter_* → Postgres-Haystack
                              ├─ neo4j_* → Neo4j
                              ├─ trigger_* → populate job
                              └─ optional later: decompose_*, predict_*, rationale_*
```

**What consolidates:** tool **registration**, **validation**, **tenant checks**, and **backend access**.  
**What does not:** multi-agent **policy**, **sequencing**, **synthesis**, full recommend saga, or Spring’s public API.

---

## 7. Implementation sketch (non-normative)

### 7.1 Shared core (Mode A)

```text
app/tools/core/
  project_vector.py   # pure: store + query → hits
  project_kg.py       # pure: kg + query → hits
  fleet_sql.py        # pure: conn + filters → rows
app/agents/tools.py   # ProjectTool wrappers (today + hybrid)
mcp_server/           # FastMCP app registering same core functions
```

### 7.2 FastMCP registration (illustrative)

```python
# mcp_server/main.py — conceptual
from fastmcp import FastMCP
from app.tools.core.project_vector import search_project_vectors
from app.tools.core.project_kg import query_project_kg

mcp = FastMCP("haystack-project-tools")

@mcp.tool()
def project_vector_search(user_id: str, ingest_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Dense retrieve for one project ingest session. Tenant args required."""
    return search_project_vectors(user_id=user_id, ingest_id=ingest_id, query=query, top_k=top_k)

@mcp.tool()
def project_kg_query(user_id: str, ingest_id: str, query: str, limit: int = 10) -> list[dict]:
    """KG-1 query for one project ingest session. Tenant args required."""
    return query_project_kg(user_id=user_id, ingest_id=ingest_id, query=query, limit=limit)
```

**Critical difference vs today:** tools take **`user_id` / `ingest_id`** (and resolve store/KG inside the server), not a Python `session` object that only exists in the API process.

### 7.3 LangGraph client side (when M4)

Same pattern as MCP study: `MCPTool(name="project_vector_search", server_info=StreamableHttpServerInfo(url=...))`; nodes pass tenant ids from agent state (already present: `user_id`, `ingest_id` in `ProjectKnowledgeAgentState`).

---

## 8. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Separate MCP cannot see **InMemory** sessions | **High** pre-I1 | **I1 Pgvector** is the fix for vector; Mode B only as temporary bridge |
| Embedder / dim mismatch app vs MCP vs Pgvector column | **High** after I1 | Single settings source; fail fast on dim check |
| Dual implementation drift (in-process vs MCP) | Medium | Mode A shared core; contract tests on tool names + hit shape |
| Extra latency (HTTP hop + embedder on server) | Medium | Measure M4 stub parity; co-locate sidecar on DO |
| Multi-replica without Pgvector | High | Do not scale out project Q&A until I1 |
| KG-1 still process-local after I1 | Medium | Hybrid `AGENT_TOOLS`; shared artifact volume for MCP KG |
| Over-broad MCP tools (shell, free SQL, full recommend) | High | Allowlist §5 / §5.1; deny list in M0 |
| Pricing model not multi-instance safe | Medium | Keep pricing on FastAPI or dedicated service until hardened |
| Indexing multipart via MCP | Medium | Keep Spring ingest on FastAPI; MCP optional later |
| Auth on public MCP | High on DO | Private network + API key/mTLS; no public bind |

---

## 9. Phasing (aligned with existing tracks)

| Phase | Consolidation work | Depends on |
|-------|-------------------|------------|
| **C0** | This study + OpenSpec allowlist (M0) | — |
| **C1** | Mode A: extract shared tool core; keep in-process wrappers | — |
| **C2** | Mode B **or** M1 hello FastMCP (ping only) | Network |
| **I1** | **Indexing → PgvectorDocumentStore** (dual-plane Track I) | Postgres-Haystack + pgvector |
| **C3** | Mode C fleet tools on server | T1/T3 |
| **C4a** | Mode C **`project_vector_search`** on server (Pgvector) | **I1** |
| **C4b** | Mode C **`project_kg_query`** on server | Shared KG load path |
| **C5** | Recommend tools: fleet filter, booking, **`predict_asset_price`**, Neo4j read | D/T + model package |
| **C6** | Recommend agent graph **[5]–[8]** after [4]; synthesis in orchestrator | C4a + C5 |
| **C7** | `AGENT_TOOLS=mcp` default for selected envs; parity tests | M4 + C6 |

**Do not block** Stage-1 agents or T0–T1 on MCP. **Do prioritize I1** before Mode C project vector.

Order of preference for delivery:

1. **C1 (shared core)** — always  
2. **I1 Pgvector** — unlocks multi-user + MCP sidecar vector  
3. **Fleet on FastMCP (C3)** when Plane A ready  
4. **Project vector on FastMCP (C4a)** after I1  
5. **Project KG on FastMCP (C4b)** when load path ready  
6. Optional Mode B only if MCP surface needed **before** I1  

---

## 10. Decision criteria (when to call consolidation “done”)

| Criterion | Pass condition |
|-----------|----------------|
| Catalog | All agent-invoked tools appear on one allowlist (FastMCP and/or hybrid flag) |
| Names | MCP tool names match as-built constants (`TOOL_PROJECT_*`) |
| Tenant | Every project/fleet read tool requires `user_id` (+ `ingest_id` where applicable) |
| Orchestration | LangGraph graph shape unchanged; synthesis not on MCP |
| State | Project tools do not depend on API-only closures when Mode C is enabled |
| Parity | Stub Q&A tests: in-process vs MCP same `sources_used` / hit contracts |
| Ops | Profile `mcp` optional; default dev stack remains light |

---

## 11. Alternatives considered

| Option | Why not primary |
|--------|-----------------|
| Keep tools forever only in `app/agents/tools.py` | Works for Stage 1; weak for external agents, fleet ops packaging, multi-language clients |
| Stdio MCP per tool via `uvx` | Poor multi-user / multi-replica (MCP study Option C) |
| Neo4j official MCP only | Does not cover project vector/KG or fleet SQL |
| Move LangGraph into FastMCP | Wrong layer; harder testing; Spring path still needs FastAPI |

---

## 12. Open questions

1. Ship **I1 then Mode C vector only**, or still use **Mode B** before I1? (**Recommend: I1 first.**)  
2. KG-1 durable form for server load: shared volume JSON only, or migrate project graph earlier?  
3. One unified FastMCP image vs split “project MCP” + “fleet MCP”? (Default: **one** allowlisted server.)  
4. Should CI run MCP parity jobs only under profile `mcp` + Testcontainers Pgvector?  
5. Which §5.1.1 optional tools (needs / price / rationale) enter OpenSpec first?  

---

## 13. References

- As-built agents: `app/agents/tools.py`, `app/agents/graph.py`, `app/agents/nodes.py`  
- Session / KG: `app/services/project_knowledge_session.py`, `app/pipelines/kg/*`  
- Indexing / retrieve: `app/pipelines/indexing/*`, `app/services/indexing.py`  
- Recommend path: `app/services/recommendations.py`, `app/pipelines/intake_front.py`, filters, pricing  
- MCP deploy study: [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md)  
- Dual-plane §4.5 Pgvector / §4.6 MCP: [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md)  
- [FastMCP](https://gofastmcp.com/) — server framework for MCP tools  
- [Haystack MCP / mcp-haystack](https://haystack.deepset.ai/integrations/mcp) — client  
- [PgvectorDocumentStore](https://docs.haystack.deepset.ai/docs/pgvectordocumentstore)  

---

## 14. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial study: consolidate multi-agent tools onto FastMCP; Modes A–D; as-built session constraint; GO with conditions |
| **1.1.0** | 2026-08-10 | **Pgvector target re-check:** Mode C vector **GO** after I1; KG residual; **§5.1** inventory of unlisted pipeline/service capabilities |
| **1.2.0** | 2026-08-10 | **Post-[4] recommend:** orchestrator = agents + FastMCP tools; pricing **GO**; §5.3; Neo4j + Postgres-Haystack + ML model |
| **1.3.0** | 2026-08-10 | Link **ml-pricing** study; feature assembly + 1e util; Neo4j not model input |

---

## 15. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Can FastMCP consolidate multi-agent tools? | **Yes (GO)** — stronger after **Pgvector I1** |
| InMemory → Pgvector cutover | **GO** (product target); keep InMemory for CI |
| Replace LangGraph with FastMCP? | **No** — consolidate **tools** only |
| **Recommend after [4]?** | **Yes** — agents call FastMCP; orchestrator synthesizes |
| Recommend tool backends | **Postgres-Haystack** + **Neo4j** + **ML pricing** + project Pgvector/KG-1 |
| Best engineering pattern | **Mode A** shared core + thin wrappers |
| Early MCP surface without extra container | **Mode B** optional; prefer **I1 first** |
| Production compose / DO | **Mode C** sidecar; vector on **Pgvector** |
| `project_vector_search` on sidecar | **Yes after I1** |
| `project_kg_query` on sidecar | **Conditional** — shared KG load / hybrid |
| `predict_asset_price` on FastMCP | **Yes** — see [`ml-pricing-multi-agent-fastmcp.md`](./ml-pricing-multi-agent-fastmcp.md) |
| Unlisted pipeline steps as MCP | **Selective** (§5.1); not full recommend monolith |
| Fleet tools on sidecar | **Yes** after T1/T3 |
| Indexing multipart | Prefer **in-process** FastAPI → Pgvector writer |
| Client for agents | **mcp-haystack** when `AGENT_TOOLS=mcp` |
| Phasing | C1 → **I1** → C3 fleet → C4a vector → **C5 pricing/fleet recommend tools** → **C6 recommend graph** |

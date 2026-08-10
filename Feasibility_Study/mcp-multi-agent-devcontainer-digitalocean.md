# Feasibility Study: MCP Server for Multi-Agent  
## Devcontainer / Docker Compose and DigitalOcean

| Field | Value |
|-------|--------|
| **Document type** | Architecture / integration feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.6.0 |
| **Application** | `haystack-fast-api` multi-agent + tool layer |
| **Local platform** | [Heavy-Rental Haystack-Fast-API devcontainer](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API) |
| **Cloud** | DigitalOcean (Droplet / DOKS; no managed MCP product) |
| **Related** | Dual-plane §4.6/§11.12 · consolidation · ml-pricing · synthesis recommend · [`mcp-server-pyproject-and-config-repo-compose.md`](./mcp-server-pyproject-and-config-repo-compose.md) (implement server/deps + config-repo PR) · spring resilience |

---

## 1. Executive summary

### Question

Is a **Model Context Protocol (MCP) server** suitable for **multi-agent** tools in this project:

1. On the **current** docker-compose / devcontainer stack (`db`, `db-sync`, `neo4j`, app on `heavy-rental-network`)?  
2. On **DigitalOcean** in production-like deployments?

### Verdicts

| Question | Result |
|----------|--------|
| MCP for multi-agent **feasible**? | **Yes** |
| Required for Stage-1 project Q&A **today**? | **No** — keep **in-process** tools (`app/agents/tools.py`) |
| Best local pattern? | Optional Compose service **`mcp-haystack`** (**FastMCP server**) + app **`mcp-haystack` client** over streamable HTTP |
| Best DO pattern? | Same **server** image as **sidecar**; app holds **mcp-haystack** client; private VPC to Postgres-Haystack + Neo4j |
| Stdio MCP (`uvx` per tool) in multi-replica? | **Poor fit** — prefer HTTP/streamable transport |
| MCP as source of truth? | **No** — tool **transport** only |
| Day-one with Kafka + full free ReAct over MCP? | **No** — phase after sync/Neo4j populate (R4 after D3/T3) |

**Overall:** **GO for a later MCP stack (R4/M\*)**: **FastMCP (server) + mcp-haystack (Haystack client)**. Not a rewrite of Stage-1 agents. Spring continues to call **FastAPI HTTP**; MCP is how **agents** (and optional external clients) call **tools**.

**Tool consolidation:** FastMCP **can** host a consolidated tool catalog for multi-agent use. Full analysis (shared core, in-process vs sidecar, InMemory session constraint, Modes A–D):  
[`fastmcp-tool-consolidation-multi-agent.md`](./fastmcp-tool-consolidation-multi-agent.md).

| Consolidation snapshot | Result |
|------------------------|--------|
| Logical catalog on FastMCP | **GO** |
| LangGraph stays orchestrator | **GO** |
| **InMemory → Pgvector (I1)** | **GO** — product DocumentStore target |
| Sidecar **`project_vector_search`** after I1 | **GO** — shared Pgvector + tenant filters |
| Sidecar **`project_kg_query`** | **Conditional** — shared KG load / hybrid |
| Sidecar project tools **pre-I1** (InMemory only) | **No** for vector |
| Sidecar fleet tools | **GO** after T1/T3 |
| Extra pipeline capabilities as MCP | **Selective** — see consolidation study §5.1 |
| **Recommend after indexing [4]** via FastMCP tools | **GO** — fleet SQL + Neo4j + **ML pricing** + project context; synthesis in orchestrator |
| Preferred build path | Shared core → **I1** → fleet/Neo4j MCP → pricing tool → **recommend agents** |

---

## 2. Current setup (baseline)

### 2.1 As-built multi-agent (app)

| Piece | Today |
|-------|--------|
| Orchestration | LangGraph fixed sequence: research → graph → synthesis |
| Tools | **In-process** `project_vector_search`, `project_kg_query` |
| Session | `ProjectKnowledgeSession` (DocumentStore + KG-1) after ingest |
| MCP | **Not deployed**; OpenSpec marks Hayhooks/MCP as **optional** |

### 2.2 As-built devcontainer / compose

| Service | Role |
|---------|------|
| `haystack-fast-api` | App workspace; env to `db`, Neo4j |
| `db` (`postgres-haystack`) | Domain + future Pgvector |
| `db-sync` | Merge from `postgres-primary` (default **daily**) |
| `neo4j` | Neo4j 5 (DocumentStore path today; fleet projection planned T3) |
| Network | External `heavy-rental-network` |

**No MCP service** in compose today.

### 2.3 What MCP would add

```text
Spring ──HTTP──► FastAPI (ingest / Q&A / recommend)
                    │
                    ▼
              Multi-Agent Orchestrator (LangGraph)
              • [4] indexing tool (gate)
              • AFTER [4]: agents call FastMCP tools (target)
              • synthesis → recommendation
                    │
        ┌───────────┴───────────┐
        │ in-process tools (now)│
        │        and/or         │
        │ mcp-haystack client ──HTTP──► FastMCP server
        │                         ├─► Postgres-Haystack (fleet SQL + Pgvector)
        │                         ├─► Neo4j KG-2 (graph context)
        │                         ├─► ML pricing model (predict_asset_price)
        │                         └─► trigger neo4j-populate job
        └───────────────────────┘
```

Spring does **not** need to speak MCP for the recommender portal path.

---

## 3. MCP options suitable for this stack

| Option | Description | Local compose | DigitalOcean | Recommendation |
|--------|-------------|---------------|--------------|----------------|
| **A. In-process only** | Keep `app/agents/tools.py` | No new service | Same process as API | **Default now (R1–R2)** |
| **B. FastMCP server + mcp-haystack client** | **Server:** FastMCP process with allowlisted tools · **Client:** PyPI **`mcp-haystack`** (`MCPTool` + HTTP transport) in the app | New service + app dep | Sidecar server + app client | **Recommended for R4** |
| **C. MCP stdio + uvx** | Subprocess tools per call | Fragile in long-lived multi-user containers | Poor multi-replica | **Avoid for prod agents** |
| **D. Neo4j official MCP only** | Cypher / GraphRAG MCP; project tools stay in-process | Optional second container | Same | **Hybrid OK** after T3 |
| **E. Hayhooks pipeline tools** | Optional pipeline HTTP edge | Optional | Optional | Not fleet SoT; optional complement |

### Transport choice

| Transport | Fit |
|-----------|-----|
| **Streamable HTTP / HTTP MCP** (e.g. `StreamableHttpServerInfo` in **mcp-haystack**) | **Best** for Docker Compose + DO — one long-lived server, healthchecks, network DNS (`mcp-haystack:8100`) |
| **SSE-only MCP** | Possible depending on server; still server-side process |
| **Stdio** | Fine for laptop demos; **not** primary for compose multi-agent |

---

## 3.1 Recommended stack detail: FastMCP server + mcp-haystack client

This is the **canonical stack** for this project when MCP is adopted.

### Server vs client

| Role | Technology | Runs where | Responsibility |
|------|------------|------------|----------------|
| **MCP server** | **FastMCP** (or compatible MCP HTTP server) | Compose service / DO sidecar named e.g. `mcp-haystack` | Register tools (`project_vector_search`, …); enforce allowlist + tenant args; open connections to `db` / Neo4j / populate job |
| **MCP client** | **`mcp-haystack`** (Haystack core integration) | **Inside `haystack-fast-api`** (uv env) | Discover/invoke remote tools via `MCPTool`; plug into LangGraph nodes or Haystack `ToolInvoker` / chat generators |
| **Agent graph** | LangGraph (existing) | App process | Policy, sequencing, synthesis; does not embed tool SQL |

```text
┌─────────────────────────────────────────────────────────────┐
│ haystack-fast-api                                           │
│  LangGraph: research → graph → synthesis                    │
│       │                                                     │
│       │  AGENT_TOOLS=mcp                                    │
│       ▼                                                     │
│  mcp-haystack CLIENT                                        │
│    MCPTool("project_vector_search", server_info=…)          │
│    MCPTool("project_kg_query", …)                           │
│    StreamableHttpServerInfo(url=MCP_SERVER_URL)             │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP MCP (streamable)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ mcp-haystack SERVER (FastMCP)                               │
│  tools: project_*, retrieve_fleet_*, neo4j_*, trigger_*     │
│  → db · neo4j · neo4j-populate                              │
└─────────────────────────────────────────────────────────────┘
```

### Packages and install (illustrative)

| Component | Install | Notes |
|-----------|---------|--------|
| App client | `uv add mcp-haystack` (when M4) | [Integration docs](https://haystack.deepset.ai/integrations/mcp); depends on Haystack 2.x tool APIs |
| Server | Image with `mcp` / FastMCP + project tool modules | Pin versions in server `pyproject` or requirements |
| Optional | Official Neo4j MCP binary/container | Hybrid graph exploration only |

### Client usage sketch (non-normative)

Exact class names follow the installed `mcp-haystack` version; pattern from Haystack MCP examples:

```python
import os
from haystack_integrations.tools.mcp import MCPTool, StreamableHttpServerInfo

server_info = StreamableHttpServerInfo(url=os.environ["MCP_SERVER_URL"])
# e.g. http://mcp-haystack:8100/mcp

tools = [
    MCPTool(name="project_vector_search", server_info=server_info),
    MCPTool(name="project_kg_query", server_info=server_info),
    # later: retrieve_fleet_assets, trigger_neo4j_populate, neo4j_cypher_read
]

# LangGraph research/graph nodes call tools by name with user_id + ingest_id
# Hybrid: if AGENT_TOOLS=inprocess, keep app.agents.tools.ProjectTool instead
```

### LangGraph wiring (feature flag)

| `AGENT_TOOLS` | Behaviour |
|---------------|-----------|
| `inprocess` (default) | `app/agents/tools.py` — **current as-built**; no MCP server required |
| `mcp` | All agent tools via **mcp-haystack** client → FastMCP server |
| `hybrid` | Project tools in-process; fleet/Neo4j tools via MCP (or reverse) during migration |

Map stable names so traces stay comparable:

| As-built in-process | MCP tool name (same string) |
|---------------------|-----------------------------|
| `project_vector_search` | `project_vector_search` |
| `project_kg_query` | `project_kg_query` |

### Env matrix

| Variable | Example | Owner |
|----------|---------|--------|
| `AGENT_TOOLS` | `inprocess` | App |
| `MCP_SERVER_URL` | `http://mcp-haystack:8100/mcp` | App (client) |
| `MCP_API_KEY` | secret | App + server |
| `PGHOST` / `PG*` | `db` | **Server** |
| `NEO4J_URI` / user / password | `bolt://neo4j:7687` | **Server** |

### What Spring uses

**Nothing MCP-related.** Portal/Spring → FastAPI REST (see Spring resilience study). Only the **agent runtime** (and optional IDE agents) use the MCP server.

### Non-goals for this stack

- Replacing FastAPI public API with MCP  
- Using only Neo4j MCP without custom project tools  
- Stdio MCP as the production multi-replica path  

---

## 4. Recommended tool catalog

Align with dual-plane study §4.6. Prefer **narrow, auditable** tools.

### 4.1 Project plane (after ingest)

| Tool | Backing | Notes |
|------|---------|--------|
| `project_vector_search` | **As-built:** InMemory · **Target (I1):** **PgvectorDocumentStore** | **Require** `user_id` + `ingest_id`; Mode C **GO** after I1 |
| `project_kg_query` | KG-1 session or **shared** artifact load | Tenant scoping; Mode C **conditional** (not fixed by Pgvector alone) |

### 4.2 Fleet plane (after Track D / T\*)

| Tool | Backing | Notes |
|------|---------|--------|
| `retrieve_fleet_assets` | SQL read on `db` (mirrored domain) | Read-only; allowlisted tables/columns |
| `neo4j_cypher_read` | Neo4j fleet labels | Parameterized templates; **no** free-form destructive Cypher |
| `trigger_neo4j_populate` | Enqueue / call populate job | Needs **T3** service; returns `job_id`, not full rebuild in request |

### 4.3 Indexing

| Tool | Recommendation |
|------|----------------|
| `run_indexing_from_request` | Prefer **in-process** from FastAPI/Spring ingest path (latency, multipart, idempotency). After I1, pipeline **writes Pgvector**. Expose via MCP only for **external** agent hosts if needed. |

### 4.3.1 Optional later tools (code exists; not Stage-1 agent tools)

Inventory of `app/pipelines` / `app/services` capabilities **not** in the Stage-1 LangGraph tool map. Full table: consolidation study **§5.1**.

| Proposed MCP name | Source | FastMCP? |
|-------------------|--------|----------|
| `load_project_kg_artifact` | `load_knowledge_graph_from_artifact` | **GO** helper for KG tool |
| `decompose_project_needs` | need decomposer | **CONDITIONAL** Stage 2+ |
| `filter_fleet_candidates` | `asset_candidate_filter` | **CONDITIONAL** after fleet SQL |
| `check_booking_availability` | `booking_availability_filter` | **CONDITIONAL** after booking mirror |
| `predict_asset_price` | pricing client / ML model | **GO** — feature list, guardrails, 1e util: [ml-pricing study](./ml-pricing-multi-agent-fastmcp.md); package `model.pkl` + feature_schema |
| `generate_rank_rationale` | `rank_rationale_generator` | **CONDITIONAL** LLM |
| Full `recommend_from_project_spec` as **one** MCP tool | `RecommendationService` | **NO** — use **narrow tools** + orchestrator **[5]–[8]** |
| `run_project_knowledge_agents` / QA service | multi-agent graph | **NO** as MCP tool — **is** the orchestrator |
| `seed_fleet` / offline `ml-experiments` | seed / train | **NO** |

### 4.4 What not to put on MCP day one

- Arbitrary shell  
- Unscoped SQL  
- Unscoped Cypher write/delete  
- Direct writes to `postgres-primary`  
- Full recommend pipeline as one tool  
- Model training  

### 4.5 Consolidation mapping (as-built → FastMCP) under Pgvector target

Stage-1 tools are **session closures** today (`build_session_tools(session)` in `app/agents/tools.py`). Consolidation does **not** move LangGraph onto FastMCP; it moves **tool hosting**. **I1 Pgvector** makes sidecar vector search feasible.

| As-built | FastMCP tool | Needs for separate container |
|----------|--------------|------------------------------|
| `build_project_vector_search_tool(session)` | `project_vector_search(user_id, ingest_id, query, top_k)` | **I1 Pgvector** + same embedder dim + DSN on server |
| `build_project_kg_query_tool(session)` | `project_kg_query(user_id, ingest_id, query, limit)` | Shared KG artifact / durable load path (**not** solved by Pgvector alone) |
| (future) fleet SQL / Neo4j / trigger | Same names as §4.2 | `db` + Neo4j + T3 job |
| (optional) §4.3.1 tools | See names above | Per-tool data + secrets |

**Engineering modes** (detail in consolidation study):

| Mode | What | Extra container |
|------|------|-----------------|
| **A** Shared core library + dual wrappers | Always | No |
| **B** In-process FastMCP | Bridge only if needed **before** I1 | No |
| **C** Sidecar FastMCP | Compose/DO; **vector GO after I1** | Yes (`profile mcp`) |
| **D** Hybrid catalog | Vector MCP post-I1; KG in-process until shared load; fleet on MCP | Optional |

---

## 5. Devcontainer / Docker Compose plan

### 5.1 Target local topology (after T4 + M\*)

```text
heavy-rental-network
  postgres-primary          # Spring stack
  db (postgres-haystack)
  db-sync
  neo4j
  neo4j-populate            # T3 — optional dependency of MCP tool
  haystack-fast-api         # LangGraph agents (in-process and/or MCP client)
  mcp-haystack              # NEW optional — MCP HTTP server :8100
```

### 5.2 Phases M0–M7

| Phase | Name | Work | Depends on | Exit criteria |
|-------|------|------|------------|---------------|
| **M0** | Spec & allowlist | OpenSpec/design: tools, auth, Safeguards; MCP not SoT | — | Written allowlist + denial list |
| **M1** | Hello MCP **server** on compose | Optional **FastMCP** service; “ping”/echo; invoke via raw MCP client or curl | Network only | Tool invoke succeeds on network DNS |
| **M2** | Project read tools on **server** | Wrap vector + KG query with tenant args | Ingest + session (as-built or I1) | Server tools return scoped hits |
| **M3** | Fleet tools on **server** | SQL read + constrained Neo4j read + `trigger_neo4j_populate` | **T1+** fresh mirror; **T3** populate job | Server can list assets / trigger populate safely |
| **M4** | **mcp-haystack client** in app | `uv add mcp-haystack`; `MCPTool` + `StreamableHttpServerInfo`; `AGENT_TOOLS=mcp\|hybrid` | M2 | LangGraph Q&A parity vs in-process (stub) |
| **M5** | Recommend tools on server | Fleet filters + **`predict_asset_price`** (bake/mount `ml-experiments/artifacts`, same feature_schema; optional live util from `db` when 1e ready) | M3 + model package + T1/T3 | Tools return candidates + clamped `price_per_day` |
| **M6** | Recommend agent graph after [4] | Orchestrator **[5]–[8]**: agents → FastMCP only → synthesis | M4–M5 + I1 | End-to-end recommend from tool context |
| **M7** | Cloud hardening | Auth (API key/mTLS), no public bind, secrets, resource limits | M1–M6 | DO checklist green |

**Order with §11 T-phases:**  
`T0 → T1 → T3 → T4` then `M1 → M2 → M3 → M4 → M5 → M6` (M7 with DO).  
Do **not** block T0–T1 on MCP. Recommend path needs **I1 + fleet + pricing model** before M6.

### 5.3 Illustrative Compose service (not applied — study only)

```yaml
  # Optional — enable when M1 starts
  mcp-haystack:
    container_name: mcp-haystack
    # build: ./mcp-server  OR image with FastMCP + project code
    restart: unless-stopped
    environment:
      PGHOST: db
      PGPORT: "5432"
      PGDATABASE: heavy_rental
      PGUSER: postgres
      PGPASSWORD: postgres
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: heavyrental
      MCP_HOST: "0.0.0.0"
      MCP_PORT: "8100"
      # Optional: only allow internal network clients
    ports:
      - "8100:8100"   # dev only; omit public publish on DO
    depends_on:
      db:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    networks:
      - heavy-rental-network
```

**App env (when M4):** e.g. `MCP_SERVER_URL=http://mcp-haystack:8100/mcp`, `AGENT_TOOLS=mcp`.

### 5.4 Config repo file checklist

| File | Action |
|------|--------|
| `.devcontainer/docker-compose.yml` | Optional `mcp-haystack` service (profile `mcp` recommended so default stack stays light) |
| `.devcontainer/devcontainer.json` | Optional forwardPorts `8100`; document MCP URL |
| New `mcp-server/` or script | **FastMCP server** + tool implementations |
| App `pyproject.toml` / uv (M4) | **`mcp-haystack`** client dependency |
| `postCreate` / deps | Optional; prefer lockfile `uv add mcp-haystack` in app |
| Specs in config repo | Optional `004-haystack-mcp` |

Use Compose **profiles** (`profiles: ["mcp"]`) so everyday dev without MCP stays simple:

```bash
docker compose --profile mcp up -d
```

### 5.5 Two implementation styles for tools that need app state

| Style | Pros | Cons |
|-------|------|------|
| **1. MCP process imports app packages** | Direct store access | Couples deploy; heavier image |
| **2. MCP calls FastAPI internal HTTP** | Clear boundary; reuses auth/session | Extra hop; must expose internal routes |

**Recommendation:** start **M1–M2** with style **2** (internal routes or shared library carefully versioned); avoid MCP writing primary.

---

## 6. DigitalOcean feasibility

### 6.1 What DO provides / does not

| Need | DO support |
|------|------------|
| Run MCP process | **Yes** — App Platform, Droplet, or DOKS Deployment |
| Managed “MCP hosting” product | **No** |
| Reach Managed PG + Neo4j Droplet | **Yes** — VPC / private networking / trusted sources |
| Secrets | **Yes** — DO secrets / env |

### 6.2 Recommended DO shape

```text
VPC
├── Droplet/DOKS: haystack-fast-api
├── Droplet/DOKS: mcp-haystack (sidecar or sibling Service)
├── Managed PG (Postgres-Haystack + pgvector)  OR droplet PG
├── Neo4j droplet
└── (optional) neo4j-populate worker
```

| Practice | Guidance |
|----------|----------|
| Bind address | Listen on private interface; **do not** expose MCP on public internet without auth |
| Auth | API key, mTLS, or mesh identity between FastAPI and MCP |
| Scaling | Stateless MCP + shared `db`/Neo4j; avoid stdio workers per replica |
| Resources | Small CPU/RAM initially (I/O bound to PG/Neo4j) |
| Observability | Request id / `user_id` / tool name logs; metrics on tool latency & errors |

### 6.3 Mapping local → cloud

| Local | DigitalOcean |
|-------|--------------|
| FastMCP **server** `mcp-haystack:8100` | Same image as private Service / sidecar |
| App **mcp-haystack client** + `MCP_SERVER_URL` | Same env on API deployment |
| `db` / `neo4j` hostnames | Managed PG host + Neo4j private IP |
| Compose profile `mcp` | Feature flag / separate Deployment |
| Port publish 8100 to laptop | Omit public LB; only app (client) talks to MCP server |

---

## 7. Security and multi-tenant rules

| Rule | Rationale |
|------|-----------|
| Project tools **require** `user_id` (+ `ingest_id`) | Prevent cross-tenant retrieval |
| Fleet SQL **read-only** + allowlist | MCP must not mutate OLTP mirror casually |
| Neo4j writes only via **populate job** tool | Controlled graph rebuild/upsert |
| Cypher templates only | Reduce injection / drop-database risk |
| No credentials in tool responses | Logs/redaction |
| Rate limit tool calls | Protect PG/Neo4j under agent loops |
| Align with OpenSPDD Safeguards | Fix prompt/spec first; tool allowlist is the hard boundary |

---

## 8. Feasibility matrix

| Criterion | Verdict |
|-----------|---------|
| MCP with LangGraph multi-agent | **Feasible** |
| Fit current Stage-1 without MCP | **Yes — preferred initially** |
| Fit Heavy-Rental compose | **Feasible** as optional service/profile |
| Fit DigitalOcean | **Feasible** as sidecar; DIY process |
| Replace Spring→FastAPI REST | **No** — different concern |
| Replace `db-sync` / CDC | **No** |
| Replace indexing FileTypeRouter | **No** |
| Enable external agent hosts (Cursor, etc.) later | **Yes** (HTTP MCP) with strong auth |

---

## 9. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Premature MCP complexity | High | M0–M1 only after R1/T1 stable |
| Agent free-form tool abuse | High | Allowlist + constrained Cypher/SQL |
| Public MCP on DO | High | Private network + auth |
| Stdio MCP in multi-replica | Medium | HTTP server only |
| Double path (in-process vs MCP) drift | Medium | Shared library or single implementation behind flag |
| Session state not visible to MCP process | Medium | Internal HTTP to app or shared Pgvector + session registry store |
| Confusing Neo4j DocumentStore vs fleet tools | Medium | Label/DB isolation (dual-plane §11.6) |

---

## 10. Relation to other tracks

| Track / phase | MCP dependency |
|---------------|----------------|
| **T0–T1** db-sync | MCP not required |
| **T3–T4** neo4j-populate | Enables `trigger_neo4j_populate` tool (M3) |
| **I1** Pgvector | Better multi-replica project tools via MCP |
| **R1–R2** agent + Q&A | In-process tools |
| **R4–R5** | MCP packaging + cross-plane agents |
| **C1–C2** Spring resilience | Spring still uses FastAPI REST/SSE jobs, not MCP |

```text
T0 → T1 → T3 → T4 ──► M1 → M2 → M3 → M4 → M5 → M6 (recommend)
R1 → R2 ─────────────► R4 (MCP) → R5
```

---

## 11. Suggested spikes

1. **M1:** FastMCP “ping” **server** on `heavy-rental-network`; invoke from app container.  
2. **M2:** Server tool `project_vector_search` with fixture ingest + tenant args.  
3. **M4:** `uv add mcp-haystack`; `MCPTool` + `StreamableHttpServerInfo` calls M2 tool from LangGraph stub.  
4. **Compare latency:** in-process tool vs mcp-haystack client hop (stub mode).  
5. **M3 dry-run:** `trigger_neo4j_populate` returns job id without full graph load.  
6. **Auth fail closed:** client without API key rejected by server.  
7. **Tenant isolation:** two `user_id`s cannot read each other’s chunks via MCP.

---

## 12. Open questions

1. Should MCP run **in-process** in the same image as FastAPI first (simpler) vs always separate container?  
2. Will external tools (IDE agents) call MCP, or only LangGraph inside the app?  
3. Auth mechanism for MCP on DO (API key vs mTLS)?  
4. Single Neo4j MCP (official) + custom project MCP vs one unified server?  
5. After I1, does MCP read Pgvector directly or only via app API?  

---

## 13. References

- Dual-plane study: [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4.6, §10 R4–R5, §11.12  
- **Tool consolidation:** [`fastmcp-tool-consolidation-multi-agent.md`](./fastmcp-tool-consolidation-multi-agent.md)  
- Spring wire: [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md)  
- Devcontainer: [Haystack-Fast-API](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)  
- [Haystack MCP integration](https://haystack.deepset.ai/integrations/mcp) — **`mcp-haystack` client**  
- [mcp-haystack on PyPI](https://pypi.org/project/mcp-haystack/)  
- [FastMCP](https://gofastmcp.com/) — **server** framework  
- [Neo4j MCP / GenAI](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)  
- OpenSpec: `openspec/specs/knowledge-graph/`, `equipment-recommendation/` (MCP optional)  
- As-built tools: `app/agents/tools.py`, session: `app/services/project_knowledge_session.py`  

---

## 14. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial MCP multi-agent feasibility: compose + DO; phases M0–M5 |
| **1.0.1** | 2026-08-10 | DocumentStore path for agents: InMemory/Pgvector only |
| **1.1.0** | 2026-08-10 | **FastMCP server + mcp-haystack client** stack detail, LangGraph flag, install/env matrix |
| **1.2.0** | 2026-08-10 | Link + §4.5 **tool consolidation** (as-built session constraint; Modes A–D pointer) |
| **1.3.0** | 2026-08-10 | **Pgvector I1:** sidecar vector **GO**; §4.3.1 optional tools from pipelines/services; KG residual |
| **1.4.0** | 2026-08-10 | **Post-[4] recommend:** orchestrator + FastMCP (fleet, Neo4j, pricing); phases M5–M6 |
| **1.5.0** | 2026-08-10 | Link **ml-pricing** study; M5 model artifacts + feature contract |
| **1.6.0** | 2026-08-10 | Link **implementation** study: pyproject deps + config-repo Compose PR |

---

## 15. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Adopt MCP for multi-agent? | **Yes, later (R4 / M\*)** |
| Required for Stage-1 now? | **No** — in-process tools |
| **DocumentStore target** | **PgvectorDocumentStore** (I1); InMemory for CI |
| **Consolidate tools onto FastMCP?** | **Yes** — not orchestration / not final recommend |
| **Recommend after [4]?** | **Yes** — agents run FastMCP tools; orchestrator synthesizes |
| Recommend backends via tools | **Postgres-Haystack** + **Neo4j** + **ML pricing** + project context |
| **Server** | **FastMCP** (Compose/DO service `mcp-haystack`) |
| **Client** | **mcp-haystack** in app (`MCPTool` + `StreamableHttpServerInfo`) |
| Local deploy | Optional Compose service + **profile `mcp`** + app `MCP_SERVER_URL` |
| Cloud deploy | Server sidecar on DO; app holds client; private network; auth required |
| Transport | **HTTP / streamable HTTP**, not stdio for prod |
| Spring integration | Still **REST to FastAPI**; Spring does **not** use mcp-haystack |
| `project_vector_search` on sidecar | **After I1 Pgvector** |
| `project_kg_query` on sidecar | Shared KG load or hybrid |
| `predict_asset_price` | **GO** — details in [`ml-pricing-multi-agent-fastmcp.md`](./ml-pricing-multi-agent-fastmcp.md) |
| Optional pipeline MCP tools | Selective (§4.3.1); no full recommend monolith |
| First compose work | **Not before T1/T3** for fleet tools; M1 server hello anytime; M4 client wiring |
| **Implement server + pyproject?** | **GO** — see [`mcp-server-pyproject-and-config-repo-compose.md`](./mcp-server-pyproject-and-config-repo-compose.md) |
| **Config-repo Compose PR?** | **GO** — profile `mcp`; sequence after server image/skeleton |
| Avoid | Public unauthenticated MCP; free-form Cypher/SQL; MCP as data SoT |

# Feasibility Study: MCP Server for Multi-Agent  
## Devcontainer / Docker Compose and DigitalOcean

| Field | Value |
|-------|--------|
| **Document type** | Architecture / integration feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.0.1 |
| **Application** | `haystack-fast-api` multi-agent + tool layer |
| **Local platform** | [Heavy-Rental Haystack-Fast-API devcontainer](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API) |
| **Cloud** | DigitalOcean (Droplet / DOKS; no managed MCP product) |
| **Related** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) (§4.6, §10 R4–R5, **§11.12**); [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) |

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
| Best local pattern? | Optional Compose service **`mcp-haystack`** using **streamable HTTP** MCP on the shared network |
| Best DO pattern? | Same image as **sidecar** next to FastAPI; private VPC to Postgres-Haystack + Neo4j |
| Stdio MCP (`uvx` per tool) in multi-replica? | **Poor fit** — prefer HTTP/streamable transport |
| MCP as source of truth? | **No** — tool **transport** only |
| Day-one with Kafka + full free ReAct over MCP? | **No** — phase after sync/Neo4j populate (R4 after D3/T3) |

**Overall:** **GO for a later MCP sidecar (R4/M\*)**, not as a rewrite of Stage-1 agents. Spring continues to call **FastAPI HTTP**; MCP is how **agents** (and optional external clients) call **tools**.

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
Spring ──HTTP──► FastAPI (ingest / Q&A / later recommend)
                    │
                    ▼
              LangGraph multi-agent
                    │
        ┌───────────┴───────────┐
        │ in-process tools (now)│
        │        and/or         │
        │ MCP client ──HTTP──► mcp-haystack service
        │                         ├─► db (Postgres-Haystack)
        │                         ├─► neo4j (fleet / graph tools)
        │                         └─► trigger neo4j-populate job
        └───────────────────────┘
```

Spring does **not** need to speak MCP for the recommender portal path.

---

## 3. MCP options suitable for this stack

| Option | Description | Local compose | DigitalOcean | Recommendation |
|--------|-------------|---------------|--------------|----------------|
| **A. In-process only** | Keep `app/agents/tools.py` | No new service | Same process as API | **Default now (R1–R2)** |
| **B. MCP HTTP/streamable server sidecar** | FastMCP (or equivalent) + stable tool names; Haystack `mcp-haystack` / custom client | New service on network | Sidecar container / second process | **Recommended for R4** |
| **C. MCP stdio + uvx** | Subprocess tools per call | Fragile in long-lived multi-user containers | Poor multi-replica | **Avoid for prod agents** |
| **D. Neo4j official MCP only** | Cypher / GraphRAG MCP; project tools stay in-process | Optional second container | Same | **Hybrid OK** after T3 |
| **E. Hayhooks pipeline tools** | Optional pipeline HTTP edge | Optional | Optional | Not fleet SoT; optional complement |

### Transport choice

| Transport | Fit |
|-----------|-----|
| **Streamable HTTP / HTTP MCP** (e.g. `StreamableHttpServerInfo` in mcp-haystack) | **Best** for Docker Compose + DO — one long-lived server, healthchecks, network DNS (`mcp-haystack:8100`) |
| **SSE-only MCP** | Possible depending on server; still server-side process |
| **Stdio** | Fine for laptop demos; **not** primary for compose multi-agent |

Haystack integration: `pip install mcp-haystack` — client can attach MCP tools to generators/pipelines; multi-agent can wrap the same invocations.

---

## 4. Recommended tool catalog

Align with dual-plane study §4.6. Prefer **narrow, auditable** tools.

### 4.1 Project plane (after ingest)

| Tool | Backing | Notes |
|------|---------|--------|
| `project_vector_search` | DocumentStore (InMemory today; **Pgvector** after I1) | **Require** `user_id` + `ingest_id` |
| `project_kg_query` | KG-1 session or artifact load | Same tenant scoping |

### 4.2 Fleet plane (after Track D / T\*)

| Tool | Backing | Notes |
|------|---------|--------|
| `retrieve_fleet_assets` | SQL read on `db` (mirrored domain) | Read-only; allowlisted tables/columns |
| `neo4j_cypher_read` | Neo4j fleet labels | Parameterized templates; **no** free-form destructive Cypher |
| `trigger_neo4j_populate` | Enqueue / call populate job | Needs **T3** service; returns `job_id`, not full rebuild in request |

### 4.3 Indexing

| Tool | Recommendation |
|------|----------------|
| `run_indexing_from_request` | Prefer **in-process** from FastAPI/Spring ingest path (latency, multipart, idempotency). Expose via MCP only for **external** agent hosts if needed. |

### 4.4 What not to put on MCP day one

- Arbitrary shell  
- Unscoped SQL  
- Unscoped Cypher write/delete  
- Direct writes to `postgres-primary`  

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

### 5.2 Phases M0–M5

| Phase | Name | Work | Depends on | Exit criteria |
|-------|------|------|------------|---------------|
| **M0** | Spec & allowlist | OpenSpec/design: tools, auth, Safeguards; MCP not SoT | — | Written allowlist + denial list |
| **M1** | Hello MCP on compose | Add optional service; FastMCP “ping”/echo; hit from app container | Network only | Tool invoke succeeds on network DNS |
| **M2** | Project read tools | Wrap vector + KG query with tenant args; session store access (or HTTP back to app) | Ingest + session (as-built or I1) | Q&A path works via MCP flag |
| **M3** | Fleet tools | SQL read + constrained Neo4j read + `trigger_neo4j_populate` | **T1+** fresh mirror; **T3** populate job | Agent can list assets / trigger populate safely |
| **M4** | Agent wiring | LangGraph feature flag `AGENT_TOOLS=inprocess\|mcp\|hybrid` | M2 | Parity tests stub mode |
| **M5** | Cloud hardening | Auth (API key/mTLS), no public bind, secrets, resource limits | M1–M4 | DO checklist green |

**Order with §11 T-phases:**  
`T0 → T1 → T3 → T4` then `M1 → M2 → M3 → M4`.  
Do **not** block T0–T1 on MCP.

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
| New `mcp-server/` or script | FastMCP app + tool implementations |
| `postCreate` / deps | `mcp`, `mcp-haystack` if client in app |
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
| `mcp-haystack:8100` on compose network | K8s Service DNS or private hostname |
| `db` / `neo4j` hostnames | Managed PG host + Neo4j private IP |
| Compose profile `mcp` | Feature flag / separate Deployment |
| Port publish 8100 to laptop | Omit public LB; only app talks to MCP |

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
T0 → T1 → T3 → T4 ──► M1 → M2 → M3 → M4 → M5
R1 → R2 ─────────────► R4 (MCP) → R5
```

---

## 11. Suggested spikes

1. **M1:** FastMCP “ping” container on `heavy-rental-network`; invoke from `haystack-fast-api` container.  
2. **M2:** One tool `project_vector_search` via MCP with mock session / fixture ingest.  
3. **Compare latency:** in-process tool vs MCP hop (stub mode).  
4. **M3 dry-run:** `trigger_neo4j_populate` returns job id without full graph load.  
5. **Auth fail closed:** request without API key rejected on MCP.  
6. **Tenant isolation:** two `user_id`s cannot read each other’s chunks via MCP.

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
- Spring wire: [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md)  
- Devcontainer: [Haystack-Fast-API](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)  
- [Haystack MCP integration](https://haystack.deepset.ai/integrations/mcp) (`mcp-haystack`)  
- [Neo4j MCP / GenAI](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)  
- OpenSpec: `openspec/specs/knowledge-graph/`, `equipment-recommendation/` (MCP optional)  
- As-built tools: `app/agents/tools.py`  

---

## 14. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial MCP multi-agent feasibility: compose + DO; phases M0–M5 |
| **1.0.1** | 2026-08-10 | DocumentStore path for agents: InMemory/Pgvector only |

---

## 15. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Adopt MCP for multi-agent? | **Yes, later (R4 / M\*)** |
| Required for Stage-1 now? | **No** — in-process tools |
| Local deploy | Optional Compose service + **profile `mcp`** |
| Cloud deploy | Sidecar on DO; private network; auth required |
| Transport | **HTTP / streamable HTTP**, not stdio for prod |
| Spring integration | Still **REST to FastAPI**; MCP is agent-tool side |
| First compose work | **Not before T1/T3** for fleet tools; M1 can be hello-only anytime |
| Avoid | Public unauthenticated MCP; free-form Cypher/SQL; MCP as data SoT |

# Feasibility Study: Implementing MCP Server + `pyproject` Dependencies, and Config-Repo Compose PR

| Field | Value |
|-------|--------|
| **Document type** | Implementation / delivery feasibility study |
| **Status** | Complete (study only — does **not** apply the changes) |
| **Date** | 2026-08-10 |
| **Version** | 1.0.0 |
| **Application** | `haystack-fast-api` + Heavy-Rental devcontainer config repo |
| **Questions** | (1) Is it feasible to **implement** the FastMCP server and add dependencies to **`pyproject.toml`**? (2) Is it feasible to land a **Compose PR** in the **config repo** for MCP (and related services)? |
| **App repo** | This workspace (`haystack-fast-api`) — `pyproject.toml`, optional `mcp_server/` package |
| **Config repo** | [heavy-rental-devcontainer-configuration](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration) — `Haystack-Fast-API` compose on `develop` |
| **Related** | [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md) · [`fastmcp-tool-consolidation-multi-agent.md`](./fastmcp-tool-consolidation-multi-agent.md) · dual-plane §11.12 |

> Earlier planning treated these as **out of scope for docs-only work**. This study answers **whether and how** they should be done when implementation starts—not a substitute for an actual PR.

---

## 1. Executive summary

### Verdicts

| Question | Result |
|----------|--------|
| Implement FastMCP **server** in/near app monorepo? | **GO** |
| Add deps to app **`pyproject.toml`** / uv lock? | **GO** (phased: client vs server) |
| Land **config-repo Compose PR** for optional `mcp-haystack` service? | **GO** |
| Do both in **one** PR across two repos? | **No** — split app vs config; order matters |
| Block Stage-1 / T0–T1 on MCP server PR? | **No** |
| Required before M1 “hello MCP”? | Server image **or** local process + network DNS; compose PR recommended for team parity |

**Overall:** Both workstreams are **feasible and recommended** when leaving pure-docs mode. Prefer **phased deps** (don’t force `mcp-haystack` client on all devs before M4) and **Compose profile `mcp`** so default stack stays light.

---

## 2. Part A — Implementing server + `pyproject` dependencies

### 2.1 Current as-built (`pyproject.toml`)

| Present | Missing (for MCP stack) |
|---------|-------------------------|
| `haystack-ai`, `langgraph`, FastAPI, embedders stack | **`mcp-haystack`** (Haystack MCP **client**) |
| ML stack (`xgboost`, `joblib`, …) | **FastMCP** / `mcp` SDK for **server** |
| No `mcp_server` package in tree | Server entrypoint, tool modules, Dockerfile optional |

### 2.2 Dependency split (recommended)

| Package | Where | When | Purpose |
|---------|-------|------|---------|
| **`mcp-haystack`** | App `pyproject.toml` **dependencies** (or optional group) | **M4** | `MCPTool`, `StreamableHttpServerInfo` in LangGraph |
| **`fastmcp`** and/or **`mcp`** | Server project: `mcp_server/pyproject.toml` **or** app optional group `mcp-server` | **M1** | Host tools over streamable HTTP |
| Shared tool core | `app/tools/` or shared package | **C1** | Avoid dual implementations |
| `pgvector-haystack` (when I1) | App (+ server if project tools on MCP) | **I1** | PgvectorDocumentStore |
| Unchanged | Existing haystack, langgraph, xgboost | — | Pricing can stay on app or mount artifacts on server |

**Optional dependency groups** (illustrative):

```toml
# app pyproject — illustrative only
[dependency-groups]
mcp-client = ["mcp-haystack>=…"]
mcp-server = ["fastmcp>=…", "mcp>=…"]  # if server shares app uv project
```

Or **separate** `mcp_server/pyproject.toml` + Docker image so the API image stays slim.

### 2.3 Server implementation layout (illustrative)

```text
haystack-fast-api/
  app/                     # API + LangGraph + mcp-haystack client (M4)
  mcp_server/              # optional package
    __main__.py / main.py  # FastMCP app, port 8100
    tools/
      project.py
      fleet.py
      pricing.py           # wraps predict_price or HTTP to app
    pyproject.toml         # OR inherit monorepo
  Dockerfile.mcp           # optional
```

| Concern | Feasibility | Guidance |
|---------|-------------|----------|
| Hello tool `ping` | **GO** | M1 exit criteria |
| Project vector tool | **GO** after I1 on sidecar | Tenant args required |
| Fleet SQL tools | **GO** after T1 | Read-only DSN to `db` |
| Pricing tool | **GO** | Bundle `model.pkl` or call app-internal function |
| Auth | **GO** | API key env for DO; optional local |
| Tests | **GO** | Unit tools without full compose; one compose integration job |

### 2.4 App `pyproject` change procedure (when implementing)

1. Confirm package names/versions against current Haystack 2.x (`mcp-haystack` release notes).  
2. `uv add mcp-haystack` (M4) → commit `pyproject.toml` + `uv.lock`.  
3. Feature-flag client: `AGENT_TOOLS=inprocess|mcp|hybrid`, `MCP_SERVER_URL`.  
4. CI: default tests stay **in-process** (no MCP required); optional job with profile `mcp`.  
5. Server: either second uv project or `[dependency-groups] mcp-server` + entrypoint script.  
6. Do **not** add heavy MCP server deps to the default runtime path if most developers never run M1.

### 2.5 Risks (Part A)

| Risk | Mitigation |
|------|------------|
| Version skew haystack-ai vs mcp-haystack | Pin ranges; smoke test MCPTool import |
| Lockfile conflict / large diff | Isolated PR: “deps only” then “wiring” |
| Server imports full app (circular) | Shared pure `app/tools/core` only on server |
| Model artifacts missing on server image | Volume mount `ml-experiments/artifacts` in compose |
| Accidental public MCP | Bind `8100` internal network only on DO |

### 2.6 Part A decision card

| Decision | Recommendation |
|----------|----------------|
| Implement FastMCP server? | **Yes (GO)** when starting M1 |
| Add to `pyproject.toml`? | **Yes** — client at M4; server deps in server package or optional group at M1 |
| Single monorepo PR for server+client? | Prefer **server first**, **client later** (two PRs) |
| Block default CI on MCP? | **No** |

---

## 3. Part B — Config-repo Compose PR

### 3.1 Why a separate repo PR

| Repo | Owns |
|------|------|
| **haystack-fast-api** | Application code, `pyproject`, optional `Dockerfile.mcp`, tool code |
| **heavy-rental-devcontainer-configuration** | `.devcontainer/docker-compose.yml`, network, `db`, `db-sync`, `neo4j`, app service env, scripts |

MCP **service definition**, `profiles: ["mcp"]`, DNS name `mcp-haystack`, and env wiring for local/devcontainer **must** land in the **config repo** (or be duplicated—undesirable). Dual-plane §11 already treats this compose as SoT for local topology.

### 3.2 Proposed Compose delta (illustrative — study only)

```yaml
  # heavy-rental-devcontainer-configuration / Haystack-Fast-API
  mcp-haystack:
    profiles: ["mcp"]
    container_name: mcp-haystack
    # build: context from app repo Dockerfile.mcp  OR image:
    restart: unless-stopped
    environment:
      PGHOST: db
      PGPORT: "5432"
      PGDATABASE: heavy_rental   # confirm actual name in compose
      NEO4J_URI: bolt://neo4j:7687
      MCP_HOST: "0.0.0.0"
      MCP_PORT: "8100"
      # MCP_API_KEY: optional local
    ports:
      - "8100:8100"   # dev only
    depends_on:
      db:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    networks:
      - heavy-rental-network

  # haystack-fast-api service env (when profile mcp + M4):
  #   MCP_SERVER_URL: http://mcp-haystack:8100/mcp
  #   AGENT_TOOLS: inprocess   # default; mcp when ready
```

| Item | Feasible? | Notes |
|------|-----------|--------|
| Optional profile `mcp` | **GO** | Default `up` unchanged |
| Join `heavy-rental-network` | **GO** | Same as app/db/neo4j |
| `depends_on` db/neo4j | **GO** | For fleet tools later; M1 ping needs only network |
| Build context from app monorepo | **GO** | Document monorepo path / submodule / CI build-publish image |
| Port 8100 publish | **GO** local; omit public on DO | |
| postCreate / README | **GO** | `docker compose --profile mcp up -d` |
| db-sync / neo4j-populate unchanged | **Yes** | Separate T* PRs |

### 3.3 PR sequencing (recommended)

```text
1) App PR (optional): mcp_server skeleton + Dockerfile.mcp + CI image build
2) Config-repo PR: compose service + profile + env stubs + docs
3) App PR: uv add mcp-haystack + AGENT_TOOLS wiring (M4)
4) Later: I1 / fleet tools expand server + compose env only if needed
```

| Anti-pattern | Why |
|--------------|-----|
| Config PR references image that doesn’t exist | Broken `up` for profile mcp |
| Force MCP profile on all developers | Heavier laptop stack; CI flake |
| Put FastMCP only in config repo without app code | No tool implementations to run |

### 3.4 Config-repo PR checklist (when implementing)

- [ ] Service `mcp-haystack` with `profiles: ["mcp"]`  
- [ ] Network + depends_on documented  
- [ ] Env vars aligned with MCP study matrix  
- [ ] README: how to enable profile; default path without MCP  
- [ ] Do not change 24h→shorter sync unless T1 PR  
- [ ] Optional: healthcheck hitting MCP ping tool  
- [ ] Coordinate image tag / build args with app repo release  

### 3.5 Risks (Part B)

| Risk | Mitigation |
|------|------------|
| Two-repo review lag | Land compose with `image: …` placeholder only after image published; or build context documented |
| Env secret leakage | No real API keys in compose; use env_file gitignored |
| Name collision `mcp-haystack` client package vs service | Document: service = server; PyPI = client |
| Developers on old config | Changelog + profile opt-in |

### 3.6 Part B decision card

| Decision | Recommendation |
|----------|----------------|
| Config-repo Compose PR for MCP? | **Yes (GO)** |
| Profile | **`mcp`** optional |
| Default stack without MCP? | **Unchanged** |
| Couple with neo4j-populate PR? | **No** — separate T3 PR |
| Couple with app client deps PR? | **Sequence**, don’t squash into one cross-repo mega-PR |

---

## 4. Combined delivery map

| Work item | Repo | Feasible | Phase |
|-----------|------|----------|-------|
| FastMCP server code + tools skeleton | **App** | **GO** | M1 |
| Server deps (`fastmcp` / `mcp`) | **App** server package or group | **GO** | M1 |
| Compose service + profile | **Config** | **GO** | M1 (with image) |
| `mcp-haystack` in app `pyproject` | **App** | **GO** | M4 |
| `AGENT_TOOLS` / `MCP_SERVER_URL` | **App** + compose env | **GO** | M4 |
| Project/fleet/pricing tools | **App** server | **GO** | M2–M5 |
| DO sidecar | Deploy, not config-repo only | **GO** | M7 |

```text
Docs-only (done) ──► App: server skeleton + deps
                 ──► Config: compose profile mcp
                 ──► App: client mcp-haystack + LangGraph flag
                 ──► Tools expand (vector/fleet/price)
```

---

## 5. Explicitly **not** done by this study

- Applying `uv add` or editing `pyproject.toml` in this workspace  
- Opening a GitHub PR on the config repo  
- Publishing a Docker image  

Those are **implementation tasks** once product prioritizes M1/M4.

---

## 6. References

- MCP deploy: [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md)  
- Consolidation: [`fastmcp-tool-consolidation-multi-agent.md`](./fastmcp-tool-consolidation-multi-agent.md)  
- Dual-plane §11 / §11.12: [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md)  
- Config SoT: [Haystack-Fast-API devcontainer](https://github.com/Heavy-Rental/heavy-rental-devcontainer-configuration/tree/develop/Haystack-Fast-API)  
- App deps today: `pyproject.toml`  

---

## 7. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Feasibility of MCP **server implementation**, **pyproject deps**, and **config-repo Compose PR** (previously out-of-scope for docs-only) |

---

## 8. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Implement FastMCP server? | **GO** (app repo, M1) |
| Add `pyproject` deps? | **GO** — server at M1; **`mcp-haystack` client at M4** |
| Optional dependency groups? | **Yes** preferred |
| Config-repo Compose PR? | **GO** — profile **`mcp`**, service `mcp-haystack` |
| Default compose without profile? | **Unchanged** (light stack) |
| Single cross-repo PR? | **No** — sequence app server → config compose → app client |
| Block T0–T1 / Stage-1? | **No** |
| This study applies code/PR? | **No** — feasibility only |

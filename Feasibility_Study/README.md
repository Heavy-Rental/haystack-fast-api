# Feasibility studies

Architecture and infrastructure studies for `haystack-fast-api` (docs only; not runtime source of truth).

## Architecture principles (folder-wide)

These apply across studies unless a study explicitly narrows scope:

| Principle | Detail |
|-----------|--------|
| **Tool model** | Multi-agent invokes tools **in-process** (shared Python tool module). A separate MCP/FastMCP tool server is **not** part of the architecture. |
| **Indexing [4]** | **Forced non-agent Coordinator gate** before recommend tools; files never enter LLM context as raw bytes. |
| **Roles** | **Coordinator / Worker / Delegator** is an **alias layer** over Orchestrator + domain agents — see [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md). Primary terms remain Orchestrator / tools / synthesis. Every agent has **A–L** (through **seq/par processing**; C/W/D §10). Fleet LTM = **`postgres_haystack`←`postgres-primary`**; must-seq gate & fleet→price; may-par across needs (capped). |
| **Delegator** | **Explicit allowlisted router** (not free ReAct). |
| **Multi-need recommend** | **Fan-out Workers per need** for fleet **[6]** and pricing **[7]**; Coordinator **[8]** merges tool-free. |
| **Observability** | Prefer `role=coordinator\|delegator\|worker` (+ `need_id` on fan-out) in logs / `tool_traces`. |
| **Disambiguation** | Agent **Worker** ≠ ops **job worker** (202 jobs, Neo4j populate, Uvicorn). |
| **Planes** | KG-1 (project) and KG-2 (fleet Neo4j) stay separate; Spring remains HTTP REST client. |
| **Fleet data path** | **`postgres-primary`** (write SoT) → **`postgres_haystack_sync`** → **`postgres_haystack` / `heavy_rental`** (agent read mirror). |

**How to read:** start with dual-plane for data + request flow; C/W/D for agent roles; implementation plan for phased rollout; other studies for specialty depth (pricing, synthesis, Spring wire, Call 1, SuperComponent).

| Study | Topic | Version |
|-------|--------|---------|
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane: fleet sync primary→Haystack PG→Neo4j; post-[4] recommend via **in-process tools**; C/W/D-aligned graph; Pgvector; Call 1 lean + FR-IX-023 TARGET. Hosts **`postgres_haystack`** + sync **`postgres_haystack_sync`**. | **2.7.2** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring ↔ FastAPI wire; multi-call saga; internal `/internal/v1/recommendations` routes; C/W/D internal to FastAPI. | **1.3.1** |
| [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) | ML pricing as **in-process** agent tool; pricing **Worker** fan-out per need; Phase 1e/2a. | **1.2.0** |
| [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) | Synthesis **[8]** (Coordinator) → recommended assets + predicted rent prices. | **1.4.1** |
| [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) | C/W/D role vocabulary; **[4]** forced non-agent gate; explicit Delegator router; fan-out Workers per need; **§10 A–L templates** (seq/par + workflow; haystack←primary). | **2.1.0** |
| [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) | Indexing Pipeline → Haystack SuperComponent (optional packaging for Coordinator gate **[4]**). | **1.2.1** |
| [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) | Call 1 lean body (`ingest_id`, `user_id`, `user_requirement_summary`); full needs/dates/budget TARGET; not Call 3. | **1.1.0** |

### Implementation plan

| Document | Topic | Version |
|----------|--------|---------|
| [`implementation-plan.md`](./implementation-plan.md) | Stage catalog S0–S9 / S7.0–S7.7; Call 1 lean body; Call 2 request contract; **TDD (P9) + BDD (P10)**; **PR template**; C/W/D A–L. | **3.3.1** |

Normative product behaviour remains under [`../openspec/`](../openspec/). Pricing decision log: [`../docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md).

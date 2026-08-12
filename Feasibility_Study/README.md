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
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane + Spring multi-call: Call 1 ingest · Call 2 recommend · Call 3 chatbot Q&A. | **2.7.4** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring ↔ FastAPI wire; Call 1/2/3 saga; resilience C1–C3. | **1.3.2** |
| [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) | ML pricing as **in-process** agent tool; pricing **Worker** fan-out per need; Phase 1e/2a. | **1.2.1** |
| [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) | Synthesis **[8]** → assets + prices (**HTTP Call 2** recommend path). | **1.4.2** |
| [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) | C/W/D roles; Call 2 recommend / Call 3 Q&A numbering aligned. | **2.1.1** |
| [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) | Indexing Pipeline → Haystack SuperComponent (optional packaging for Coordinator gate **[4]**). | **1.2.1** |
| [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) | Call 1 lean body; FR-IX-023 **as-built** S1a–S1e; not Call 2 recommend quote. | **1.2.1** |

### Implementation plan

| Document | Topic | Version |
|----------|--------|---------|
| [`implementation-plan.md`](./implementation-plan.md) | Stage catalog; Call 2=recommend, Call 3=chatbot Q&A; portal dual-hop; TDD/BDD. **S3 as-built** (agent indexing tool + Coordinator gate [4]; SuperComponent S3.3 deferred). | **3.5.2** |
| [`phase2-s2a-haystack-implementation-plan.md`](./phase2-s2a-haystack-implementation-plan.md) | **Phase 2 / S2a only** — haystack-fast-api: `Idempotency-Key`, correlation logging, docs. **Implemented** (FR-IX-024/025; §7 test runbook). | **1.1.2** |
| [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) | **S2b** Spring client + portal Call 1→2 recommend. Export: [`../Feasibility_Study_Spring/`](../Feasibility_Study_Spring/). | **2.0.0** |

**Stage S3 (haystack, as-built):** `run_indexing_from_request` + forced `START→index_gate→END` behind `INDEXING_VIA_AGENT_GATE` (default off). OpenSpec FR-IX-026 · archive `openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/`.

### Spring Boot handoff package

| Package | Topic | Version |
|---------|--------|---------|
| [`../Feasibility_Study_Spring/`](../Feasibility_Study_Spring/) | **Copy into Spring Boot project** — portal mapping (React project-spec → Call 1 then Call 2) + S2b plan + wire + HANDOFF | **2.0.0** |
| [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) | Portal → Call 1/2 recommend/3 Q&A | **2.0.0** |

Normative product behaviour remains under [`../openspec/`](../openspec/). Pricing decision log: [`../docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md).

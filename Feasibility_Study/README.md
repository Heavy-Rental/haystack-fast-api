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
| **Default pytest** | `uv run pytest` is CI-safe (memory DocumentStore). `tests/conftest.py` forces mock embedder **dim 384**, stub agents, temp KG dir so host `.env` does not break CI. Vector tools: query embedder mode/dim **must** match session store; tenant filters on `user_id`/`ingest_id`. Optional `@pytest.mark.pgvector` (S5-I1) skipped unless `RUN_PGVECTOR_TESTS=1`. `neo4j` marker remains **TARGET**. Details: [`implementation-plan.md`](./implementation-plan.md) §7.0 · OpenSpec project-setup. |

**How to read:** start with dual-plane for data + request flow; C/W/D for agent roles; implementation plan for phased rollout; other studies for specialty depth (pricing, synthesis, Spring wire, Call 1, SuperComponent).

| Study | Topic | Version |
|-------|--------|---------|
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane + Spring multi-call: Call 1 ingest · Call 2 recommend · Call 3 chatbot Q&A. **I0+I1 DocumentStore cutover as-built** (factory wire, tenant filters, TTL). | **2.7.7** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring ↔ FastAPI wire; Call 1/2/3 saga; resilience C1–C3. | **1.3.2** |
| [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) | ML pricing as **in-process** agent tool; pricing **Worker** fan-out per need; **S6 tool as-built**; **S7.3 Workers [7]×N as-built**; **S7.5 HTTP flag**. | **1.2.4** |
| [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) | Synthesis **[8]** → assets + prices (**HTTP Call 2** recommend path). **S7.4 stub [8] as-built**; **S7.5 HTTP enrich as-built**; **S7.7 A–L prompts as-built**. | **1.4.6** |
| [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) | C/W/D roles; Call 2 recommend / Call 3 Q&A numbering aligned. **S7.0–S7.1 + S7.3–S7.7 as-built**. | **2.1.5** |
| [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) | Indexing Pipeline → Haystack SuperComponent (optional packaging for Coordinator gate **[4]**). | **1.2.1** |
| [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) | Call 1 lean body; FR-IX-023 **as-built** S1a–S1e; not Call 2 recommend quote. | **1.2.2** |

### Implementation plan

| Document | Topic | Version |
|----------|--------|---------|
| [`implementation-plan.md`](./implementation-plan.md) | Stage catalog; Call 2=recommend, Call 3=chatbot Q&A; portal dual-hop; TDD/BDD. **S3 as-built**; **S5-I0+I1 as-built**; **S6 as-built**; **S7.0+S7.1+S7.3–S7.7 as-built** (state, tools, LangGraph DAG, stub synthesis, Call 2 flag, traces, A–L prompts + tool DI); **§7.0 default pytest isolation** (mock dim 384). | **3.9.0** |
| [`phase2-s2a-haystack-implementation-plan.md`](./phase2-s2a-haystack-implementation-plan.md) | **Phase 2 / S2a only** — haystack-fast-api: `Idempotency-Key`, correlation logging, docs. **Implemented** (FR-IX-024/025; §7 test runbook + conftest isolation). | **1.1.3** |
| [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) | **S2b** Spring client + portal Call 1→2 recommend. Export: [`../Feasibility_Study_Spring/`](../Feasibility_Study_Spring/). | **2.0.0** |

**Stage S3 (haystack, as-built):** `run_indexing_from_request` + forced `START→index_gate→END` behind `INDEXING_VIA_AGENT_GATE` (default off). OpenSpec FR-IX-026 · archive `openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/`.

**Stage S5-I0 (haystack, as-built):** `INDEXING_DOCUMENT_STORE` + `build_document_store()` (`memory` default \| `pgvector`). OpenSpec FR-IX-027 · archive `openspec/changes/archive/2026-08-12-s5-i0-document-store-factory/`.

**Stage S5-I1 (haystack, as-built):** `create_session_document_store()` wired into Call 1 + session; retrieval filters `user_id`+`ingest_id`; optional TTL/delete; dual-mode tests. OpenSpec FR-IX-028 · archive `openspec/changes/archive/2026-08-12-s5-i1-document-store-pipeline-wire/`.

**Stage S6 (haystack, as-built):** in-process agent tool `predict_asset_price` → `pricing_client.predict_price_for_asset` (production model + per-asset clamp; never silent zeros). Phase 1e/2a/2b/2c already production. Phase 7 Workers [7]×N **as-built S7.3**. OpenSpec dynamic-pricing US-5 · archive `openspec/changes/archive/2026-08-12-s6-predict-asset-price-tool/`.

**Stage S7.0 (haystack, as-built):** `RecommendAgentState` TypedDict + `validate_state_transition` / partition write helpers (F-2). Illegal Worker writes rejected; gate false blocks fleet. OpenSpec archive `openspec/changes/archive/2026-08-12-s7-0-recommend-agent-state/`.

**Stage S7.1 (haystack, as-built):** allowlisted in-process tools `decompose_project_needs`, `retrieve_fleet_assets`, `filter_fleet_candidates`, `check_booking_availability` + DI factory (fake seed default / SQL DTO backend). Free-form SQL rejected. Graph wiring **as-built S7.3**. OpenSpec archive `openspec/changes/archive/2026-08-12-s7-1-fleet-tool-catalog/`.

**Stage S7.3 (haystack, as-built):** isolated recommend LangGraph DAG `check_gate → project_worker → delegator → execute_needs → synthesis`. Must-seq fleet→price within need; `RECOMMEND_FANOUT_CAP` batches across needs (cap=1 serializes). Gate false skips fleet/price. OpenSpec archive `openspec/changes/archive/2026-08-12-s7-3-s7-4-recommend-graph-synthesis/`.

**Stage S7.4 (haystack, as-built):** tool-free Coordinator stub synthesis [8] → `results_by_need`; empty fleet / missing prices → `item: null` + warning; no invent; F-2 on apply. Same archive as S7.3.

**Stage S7.5 (haystack, as-built):** Call 2 `getassetrecommendations` optionally runs the C/W/D graph behind `RECOMMEND_VIA_AGENT_GRAPH` (default off). Same quote DTO; gate refuse → 400. OpenSpec archive `openspec/changes/archive/2026-08-12-s7-5-s7-6-call2-enrich-traces/`.

**Stage S7.6 (haystack, as-built):** recommend `tool_traces` include `role`, `node`, `need_id` on fan-out, and `duration_ms >= 0` on terminal spans. Traces stay off the public quote body. Same archive as S7.5.

**Stage S7.7 (haystack, as-built):** isolated A–L recommend prompts (`app/agents/recommend_prompts.py`) + `build_recommend_runtime` tool DI + Delegator `worker_kind` allowlist (`validate_work_plan`). Stage-1 Q&A prompts unchanged. OpenSpec archive `openspec/changes/archive/2026-08-13-s7-7-prompts-a-l-tool-di/`.

### Spring Boot handoff package

| Package | Topic | Version |
|---------|--------|---------|
| [`../Feasibility_Study_Spring/`](../Feasibility_Study_Spring/) | **Copy into Spring Boot project** — portal mapping (React project-spec → Call 1 then Call 2) + S2b plan + wire + HANDOFF | **2.0.0** |
| [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) | Portal → Call 1/2 recommend/3 Q&A | **2.0.0** |

Normative product behaviour remains under [`../openspec/`](../openspec/). Pricing decision log: [`../docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md).

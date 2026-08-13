# Proposal: HTTP Call 2 multi-agent enrich + tool_traces (S7.5 + S7.6 / Phase 7)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S7.5 + S7.6) |
| **Date** | 2026-08-12 |
| **Trace** | C/W/D Coordinator handoff I; G-1 traces; equipment-recommendation FR notes |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 / stages **S7.5** + **S7.6** |
| **Study** | [`Feasibility_Study/multi-agent-synthesis-recommend-output.md`](../../../../Feasibility_Study/multi-agent-synthesis-recommend-output.md) · [`Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../../../../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

S7.3/S7.4 shipped the recommend DAG + stub synthesis but Call 2 still used `RecommendationService` only. Portal/Spring need the **same quote DTO** optionally produced by the C/W/D graph, plus a G-1 `tool_traces` contract (`role`, `need_id`, `duration_ms`).

## What shipped

| Item | Behaviour |
|------|-----------|
| Flag `RECOMMEND_VIA_AGENT_GRAPH` | Default **false** (MVP `RecommendationService`); `true` runs `run_recommend_graph` |
| Same Call 2 DTO | `AssetRecommendResponse` (`quoteRef`, `items[]`); no `answer`; no `tool_traces` on the body |
| Gate refuse | Session `meta.indexing_ok=false` → **400** `{"error","message"}` |
| Missing session | **404** unchanged |
| Traces | Terminal spans (`ok` / `completed` / `error` / `refused`) include `duration_ms >= 0`; fan-out has `need_id` |
| Empty fleet | `item: null` + warning (unchanged S7.4); fleet worker traces still present |

## Spec / design

- `openspec/specs/equipment-recommendation/spec.md` — S7.5 / S7.6 FRs (1.3.0)
- `openspec/specs/equipment-recommendation/design.md` — file map
- `openspec/specs/recommendation-pipeline/spec.md` + `contracts/get-asset-recommendations.md`
- `openspec/TRACEABILITY.md` — S7.5 / S7.6 map
- Feasibility_Study implementation-plan **3.8.0**

## Code

- `app/config.py` — `RECOMMEND_VIA_AGENT_GRAPH`
- `app/services/session_recommend.py` — graph branch + `results_to_recommend_response`
- `app/agents/recommend_traces.py` — `append_tool_trace` / `elapsed_ms`
- `app/agents/recommend_nodes.py`, `recommend_synthesis.py` — timed traces
- `tests/test_recommend_http_call2.py`, `tests/test_tool_traces.py`
- `tests/fixtures/recommend/golden_call2_quote.json`

## Out of scope (follow-up)

- Neo4j tools (S7.2)
- Prompts A–L / LLM synthesis rationale (S7.7)
- Production default flip to the graph
- Prometheus / histogram exporter

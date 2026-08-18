# Proposal: Recommend LangGraph DAG + tool-free synthesis (S7.3 + S7.4 / Phase 7)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S7.3 + S7.4) |
| **Date** | 2026-08-12 |
| **Trace** | C/W/D §10.0.10–§10.0.11; Coordinator [8] merge; equipment-recommendation FR notes |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 / stages **S7.3** + **S7.4** |
| **Study** | [`Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../../../../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) · [`Feasibility_Study/multi-agent-synthesis-recommend-output.md`](../../../../Feasibility_Study/multi-agent-synthesis-recommend-output.md) |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

S7.0/S7.1 shipped state + tools but not the recommend graph. Workers need a forced DAG (gate → [5] → Delegator → ([6]→[7])×N → [8]) and a **tool-free** Coordinator merge so synthesis cannot invent `asset_id` or rates.

## What shipped

| Item | Behaviour |
|------|-----------|
| `check_gate` | Coordinator non-agent: `indexing_ok=false` → refuse; no fleet/price tools |
| Project Worker [5] | `decompose_project_needs` + quantity expand → `project.needs` |
| Delegator | Explicit `work_plan` per unit-need (not ReAct); Workers do not spawn siblings |
| `execute_needs` | Cap batches: `fanout_cap=1` serializes fleet→price per need; `≥2` fleets then prices |
| Fleet / Pricing Workers | Allowlisted tools; F-2 `write_fleet_slice` / `write_price_rows`; empty fleet skips [7] |
| Stub synthesis [8] | Tool-free merge → `results_by_need`; empty fleet / no price → `item: null` + warning |
| Config | `RECOMMEND_FANOUT_CAP` (default 4, min 1) |
| Isolation | New modules only; Stage-1 Q&A `app/agents/graph.py` unchanged |
| HTTP Call 2 | **Not wired** (S7.5) |

## Spec / design

- `openspec/specs/equipment-recommendation/spec.md` — DAG + synthesis FRs (1.2.0)
- `openspec/specs/equipment-recommendation/design.md` — file map
- `openspec/specs/recommendation-pipeline/spec.md` — key-decision pointer
- `openspec/TRACEABILITY.md` — S7.3 / S7.4 map
- Feasibility_Study implementation-plan **3.7.0**

## Code

- `app/agents/recommend_graph.py`
- `app/agents/recommend_nodes.py`
- `app/agents/recommend_synthesis.py`
- `app/config.py` — `RECOMMEND_FANOUT_CAP`
- `tests/test_recommend_graph_order.py`, `test_recommend_fanout.py`, `test_recommend_synthesis.py`
- `tests/fixtures/recommend/golden_results_by_need.json`

## Out of scope (follow-up)

- Neo4j tools (S7.2)
- HTTP Call 2 multi-agent enrich (S7.5)
- Full `tool_traces` metrics / duration histograms (S7.6)
- Prompts A–L (S7.7)

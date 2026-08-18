# Proposal: RecommendAgentState + partition validation (S7.0 / Phase 7)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S7.0) |
| **Date** | 2026-08-12 |
| **Trace** | C/W/D §10.0.3 / F-2; equipment-recommendation agent state |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 / stage **S7.0** |
| **Study** | [`Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../../../../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) §10.0.3, §10.0.5 F-2 |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

Multi-agent recommend (Phase 7) needs a shared STM schema and **F-2 partition validation** so Workers cannot corrupt other roles' slices (no invent inventory/rates via illegal writes; gate false blocks fleet).

## What shipped

| Item | Behaviour |
|------|-----------|
| `RecommendAgentState` TypedDict | `run`, `project`, `work_plan`, `fleet_by_need`, `prices_by_need`, `recommendation`, `tool_traces`, `persistence` |
| Role write partitions | Coordinator / Delegator / project / fleet / pricing Workers |
| `validate_state_transition(role, current, proposed)` | Illegal partition → `StateTransitionError` |
| Dependencies | Pricing `asset_id` must be in fleet candidates; silent zero rates rejected |
| Business rules | `indexing_ok` required before fleet/pricing writes |
| Helpers | `apply_partition_write`, `write_fleet_slice`, `write_price_rows`, `empty_recommend_state` |
| Phase 7 graph | **Not wired** (state module only) |

## Spec / design

- `openspec/specs/equipment-recommendation/spec.md` — agent state FR notes + change control
- `openspec/TRACEABILITY.md` — S7.0 map
- Feasibility_Study implementation-plan **3.6.0** · C/W/D study **2.1.2**

## Code

- `app/agents/recommend_state.py`
- `app/agents/__init__.py` — exports
- `tests/test_recommend_agent_state.py`
- `tests/fixtures/recommend/state_*.json`

## Out of scope (follow-up)

- LangGraph recommend DAG (S7.3)
- Tool-free synthesis (S7.4)
- HTTP Call 2 multi-agent enrich (S7.5)
- Prompts A–L (S7.7)

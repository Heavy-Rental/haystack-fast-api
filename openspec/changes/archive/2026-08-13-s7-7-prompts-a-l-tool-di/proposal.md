# Proposal: Prompts A–L + tool DI (S7.7 / Phase 7)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S7.7) |
| **Date** | 2026-08-13 |
| **Trace** | C/W/D §10 A–L + §10.8; equipment-recommendation prompt contracts |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 / stage **S7.7** |
| **Study** | [`Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../../../../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) §10, §11 |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

S7.3–S7.6 shipped the recommend DAG, stub merge, Call 2 flag, and traces, but recommend agents still had no isolated A–L prompt contracts and the Delegator did not fail closed on unknown `worker_kind`. Stage-1 Q&A prompts must stay uncontaminated.

## What shipped

| Item | Behaviour |
|------|-----------|
| `app/agents/recommend_prompts.py` | `RECOMMEND_SYNTHESIS_*`, `DELEGATOR_POLICY_*`, `PROJECT_WORKER_*`, `FLEET_WORKER_*`, `PRICING_WORKER_*` (A–L compact) |
| Tool-free synthesis prompt | Declares **Tools: none**; no invent `asset_id` / `daily_rate`; L-1 sequential barrier |
| Stage-1 isolation | `app/agents/prompts.py` unchanged; Q&A still forbids invent fleet |
| `build_recommend_runtime` | DI catalog + `agent_mode` (`stub` default) |
| `ALLOWED_WORKER_KINDS` | `fleet_worker` \| `pricing_worker` |
| `validate_work_plan` | Unknown `worker_kind` → `UnknownWorkerKindError` |
| Stub rationale | `stub_recommend_rationale` (golden prefix preserved) |
| LLM rationale | `apply_rationale_only` — text only; invented asset/rates ignored |

## Spec / design

- `openspec/specs/equipment-recommendation/spec.md` — S7.7 FR (1.4.0)
- `openspec/specs/equipment-recommendation/design.md` — file map
- `openspec/spdd/prompts/recommend-agents.md` — OpenSPDD index
- `openspec/TRACEABILITY.md` — S7.7 map
- Feasibility_Study implementation-plan **3.9.0**

## Code

- `app/agents/recommend_prompts.py`
- `app/agents/tool_factory.py` — worker-kind allowlists + runtime
- `app/agents/recommend_nodes.py` — Delegator + execute_needs validate plan
- `app/agents/recommend_synthesis.py` — prompt-backed stub rationale
- `app/agents/recommend_graph.py` — optional `RecommendRuntime`
- `tests/test_recommend_prompts.py`, `tests/test_agent_tool_di.py`

## Out of scope (follow-up)

- Neo4j tools (S7.2)
- Production default flip to `RECOMMEND_VIA_AGENT_GRAPH`
- Worker [5] live `project_vector_search` / `project_kg_query`

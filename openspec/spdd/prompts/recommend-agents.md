# OpenSPDD Prompt Index: Recommend Agents (S7.7)

| Field | Value |
|-------|--------|
| **Capability** | `equipment-recommendation` Phase 7 / S7.7 |
| **Authoritative prompts** | [`app/agents/recommend_prompts.py`](../../../app/agents/recommend_prompts.py) |
| **Behaviour** | [`openspec/specs/equipment-recommendation/spec.md`](../../specs/equipment-recommendation/spec.md) |
| **Design** | [`openspec/specs/equipment-recommendation/design.md`](../../specs/equipment-recommendation/design.md) |
| **Templates** | C/W/D §10 A–L · [`Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../../../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) |

> **OpenSPDD rule:** When recommend-agent behaviour is wrong, **edit the structured prompts in `app/agents/recommend_prompts.py` first**, then code. Do not rewrite Stage-1 [`app/agents/prompts.py`](../../../app/agents/prompts.py).

Recommend tools only via the in-process catalog. Synthesis **[8]** has **no tools**.

---

## Intents & tool allowlists

| Constant | Agent | Intent (summary) | Tools |
|----------|-------|------------------|-------|
| `RECOMMEND_SYNTHESIS_INTENT` | Coordinator [8] | Merge tool-backed fleet + prices into `results_by_need` | **None** |
| `DELEGATOR_POLICY_INTENT` | Delegator | Emit allowlisted `work_plan[]` | **None** |
| `PROJECT_WORKER_INTENT` | Worker [5] | Ground spec then decompose into `needs[]` | `project_vector_search`, `project_kg_query`, `decompose_project_needs` |
| `FLEET_WORKER_INTENT` | Worker [6] | Retrieve / filter / availability for one `need_id` | `retrieve_fleet_assets`, `filter_fleet_candidates`, `check_booking_availability` |
| `PRICING_WORKER_INTENT` | Worker [7] | Price known candidates for one `need_id` | `predict_asset_price` only |

System prompt constants: `RECOMMEND_SYNTHESIS_SYSTEM`, `DELEGATOR_POLICY_SYSTEM`, `PROJECT_WORKER_SYSTEM`, `FLEET_WORKER_SYSTEM`, `PRICING_WORKER_SYSTEM`.

Each system prompt encodes A (objective), D (write partition), E (environment / tools), and L-1/L-2/L-3 (seq / par / hybrid).

---

## Synthesis rules (normative)

- Tools: none. Consume STM only.
- Copy `asset_id` and `daily_rate` from tool-backed state. Never invent.
- Empty fleet or missing prices → `item: null` + warning.
- L-1: sequential barrier after need pipelines.
- Keep `results_by_need` expanded (one row per unit-need). Do **not** put
  `quantity` on `RecommendationItem`. Call 2 quote collapse (FR-P-013) is
  `map_recommend_to_quote`, not Coordinator [8].

Stub helper: `stub_recommend_rationale(description, asset_id)` (`PROJECT_AGENT_MODE=stub`).  
LLM may rewrite rationale only via `apply_rationale_only` — invented `asset_id` / rates are ignored.

---

## Topology binding

```text
check_gate → project_worker [5] → delegator → execute_needs ([6]→[7]×N) → synthesis [8]
```

Delegator `worker_kind` allowlist: `fleet_worker` \| `pricing_worker` (`validate_work_plan`).
Env: `PROJECT_AGENT_MODE` (`stub` \| `llm`), `RECOMMEND_FANOUT_CAP`, `RECOMMEND_VIA_AGENT_GRAPH`.

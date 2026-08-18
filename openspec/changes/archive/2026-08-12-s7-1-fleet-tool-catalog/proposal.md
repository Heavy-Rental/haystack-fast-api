# Proposal: In-process fleet / needs tool catalog (S7.1 / Phase 7)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S7.1) |
| **Date** | 2026-08-12 |
| **Trace** | C/W/D Worker [5]/[6] tools; equipment-recommendation FR-018 / tool allowlist |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 / stage **S7.1** |
| **Study** | [`Feasibility_Study/multi-agent-coordinator-worker-delegator.md`](../../../../Feasibility_Study/multi-agent-coordinator-worker-delegator.md) §10.4–§10.5; dual-plane tool catalog |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

Fleet / project Workers need **allowlisted in-process tools** (no free-form SQL/Cypher, no MCP server) with a DI factory for fake seed (CI) vs SQL-projected DTO backends.

## What shipped

| Item | Behaviour |
|------|-----------|
| `decompose_project_needs` | Stub/LLM decomposer → need DTOs |
| `retrieve_fleet_assets` | Read-only fleet list; optional category filter; empty → [] |
| `filter_fleet_candidates` | Category / height filter; never invents `asset_id` |
| `check_booking_availability` | Overlap → available + unavailable lists |
| Free-form SQL guard | `sql` / `cypher` / `raw_sql` kwargs → `FreeFormSqlRejected` |
| Factory | `build_recommend_tool_catalog(backend="fake"\|"sql")`; allowlist rejects unknown names |
| Phase 7 graph | **Not wired** (tools only; S7.3+) |

## Spec / design

- `openspec/specs/equipment-recommendation/spec.md` — tool catalog FR notes
- `openspec/specs/recommendation-pipeline/spec.md` — agent tool pointer
- `openspec/TRACEABILITY.md` — S7.1 map
- Feasibility_Study implementation-plan **3.6.0**

## Code

- `app/agents/fleet_tools.py`
- `app/agents/tool_factory.py`
- `app/agents/__init__.py` — exports
- `tests/test_fleet_tools.py`, `tests/test_tool_factory.py`
- `tests/fixtures/recommend/fleet_seed.json`

## Out of scope (follow-up)

- Neo4j tools (S7.2)
- LangGraph DAG fan-out (S7.3)
- Live SQL repository queries (optional when S4 mirror ready; factory accepts injected DTOs now)

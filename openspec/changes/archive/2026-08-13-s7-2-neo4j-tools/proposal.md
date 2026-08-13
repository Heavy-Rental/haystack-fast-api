# Proposal: Neo4j tools (S7.2 / Phase 7)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S7.2) |
| **Date** | 2026-08-13 |
| **Trace** | C/W/D §10.3 K-3 skip + §10.5 optional `neo4j_cypher_read`; dual-plane §4.6.3 / §4.7 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 / stage **S7.2** |
| **Study** | [`Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md`](../../../../Feasibility_Study/postgres-haystack-neo4j-realtime-sync.md) §4.6–§4.7 |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

S7.1 shipped SQL fleet tools; S7.3–S7.7 shipped the recommend DAG. KG-2 still needed **allowlisted in-process tools** so Fleet Worker [6] can optionally read graph neighbors without a live Neo4j or free-form Cypher. Recommend must not block when the graph is empty (K-3).

## What shipped

| Item | Behaviour |
|------|-----------|
| `neo4j_cypher_read` | Templates only (`asset_neighbors`, `assets_by_category`, `compatible_attachments`). Empty graph → `[]`. |
| `trigger_neo4j_populate` | Returns `job_id` immediately; `status=noop` (empty) or `queued`; `blocking=false`. Ops-only. |
| `FreeFormCypherRejected` | `cypher` / `query` / `raw_cypher` / `sql` kwargs rejected |
| `UnknownNeo4jTemplateError` | Unknown template name fail-closed |
| `FakeNeo4jBackend` | Default empty; fixture inject for tests |
| Factory | Tools on `RECOMMEND_TOOL_ALLOWLIST`; `include_neo4j_tools` toggle |
| Delegator K-3 | Empty graph → `skip_tools: [neo4j_cypher_read]`; SQL fleet tools stay required |
| Fleet worker | Optional `graph_notes` when plan includes the tool and backend is non-empty |

## Spec / design

- `openspec/specs/equipment-recommendation/spec.md` — S7.2 FR (1.5.0)
- `openspec/specs/equipment-recommendation/design.md` — file map
- `openspec/specs/knowledge-graph/spec.md` — FR-KG-011 still Stage 2; S7.2 is fake tools only
- `openspec/TRACEABILITY.md` — S7.2 map
- Feasibility_Study implementation-plan **3.10.0**

## Code

- `app/agents/neo4j_tools.py`
- `app/agents/tool_factory.py` — catalog `neo4j` backend + tool registration
- `app/agents/recommend_nodes.py` — Delegator skip + optional fleet read
- `app/agents/recommend_state.py` — optional `FleetSlice.graph_notes`
- `tests/test_neo4j_tools.py`, `tests/fixtures/recommend/neo4j_graph.json`

## Out of scope (follow-up)

- Live Neo4j driver / compose populate job (S8)
- FR-KG-011 persist KG-2 as-built
- Calling `trigger_neo4j_populate` on the recommend hot path
- Production default flip to `RECOMMEND_VIA_AGENT_GRAPH`

# Proposal: S8.3 live Neo4j tools (app)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** |
| **Date** | 2026-08-13 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 8 / **8.3** |
| **Trace** | S7.2 tool contracts; dual-plane §4.6.3 / D3; FR-KG-011 load path |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

S8.1–S8.2 persist KG-2 in the config pack (`neo4j-populate` + post-sync/admin HTTP). S7.2 shipped allowlisted in-process tools against `FakeNeo4jBackend`. Agents still could not read the live fleet graph or enqueue populate from this app.

## What shipped

| Item | Behaviour |
|------|-----------|
| `NEO4J_BACKEND=fake\|bolt` | Default **fake** (CI). `bolt` uses a live driver. |
| `BoltNeo4jBackend` | Implements `Neo4jBackend`; fleet labels only; never reads/writes `:Document`. |
| `neo4j_cypher_read` | Same templates; live backend maps to the S7.2 node/rel shape. |
| `trigger_neo4j_populate` | Fake: `noop`/`queued`. Bolt: non-blocking `POST` to `NEO4J_POPULATE_URL`. Failure → `unavailable`. Never on recommend hot path. |
| K-3 | Empty **or** Bolt-unavailable → skip `neo4j_cypher_read`; SQL fleet still runs. |
| FR-KG-011 | Persist = pack T3/T4; **load** = app S8.3. |
| `@pytest.mark.neo4j` | Optional; skip unless `RUN_NEO4J_TESTS=1`. |

## Out of scope (still open)

- Call `trigger_neo4j_populate` from the recommend DAG
- Flip `RECOMMEND_VIA_AGENT_GRAPH` default
- Worker [5] live `project_vector_search` / `project_kg_query`
- Config-repo compose / table-name alignment
- Dual-write Spring → Neo4j

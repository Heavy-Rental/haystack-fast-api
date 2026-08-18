# Tasks: S8.3 live Neo4j tools

## Code

- [x] TDD: default `NEO4J_BACKEND=fake`; catalog stays `FakeNeo4jBackend`
- [x] TDD: populate HTTP stub → POST URL, `blocking=false`
- [x] TDD: populate HTTP failure → `status=unavailable`, non-blocking
- [x] TDD: K-3 skip when Bolt unavailable; fleet SQL still runs
- [x] TDD: Bolt mapper matches fixture templates; `:Document` dropped
- [x] Settings `NEO4J_*` + conftest forces `NEO4J_BACKEND=fake`
- [x] `BoltNeo4jBackend` + `UnavailableNeo4jBackend` + populate HTTP client
- [x] Factory / `run_recommend_graph` select backend from settings
- [x] Optional extra `neo4j`; `@pytest.mark.neo4j` integration pack
- [x] Regression: `uv run pytest tests/ -q` (312 passed, 5 skipped)

## Docs

- [x] OpenSpec equipment-recommendation + knowledge-graph FR-KG-011
- [x] AGENTS.md, TRACEABILITY, project.md, project-setup
- [x] Feasibility_Study implementation-plan 3.16.0, README, dual-plane, C/W/D
- [x] CHANGELOG Unreleased
- [x] Archive this change

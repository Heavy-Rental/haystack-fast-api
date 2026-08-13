# Tasks: S7.2 Neo4j tools (Phase 7)

## Code

- [x] TDD: `tests/test_neo4j_tools.py` (empty → []; free-form Cypher reject; fixture template; populate non-blocking; K-3 skip; graph_notes when present)
- [x] TDD: `tests/test_tool_factory.py` (catalog exposes Neo4j tools; omit toggle)
- [x] Implement `app/agents/neo4j_tools.py`
- [x] Register tools on `RECOMMEND_TOOL_ALLOWLIST` + `build_recommend_tool_catalog`
- [x] Delegator K-3 skip + fleet worker optional read
- [x] Fixture `tests/fixtures/recommend/neo4j_graph.json`
- [x] Regression: full `uv run pytest tests/` (293 passed, 3 skipped)

## Docs

- [x] OpenSpec equipment-recommendation 1.5.0 + design file map + TRACEABILITY + this archive
- [x] knowledge-graph FR-KG-011 still Stage 2 (S7.2 fake tools pointer)
- [x] `openspec/AGENTS.md` building-block list
- [x] Feasibility_Study implementation-plan 3.10.0, C/W/D, synthesis, dual-plane, README
- [x] CHANGELOG Unreleased

## Explicit non-goals

- [ ] S8 live Neo4j driver / populate-from-haystack job
- [ ] Mark FR-KG-011 as-built
- [ ] Flip production default to the graph
- [ ] Call `trigger_neo4j_populate` during recommend

# Tasks: S7.1 fleet / needs tool catalog (Phase 7)

## Code

- [x] TDD: `tests/test_fleet_tools.py` (category filter, availability overlap, empty fleet, stub decomposer, free-form SQL reject)
- [x] TDD: `tests/test_tool_factory.py` (allowlist unknown name, fake catalog, SQL empty DTOs)
- [x] Implement `app/agents/fleet_tools.py` + `app/agents/tool_factory.py`
- [x] Fixture `tests/fixtures/recommend/fleet_seed.json`
- [x] Export from `app/agents/__init__.py`
- [x] Regression: full `uv run pytest tests/`

## Docs

- [x] OpenSpec equipment-recommendation + recommendation-pipeline notes + TRACEABILITY + this archive
- [x] Feasibility_Study implementation-plan 3.6.0, C/W/D 2.1.2, README
- [x] specification/ README archive row

## Explicit non-goals

- [ ] S7.2 Neo4j tools
- [ ] S7.3 recommend LangGraph DAG
- [ ] Live ORM SQL inside tools (DTOs only for sql backend)

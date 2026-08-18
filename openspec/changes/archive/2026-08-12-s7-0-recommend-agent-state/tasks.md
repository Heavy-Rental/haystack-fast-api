# Tasks: S7.0 RecommendAgentState + partition validation (Phase 7)

## Code

- [x] TDD: `tests/test_recommend_agent_state.py` (fleet cannot write recommendation; unknown price asset_id; legal fleet write; gate false blocks)
- [x] Implement `app/agents/recommend_state.py` (TypedDict, validate, apply, helpers)
- [x] Fixtures `tests/fixtures/recommend/state_minimal.json`, `state_gate_false.json`
- [x] Export from `app/agents/__init__.py`
- [x] Regression: full `uv run pytest tests/`

## Docs

- [x] OpenSpec equipment-recommendation notes + TRACEABILITY + this archive
- [x] Feasibility_Study implementation-plan 3.6.0, C/W/D 2.1.2, README
- [x] specification/ README archive row

## Explicit non-goals

- [ ] S7.3 LangGraph recommend DAG
- [ ] S7.4 synthesis
- [ ] S7.5 HTTP enrich

# Tasks: S7.3 recommend LangGraph DAG + S7.4 tool-free synthesis (Phase 7)

## Code

- [x] TDD: `tests/test_recommend_graph_order.py` (within-need order, gate refuse, Q&A isolation)
- [x] TDD: `tests/test_recommend_fanout.py` (once per need_id; cap=1 serial; cap=2 batch)
- [x] TDD: `tests/test_recommend_synthesis.py` (golden asset/rates, empty fleet, no zeros, no invent, schema)
- [x] Fixture `tests/fixtures/recommend/golden_results_by_need.json`
- [x] Implement `app/agents/recommend_nodes.py` + `recommend_graph.py`
- [x] Implement `app/agents/recommend_synthesis.py` (tool-free stub [8])
- [x] Config `RECOMMEND_FANOUT_CAP` (default 4)
- [x] Export from `app/agents/__init__.py`
- [x] Regression: full `uv run pytest tests/` (260 passed, 3 skipped)

## Docs

- [x] OpenSpec equipment-recommendation 1.2.0 + design file map + TRACEABILITY + this archive
- [x] recommendation-pipeline key-decision row
- [x] `openspec/AGENTS.md` runtime flow
- [x] specification/ README + SPEC-agentic pointer
- [x] Feasibility_Study implementation-plan 3.7.0, C/W/D, synthesis, README, ml-pricing P5 note

## Explicit non-goals

- [ ] S7.2 Neo4j tools
- [ ] S7.5 HTTP Call 2 multi-agent enrich
- [ ] S7.6 full metrics contract
- [ ] S7.7 prompts A–L

# Tasks: S7.5 HTTP Call 2 enrich + S7.6 tool_traces (Phase 7)

## Code

- [x] TDD: `tests/test_tool_traces.py` (roles/nodes, fan-out `need_id`, `duration_ms >= 0`, empty fleet warning)
- [x] Implement `app/agents/recommend_traces.py` + wire nodes/synthesis
- [x] TDD: `tests/test_recommend_http_call2.py` (flag on quote, flag off no graph, gate 400, multi-need golden, missing session 404)
- [x] TDD: `tests/test_config.py` flag default false
- [x] Config `RECOMMEND_VIA_AGENT_GRAPH` (default false)
- [x] `SessionRecommendService` graph branch + `results_to_recommend_response`
- [x] Fixture `tests/fixtures/recommend/golden_call2_quote.json`
- [x] `.env.example` + `tests/conftest.py` isolation (`INDEXING_DOCUMENT_STORE=memory`, flag off)
- [x] Regression: full `uv run pytest tests/` (270 passed, 3 skipped)

## Docs

- [x] OpenSpec equipment-recommendation 1.3.0 + design file map + TRACEABILITY + this archive
- [x] recommendation-pipeline key-decision + Call 2 contract
- [x] `openspec/AGENTS.md` runtime flow
- [x] specification/ README + SPEC-agentic pointer
- [x] Feasibility_Study implementation-plan 3.8.0, C/W/D, synthesis, README, ml-pricing P5 note

## Explicit non-goals

- [ ] S7.2 Neo4j tools
- [ ] S7.7 prompts A–L
- [ ] Flip production default to the graph

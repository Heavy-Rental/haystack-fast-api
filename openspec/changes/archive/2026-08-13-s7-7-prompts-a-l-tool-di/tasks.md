# Tasks: S7.7 Prompts A–L + tool DI (Phase 7)

## Code

- [x] TDD: `tests/test_recommend_prompts.py` (Q&A isolation; synthesis no tools; A–L partitions; stub deterministic; LLM cannot invent asset)
- [x] TDD: `tests/test_agent_tool_di.py` (fake fleet inject; worker_kind allowlist; unknown kind rejected; execute_needs refuse)
- [x] Implement `app/agents/recommend_prompts.py`
- [x] `ALLOWED_WORKER_KINDS` / `WORKER_TOOL_ALLOWLISTS` / `validate_work_plan` / `build_recommend_runtime`
- [x] Wire Delegator + execute_needs + synthesis
- [x] Regression: full `uv run pytest tests/` (282 passed, 3 skipped)

## Docs

- [x] OpenSpec equipment-recommendation 1.4.0 + design file map + TRACEABILITY + this archive
- [x] `openspec/spdd/prompts/recommend-agents.md`
- [x] `openspec/AGENTS.md` building-block list
- [x] Feasibility_Study implementation-plan 3.9.0, C/W/D, synthesis, README
- [x] CHANGELOG Unreleased

## Explicit non-goals

- [ ] S7.2 Neo4j tools
- [ ] Flip production default to the graph
- [ ] Worker [5] live vector / KG-1 calls

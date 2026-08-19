# Documentation index (haystack-fast-api)

Engineer-facing guides. **Normative behaviour** lives under [`../openspec/`](../openspec/) (OpenSpec). Feasibility studies live under [`../Feasibility_Study/`](../Feasibility_Study/).

## Product / HTTP journey

| Doc | Description |
|-----|-------------|
| [`call1-call2-endpoint-process.md`](./call1-call2-endpoint-process.md) | Full Call 1 ingest + Call 2 recommend process, env, eval §11 |
| [`multi-agent-architecture.md`](./multi-agent-architecture.md) | **Multi-agent systems** (indexing gate, Call 3 Q&A, Call 2 C/W/D) |
| [`integrations/spring-boot-api-contract.md`](./integrations/spring-boot-api-contract.md) | Spring ↔ FastAPI wire notes |

## Multi-agent (start here)

**[`multi-agent-architecture.md`](./multi-agent-architecture.md)** covers:

- Path A — Indexing Coordinator gate [4]  
- Path B — Project-knowledge Q&A (Call 3)  
- Path C — Recommend C/W/D (Call 2)  
- Tools, state partitions, `tool_traces`, env flags, code map, tests  

OpenSPDD prompt indexes: [`../openspec/spdd/prompts/`](../openspec/spdd/prompts/).

## Evaluation

| Doc | Description |
|-----|-------------|
| [`eval/README.md`](./eval/README.md) | Eval folder index |
| [`eval/call1-call2-eval-results.md`](./eval/call1-call2-eval-results.md) | Committed scoreboard |
| [`eval/call1-call2-test-data-and-predictions.json`](./eval/call1-call2-test-data-and-predictions.json) | Inputs + gold + predictions |

```bash
uv run python scripts/export_eval_test_data.py
uv run pytest tests/test_call1_call2_eval_pack.py -q
# HTML: reports/pytest-report.html
```

## Testing guides

| Doc | Description |
|-----|-------------|
| [`testing/knowledge-graph-testing-guide.md`](./testing/knowledge-graph-testing-guide.md) | KG + multi-agent Q&A |
| [`testing/recommendation-pipeline-testing-guide.md`](./testing/recommendation-pipeline-testing-guide.md) | FR-010 + recommend tests |
| [`testing/recommendation-postman-testing-guide.md`](./testing/recommendation-postman-testing-guide.md) | Postman (legacy notes) |

Also: [`../postman/README.md`](../postman/README.md) · [`../QUICKSTART.md`](../QUICKSTART.md).

## Pricing

| Doc | Description |
|-----|-------------|
| [`dynamic-pricing-masterplan.md`](./dynamic-pricing-masterplan.md) | Pricing product plan |
| [`dynamic-pricing-execution-plan.md`](./dynamic-pricing-execution-plan.md) | Execution plan |
| [`dynamic-pricing-scheduled-retrain-plan.md`](./dynamic-pricing-scheduled-retrain-plan.md) | Phase 3 scheduled-retrain plan; Phase 3a foundations complete |

## Spec entry points

| Path | Role |
|------|------|
| [`../openspec/AGENTS.md`](../openspec/AGENTS.md) | SDD reading order + runtime flow |
| [`../openspec/specs/portal-dual-hop/spec.md`](../openspec/specs/portal-dual-hop/spec.md) | Call 1→2 process requirements |
| [`../openspec/specs/knowledge-graph/spec.md`](../openspec/specs/knowledge-graph/spec.md) | KG-1 + Stage-1 agents |
| [`../openspec/specs/equipment-recommendation/spec.md`](../openspec/specs/equipment-recommendation/spec.md) | Parent product + Phase 7 |

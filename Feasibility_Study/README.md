# Feasibility studies

Architecture and infrastructure studies for `haystack-fast-api` (docs only; not runtime source of truth).

**Tool model:** Multi-agent invokes tools **in-process** (shared Python tool module). A separate MCP/FastMCP tool server is **not** part of the architecture.

| Study | Topic | Version |
|-------|--------|---------|
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane: fleet sync primary→Haystack PG→Neo4j; post-[4] recommend via **in-process tools**; Pgvector; Call 1 TARGET summary. | **2.5.0** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring ↔ FastAPI wire; multi-call saga; Call 3 = multi-agent + in-process tools. | **1.2.0** |
| [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) | ML pricing as **in-process** agent tool; features, guardrails, Phase 1e/2a. | **1.1.0** |
| [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) | Synthesis **[8]** → recommended assets + predicted rent prices. | **1.1.0** |
| [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) | Indexing Pipeline → Haystack SuperComponent (optional packaging). | **1.1.0** |
| [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) | Call 1 response: needs + dates + budget (TARGET). | **1.0.0** |

Normative product behaviour remains under [`../openspec/`](../openspec/). Pricing decision log: [`../docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md).

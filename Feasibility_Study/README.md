# Feasibility studies

Architecture and infrastructure studies for `haystack-fast-api` (docs only; not runtime source of truth).

| Study | Topic | Version |
|-------|--------|---------|
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane. **Post-[4] recommend** + SuperComponent + synthesis links. | **2.3.0** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring ↔ FastAPI wire; multi-call saga; call 3 = recommend via agents + FastMCP (internal). | **1.1.0** |
| [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md) | FastMCP deploy; recommend tools + M5–M6. | **1.6.0** |
| [`fastmcp-tool-consolidation-multi-agent.md`](./fastmcp-tool-consolidation-multi-agent.md) | Tool consolidation; post-[4] recommend via FastMCP. | **1.3.0** |
| [`ml-pricing-multi-agent-fastmcp.md`](./ml-pricing-multi-agent-fastmcp.md) | ML pricing features, guardrails, FastMCP tool. | **1.0.0** |
| [`indexing-pipeline-supercomponent.md`](./indexing-pipeline-supercomponent.md) | Indexing Pipeline → SuperComponent **GO**. | **1.0.0** |
| [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) | **Synthesis [8]** → recommended **assets** + **predicted rent price** (target **GO**; Stage-1 Q&A gap). | **1.0.0** |
| [`mcp-server-pyproject-and-config-repo-compose.md`](./mcp-server-pyproject-and-config-repo-compose.md) | **Implement** FastMCP server + **`pyproject` deps**; **config-repo Compose PR** (profile `mcp`) — delivery feasibility. | **1.0.0** |

Normative product behaviour remains under [`../openspec/`](../openspec/). Pricing decision log: [`../docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md).

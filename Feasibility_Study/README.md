# Feasibility studies

Architecture and infrastructure studies for `haystack-fast-api` (docs only; not runtime source of truth).

| Study | Topic | Version |
|-------|--------|---------|
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane: fleet sync + request path. **§11** devcontainer T0–T5; **§11.12** optional MCP compose. Pgvector cutover. Tracks D / I / R / T. | **1.5.0** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring Boot ↔ FastAPI: multi-call saga, REST vs SSE vs jobs; resilience. SSE not for file upload. | 1.0.0 |
| [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md) | **MCP server for multi-agent**: in-process vs HTTP sidecar; Compose profile; DigitalOcean sidecar; phases M0–M5; security. | **1.0.0** |

Normative product behaviour remains under [`../openspec/`](../openspec/).

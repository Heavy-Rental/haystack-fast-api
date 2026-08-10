# Feasibility studies

Architecture and infrastructure studies for `haystack-fast-api` (docs only; not runtime source of truth).

| Study | Topic | Version |
|-------|--------|---------|
| [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) | Dual plane: fleet sync + request path. **§11 Devcontainer transition** (primary→haystack real-time + Neo4j populate). Pgvector cutover. Spring multi-call §2.1. Tracks D / I / R / T. | **1.4.0** |
| [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) | Spring Boot ↔ FastAPI connectivity: multi-call saga, REST vs SSE vs jobs; resilience. SSE not for file upload. | 1.0.0 |

Normative product behaviour remains under [`../openspec/`](../openspec/).

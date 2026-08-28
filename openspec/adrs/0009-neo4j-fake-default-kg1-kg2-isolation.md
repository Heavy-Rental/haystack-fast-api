# `NEO4J_BACKEND` fake default vs bolt; KG-1 ≠ KG-2

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-13 |
| **Deciders** | haystack-fast-api |
| **Trace** | FR-KG-011; S7.2 / S8.1–S8.3 |

## Context and Problem Statement

Agents need optional fleet graph context (KG-2) without mixing it into project DocumentStore / Ragas KG-1, and without requiring Bolt in CI.

## Considered Options

* Single Neo4j graph for project chunks and fleet
* Always-on Bolt in the app
* Fake default + live Bolt; templates only; fleet labels isolated from `:Document`

## Decision Outcome

Chosen option: **`NEO4J_BACKEND=fake` default; `bolt` live**. `neo4j_cypher_read` is template-only (no free-form Cypher). `trigger_neo4j_populate` is non-blocking HTTP to admin `:8089` (`NEO4J_POPULATE_URL`). K-3: empty or Bolt-unavailable backends skip Neo4j so recommend is not blocked. Persist = S8.1–S8.2 ops job (config pack locally; this repo’s deploy-pipeline vendors copies for academy/paid — **ADR-0012**); load = app S8.3. Fleet labels (`:Asset` / `:Booking` / `:Category`) MUST NOT drop KG-1 `:Document`.

### Consequences

* Good: CI has no Neo4j dependency; project and fleet graphs cannot clobber each other.
* Bad / accepted: optional `@pytest.mark.neo4j`; graph notes are enrichment only, never a source of invented `equipment.id`.

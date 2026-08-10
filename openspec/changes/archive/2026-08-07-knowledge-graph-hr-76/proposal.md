# Proposal: Knowledge Graph assembly (HR-76)

| Field | Value |
|-------|--------|
| **Change id** | `2026-08-07-knowledge-graph-hr-76` |
| **Status** | **Archived** — Stage 1 Part A as-built |
| **Capability** | `knowledge-graph` (Part A assembly) |
| **Tracking** | **HR-76** |
| **Normative now** | [`openspec/specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md) · [`design.md`](../../../specs/knowledge-graph/design.md) |
| **Tasks** | [`tasks.md`](./tasks.md) |

## Why

Agents need structured project knowledge alongside vector chunks. After the shared indexing head joins cleaned/split documents, the system must assemble a Ragas-style **KG-1** from post-join chunks, persist a user-scoped JSON artifact, and hard-fail if build/save fails—so multi-agent Q&A can later query both DocumentStore and graph.

## What changes

- Mandatory KG after `final_doc_joiner` (sibling branch to embed/write).
- Modules: `app/pipelines/kg/` (bridge, generator, saver, runner) hooked from indexing service.
- Config: `KG_ARTIFACT_DIR`, `KG_APPLY_TRANSFORMS` (default off = document nodes).
- Removed: optional soft-fail via `KG_ENABLED` / `KG_STRICT` (always on, hard-fail).
- Ingest response `kg_*` fields; sanitize `user_id` for filesystem paths.
- Stamp `user_id` + `ingest_id` meta on KG chunks.

## Scope

| In scope | Out of scope |
|----------|--------------|
| Part A assembly (FR-KG-001…008) | Multi-agent Q&A (see `2026-08-08-kg-multi-agent-stage1`) |
| Document-node + optional full Ragas transforms | KG-2 equipment stockpile |
| JSON artifact under `artifacts/kg/{user_id}/` | Neo4j |

## Impact

- Indexing path always runs KG; ingest fails if KG fails.
- Depends on indexing `user_id` requirement and post-join chunk availability.
- Enables session registration for Stage-1 agents (follow-on change).

## Non-goals

- Replacing recommend MVP (SQL → availability → `predict_price`).
- Training pricing models.
- Mandatory Neo4j.

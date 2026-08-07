# Specification: Knowledge Graph after Indexing (HR-76)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (Spec-kit) |
| **Status** | **As-built** — post-`final_doc_joiner` KG; full Ragas transforms only on `KnowledgeGraphGenerator` |
| **Feature id** | `knowledge-graph` |
| **Tracking** | **HR-76** |
| **Reading map** | [`README.md`](./README.md) Path B step 6 |
| **Previous** | [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) |
| **Tasks** | [`tasks-knowledge-graph.md`](./tasks-knowledge-graph.md) |
| **Parent** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) §11.1 |
| **Env** | [`.env.example`](../.env.example) |
| **Tests** | `tests/test_knowledge_graph.py` |

---

## Conflict rule

| Concern | Owner |
|---------|--------|
| Live HTTP field list (including `kg_*` on response) | Indexing SPEC + this SPEC (KG semantics) |
| When KG runs, transforms location, artifact path | **This SPEC** |
| Parent §11 product vision | Parent; as-built = this child |

---

## Placement (after indexing step 5)

```text
[5 indexing] … → final_doc_joiner
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
 doc_embedder → writer         [6 this SPEC]
 InMemoryDocumentStore         bridge → KnowledgeGraphGenerator
                                        ├─ DOCUMENT nodes
                                        └─ full Ragas transforms
                                           only if KG_APPLY_TRANSFORMS
                                   → saver
                                   {KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json
```

---

## Functional requirements

| ID | Requirement |
|----|-------------|
| **FR-KG-001** | `user_id` required on ingest (indexing SPEC). |
| **FR-KG-002** | KG chunks MUST carry `user_id` + `ingest_id` meta. |
| **FR-KG-003** | When `KG_ENABLED=true`, build from **post-join** chunks; save under user-scoped path. |
| **FR-KG-004** | Full Ragas transforms **only** in `KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true`. |
| **FR-KG-005** | Default transforms **off** (document nodes). |
| **FR-KG-006** | Soft-fail unless `KG_STRICT`. |
| **FR-KG-007** | Response: `kg_built`, `kg_node_count`, `kg_relationship_count`, `kg_artifact_path`, `kg_transform_applied`. |
| **FR-KG-008** | Sanitize `user_id` for filesystem paths. |

---

## Config

| Env | Default |
|-----|---------|
| `KG_ENABLED` | `false` |
| `KG_ARTIFACT_DIR` | `artifacts/kg` |
| `KG_APPLY_TRANSFORMS` | `false` |
| `KG_STRICT` | `false` |

---

## Modules

| Path | Role |
|------|------|
| `app/pipelines/kg/bridge.py` | Haystack → LangChain |
| `app/pipelines/kg/generator.py` | Nodes + optional full Ragas transforms |
| `app/pipelines/kg/saver.py` | User-scoped JSON |
| `app/pipelines/kg/runner.py` | `run_knowledge_graph` |
| `app/services/indexing.py` | Hook when `KG_ENABLED` |

---

## Acceptance criteria

1. `KG_ENABLED=false` → `kg_built=false`.  
2. `KG_ENABLED=true`, transforms false → artifact under `{user_id}/`, `kg_transform_applied=false`, nodes ≥ 1.  
3. Two users → two paths.  
4. Missing `user_id` → 400 (indexing).  

---

## Out of scope

Neo4j; online multi-agent KG query; Naive RAG HTTP; recommend reattach.

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-07 | HR-76 as-built |
| **0.1.1** | 2026-08-07 | Sequential map; expanded AC/modules |

---

**Reading order:** [← Indexing](./SPEC-indexing-file-type-router.md) · [Map](./README.md) · [Next: .env.example →](../.env.example)

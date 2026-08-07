# Specification: Knowledge Graph after Indexing (HR-76)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (Spec-kit) |
| **Status** | **As-built** — **mandatory** post-`final_doc_joiner` KG; full Ragas transforms only on `KnowledgeGraphGenerator` |
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
 doc_embedder → writer         [6 this SPEC — mandatory]
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
| **FR-KG-003** | After successful index write, **MUST** build KG from **post-join** chunks and save under user-scoped path. |
| **FR-KG-004** | Full Ragas transforms **only** in `KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true`. |
| **FR-KG-005** | Default transforms **off** (document nodes). |
| **FR-KG-006** | KG failure **MUST** fail the ingest request (hard-fail; no soft-fail path). |
| **FR-KG-007** | Response: `kg_built`, `kg_node_count`, `kg_relationship_count`, `kg_artifact_path`, `kg_transform_applied`. On success `kg_built` is always `true`. |
| **FR-KG-008** | Sanitize `user_id` for filesystem paths. |

---

## Config

| Env | Default | Notes |
|-----|---------|--------|
| `KG_ARTIFACT_DIR` | `artifacts/kg` | User-scoped subdirs |
| `KG_APPLY_TRANSFORMS` | `false` | Document nodes only unless true |

`KG_ENABLED` / `KG_STRICT` are **removed** — creation is always on and hard-fail is always on.

---

## Modules

| Path | Role |
|------|------|
| `app/pipelines/kg/bridge.py` | Haystack → LangChain |
| `app/pipelines/kg/generator.py` | Nodes + optional full Ragas transforms |
| `app/pipelines/kg/saver.py` | User-scoped JSON |
| `app/pipelines/kg/runner.py` | `run_knowledge_graph` |
| `app/services/indexing.py` | Always runs KG after index; hard-fails on error |

---

## Acceptance criteria

1. Successful ingest → `kg_built=true`, artifact under `{user_id}/`, `kg_transform_applied=false` when transforms off, nodes ≥ 1.  
2. KG build/save failure → request fails (not 200 with warnings only).  
3. Two users → two paths.  
4. Missing `user_id` → 400 (indexing).  

---

## Out of scope

Neo4j; online multi-agent KG query; Naive RAG HTTP; recommend reattach.

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-07 | HR-76 as-built (optional KG) |
| **0.1.1** | 2026-08-07 | Sequential map; expanded AC/modules |
| **0.2.0** | 2026-08-07 | Mandatory KG + hard-fail; remove `KG_ENABLED` / `KG_STRICT` |

---

**Reading order:** [← Indexing](./SPEC-indexing-file-type-router.md) · [Map](./README.md) · [Next: .env.example →](../.env.example)

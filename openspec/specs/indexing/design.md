# Indexing Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, Outcomes, and Requirements (FR-IX-001–022 + MIME classification map). Live HTTP owner for `POST /api/v1/recommendations/from-project-spec`; conflict rule: live route wins here; KG rules in [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md).

**API field tables:** [`contracts/ingest-from-project-spec.md`](./contracts/ingest-from-project-spec.md).

## E — Entities

| Concept | Role |
|---------|------|
| ByteStream source | Uploaded file or `project_text` packaged with `mime_type` |
| data_kind | `structured` \| `unstructured` \| `mixed` aggregate classification |
| Document | Haystack document after MIME-specific convert |
| Chunk | Post-split unit with meta (`user_id`, `ingest_id`, …) and optional embedding |
| final_doc_joiner | Merge point of unstructured and CSV preprocess branches |
| InMemoryDocumentStore | Default process-local write target |
| ingest_id | Response id (`ing_` + hex) for the ingest transaction |
| kg_* fields | Mandatory post-join KG outcome (see knowledge-graph capability) |

## A — Approach

Aligned with Packt Ch. 4 indexing flowchart
([indexing_pipeline.png](https://github.com/PacktPublishing/Building-Natural-Language-and-LLM-Pipelines/blob/main/ch4/jupyter-notebooks/images/indexing_pipeline.png)):
**FileTypeRouter → dual preprocess branches → joiner → embed → write**.

### Dual-branch pipeline diagram

```text
  POST /from-project-spec (user_id required)
       │
       ▼
  file_type_router → dual-branch convert/clean/split
       │
       ▼
  final_doc_joiner
       ├─► doc_embedder → writer → InMemoryDocumentStore
       └─► post-join chunks → KG (mandatory; see knowledge-graph SPEC)
       │
       ▼
  IngestFromProjectSpecResponse
```

**Branch detail:**

- **Unstructured:** sanitizer (or equivalent quality gate) → `DocumentCleaner` → word `DocumentSplitter`
- **CSV:** CSV-oriented cleaner → row-wise `CSVDocumentSplitter`
- **JSON/XLSX:** use unstructured clean/split path but count as **structured** for `data_kind`
- Meet at **`final_doc_joiner`** → embed → write; parallel post-join path builds mandatory user-scoped KG

Default embedder is CI-safe (`MockDocumentEmbedder`); optional `openai` / `sentence-transformers` via `INDEXING_EMBEDDER`. Async HTTP offloads sync pipeline via `run_in_threadpool`.

## S — Structure

### Modules

| Path | Role |
|------|------|
| `app/pipelines/indexing/*` | Dual-branch index graph, store, embedder |
| `app/pipelines/kg/*` | Mandatory KG (HR-76) |
| `app/services/indexing.py` | Index + mandatory KG (hard-fail) |
| `app/api/recommendations.py` | Thin HTTP |
| `app/schemas/indexing.py` | Response DTO |
| `app/config.py` | `INDEXING_*`, `KG_*` |
| `postman/` | Live collection |

### Package notes under `app/pipelines/indexing/`

| Module (as-built) | Role |
|-------------------|------|
| `mime_map.py` | Extensions, MIME sets, structured/unstructured sets |
| `data_kind_classifier.py` | `@component` using `FileTypeRouter` |
| `pipeline.py` | `build_indexing_pipeline`, `run_indexing_pipeline`; dual-branch + joiners |
| converters / cleaners / splitters | Per-MIME convert; CSV vs unstructured preprocess |
| embedder factory + store singleton | Mock default; optional openai / sentence-transformers; test reset |

## O — Operations

### Config

- `INDEXING_*` — embedder mode, splitter/store-related settings (see [`.env.example`](../../../.env.example))
- `KG_*` — artifact dir, transforms flag (owned by knowledge-graph capability; required for success path)

### Tests

| Area | Modules / notes |
|------|-----------------|
| Component + pipeline | `tests/test_indexing_*.py` (router, converters, dual-branch, write path) |
| HTTP ingest fields | `tests/test_recommendations_intake.py` (ingest response, not recommend envelope) |
| Mandatory KG | `tests/test_knowledge_graph.py`; hard-fail and Stage-1 Q&A see knowledge-graph **Testing** |
| Recommend unit tests | Service-level only; not bound to this HTTP route |

### Manual

- Postman collection, environment, fixtures: [`../../../postman/README.md`](../../../postman/README.md)
- Live route verification sequence may include KG multi-agent (Postman 15→16) per knowledge-graph testing notes

## N — Norms

- Packt Ch. 4 dual-branch flowchart is the design reference for graph topology.
- MIME map and FR-IX requirements in [`spec.md`](./spec.md) are normative; design must not invent alternate classification.
- Thin routers; orchestration in `IndexingIngestService`; Haystack graph under `app/pipelines/indexing/`.
- Spec process: OpenSpec capability; Spec-kit tasks archive; OpenSPDD REASONS here; fix prompt/spec first.
- Cross-capability: after joiner, KG is mandatory (HR-76)—do not document it as future-only.

## S — Safeguards

### Out of scope (still)

- Persistent multi-instance DocumentStore
- Naive/hybrid RAG **query** HTTP on this capability
- Recommend reattach on this route (T017)
- `LinkContentFetcher` branch (T030)

### Forbidden without dedicated SDD

- Restoring `intake_front` / `results_by_need` as default HTTP graph without reattach change
- Soft-failing KG on the success path
- Embedding production secrets in VCS; non-CI-safe default embedder for tests
- Silent swap of process-local store for multi-instance persistence without change control

## Packt Ch.4 alignment

| Ch.4 pattern | As-built mapping |
|--------------|------------------|
| FileTypeRouter | Explicit router; MIME buckets authoritative |
| Per-MIME converters | FR-IX-012 map |
| Dual preprocess | Unstructured word path vs CSV clean/row-split |
| Joiner | `final_doc_joiner` |
| Embed → write | `doc_embedder` → `DocumentWriter` → `InMemoryDocumentStore` |
| Extension (this product) | Post-join mandatory user-scoped KG (HR-76) |

## Key decisions

| Decision | Rationale |
|----------|-----------|
| Reroute public from-project-spec to indexing | Packt-style index before recommend reattach |
| InMemoryDocumentStore default | CI-safe process-local; persistent later |
| MockDocumentEmbedder default | CI without external embedding APIs |
| Mandatory KG after joiner | HR-76 identity + graph; hard-fail |
| JSON/XLSX structured data_kind + unstructured clean path | Count kind vs preprocess topology |

## Change control

See [`spec.md`](./spec.md) change-control table (0.1.0–0.6.0 historical; 1.0.0 OpenSpec migration).

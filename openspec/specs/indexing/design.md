# Indexing Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, Outcomes, and Requirements (FR-IX-001–025 + MIME classification map). Live HTTP owner for `POST /internal/v1/recommendations/submitprojectspecification`; conflict rule: live route wins here; KG rules in [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md).

**API field tables:** [`contracts/ingest-from-project-spec.md`](./contracts/ingest-from-project-spec.md).  
**Resilience (S2a):** FR-IX-024 idempotency + FR-IX-025 correlation — process-local only in C1.

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
  POST /submitprojectspecification (user_id required)
       │
       ├─ middleware: X-Correlation-Id / traceparent → logging context (S2a)
       │
       ├─ if Idempotency-Key present (scoped user_id + key):
       │     hit in-memory store? → return cached lean 200 (same ingest_id)
       │     else run pipeline below → store only on 200
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
  IngestFromProjectSpecResponse (lean public body)
       │  as-built S1a: ingest_id, user_id, user_requirement_summary, warnings
       │  as-built S1b: tentative_* echo request dates
       │  as-built S1c: needs_summary[] via need decomposer (stub/LLM)
       │  as-built S1d: expected_budget extract-only (never invent)
       │  as-built S1e: free-text/file dates if request omits (request preferred)
       │  FR-IX-023 Call 1 summary: as-built (Phase 1.7)
       │  as-built S2a: Idempotency-Key replay (FR-IX-024); correlation echo (FR-IX-025)
       ▼
  project-spec summary enrichment (after successful index + KG only)
       • needs_summary (decomposer / LLM)                     [S1c]
       • expected_budget (extract or null; never invent)      [S1d]
       • tentative_* free-text/file extract if request omits  [S1e]

       │
       ▼
  enriched response (still not results_by_need)
       │
       │  Portal dual-hop (Spring-owned):
       │  React POST /api/recommendations/project-spec
       │    → Call 1 (this diagram) → persist ingest_id
       │    → Call 2 getassetrecommendations → recommend quote (primary to React)
       │    → optional Call 3 project-knowledge/query → chatbot Q&A
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
| `app/services/ingest_idempotency.py` | **as-built S2a:** process-local `Idempotency-Key` store (FR-IX-024) |
| `app/middleware/correlation.py` | **as-built S2a:** `X-Correlation-Id` / `traceparent` (FR-IX-025) |
| `app/api/recommendations.py` | Thin HTTP; optional `Idempotency-Key` on ingest |
| `app/schemas/indexing.py` | Response DTO — FR-IX-023 as-built (S1a–S1e) |
| `app/services/need_decomposer.py` / LLM | **as-built S1c:** needs_summary from project text |
| `app/services/project_spec_budget.py` | **as-built S1d:** expected_budget extract |
| `app/services/project_spec_dates.py` | **as-built S1e:** resolve_rental_dates (request preferred) |
| `app/config.py` | `INDEXING_*`, `KG_*`, `IDEMPOTENCY_TTL_SECONDS` |
| `postman/` | Live collection |

### As-built extraction notes (FR-IX-023 / Phase 1.7)

| Output | Source precedence |
|--------|-------------------|
| `needs_summary` | Decompose resolved project text (and/or KG-1 nodes); stub decomposer for CI |
| `tentative_*` dates | Request `start_date`/`end_date` if set; else extract from text/file; else null |
| `expected_budget` | Extract currency/amount phrases from text; else null + warning — **not** `include_pricing` |
| Still after index | Summary MUST NOT run if index/KG hard-fail |

Compact response: portal may only need identity + summary; technical index/KG fields stay in session `meta` (not public body).

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
- `IDEMPOTENCY_TTL_SECONDS` — optional TTL for process-local successful ingest cache (default `86400`; ≤0 disables expiry)

### Tests

| Area | Modules / notes |
|------|-----------------|
| Component + pipeline | `tests/test_indexing_*.py` (router, converters, dual-branch, write path) |
| HTTP ingest fields | `tests/test_recommendations_intake.py` (FR-IX-023 lean body, not recommend envelope) |
| Idempotency (S2a) | `tests/test_ingest_idempotency.py` (same key, missing key, multipart, failure not cached, single-flight, blank key, TTL unit) |
| Correlation (S2a) | `tests/test_correlation_middleware.py` (echo, mint, log binds `correlation_id`, Q&A) |
| Date extract (S1e) | `tests/test_project_spec_dates.py` + intake free-text date cases |
| Budget extract (S1d) | `tests/test_project_spec_budget.py` + intake budget cases |
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

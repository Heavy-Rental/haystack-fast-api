# Specification: Indexing Pipeline (File Type Router → Vectorize)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (Spec-kit Specify artifact) |
| **Status** | **As-built** — Packt dual-branch index → store; `user_id` required; optional HR-76 KG after `final_doc_joiner` |
| **Feature id** | `indexing-file-type-router` |
| **Tracking** | HR-74 · HR-76 (identity + KG hook) |
| **Spec location** | `specification/SPEC-indexing-file-type-router.md` |
| **Reading map** | [`README.md`](./README.md) Path B step 5 |
| **Tasks** | [`tasks-indexing-file-type-router.md`](./tasks-indexing-file-type-router.md) |
| **Next in flow** | [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md) |
| **Postman (live HTTP)** | [`../postman/README.md`](../postman/README.md) |
| **Env** | [`.env.example`](../.env.example) |
| **Parent** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) |
| **Supersedes for route** | `intake_front` / FR-010 recommend as default HTTP graph |

**Spec-kit phases:** Specify (this file) → Plan → Tasks → Implement → Converge.

When behaviour here and the codebase diverge, update them in the **same change set**.

---

## Document roles & conflict rule

| Document | Owns |
|----------|------|
| **This SPEC** | Live HTTP index graph, MIME map, `user_id`, full ingest response table |
| [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md) | Optional KG after `final_doc_joiner` |
| [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) | FR-010 **service-level** (not default route) |
| [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) | Deferred recommend envelope |
| Parent agentic SPEC | Product vision / catalog |
| [`../postman/README.md`](../postman/README.md) | Live Postman |

**Conflict rule:** Live route → **this SPEC**. Optional KG rules → knowledge-graph SPEC. Recommend envelope without “deferred” label loses to this SPEC.

**As-built vs parent FR-040:** live response is **ingest + optional kg_***, not ranked `results_by_need`.

---

## 1. Purpose

Introduce a Haystack **indexing-style pipeline** that starts with **file type routing** (extension / MIME) so project-spec uploads are classified as **structured** or **unstructured**, then converted, chunked, embedded, and written to a DocumentStore.

**Part 1 delivered:**

1. `FileTypeRouter`-backed classification under `app/pipelines/indexing/`.
2. Reroute `POST /api/v1/recommendations/from-project-spec` to this pipeline **instead of** `build_intake_front_pipeline` / FR-010 recommend.

**Part 2 delivered:**

3. MIME-specific converters on structured and unstructured branches → Haystack `Document`s.
4. API response includes `document_count` and truncated `documents[]` previews.

**Part 3 delivered:**

5. `DocumentCleaner` → `DocumentSplitter` → document embedder → `DocumentWriter`.
6. Default process-local `InMemoryDocumentStore`; CI-safe default embedder (`MockDocumentEmbedder`).
7. Response fields `chunk_count`, `documents_written`, and `has_embedding` on previews.

**HR-76 (shipped):** required `user_id`; optional user-scoped KG after post-join chunks ([`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md)).

**Out of scope (still):** persistent multi-instance DocumentStore; Naive/hybrid RAG **query** HTTP; recommend reattach on this route (T017); `LinkContentFetcher` (T030).

---

## 2. Outcomes

- Multipart file uploads are packaged as Haystack `ByteStream` with `mime_type` derived from filename extension.
- Pipeline classifies each source as structured, unstructured, or unclassified.
- Classified sources are **converted** to Haystack `Document`s by MIME type.
- Converted documents are **cleaned, split, embedded, and written** to a DocumentStore.
- Request requires **`user_id`** (optional `user_name`); echoed on response; stamped on chunk meta.
- Successful responses return ingest fields plus optional **`kg_*`** when `KG_ENABLED=true`.
- Missing `user_id`, unclassified type, empty source, or zero written chunks → **400**.
- Dates accepted; unused for ranking until reattach.

---

## 3. MIME / extension map (normative)

| Kind | Extensions | MIME types |
|------|------------|------------|
| **Unstructured** | `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.html`, `.htm` | `text/plain`, `text/markdown`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/html` |
| **Structured** | `.csv`, `.json`, `.xlsx` | `text/csv`, `application/json`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| **Unclassified** | other / unknown | → **400** |

**Routing note:** Explicit `FileTypeRouter`. Unstructured: sanitizer → cleaner → word split. CSV: CSV cleaner → row-wise split. Meet at **`final_doc_joiner`** → embed → write. JSON/XLSX use unstructured clean/split path but count as **structured** for `data_kind`.

---

## 4. Functional requirements

| ID | Requirement |
|----|-------------|
| **FR-IX-001** | `POST /api/v1/recommendations/from-project-spec` MUST run the **indexing file-type pipeline**, not `intake_front`, as the default HTTP path. |
| **FR-IX-002** | Uploaded files MUST be classified by extension/MIME into **structured** or **unstructured**. |
| **FR-IX-003** | Unclassified / unsupported types MUST yield HTTP **400** `{"error","message"}`. |
| **FR-IX-004** | Routers stay thin; MIME policy and branching live under `app/pipelines/` / services. |
| **FR-IX-005** | Components follow Haystack 2.0: `@component`, typed sockets, `run()` → `dict`. |
| **FR-IX-006** | Non-empty JSON `project_text` MUST be treated as unstructured `text/plain` when no file (or in addition to file sources). |
| **FR-IX-007** | Part 3 MAY use a process-local `InMemoryDocumentStore` by default; persistent stores are a later swap. |
| **FR-IX-008** | Async handlers MUST offload sync pipeline work with `run_in_threadpool`. |
| **FR-IX-009** | Empty file bytes and empty combined sources → **400**. |
| **FR-IX-010** | Classification MUST use Haystack `FileTypeRouter` (wrapped or connected) so MIME buckets are authoritative. |
| **FR-IX-011** | After classification, structured and unstructured sources MUST be converted to Haystack `Document`s via MIME-specific converters. |
| **FR-IX-012** | Converter map: plain/json text → `TextFileToDocument`; markdown → `MarkdownToDocument`; html → `HTMLToDocument`; pdf → `PyPDFToDocument`; docx → `DOCXToDocument`; csv → `CSVToDocument`; xlsx → `XLSXToDocument`. |
| **FR-IX-013** | Zero documents after successful classification (hard conversion failure) → **400**. Soft per-file conversion issues MAY appear in `warnings`. |
| **FR-IX-014** | After convert, unstructured vs CSV preprocess separately, then **join** → embed → write. |
| **FR-IX-015** | Default embedder MUST be CI-safe (`MockDocumentEmbedder` or equivalent). Optional `openai` mode via `INDEXING_EMBEDDER`. |
| **FR-IX-016** | Successful ingest MUST report `documents_written` ≥ 1 (and matching `chunk_count` for the default path). Zero written chunks → **400**. |
| **FR-IX-017** | Successful responses MUST use `IngestFromProjectSpecResponse` (`ingest_id`, …). MUST NOT return `recommendation_id` / `results_by_need` on the default path until reattach is specified. |
| **FR-IX-018** | Indexing graph MUST expose an explicit **FileTypeRouter** (or equivalent) with **parallel** unstructured vs CSV preprocess branches, then join before embed/write (Packt Ch. 4 pattern). |
| **FR-IX-019** | CSV branch MUST use CSV-oriented clean/split (e.g. `CSVDocumentCleaner` + row-wise `CSVDocumentSplitter`), not only the unstructured word splitter. |
| **FR-IX-020** | Unstructured branch MUST run sanitizer (or equivalent quality gate) → `DocumentCleaner` → word `DocumentSplitter` before the final joiner. |
| **FR-IX-021** | Request MUST include `user_id`; MAY include `user_name`. Chunks SHOULD carry these in metadata. |
| **FR-IX-022** | When `KG_ENABLED=true`, after **`final_doc_joiner`** chunks exist, MAY build a user-scoped KG; full Ragas transforms run only inside `KnowledgeGraphGenerator` (see [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md)). |

---

## 5. API contract (as-built)

### Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant for meta + KG path |
| `user_name` | no | Echo / audit |
| `project_text` and/or `file` | one non-empty source | JSON-only needs non-empty text |
| `start_date` / `end_date` | no | Window valid if both set |
| `options` / `include_pricing` | no | Accepted; unused until reattach |

### Success response `200` — `IngestFromProjectSpecResponse`

| Field | Type | Notes |
|-------|------|--------|
| `ingest_id` | string | `ing_` + hex |
| `user_id` / `user_name` | string / null | Echo |
| `data_kind` | structured \| unstructured \| mixed | |
| `mime_types_seen` / `filenames` | string[] | |
| `structured_count` / `unstructured_count` | int | Sources |
| `document_count` (+ structured/unstructured_document_count) | int | Pre-split logical units |
| `chunk_count` / `documents_written` | int | After split/write |
| `documents` | object[] | Previews + meta (`user_id`, `ingest_id`, …) |
| `kg_built` | bool | Default false |
| `kg_node_count` / `kg_relationship_count` | int \| null | |
| `kg_artifact_path` | string \| null | Under `KG_ARTIFACT_DIR/{user_id}/` |
| `kg_transform_applied` | bool | Full Ragas on generator |
| `warnings` | string[] | |

**Breaking:** no default `results_by_need`; **`user_id` required**.
---

## 6. Design

Aligned with Packt Ch. 4 indexing flowchart
([indexing_pipeline.png](https://github.com/PacktPublishing/Building-Natural-Language-and-LLM-Pipelines/blob/main/ch4/jupyter-notebooks/images/indexing_pipeline.png)):
**FileTypeRouter → dual preprocess branches → joiner → embed → write**.

```text
  POST /from-project-spec (user_id required)
       │
       ▼
  file_type_router → dual-branch convert/clean/split
       │
       ▼
  final_doc_joiner
       ├─► doc_embedder → writer → InMemoryDocumentStore
       └─► (KG_ENABLED) post-join chunks → KG (see knowledge-graph SPEC)
       │
       ▼
  IngestFromProjectSpecResponse
```

### Modules

| Path | Role |
|------|------|
| `app/pipelines/indexing/*` | Dual-branch index graph, store, embedder |
| `app/pipelines/kg/*` | Optional KG (HR-76) |
| `app/services/indexing.py` | Index + optional KG hook |
| `app/api/recommendations.py` | Thin HTTP |
| `app/schemas/indexing.py` | Response DTO |
| `app/config.py` | `INDEXING_*`, `KG_*` |
| `postman/` | Live collection |

### Tests

`tests/test_indexing_*.py`, `tests/test_knowledge_graph.py`, `tests/test_recommendations_intake.py`.

---

## 7. Acceptance criteria

1. **Given** multipart `needs.csv`, **when** POST, **then** `data_kind=structured`, `structured_count≥1`, `document_count≥1`, content preview includes CSV text.
2. **Given** multipart `brief.md` or JSON `project_text`, **when** POST, **then** `data_kind=unstructured` and `document_count≥1` with extracted text.
3. **Given** unsupported extension (e.g. `.bin`), **when** POST, **then** **400**.
4. **Given** empty file / empty text, **when** POST, **then** **400**.
5. **Given** unit tests on the router component, **when** run standalone, **then** MIME map matches §3.
6. **Given** the route handler, **when** Parts 1–3 ship, **then** it does not call `run_intake_front` as primary path.
7. **Given** `.docx` / `.xlsx` with valid content, **when** convert runs, **then** at least one Document is produced.
8. **Given** successful convert, **when** Part 3 pipeline runs, **then** `documents_written ≥ 1`, chunk previews have `has_embedding=true`, and the DocumentStore count increases.
9. **Given** a successful POST, **when** body is inspected, **then** `ingest_id` and `user_id` present; `results_by_need` absent.
10. **Given** no `user_id`, **when** POST, **then** **400**.

---

## 8. Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-07 | Part 1 FileTypeRouter + route reroute |
| **0.2.0** | 2026-08-07 | Part 2 converters |
| **0.3.0** | 2026-08-07 | Part 3 embed/write |
| **0.3.1** | 2026-08-07 | Spec reconcile vs recommend SPECs |
| **0.4.0** | 2026-08-07 | Packt dual-branch FR-IX-018–020 |
| **0.5.0** | 2026-08-07 | HR-76 user_id + KG hook FR-IX-021–022 |
| **0.6.0** | 2026-08-07 | Sequential reading map; full API tables; KG not “future-only” |

---

**Reading order:** [← Setup](./SPEC-project-setup.md) · [Map](./README.md) · [Next: Knowledge graph →](./SPEC-knowledge-graph.md)

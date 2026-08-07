# Specification: Indexing Pipeline (File Type Router → Vectorize)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (Spec-kit Specify artifact) |
| **Status** | **As-built Parts 1–3** — classify → convert → clean → split → embed → write |
| **Feature id** | `indexing-file-type-router` |
| **Spec location** | `specification/SPEC-indexing-file-type-router.md` |
| **Tasks** | [`tasks-indexing-file-type-router.md`](./tasks-indexing-file-type-router.md) |
| **Postman (live HTTP)** | [`../postman/README.md`](../postman/README.md) |
| **Parent** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) (FR-019d, indexing pipeline; §11 KG target) |
| **Supersedes for route** | `intake_front` / FR-010 recommend as the **default HTTP** graph for `POST .../from-project-spec` |

**Spec-kit phases:** Specify (this file) → Plan → Tasks → Implement → Converge.

When behaviour here and the codebase diverge, update them in the **same change set**.

---

## Document roles & conflict rule

| Document | Owns |
|----------|------|
| **This SPEC** | **Live** behaviour of `POST /api/v1/recommendations/from-project-spec`: indexing pipeline, MIME map, ingest response (`IngestFromProjectSpecResponse`) |
| [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) | FR-010.1–8 **service-level** recommend graph (`RecommendationService`, seed fleet) — **not** the default public route |
| [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) | Request shapes; **deferred** recommend response envelope for reattach |
| Parent agentic SPEC | Product vision, catalog policy, **target** KG / hybrid retrieval |
| [`../postman/README.md`](../postman/README.md) | Live HTTP Postman collection for **ingest** |

**Conflict rule (normative):** As of **2026-08-07**, the public route is owned by this **indexing** SPEC. Recommend FR-010 remains in code for unit tests and **reattach**, but is **not** the default HTTP path. Where older SPECs describe `recommendation_id` / `results_by_need` on this route without a deferred label, **this SPEC wins**.

**As-built deviation from parent FR-040 recommend envelope:** parent still describes target recommend API; **current as-built** returns ingest classification + vectorize metadata only (see §5).

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

**Out of scope (still):**

- Persistent vector DB / multi-instance store  
- Hybrid retrieval **query** path  
- Knowledge graph build (parent §11 **target**; feasible **after** store write — see tasks T020)  
- LLM need decompose + FR-010.4–8 ranking on **this** route (reattach = T017)

---

## 2. Outcomes

- Multipart file uploads are packaged as Haystack `ByteStream` with `mime_type` derived from filename extension.
- Pipeline classifies each source as structured, unstructured, or unclassified.
- Classified sources are **converted** to Haystack `Document`s by MIME type.
- Converted documents are **cleaned, split, embedded, and written** to a DocumentStore.
- Successful responses return an **ingest** envelope (`data_kind`, convert counts, `chunk_count`, `documents_written`, chunk previews with `has_embedding`).
- Unclassified, empty input, conversion with zero documents, or zero written chunks → HTTP **400** shared error JSON.
- JSON-only `project_text` is treated as unstructured `text/plain`.
- FastAPI handlers stay thin; type policy, conversion, and vectorize live in pipelines/services.
- Optional `start_date` / `end_date` are accepted for API stability; **unused for ranking** until recommend is reattached.

---

## 3. MIME / extension map (normative)

| Kind | Extensions | MIME types |
|------|------------|------------|
| **Unstructured** | `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.html`, `.htm` | `text/plain`, `text/markdown`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/html` |
| **Structured** | `.csv`, `.json`, `.xlsx` | `text/csv`, `application/json`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| **Unclassified** | other / unknown | → **400** |

**Routing note:** Decision routing is **classify** (kind) + **convert** (per-MIME). After convert, clean → split → embed → write is a **shared** path for both kinds.

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
| **FR-IX-014** | After convert, the pipeline MUST run clean → split → embed → write. |
| **FR-IX-015** | Default embedder MUST be CI-safe (`MockDocumentEmbedder` or equivalent). Optional `openai` mode via `INDEXING_EMBEDDER`. |
| **FR-IX-016** | Successful ingest MUST report `documents_written` ≥ 1 (and matching `chunk_count` for the default path). Zero written chunks → **400**. |
| **FR-IX-017** | Successful responses MUST use `IngestFromProjectSpecResponse` (`ingest_id`, …). MUST NOT return `recommendation_id` / `results_by_need` on the default path until reattach is specified. |
| **FR-IX-018** | Indexing graph MUST expose an explicit **FileTypeRouter** (or equivalent) with **parallel** unstructured vs CSV preprocess branches, then join before embed/write (Packt Ch. 4 pattern). |
| **FR-IX-019** | CSV branch MUST use CSV-oriented clean/split (e.g. `CSVDocumentCleaner` + row-wise `CSVDocumentSplitter`), not only the unstructured word splitter. |
| **FR-IX-020** | Unstructured branch MUST run sanitizer (or equivalent quality gate) → `DocumentCleaner` → word `DocumentSplitter` before the final joiner. |

---

## 5. API contract (as-built)

### Request

- JSON: `project_text` (required non-empty for JSON-only), optional `start_date` / `end_date` / `options` (dates validated when both set: `end_date` ≥ `start_date`).
- Multipart: `file` and/or `project_text`, optional dates / `include_pricing` (accepted; pricing unused until reattach).

### Success response `200` — `IngestFromProjectSpecResponse`

| Field | Type | Notes |
|-------|------|--------|
| `ingest_id` | string | `ing_` + hex |
| `data_kind` | `"structured"` \| `"unstructured"` \| `"mixed"` | From classified sources |
| `mime_types_seen` | string[] | Distinct MIME types matched |
| `filenames` | string[] | From ByteStream meta / synthetic name |
| `structured_count` | int | Classified structured **sources** |
| `unstructured_count` | int | Classified unstructured **sources** |
| `document_count` | int | Documents after convert (pre-split) |
| `structured_document_count` | int | |
| `unstructured_document_count` | int | |
| `chunk_count` | int | Chunks after split/embed |
| `documents_written` | int | Chunks written to DocumentStore |
| `documents` | object[] | Chunk previews: `content_preview`, `content_length`, `meta`, `data_kind`, `has_embedding` |
| `warnings` | string[] | e.g. in-memory store note |

**Breaking change (vs pre-2026-08-07 recommend MVP):** this route no longer returns `recommendation_id` / `results_by_need` / ranked `item`. Recommend pipeline remains under `app/services/recommendations.py` for reattach or a future separate route.

---

## 6. Design

Aligned with Packt Ch. 4 indexing flowchart
([indexing_pipeline.png](https://github.com/PacktPublishing/Building-Natural-Language-and-LLM-Pipelines/blob/main/ch4/jupyter-notebooks/images/indexing_pipeline.png)):
**FileTypeRouter → dual preprocess branches → joiner → embed → write**.

```text
  POST /from-project-spec
       │
       ▼
  package ByteStream(s)
       │
       ▼
  IndexingIngestService
       │
       ▼
  Pipeline (Packt-style)
       file_type_router
            ├─ unstructured MIME → converters → unstructured_joiner
            │       → sanitizer → text_cleaner → text_splitter ─┐
            ├─ text/csv → csv_converter → csv_cleaner             │
            │            → csv_splitter (row-wise) ───────────────┤
            └─ json/xlsx → converters → unstructured path ───────┤
                                                                  ▼
                                                         final_doc_joiner
                                                                  │
                                                           doc_embedder
                                                                  │
                                                              writer
                                                                  │
                                                     InMemoryDocumentStore
       │
       ▼
  IngestFromProjectSpecResponse
```

Optional later: `LinkContentFetcher` → HTML converter (book web branch; T030).

### Modules

| Path | Role |
|------|------|
| `app/pipelines/indexing/mime_map.py` | Extension ↔ MIME constants |
| `app/pipelines/indexing/data_kind_classifier.py` | Collapse MIME buckets → kinds |
| `app/pipelines/indexing/document_converter.py` | MIME → Haystack converters → Documents |
| `app/pipelines/indexing/document_store.py` | Shared `InMemoryDocumentStore` |
| `app/pipelines/indexing/embedder_factory.py` | mock / openai document embedder |
| `app/pipelines/indexing/pipeline.py` | `build_indexing_pipeline` / `run_indexing_pipeline` |
| `app/services/indexing.py` | Orchestration + errors |
| `app/api/recommendations.py` | Thin HTTP; ByteStream packaging |
| `app/schemas/indexing.py` | Response DTO |
| `app/config.py` | `INDEXING_*` settings |
| `postman/` | Live HTTP collection + fixtures |

### Future (not as-built)

```text
  … → write → InMemoryDocumentStore
                    │
                    ▼  (optional / offline — T020)
              load docs → knowledge graph → KG_ARTIFACT_DIR/*.json
```

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
9. **Given** a successful POST, **when** body is inspected, **then** `ingest_id` is present and `results_by_need` is absent.

---

## 8. Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-07 | Part 1: FileTypeRouter classification; reroute `/from-project-spec` off recommend pipeline |
| **0.2.0** | 2026-08-07 | Part 2: MIME converters; response adds document previews/counts |
| **0.3.0** | 2026-08-07 | Part 3: clean → split → embed → write; `chunk_count` / `documents_written` |
| **0.3.1** | 2026-08-07 | Spec reconcile: authority/conflict rule; Part labels; links to postman + deferred KG/recommend; FR-IX-017 |
| **0.4.0** | 2026-08-07 | Packt Ch.4 dual-branch graph (router, CSV branch, sanitizer, final joiner); FR-IX-018–020 |

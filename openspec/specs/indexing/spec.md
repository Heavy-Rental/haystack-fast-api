# Indexing Specification (File Type Router → Vectorize)

| Field | Value |
|-------|--------|
| **Status** | as-built |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD |
| **Feature id** | `indexing-file-type-router` |
| **Tracking** | HR-74 · HR-76 (identity + KG hook) |
| **Contracts** | [`contracts/ingest-from-project-spec.md`](./contracts/ingest-from-project-spec.md) |
| **Design** | [`design.md`](./design.md) |
| **Archived tasks** | [`../../changes/archive/2026-08-07-indexing-file-type-router/tasks.md`](../../changes/archive/2026-08-07-indexing-file-type-router/tasks.md) |
| **Next in flow** | [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) |
| **Postman (live HTTP)** | [`../../../postman/README.md`](../../../postman/README.md) |
| **Env** | [`../../../.env.example`](../../../.env.example) |
| **Agent map** | [`../../AGENTS.md`](../../AGENTS.md) Path B |

**Spec-kit phases:** Specify (this file) → Plan → Tasks → Implement → Converge.

When behaviour here and the codebase diverge, update them in the **same change set**.

### Document roles & conflict rule

| Document | Owns |
|----------|------|
| **This capability** | Live HTTP index graph, MIME map, `user_id`, full ingest response table |
| [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) | Mandatory KG after `final_doc_joiner` (hard-fail) |
| [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md) | FR-010 **service-level** (not default route) |
| [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md) | Deferred recommend envelope |
| Parent agentic / product vision | Catalog and product vision |
| [`../../../postman/README.md`](../../../postman/README.md) | Live Postman |

**Conflict rule:** Live route → **this capability wins here**. Optional / full KG rules → [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md). Recommend envelope without a “deferred” label loses to this capability.

**As-built vs parent FR-040:** live public response is a **lean ingest envelope** with **FR-IX-023 as-built** fields (`ingest_id`, `user_id`, `user_requirement_summary`, `tentative_*`, `needs_summary[]`, `expected_budget` | null, `warnings[]`), not ranked `results_by_need`. Index/KG technical detail runs internally (session meta).

**As-built (S1a–S1e / Phase 1.7):** full Call 1 project-spec summary. MUST NOT become FR-010 `results_by_need` without recommend reattach.

---

## Purpose

Introduce a Haystack **indexing-style pipeline** that starts with **file type routing** (extension / MIME) so project-spec uploads are classified as **structured** or **unstructured**, then converted, chunked, embedded, and written to a DocumentStore.

**Part 1 delivered:**

1. `FileTypeRouter`-backed classification under `app/pipelines/indexing/`.
2. Reroute `POST /internal/v1/recommendations/submitprojectspecification` to this pipeline **instead of** `build_intake_front_pipeline` / FR-010 recommend.

**Part 2 delivered:**

3. MIME-specific converters on structured and unstructured branches → Haystack `Document`s.
4. API response includes `document_count` and truncated `documents[]` previews.

**Part 3 delivered:**

5. `DocumentCleaner` → `DocumentSplitter` → document embedder → `DocumentWriter`.
6. Default process-local `InMemoryDocumentStore`; CI-safe default embedder (`MockDocumentEmbedder`).
7. Lean public response fields `ingest_id`, `user_id`, `user_requirement_summary`, `warnings` (internal store still has embeddings).

**HR-76 (shipped):** required `user_id`; **mandatory** user-scoped KG after post-join chunks ([`../knowledge-graph/spec.md`](../knowledge-graph/spec.md)).

### Outcomes

- Multipart file uploads are packaged as Haystack `ByteStream` with `mime_type` derived from filename extension.
- Pipeline classifies each source as structured, unstructured, or unclassified.
- Classified sources are **converted** to Haystack `Document`s by MIME type.
- Converted documents are **cleaned, split, embedded, and written** to a DocumentStore.
- Request requires **`user_id`** (optional `user_name`); echoed on response; stamped on chunk meta.
- Successful public responses return the **lean** ingest body; KG success is required for 200 but **`kg_*` are not exposed** on the public body (session registry holds artifact path).
- Missing `user_id`, unclassified type, empty source, zero written chunks, or KG failure → **400**.
- Dates accepted; unused for ranking until reattach.

### Out of scope (still)

- Persistent multi-instance DocumentStore
- Naive/hybrid RAG **query** HTTP
- Recommend reattach on this route (T017)
- `LinkContentFetcher` (T030)

---

## User Scenarios & Testing

### User Story 1 - Structured CSV ingest (Priority: P1)

A portal user uploads a structured project-spec CSV (e.g. `needs.csv`) with a required `user_id` and receives an ingest response classifying the source as structured, with documents and written chunks.

**Independent Test:** Multipart POST to `/internal/v1/recommendations/submitprojectspecification` with `user_id` and `needs.csv`.

**Acceptance Scenarios:**

1. **Given** multipart `needs.csv`, **When** POST, **Then** `data_kind=structured`, `structured_count≥1`, `document_count≥1`, content preview includes CSV text.
2. **Given** successful convert and Part 3 pipeline, **When** write completes, **Then** DocumentStore count increases and Call 1 returns lean `ingest_id` + non-empty `user_requirement_summary`.

### User Story 2 - Unstructured text / markdown ingest (Priority: P1)

A portal user submits free-text `project_text` or a markdown brief and receives unstructured classification with extracted document content.

**Independent Test:** JSON or multipart POST with non-empty `project_text` or `brief.md`.

**Acceptance Scenarios:**

1. **Given** multipart `brief.md` or JSON `project_text`, **When** POST, **Then** `data_kind=unstructured` and `document_count≥1` with extracted text.
2. **Given** a successful POST, **When** body is inspected, **Then** `ingest_id` and `user_id` present; `results_by_need` absent.

### User Story 3 - Reject unsupported or empty sources (Priority: P1)

Clients sending unsupported extensions, empty payloads, or missing identity receive HTTP 400 with shared error JSON.

**Independent Test:** POST with `.bin`, empty file/text, or no `user_id`.

**Acceptance Scenarios:**

1. **Given** unsupported extension (e.g. `.bin`), **When** POST, **Then** **400**.
2. **Given** empty file / empty text, **When** POST, **Then** **400**.
3. **Given** no `user_id`, **When** POST, **Then** **400**.

### User Story 4 - Office document conversion (Priority: P2)

Valid `.docx` / `.xlsx` content converts to at least one Haystack Document on the correct branch.

**Independent Test:** Unit/integration convert tests with sample office files.

**Acceptance Scenarios:**

1. **Given** `.docx` / `.xlsx` with valid content, **When** convert runs, **Then** at least one Document is produced.

### User Story 5 - Indexing owns the live HTTP path (Priority: P1)

The public from-project-spec route runs the indexing pipeline, not intake-front recommend.

**Independent Test:** Route handler and MIME map unit tests.

**Acceptance Scenarios:**

1. **Given** the route handler, **When** Parts 1–3 ship, **Then** it does not call `run_intake_front` as primary path.
2. **Given** unit tests on the router component, **When** run standalone, **Then** MIME map matches the MIME classification map requirement.

---

## Requirements

### Requirement: Live route runs indexing pipeline
`POST /internal/v1/recommendations/submitprojectspecification` MUST run the **indexing file-type pipeline**, not `intake_front`, as the default HTTP path.  
(Trace: FR-IX-001)

#### Scenario: Default HTTP path is indexing
- **WHEN** a client calls `POST /internal/v1/recommendations/submitprojectspecification`
- **THEN** the handler runs the indexing file-type pipeline
- **AND** does not use `build_intake_front_pipeline` / FR-010 recommend as the primary path

### Requirement: Classify uploads as structured or unstructured
Uploaded files MUST be classified by extension/MIME into **structured** or **unstructured**.  
(Trace: FR-IX-002)

#### Scenario: Structured vs unstructured classification
- **WHEN** an uploaded file has a known extension/MIME from the MIME classification map
- **THEN** it is classified as structured or unstructured accordingly

### Requirement: Unclassified types yield 400
Unclassified / unsupported types MUST yield HTTP **400** `{"error","message"}`.  
(Trace: FR-IX-003)

#### Scenario: Unsupported type rejected
- **WHEN** a client uploads an unsupported extension (e.g. `.bin`) or unknown MIME
- **THEN** the response is HTTP 400 with `error` and `message` fields

### Requirement: Thin routers; policy under pipelines/services
Routers stay thin; MIME policy and branching live under `app/pipelines/` / services.  
(Trace: FR-IX-004)

#### Scenario: Router does not own MIME policy
- **WHEN** MIME classification or branch selection is required
- **THEN** policy and branching execute under `app/pipelines/` / services, not inline in the router

### Requirement: Haystack 2.0 component conventions
Components follow Haystack 2.0: `@component`, typed sockets, `run()` → `dict`.  
(Trace: FR-IX-005)

#### Scenario: Component contract
- **WHEN** an indexing pipeline component is invoked
- **THEN** it is a Haystack 2.0 `@component` with typed sockets and returns a `dict` from `run()`

### Requirement: project_text as unstructured plain text
Non-empty JSON `project_text` MUST be treated as unstructured `text/plain` when no file (or in addition to file sources).  
(Trace: FR-IX-006)

#### Scenario: JSON-only project_text
- **WHEN** a client sends non-empty `project_text` without a file
- **THEN** the source is treated as unstructured `text/plain`

#### Scenario: project_text plus file
- **WHEN** a client sends non-empty `project_text` in addition to file sources
- **THEN** `project_text` is included as an unstructured `text/plain` source alongside files

### Requirement: Process-local DocumentStore by default
Part 3 MAY use a process-local `InMemoryDocumentStore` by default; persistent stores are a later swap.  
(Trace: FR-IX-007)

#### Scenario: Default store
- **WHEN** the indexing pipeline writes documents without a persistent-store override
- **THEN** a process-local `InMemoryDocumentStore` is used

### Requirement: Offload sync pipeline work
Async handlers MUST offload sync pipeline work with `run_in_threadpool`.  
(Trace: FR-IX-008)

#### Scenario: Threadpool offload
- **WHEN** an async HTTP handler runs the sync indexing pipeline
- **THEN** work is offloaded via `run_in_threadpool`

### Requirement: Empty sources yield 400
Empty file bytes and empty combined sources → **400**.  
(Trace: FR-IX-009)

#### Scenario: Empty file or empty combined sources
- **WHEN** file bytes are empty or all combined sources are empty
- **THEN** the response is HTTP 400

### Requirement: FileTypeRouter is authoritative for MIME buckets
Classification MUST use Haystack `FileTypeRouter` (wrapped or connected) so MIME buckets are authoritative.  
(Trace: FR-IX-010)

#### Scenario: FileTypeRouter drives classification
- **WHEN** sources are classified
- **THEN** Haystack `FileTypeRouter` (wrapped or connected) determines MIME buckets

### Requirement: Convert classified sources to Documents
After classification, structured and unstructured sources MUST be converted to Haystack `Document`s via MIME-specific converters.  
(Trace: FR-IX-011)

#### Scenario: Post-classification convert
- **WHEN** sources have been classified as structured or unstructured
- **THEN** each is converted to Haystack `Document`s via MIME-specific converters

### Requirement: MIME-specific converter map
Converter map: plain/json text → `TextFileToDocument`; markdown → `MarkdownToDocument`; html → `HTMLToDocument`; pdf → `PyPDFToDocument`; docx → `DOCXToDocument`; csv → `CSVToDocument`; xlsx → `XLSXToDocument`.  
(Trace: FR-IX-012)

#### Scenario: Converter selection by MIME
- **WHEN** a classified source has a mapped MIME type
- **THEN** the corresponding converter from the map is used

### Requirement: Zero documents after convert yields 400
Zero documents after successful classification (hard conversion failure) → **400**. Soft per-file conversion issues MAY appear in `warnings`.  
(Trace: FR-IX-013)

#### Scenario: Hard conversion failure
- **WHEN** classification succeeds but conversion yields zero documents
- **THEN** the response is HTTP 400

#### Scenario: Soft conversion issues
- **WHEN** a per-file conversion issue is soft (non-fatal for the batch)
- **THEN** it MAY appear in `warnings` without necessarily failing the whole request if other documents remain

### Requirement: Dual preprocess then join embed write
After convert, unstructured vs CSV preprocess separately, then **join** → embed → write.  
(Trace: FR-IX-014)

#### Scenario: Join before embed/write
- **WHEN** convert completes for unstructured and CSV branches
- **THEN** each branch preprocesses separately
- **AND** branches join before embed and write

### Requirement: CI-safe default embedder
Default embedder MUST be CI-safe (`MockDocumentEmbedder` or equivalent). Optional `openai` mode via `INDEXING_EMBEDDER`.  
(Trace: FR-IX-015)

#### Scenario: Default embedder is mock
- **WHEN** `INDEXING_EMBEDDER` is unset or set to the default mock mode
- **THEN** a CI-safe `MockDocumentEmbedder` (or equivalent) is used

#### Scenario: Optional openai embedder
- **WHEN** `INDEXING_EMBEDDER` is set to `openai`
- **THEN** the optional OpenAI document embedder mode is used

### Requirement: Successful ingest reports written chunks
Successful ingest MUST write ≥ 1 chunk internally (zero written chunks → **400**). Public body MUST NOT require `documents_written` / `chunk_count` (lean S1a).  
(Trace: FR-IX-016)

#### Scenario: At least one written document
- **WHEN** ingest completes successfully
- **THEN** the request succeeds with lean `ingest_id` and non-empty `user_requirement_summary`

#### Scenario: Zero written chunks rejected
- **WHEN** the pipeline would write zero chunks
- **THEN** the response is HTTP 400

### Requirement: Ingest response shape (no recommend envelope)
Successful responses MUST use lean `IngestFromProjectSpecResponse` (`ingest_id`, `user_id`, `user_requirement_summary`, `warnings`). MUST NOT return `recommendation_id` / `results_by_need` on the default path until reattach is specified. MUST NOT expose technical `documents[]` / public `kg_*` on the default lean body.  
(Trace: FR-IX-017)

#### Scenario: Ingest DTO only
- **WHEN** a successful default-path response is returned
- **THEN** the body is lean `IngestFromProjectSpecResponse` with `ingest_id`, `user_id`, and `user_requirement_summary`
- **AND** does not include `recommendation_id` or `results_by_need`

### Requirement: Explicit dual-branch Packt Ch.4 graph
Indexing graph MUST expose an explicit **FileTypeRouter** (or equivalent) with **parallel** unstructured vs CSV preprocess branches, then join before embed/write (Packt Ch. 4 pattern).  
(Trace: FR-IX-018)

#### Scenario: Parallel branches then join
- **WHEN** the indexing pipeline is built
- **THEN** it exposes an explicit FileTypeRouter (or equivalent)
- **AND** parallel unstructured vs CSV preprocess branches join before embed/write

### Requirement: CSV-oriented clean and split
CSV branch MUST use CSV-oriented clean/split (e.g. `CSVDocumentCleaner` + row-wise `CSVDocumentSplitter`), not only the unstructured word splitter.  
(Trace: FR-IX-019)

#### Scenario: CSV branch preprocessing
- **WHEN** a CSV source is on the structured/CSV branch
- **THEN** CSV-oriented cleaner and row-wise splitter are used (not only the unstructured word splitter)

### Requirement: Unstructured sanitizer cleaner word split
Unstructured branch MUST run sanitizer (or equivalent quality gate) → `DocumentCleaner` → word `DocumentSplitter` before the final joiner.  
(Trace: FR-IX-020)

#### Scenario: Unstructured branch preprocessing
- **WHEN** an unstructured source is preprocessed
- **THEN** sanitizer (or equivalent) → `DocumentCleaner` → word `DocumentSplitter` run before `final_doc_joiner`

### Requirement: user_id required; user_name optional
Request MUST include `user_id`; MAY include `user_name`. Chunks SHOULD carry these in metadata.  
(Trace: FR-IX-021)

#### Scenario: user_id required
- **WHEN** a request omits `user_id`
- **THEN** the response is HTTP 400

#### Scenario: Identity on chunks
- **WHEN** chunks are written for a request with `user_id` (and optional `user_name`)
- **THEN** chunks SHOULD carry these fields in metadata
- **AND** `user_id` / `user_name` are echoed on the response

### Requirement: Mandatory KG after final_doc_joiner
After **`final_doc_joiner`** chunks exist and index write succeeds, MUST build a user-scoped KG (hard-fail on failure); full Ragas transforms run only inside `KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true` (see [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md)).  
(Trace: FR-IX-022)

#### Scenario: Mandatory user-scoped KG
- **WHEN** post-join chunks exist and index write succeeds
- **THEN** a user-scoped knowledge graph is built
- **AND** failure of KG build hard-fails the request (HTTP 400)

#### Scenario: Ragas transforms gated
- **WHEN** KG is built
- **THEN** full Ragas transforms run only inside `KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true`

### Requirement: Lean project-spec summary on ingest response (as-built S1a)
After successful index + mandatory KG, the live success body MUST be a **lean client-facing envelope**:

1. **`ingest_id`** — handle for Call 2 / Call 3  
2. **`user_id`** — request echo  
3. **`user_requirement_summary`** — deterministic string from `project_text` or extracted multipart content (not raw bytes); MAY truncate with a warning  
4. **`warnings`** — soft issues (MAY be empty)  

MUST NOT expose technical `documents[]` previews or public `kg_*` on the default lean body.  
MUST NOT treat this as ranked fleet recommendations or ML rent prices (`results_by_need` / Call 3).  
(Trace: FR-IX-017 lean; partial FR-IX-023)  
**Status:** **as-built (S1a)**.

#### Scenario: Lean summary present on success
- **GIVEN** successful ingest of a project-spec with non-empty content
- **WHEN** `POST .../submitprojectspecification` succeeds
- **THEN** the body includes `ingest_id`, `user_id`, and non-empty `user_requirement_summary`
- **AND** does not include `documents`, `kg_built`, `recommendation_id`, or `results_by_need`

### Requirement: Tentative dates echo on ingest response (as-built S1b)
After successful index + mandatory KG, the live success body MUST include:

1. **`tentative_start_date`** — echo request `start_date` when provided; else `null`  
2. **`tentative_end_date`** — echo request `end_date` when provided; else `null`  

MUST apply to both JSON and multipart requests.  
When both request dates are set, `end_date` MUST be on or after `start_date` or the request fails with **400**.  
Free-text extract when request omits dates is specified under S1e (as-built).  
(Trace: partial FR-IX-023)  
**Status:** **as-built (S1b)**.

#### Scenario: Dates from request echoed
- **GIVEN** request supplies valid `start_date` and `end_date`
- **WHEN** `POST .../submitprojectspecification` succeeds
- **THEN** `tentative_start_date` / `tentative_end_date` echo the request window

#### Scenario: Dates omitted and text has no window
- **GIVEN** request omits both dates **and** project text has no confident rental window
- **WHEN** ingest succeeds
- **THEN** `tentative_start_date` and `tentative_end_date` are null
- **AND** a warning MAY state that rental dates were not found (S1e)

#### Scenario: Invalid date window rejected
- **GIVEN** request supplies `end_date` before `start_date`
- **WHEN** ingest is attempted (JSON or multipart)
- **THEN** the response is HTTP 400 with the shared error shape

### Requirement: Full project-spec summary on ingest response (as-built FR-IX-023)

FR-IX-023 Call 1 project-spec summary is **complete** after S1a–S1e (see [`Feasibility_Study/implementation-plan.md`](../../../Feasibility_Study/implementation-plan.md) Phase 1):

| Order | Stage | Work | Status |
|-------|-------|------|--------|
| 1 | **S1c** | `needs_summary[]` via decomposer after index+KG | **as-built** |
| 2 | **S1d** | `expected_budget` extract; never invent | **as-built** |
| 3 | **S1e** | Free-text / file date extract when request omits dates | **as-built** |
| 4 | **1.7** | Mark full FR-IX-023 as-built when S1c+S1d+S1e green | **as-built** |

MUST NOT use `options.include_pricing` as a budget amount (boolean only).  
MUST NOT treat summary as ranked fleet recommendations or ML rent (`results_by_need` / Call 3).  
(Trace: FR-IX-023)  
**Status:** **as-built** for Call 1 project-spec summary (S1a–S1e).

### Requirement: Needs summary on ingest response (as-built S1c)
After successful index + mandatory KG, the live success body MUST include **`needs_summary`** (array), produced by the configured need decomposer (`NEED_DECOMPOSER=stub|llm`) on project text or extracted file content.  
Empty list + warning is allowed when no needs can be inferred; MUST NOT invent fleet inventory or rates.  
(Trace: partial FR-IX-023 / S1c)  
**Status:** **as-built (S1c)**.

#### Scenario: Needs summary present (S1c as-built)
- **GIVEN** successful ingest of a project-spec with non-empty content and stub decomposer
- **WHEN** `POST .../submitprojectspecification` succeeds
- **THEN** the body includes non-empty `needs_summary` with at least `description`
- **AND** does not include `recommendation_id` or `results_by_need`

#### Scenario: Needs summary empty with warning
- **GIVEN** decomposer returns no needs
- **WHEN** ingest succeeds
- **THEN** `needs_summary` is an empty array
- **AND** `warnings` MAY mention that needs_summary is empty

### Requirement: Expected budget on ingest response (as-built S1d)
After successful index + mandatory KG, the live success body MUST include **`expected_budget`** as either:
- an object with `amount`, optional `currency`, and `source` (e.g. `extracted`) when a confident pattern is found in project text / extracted file content; or  
- **`null`** when missing or uncertain, with a warning that budget was not found.  

MUST NOT invent a budget. MUST NOT treat `options.include_pricing` as a budget amount.  
(Trace: partial FR-IX-023 / S1d)  
**Status:** **as-built (S1d)**.

#### Scenario: Budget extracted or null (S1d as-built)
- **GIVEN** successful ingest
- **WHEN** the project-spec does not state a budget
- **THEN** `expected_budget` is null and a warning MAY state that budget was not found
- **WHEN** the project-spec states a budget confidently (e.g. `SGD 15000`)
- **THEN** `expected_budget` includes amount (and currency when known) with a source marker (e.g. extracted)

### Requirement: Free-text rental dates on ingest response (as-built S1e)
After successful index + mandatory KG, when request omits `start_date` and/or `end_date`, the service MUST attempt deterministic extract from project text / extracted file content.  
Request values MUST win over extract when present.  
When no confident dates exist, fields MUST be null (warning MAY state dates not found). MUST NOT invent dates.  
(Trace: partial FR-IX-023 / S1e)  
**Status:** **as-built (S1e)**.

#### Scenario: Dates from document when request omits (S1e as-built)
- **GIVEN** request omits dates but the project-spec states a rental window confidently (e.g. from 2026-09-01 to 2026-09-14)
- **WHEN** ingest succeeds
- **THEN** `tentative_start_date` / `tentative_end_date` are filled from the document when confident
- **AND** when request also supplies dates, request values win over extract
- **AND** when no confident dates exist, both remain null (optional warning); dates MUST NOT be invented

#### Scenario: Not recommend envelope
- **WHEN** FR-IX-023 summary fields are returned
- **THEN** body MUST NOT require ranked `item` / `pricing.daily_rate` from fleet+ML path
- **AND** Call 2 (`getassetrecommendations`) remains the path for recommended assets + predicted rent (not Call 1)

### Requirement: Idempotent ingest via Idempotency-Key (as-built S2a)
`POST /internal/v1/recommendations/submitprojectspecification` MUST accept optional header **`Idempotency-Key`**.

When the header is present (non-blank):

1. The server MUST scope the key with **`user_id`** (same key + different user → independent logical ingests).  
2. On first **successful** 200, the server MUST store the lean `IngestFromProjectSpecResponse` (process-local memory; optional TTL).  
3. On a later POST with the same scoped key, the server MUST return the **same** stored lean body (same `ingest_id`) **without** requiring a second full index + KG run.  
4. Failed **4xx/5xx** MUST NOT be cached as success; a later successful POST with the same key is new work that may then be stored.  
5. JSON and multipart MUST honour the same key.  
6. Concurrent POSTs with the same scoped key SHOULD use single-flight (wait) rather than double-indexing.

When the header is **missing** or blank, behaviour MUST remain “always new ingest” (distinct `ingest_id`s).  
Multi-replica shared store is **out of scope** for S2a; single-process limit MUST be documented.  
(Trace: FR-IX-024)  
**Status:** **as-built (S2a)**.

#### Scenario: Same key replays lean body
- **GIVEN** a successful Call 1 with `Idempotency-Key` "k1" for `user_id` U
- **WHEN** the same logical request is POSTed again with `Idempotency-Key` "k1" for U
- **THEN** the response `ingest_id` equals the first response
- **AND** a second full index+KG is not required

#### Scenario: Different keys or missing key
- **GIVEN** two successful POSTs with different `Idempotency-Key` values (or no key)
- **WHEN** both complete
- **THEN** two distinct `ingest_id`s are returned

#### Scenario: Failure not cached as success
- **GIVEN** a first POST with key "k" that returns 400
- **WHEN** a later POST with key "k" succeeds
- **THEN** the success body is returned and may be stored for subsequent replays

### Requirement: Correlation id on request path (as-built S2a)
The application MUST accept optional **`X-Correlation-Id`** and/or W3C **`traceparent`** on HTTP requests (ingest, project-knowledge Q&A, and health).

1. When `X-Correlation-Id` is present, the server MUST use it; otherwise it MUST mint a UUID.  
2. The correlation id MUST be bound into logging context for the request.  
3. The response MUST echo **`X-Correlation-Id`**.  
4. `traceparent`, when present, SHOULD be logged; C1 does not require full distributed-trace export.  
5. Correlation MUST NOT change business payload shapes (FR-IX-023 lean body unchanged).  

(Trace: FR-IX-025)  
**Status:** **as-built (S2a)**.

#### Scenario: Correlation header echoed and logged
- **GIVEN** a client sends `X-Correlation-Id: corr-1`
- **WHEN** any live route handles the request
- **THEN** the response includes `X-Correlation-Id: corr-1`
- **AND** request-path logs include the correlation id

#### Scenario: Server mints correlation when missing
- **GIVEN** no `X-Correlation-Id` header
- **WHEN** a request is handled
- **THEN** the response still includes a non-empty `X-Correlation-Id`

### Requirement: Idempotent ingest via Idempotency-Key (as-built S2a)
`POST /internal/v1/recommendations/submitprojectspecification` MUST accept optional header **`Idempotency-Key`**.

When the header is present (non-blank):

1. The server MUST scope the key with **`user_id`** (same key + different user → independent logical ingests).  
2. On first **successful** 200, the server MUST store the lean `IngestFromProjectSpecResponse` (process-local memory; optional TTL).  
3. On a later POST with the same scoped key, the server MUST return the **same** stored lean body (same `ingest_id`) **without** requiring a second full index + KG run.  
4. Failed **4xx/5xx** MUST NOT be cached as success; a later successful POST with the same key is new work that may then be stored.  
5. JSON and multipart MUST honour the same key.  
6. Concurrent POSTs with the same scoped key SHOULD use single-flight (wait) rather than double-indexing.

When the header is **missing** or blank, behaviour MUST remain “always new ingest” (distinct `ingest_id`s).  
Multi-replica shared store is **out of scope** for S2a; single-process limit MUST be documented.  
(Trace: FR-IX-024)  
**Status:** **as-built (S2a)**.

#### Scenario: Same key replays lean body
- **GIVEN** a successful Call 1 with `Idempotency-Key` "k1" for `user_id` U
- **WHEN** the same logical request is POSTed again with `Idempotency-Key` "k1" for U
- **THEN** the response `ingest_id` equals the first response
- **AND** a second full index+KG is not required

#### Scenario: Different keys or missing key
- **GIVEN** two successful POSTs with different `Idempotency-Key` values (or no key)
- **WHEN** both complete
- **THEN** two distinct `ingest_id`s are returned

#### Scenario: Failure not cached as success
- **GIVEN** a first POST with key "k" that returns 400
- **WHEN** a later POST with key "k" succeeds
- **THEN** the success body is returned and may be stored for subsequent replays

### Requirement: Correlation id on request path (as-built S2a)
The application MUST accept optional **`X-Correlation-Id`** and/or W3C **`traceparent`** on HTTP requests (ingest, project-knowledge Q&A, and health).

1. When `X-Correlation-Id` is present, the server MUST use it; otherwise it MUST mint a UUID.  
2. The correlation id MUST be bound into logging context for the request.  
3. The response MUST echo **`X-Correlation-Id`**.  
4. `traceparent`, when present, SHOULD be logged; C1 does not require full distributed-trace export.  
5. Correlation MUST NOT change business payload shapes (FR-IX-023 lean body unchanged).  

(Trace: FR-IX-025)  
**Status:** **as-built (S2a)**.

#### Scenario: Correlation header echoed and logged
- **GIVEN** a client sends `X-Correlation-Id: corr-1`
- **WHEN** any live route handles the request
- **THEN** the response includes `X-Correlation-Id: corr-1`
- **AND** request-path logs include the correlation id

#### Scenario: Server mints correlation when missing
- **GIVEN** no `X-Correlation-Id` header
- **WHEN** a request is handled
- **THEN** the response still includes a non-empty `X-Correlation-Id`

### Requirement: Optional Coordinator gate path for Call 1 (as-built S3)
`POST /internal/v1/recommendations/submitprojectspecification` MUST support an optional **Coordinator gate [4]** path for indexing:

1. Env flag **`INDEXING_VIA_AGENT_GATE`** (bool; default **`false`**).
2. When **false** (default): Call 1 MUST use direct `IndexingIngestService` (as-built baseline).
3. When **true**: Call 1 MUST run forced non-LLM LangGraph **`START → index_gate → END`**, which MUST invoke the in-process tool **`run_indexing_from_request`** wrapping the same `IndexingIngestService` (meta stamp, mandatory KG hard-fail, session registry).
4. The gate MUST NOT use LLM tool selection, free ReAct, or put raw file bytes into LLM context.
5. Lean public body (FR-IX-023) MUST be identical on both paths; Spring wire MUST NOT require flag-specific DTO fields.
6. MIME / KG / empty-source hard-fail MUST remain HTTP **400** / `BadRequestError` on both paths.
7. Gate state SHOULD expose **`indexing_ok`** (true on success; **false** on failure with no silent success `ingest_id`) for later multi-agent recommend (S7).
8. S2a `Idempotency-Key` and correlation MUST still wrap the producer (gate or direct) unchanged.

(Trace: FR-IX-026)  
**Status:** **as-built (S3)**.  
**Impl:** `app/agents/tools.py`, `app/agents/indexing_gate.py`, `app/api/recommendations.py`, `tests/test_indexing_tool.py`.  
**Note:** SuperComponent packaging (S3.3) remains optional/deferred — not required for FR-IX-026.

#### Scenario: Flag off keeps direct service path
- **GIVEN** `INDEXING_VIA_AGENT_GATE` is false or unset
- **WHEN** a client POSTs a valid project-spec
- **THEN** the lean FR-IX-023 body is returned
- **AND** the path does not require the gate graph

#### Scenario: Flag on uses forced non-LLM gate
- **GIVEN** `INDEXING_VIA_AGENT_GATE` is true
- **WHEN** a client POSTs a valid project-spec
- **THEN** `START → index_gate → END` runs without LLM tool selection
- **AND** the lean DTO matches the direct-service shape
- **AND** a project-knowledge session is registered for the returned `ingest_id`

#### Scenario: Tool parity with IndexingIngestService
- **GIVEN** the same `user_id` + `project_text` fixture
- **WHEN** `run_indexing_from_request` and `IndexingIngestService.ingest_from_project_spec` both run
- **THEN** both produce lean fields (`ingest_id`, `user_id`, non-empty summary)
- **AND** the tool path registers a `ProjectKnowledgeSession`

#### Scenario: Gate MIME hard-fail and indexing_ok false
- **GIVEN** an unsupported file type (e.g. `.bin` / `.exe`)
- **WHEN** the tool or gated graph path runs
- **THEN** the caller receives `BadRequestError` / HTTP 400
- **AND** gate state has `indexing_ok=false` with no silent success `ingest_id`

### How to test (FR-IX-026 / S3) — verification instructions

Canonical runbook (commands + Postman): [`design.md` — How to test this capability](./design.md#how-to-test-this-capability-runbook).  
Contract notes: [`contracts/ingest-from-project-spec.md` — Verification](./contracts/ingest-from-project-spec.md#verification-s3--fr-ix-026).  
Archive checklist: [`../../changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/tasks.md`](../../changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/tasks.md).

| Layer | Command / action | Pass |
|-------|------------------|------|
| **Unit / pack** | `uv run pytest tests/test_indexing_tool.py -q` | 9 passed (parity, flag on/off, MIME, `indexing_ok`) |
| **Regression** | `uv run pytest tests/ -q` | Full suite green; flag default stays off |
| **Manual flag off** | Start API without flag; POST Call 1 JSON | 200 lean FR-IX-023 body |
| **Manual flag on** | `INDEXING_VIA_AGENT_GATE=true` + same POST | Same lean DTO; session usable for Call 2/3 |
| **Manual negative** | Unsupported multipart (e.g. `.bin`) with/without flag | HTTP 400 `{"error","message"}` |
| **Postman** | Collection in `postman/`; restart API with flag for gate path | Call 1 happy + negatives; Call 2/3 after ingest |

**Independent Test (S3):** enable/disable `INDEXING_VIA_AGENT_GATE` only — no Pgvector, Neo4j, or live LLM required when `INDEXING_EMBEDDER=mock` and `KG_APPLY_TRANSFORMS=false`.

### Requirement: MIME classification map
Sources MUST be classified according to the following normative extension / MIME map. Unclassified / other / unknown → **400**.  
(Trace: MIME map §3; FR-IX-002, FR-IX-003)

| Kind | Extensions | MIME types |
|------|------------|------------|
| **Unstructured** | `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.html`, `.htm` | `text/plain`, `text/markdown`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/html` |
| **Structured** | `.csv`, `.json`, `.xlsx` | `text/csv`, `application/json`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| **Unclassified** | other / unknown | → **400** |

**Routing note:** Explicit `FileTypeRouter`. Unstructured: sanitizer → cleaner → word split. CSV: CSV cleaner → row-wise split. Meet at **`final_doc_joiner`** → embed → write. JSON/XLSX use unstructured clean/split path but count as **structured** for `data_kind`.

#### Scenario: Unstructured extension maps correctly
- **WHEN** a file has extension `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.html`, or `.htm` (or matching MIME)
- **THEN** it is classified as unstructured

#### Scenario: Structured extension maps correctly
- **WHEN** a file has extension `.csv`, `.json`, or `.xlsx` (or matching MIME)
- **THEN** it is classified as structured for `data_kind`

#### Scenario: JSON/XLSX clean path vs data_kind
- **WHEN** a JSON or XLSX source is processed
- **THEN** it uses the unstructured clean/split path
- **AND** still counts as **structured** for `data_kind`

#### Scenario: Unknown type rejected by map
- **WHEN** extension/MIME is outside the map
- **THEN** the source is unclassified and yields HTTP 400

---

## Norms (OpenSPDD)

- Live HTTP index graph and MIME policy live in this capability; KG hard-fail rules live in knowledge-graph.
- Packt Ch. 4 dual-branch pattern is normative for the graph shape (FileTypeRouter → dual preprocess → joiner → embed → write).
- CI-safe default embedder; optional modes via `INDEXING_*` settings.
- Thin routers; pipelines and services own branching.
- Portal project-spec submit hits **this Call 1 first**; Spring then **Call 2 recommend** (`getassetrecommendations` quote); optional **Call 3** chatbot Q&A (`project-knowledge/query`).

## Safeguards (OpenSPDD)

- Do not restore `results_by_need` / FR-010 as the default **Call 1** path without an explicit reattach SDD.
- Do not treat KG as optional on success path; missing `user_id`, zero chunks, or KG failure → 400.
- Do not invent a second public API style for ingest; field tables live in the contract file.
- Do not silently replace process-local `InMemoryDocumentStore` with multi-instance persistence without a dedicated change.
- Do not invent `expected_budget` or dates when not in request/document (FR-IX-023).
- Do not conflate **needs summary** with **fleet recommendation** or **predicted rent price** on Call 1.
- Do not cache failed ingest responses under `Idempotency-Key` (FR-IX-024).
- Do not claim multi-replica idempotency while the store is process-local memory only.
- Do not treat Call 2 or Call 3 as substitutes for Call 1 ingest.
- Do not make `INDEXING_VIA_AGENT_GATE` default-on without an explicit ops decision (FR-IX-026).
- Do not own the indexing gate as an LLM Worker / free ReAct tool-call (forced non-agent Coordinator edge only).
- Do not put raw file bytes into LLM context on the gate path.

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.8.0** | 2026-08-12 | **S3 as-built:** FR-IX-026 optional Coordinator gate [4] + `run_indexing_from_request` behind `INDEXING_VIA_AGENT_GATE` (default off); lean body parity; SuperComponent S3.3 deferred |
| **0.7.2** | 2026-08-12 | Call 2 recommend + Call 3 Q&A portal norms |
| **0.7.1** | 2026-08-12 | Portal dual-hop norms/safeguards (Call 1 first; Call 2 not ingest) |
| **0.7.0** | 2026-08-12 | **S2a as-built:** FR-IX-024 `Idempotency-Key` (process-local store); FR-IX-025 correlation headers; contract + design + tests |
| **0.5.0** | 2026-08-11 | **S1a lean as-built:** public body `ingest_id` + `user_id` + `user_requirement_summary` + `warnings`; internal paths `/internal/v1/recommendations/...`; full FR-IX-023 still TARGET |
| **0.5.1** | 2026-08-11 | **S1b as-built:** echo request dates as `tentative_start_date` / `tentative_end_date` (JSON + multipart); free-text date extract still TARGET |
| **0.5.2** | 2026-08-11 | FR-IX-023 delivery order: S1c needs → S1d budget → **S1e free-text dates** (after S1d) → 1.7 as-built; aligns with implementation-plan Phase 1 |
| **0.5.3** | 2026-08-11 | **S1c as-built:** `needs_summary[]` via need decomposer after index+KG; S1d/S1e still TARGET |
| **0.5.4** | 2026-08-11 | **S1d as-built:** `expected_budget` extract-only (never invent); S1e free-text dates still TARGET |
| **0.6.0** | 2026-08-11 | **S1e + 1.7:** free-text date extract as-built; **FR-IX-023 Call 1 summary fully as-built** (S1a–S1e) |


| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-07 | Part 1 FileTypeRouter + route reroute |
| **0.2.0** | 2026-08-07 | Part 2 converters |
| **0.3.0** | 2026-08-10 | OpenSpec migration / FR-IX-001…022 restatement |
| **0.4.0** | 2026-08-10 | **FR-IX-023 TARGET:** project-spec summary (needs, dates, budget) on Call 1 response |
| **0.3.0** | 2026-08-07 | Part 3 embed/write |
| **0.3.1** | 2026-08-07 | Spec reconcile vs recommend SPECs |
| **0.4.0** | 2026-08-07 | Packt dual-branch FR-IX-018–020 |
| **0.5.0** | 2026-08-07 | HR-76 user_id + KG hook FR-IX-021–022 |
| **0.6.0** | 2026-08-07 | Sequential reading map; full API tables; KG not “future-only” |
| **1.0.0** | 2026-08-10 | Migrated to OpenSpec Requirement/Scenario + OpenSPDD; contract + design split |

---

**Reading order:** [← Setup](../project-setup/spec.md) · [Agent map](../../AGENTS.md) · [Contract](./contracts/ingest-from-project-spec.md) · [Design](./design.md) · [Next: Knowledge graph →](../knowledge-graph/spec.md)

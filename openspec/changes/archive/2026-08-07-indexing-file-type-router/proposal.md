# Proposal: Indexing File Type Router (archived)

| Field | Value |
|-------|--------|
| **Change id** | `2026-08-07-indexing-file-type-router` |
| **Status** | archived / as-built |
| **Tracking** | HR-74 · HR-76 |
| **Capability** | [`../../../specs/indexing/spec.md`](../../../specs/indexing/spec.md) |
| **Contract** | [`../../../specs/indexing/contracts/ingest-from-project-spec.md`](../../../specs/indexing/contracts/ingest-from-project-spec.md) |
| **Design** | [`../../../specs/indexing/design.md`](../../../specs/indexing/design.md) |
| **Tasks** | [`./tasks.md`](./tasks.md) |

## Why

Project-spec HTTP needed a Packt-style **indexing** path (classify → convert → clean/split → embed → write) instead of treating `POST /api/v1/recommendations/from-project-spec` as the FR-010 recommend graph. Portal identity and a user-scoped knowledge graph (HR-76) had to attach after post-join chunks so ingest is tenant-aware and graph-backed without restoring `results_by_need` on the default route.

## What

### Part 1 — FileTypeRouter foundation + route reroute

- MIME map and `FileTypeRouter`-backed classification under `app/pipelines/indexing/`.
- Service + schemas; thin router offloads via `run_in_threadpool`.
- Live route runs indexing, not `intake_front` / FR-010 recommend.
- Multipart/JSON packaged as `ByteStream` with extension-derived `mime_type`.

### Part 2 — MIME-specific converters

- Structured and unstructured branches convert to Haystack `Document`s (plain/json, markdown, html, pdf, docx, csv, xlsx).
- Response gains `document_count` and truncated `documents[]` previews.
- Converter deps and tests.

### Part 3 — Vectorize + write

- Dual-branch clean/split (unstructured word path; CSV cleaner + row-wise split) → `final_doc_joiner` → embed → `DocumentWriter`.
- Default process-local `InMemoryDocumentStore`; CI-safe `MockDocumentEmbedder`; optional `openai` / later `sentence-transformers`.
- Response: `chunk_count`, `documents_written`, `has_embedding` on previews.
- Packt Ch. 4 dual-branch alignment (FR-IX-018–020).

### HR-76 — `user_id` + mandatory KG hook

- Request **requires** `user_id` (optional `user_name`); stamp on chunk meta; echo on response.
- After `final_doc_joiner` chunks and successful index write: **mandatory** user-scoped KG (hard-fail on failure).
- Success body includes `kg_*` fields (`kg_built=true` on 200). Full Ragas transforms gated by `KG_APPLY_TRANSFORMS` inside the generator (see [`../../../specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md)).

## Out of scope (deferred)

- Recommend reattach on this route (`results_by_need`) — T017
- Persistent multi-instance DocumentStore / hybrid retrieval query HTTP
- `LinkContentFetcher` branch — T030

## Normative outcome

As-built capability: [`../../../specs/indexing/`](../../../specs/indexing/). Conflict rule: live route wins in indexing; KG rules in knowledge-graph.

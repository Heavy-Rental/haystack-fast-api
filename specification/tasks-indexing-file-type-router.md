# Tasks: Indexing Pipeline (Parts 1–3 as-built + later)

**Input:** [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md)  
**Spec-kit phase:** Tasks → Implement / Converge  
**Live HTTP owner:** indexing SPEC (not FR-010 recommend on the public route)

## Phase 0 — Spec artifacts

- [x] T001 Write feature SPEC
- [x] T002 Write this tasks file

## Phase 1 — Pipeline foundation (Part 1)

- [x] T003 Create `app/pipelines/indexing/mime_map.py` (extensions, MIME sets, structured/unstructured sets)
- [x] T004 Create `app/pipelines/indexing/data_kind_classifier.py` (`@component` using `FileTypeRouter`)
- [x] T005 Create `app/pipelines/indexing/pipeline.py` (`build_indexing_pipeline`, `run_indexing_pipeline`)
- [x] T006 Export from `app/pipelines/indexing/__init__.py`

## Phase 2 — Service + schemas + endpoint (Part 1)

- [x] T007 Create `app/schemas/indexing.py` (`IngestFromProjectSpecResponse`)
- [x] T008 Create `app/services/indexing.py` (`IndexingIngestService`)
- [x] T009 Reroute `app/api/recommendations.py` to indexing service via `run_in_threadpool`
- [x] T010 Package multipart/JSON as `ByteStream` with `mime_type` (no `_decode_upload` allowlist)

## Phase 3 — Tests (Part 1)

- [x] T011 `tests/test_indexing_file_type_router.py` (component + pipeline)
- [x] T012 Rewrite `tests/test_recommendations_intake.py` for ingest response
- [x] T013 Keep recommend unit tests service-level only (not bound to this HTTP route)
- [x] T014 `pytest` green; light cross-links in parent/intake SPECs if needed

## Phase 4 — Part 2 converters

- [x] T015 Converters (structured / unstructured branches) via `SourceDocumentConverter`
- [x] T015a Wire `classify → convert` in indexing pipeline
- [x] T015b Extend response with document previews/counts
- [x] T015c Add converter deps (markdown-it-py, pypdf, python-docx, openpyxl, trafilatura, …)
- [x] T015d Tests for converters + HTTP document fields

## Phase 5 — Part 3 vectorize + write

- [x] T016 Splitter → embedder → DocumentWriter
- [x] T016a `InMemoryDocumentStore` singleton + reset for tests
- [x] T016b Embedder factory (`mock` default, optional `openai`)
- [x] T016c Config `INDEXING_*` settings
- [x] T016d Response `chunk_count` / `documents_written` / `has_embedding`
- [x] T016e Tests for write path + HTTP fields

## Phase 6 — Manual test artifacts

- [x] T019 Postman collection, environment, fixtures, and `postman/README.md`

## Phase 7 — Spec converge (non-contradiction)

- [x] T021 Reconcile specification set: indexing SPEC owns live route; mark recommend HTTP as deferred; align pipeline/testing/Postman guides

## Later (not as-built)

- [ ] T017 Optional reattach recommend after unstructured extract (restore `results_by_need` or separate route)
- [ ] T018 Persistent DocumentStore / hybrid retrieval query path
- [ ] T020 Knowledge graph after DocumentStore write (optional/offline; parent §11; `KG_ENABLED` / artifact dir)

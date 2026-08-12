# Indexing Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, Outcomes, and Requirements (FR-IX-001–026 + MIME classification map). Live HTTP owner for `POST /internal/v1/recommendations/submitprojectspecification`; conflict rule: live route wins here; KG rules in [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md).

**API field tables:** [`contracts/ingest-from-project-spec.md`](./contracts/ingest-from-project-spec.md).  
**Resilience (S2a):** FR-IX-024 idempotency + FR-IX-025 correlation — process-local only in C1.  
**Agent gate (S3):** FR-IX-026 optional Coordinator gate [4] behind `INDEXING_VIA_AGENT_GATE` (default off).

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
       │     else run producer below → store only on 200
       │
       ▼
  INDEXING_VIA_AGENT_GATE?  (S3 / FR-IX-026; default false)
       │
       ├─ false (default) ──► IndexingIngestService (direct)
       │
       └─ true ──► START → index_gate → END  (forced non-LLM Coordinator [4])
                      └─ tool run_indexing_from_request
                            └─ IndexingIngestService (same as direct)
       │
       ▼
  file_type_router → dual-branch convert/clean/split  (inside service)
       │
       ▼
  final_doc_joiner
       ├─► doc_embedder → writer → InMemoryDocumentStore
       └─► post-join chunks → KG (mandatory; see knowledge-graph SPEC)
       │
       ▼
  IngestFromProjectSpecResponse (lean public body — same on both paths)
       │  as-built S1a: ingest_id, user_id, user_requirement_summary, warnings
       │  as-built S1b: tentative_* echo request dates
       │  as-built S1c: needs_summary[] via need decomposer (stub/LLM)
       │  as-built S1d: expected_budget extract-only (never invent)
       │  as-built S1e: free-text/file dates if request omits (request preferred)
       │  FR-IX-023 Call 1 summary: as-built (Phase 1.7)
       │  as-built S2a: Idempotency-Key replay (FR-IX-024); correlation echo (FR-IX-025)
       │  as-built S3: optional gate path (FR-IX-026); lean body unchanged
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
| `app/agents/tools.py` | **as-built S3:** `run_indexing_from_request` (FR-IX-026) wraps service |
| `app/agents/indexing_gate.py` | **as-built S3:** forced `START → index_gate → END`; `indexing_ok` + traces |
| `app/services/ingest_idempotency.py` | **as-built S2a:** process-local `Idempotency-Key` store (FR-IX-024) |
| `app/middleware/correlation.py` | **as-built S2a:** `X-Correlation-Id` / `traceparent` (FR-IX-025) |
| `app/api/recommendations.py` | Thin HTTP; optional `Idempotency-Key`; flag → gate vs direct |
| `app/schemas/indexing.py` | Response DTO — FR-IX-023 as-built (S1a–S1e) |
| `app/services/need_decomposer.py` / LLM | **as-built S1c:** needs_summary from project text |
| `app/services/project_spec_budget.py` | **as-built S1d:** expected_budget extract |
| `app/services/project_spec_dates.py` | **as-built S1e:** resolve_rental_dates (request preferred) |
| `app/config.py` | `INDEXING_*` (incl. `INDEXING_DOCUMENT_STORE`), `KG_*`, `IDEMPOTENCY_TTL_SECONDS`, `INDEXING_VIA_AGENT_GATE` |
| `app/pipelines/indexing/document_store.py` | **as-built S5-I0:** `build_document_store()` + mode normalize (FR-IX-027); singleton still InMemory |
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
| `embedder_factory.py` | Mock default embedder; optional openai / sentence-transformers |
| `document_store.py` | **I0:** `build_document_store(mode=memory\|pgvector)`; `get_document_store` / `reset` stay process-local InMemory |

## O — Operations

### Config

- `INDEXING_*` — embedder mode, splitter/store-related settings (see [`.env.example`](../../../.env.example))
- `INDEXING_DOCUMENT_STORE` — **S5-I0 / FR-IX-027:** `memory` (default, CI) \| `pgvector` (factory-ready; pipeline wire is **I1**)
- `INDEXING_VIA_AGENT_GATE` — **S3 / FR-IX-026:** `false` (default) direct service; `true` forced Coordinator gate
- `KG_*` — artifact dir, transforms flag (owned by knowledge-graph capability; required for success path)
- `IDEMPOTENCY_TTL_SECONDS` — optional TTL for process-local successful ingest cache (default `86400`; ≤0 disables expiry)

### Tests (module map)

| Area | Modules / notes |
|------|-----------------|
| Component + pipeline | `tests/test_indexing_*.py` (router, converters, dual-branch, write path) |
| HTTP ingest fields | `tests/test_recommendations_intake.py` (FR-IX-023 lean body, not recommend envelope) |
| Agent gate (S3 / FR-IX-026) | `tests/test_indexing_tool.py` (tool parity, flag on/off, MIME fail, `indexing_ok`) |
| DocumentStore factory (S5-I0 / FR-IX-027) | `tests/test_document_store_factory.py` (memory default, invalid mode, mocked pgvector; no Postgres) |
| Idempotency (S2a) | `tests/test_ingest_idempotency.py` (same key, missing key, multipart, failure not cached, single-flight, blank key, TTL unit) |
| Correlation (S2a) | `tests/test_correlation_middleware.py` (echo, mint, log binds `correlation_id`, Q&A) |
| Date extract (S1e) | `tests/test_project_spec_dates.py` + intake free-text date cases |
| Budget extract (S1d) | `tests/test_project_spec_budget.py` + intake budget cases |
| Mandatory KG | `tests/test_knowledge_graph.py`; hard-fail and Stage-1 Q&A see knowledge-graph **Testing** |
| Recommend unit tests | Service-level only; not bound to this HTTP route |

### How to test this capability (runbook)

Working directory: `haystack-fast-api/` (uv project root).

**CI-safe defaults (runtime / manual):** `INDEXING_EMBEDDER=mock`, `INDEXING_EMBEDDING_DIM=384`, `PROJECT_AGENT_MODE=stub`, `KG_APPLY_TRANSFORMS=false`.

**Pytest isolation (as-built):** `tests/conftest.py` autouse forces `INDEXING_EMBEDDER=mock`, `INDEXING_EMBEDDING_DIM=384`, `PROJECT_AGENT_MODE=stub`, and a temp `KG_ARTIFACT_DIR` so a developer’s host `.env` (e.g. dim `768` for OpenAI) does not fail the suite. There are **no** optional pytest markers or external prereqs for the default suite — `uv run pytest` is the full CI path. Vector retrieval tests must embed documents with the same mode/dim the query path uses (settings or explicit kwargs).

#### Automated (default CI)

```bash
# S3 / FR-IX-026 pack only (flag on/off driven inside tests via monkeypatch)
uv run pytest tests/test_indexing_tool.py -q
# or: .venv/bin/pytest tests/test_indexing_tool.py -q

# S5-I0 / FR-IX-027 DocumentStore factory (no Postgres)
uv run pytest tests/test_document_store_factory.py -q

# Full indexing + Call 1 regression (includes S1/S2a)
uv run pytest tests/test_indexing_tool.py tests/test_recommendations_intake.py \
  tests/test_ingest_idempotency.py tests/test_correlation_middleware.py -q

# Full suite (no -m filter; no live LLM / Pgvector / Neo4j required)
uv run pytest tests/ -q
```

**S3 pack expectations** (`tests/test_indexing_tool.py`):

| Case | Pass criteria |
|------|----------------|
| Tool parity | `run_indexing_from_request` vs service → lean fields + session registered |
| Flag off HTTP | Default path → 200 lean FR-IX-023 body |
| Flag on HTTP | Same lean DTO + session; no LLM agent nodes on gate graph |
| Gate graph shape | Nodes include `index_gate`; no `research_agent` / `synthesis_agent` |
| Traces | `role=coordinator`, `node=index_gate`, `tool=run_indexing_from_request` |
| MIME fail | Tool/gate → `BadRequestError`; graph state `indexing_ok=false` |
| Flag default | `indexing_via_agent_gate is False` |

#### Manual HTTP — flag off (default / as-built)

```bash
# optional: leave INDEXING_VIA_AGENT_GATE unset or false
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
curl -s -X POST "http://localhost:8000/internal/v1/recommendations/submitprojectspecification" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_demo",
    "project_text": "Requires a 20-ton excavator on soft clay. Budget SGD 25000."
  }'
```

**Expect:** HTTP **200**; body has `ingest_id` (`ing_…`), `user_id`, non-empty `user_requirement_summary`, `warnings[]`; **no** `kg_built` / `documents` on public body.

#### Manual HTTP — flag on (Coordinator gate [4])

```bash
export INDEXING_VIA_AGENT_GATE=true
export INDEXING_EMBEDDER=mock
export PROJECT_AGENT_MODE=stub
export KG_APPLY_TRANSFORMS=false
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Re-run the same Call 1 `curl` as above.

**Expect:** Same lean DTO shape as flag-off path. Then Call 2 / Call 3 with returned `ingest_id` still work (session registered).

**Negative (MIME):** multipart unsupported file still **400** on both paths (e.g. `postman/fixtures/unsupported.bin`).

#### Postman

1. Follow [`../../../postman/README.md`](../../../postman/README.md) — import collection + local env.
2. **Flag off:** start API with defaults; run Call 1 happy paths.
3. **Flag on:** restart API with `INDEXING_VIA_AGENT_GATE=true`; re-run Call 1 requests (same collection — no separate folder).
4. Confirm Call 2 recommend / Call 3 Q&A after successful Call 1 still succeed.
5. Negative: upload `fixtures/unsupported.bin` → **400** with/without flag.

#### Health check

- [http://localhost:8000/health](http://localhost:8000/health)
- OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

### Manual (summary)

- Postman collection, environment, fixtures: [`../../../postman/README.md`](../../../postman/README.md)
- Live route verification sequence may include KG multi-agent (Postman 15→16) per knowledge-graph testing notes
- **S3 gate runbook:** section **How to test this capability** above · FR-IX-026 scenarios in [`spec.md`](./spec.md)

## N — Norms

- Packt Ch. 4 dual-branch flowchart is the design reference for graph topology.
- MIME map and FR-IX requirements in [`spec.md`](./spec.md) are normative; design must not invent alternate classification.
- Thin routers; orchestration in `IndexingIngestService`; Haystack graph under `app/pipelines/indexing/`.
- **S3 Coordinator gate [4] (optional):** when `INDEXING_VIA_AGENT_GATE=true`, Call 1 runs forced non-LLM LangGraph `START → index_gate → END` via in-process tool `run_indexing_from_request` (`app/agents/indexing_gate.py` / `app/agents/tools.py`). Default **false** keeps direct service path. Gate does **not** use LLM tool-calling; files never enter LLM context as raw bytes. Lean public body unchanged.
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
| I0 factory before I1 pipeline wire | `INDEXING_DOCUMENT_STORE` + `build_document_store()` ship first; ingest stays InMemory until I1 |
| MockDocumentEmbedder default | CI without external embedding APIs |
| Mandatory KG after joiner | HR-76 identity + graph; hard-fail |
| JSON/XLSX structured data_kind + unstructured clean path | Count kind vs preprocess topology |

## Change control

See [`spec.md`](./spec.md) change-control table (0.1.0–0.6.0 historical; 1.0.0 OpenSpec migration).

# Specification: Recommendation Intake & Pipeline Front (FR-010.1–3)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (stage slice) |
| **Status** | As-built MVP — full FR-010.1–8 path (seed fleet + experimental/fallback pricing + template rank); real Spring SQL models deferred |
| **Feature id** | `recommendation-intake-pipeline-front` |
| **Tracking** | HR-65 |
| **Branch** | `HR-65-implement-intake-stage-for-recommender-system` |
| **Intended merge base** | `develop` |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` |
| **Python package** | `app` |
| **Spec location** | `specification/SPEC-recommendation-intake-and-pipeline-front.md` |
| **As-built modules** | `app/api/recommendations.py`, `app/schemas/recommendations.py`, `app/services/recommendations.py`, `app/services/need_decomposer.py`, `app/services/pricing_client.py`, `app/pipelines/*` (intake front + asset/availability/price/rank components) |
| **Tests** | `tests/test_recommendations_intake.py`, `tests/test_pipeline_intake_front.py`, `tests/test_recommend_pipeline_mvp.py`, `tests/test_llm_need_decomposer.py` |
| **Parent feature** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) |
| **Companion intake API detail** | [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) |
| **Depends on** | [`SPEC-project.md`](./SPEC-project.md), [`SPEC-project-setup.md`](./SPEC-project-setup.md), [`01-domain.md`](./01-domain.md) |
| **Related** | [`00-overview.md`](./00-overview.md); [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) (full FR-010.1–8 as-built); [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) |
| **Audience** | Engineers and agents implementing or verifying this stage |

**Read [`SPEC-project.md`](./SPEC-project.md) and [`SPEC-project-setup.md`](./SPEC-project-setup.md) first.** Domain language: [`01-domain.md`](./01-domain.md).

This document is a **normative feature specification** under Specification Driven Development (SDD). When behaviour described here and the codebase diverge, update them in the **same change set**.

---

## Document roles

| Document | Owns |
|----------|------|
| **This SPEC** | HR-65 stage: public intake path + **FR-010 steps 1–3** (resolve text, decompose, expand quantity) as Haystack pipeline structure; stage acceptance criteria; as-built module map; verification (automated + manual) |
| [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) | Detailed public API field tables, error shape nuance, Postman/Swagger runbook (§8) |
| Parent agentic SPEC | End-to-end recommender, **FR-010.4–8**, catalog hard filter at rank time, pricing integration, KG, deployment, demo scenarios A/B/C |
| Dynamic pricing SPEC | Production `predict_price()` |
| Foundation `00` / `01` | Vision and ubiquitous language |

**Conflict rule:** For public intake HTTP contract details, prefer [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) if tables diverge; for **pipeline structure of steps 1–3** and stage boundaries vs 4–8, **this SPEC wins**. Align both in the same change set when either changes.

---

## As-built delivery (this branch)

This section is the **branch delivery map**: what HR-65 lands relative to `develop`. Behaviour requirements remain in §§1–9; this inventory must stay accurate when the branch ships.

### Delivery summary

| Deliverable | Status on branch |
|-------------|------------------|
| Free-text / file public intake API | **Shipped** |
| Haystack pipeline FR-010.1–3 (resolve → decompose → expand) | **Shipped** |
| Singular `item` response envelope | **Shipped** |
| Quantity expansion (FR-006) | **Shipped** |
| FR-010.4 Asset candidate filter | **Shipped** (seed fleet) |
| FR-010.5 Booking availability | **Shipped** (seed bookings) |
| FR-010.6 `predict_price()` | **Shipped** (ml-experiments or fallback) |
| FR-010.7–8 Rank + assemble | **Shipped** (template rationale) |
| Production LLM need decomposer | **Optional** (`NEED_DECOMPOSER=llm`) |
| Real Spring Asset/Booking ORM | **Not shipped** — seed until models land |
| PDF/DOCX ingest | **Not shipped** — text/markdown MVP |
| Foundation + feature SPECs for SDD | **Shipped** |

### Specifications added or updated on this branch

| Path | Change |
|------|--------|
| [`00-overview.md`](./00-overview.md) | Product focus: free-text/file recommender MVP |
| [`01-domain.md`](./01-domain.md) | Unit-needs, singular item, quantity expansion, intake language |
| [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) | Parent feature SDD; intake correction; FR-010 shape; child-stage links |
| [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) | Intake API contract + Postman/Swagger §8 |
| [`SPEC-recommendation-intake-and-pipeline-front.md`](./SPEC-recommendation-intake-and-pipeline-front.md) | **This SPEC** — stage SDD + branch delivery map |

### Application code added or updated

| Path | Change |
|------|--------|
| `app/api/recommendations.py` | **New** — thin `POST .../from-project-spec` (JSON + multipart) |
| `app/api/__init__.py` | Register recommendations router |
| `app/schemas/recommendations.py` | **New** — request/response + `DecomposedNeed` / `UnitNeed` |
| `app/services/need_decomposer.py` | **New** — protocol + `StubNeedDecomposer` |
| `app/services/recommendations.py` | **New** — run intake front pipeline; stub FR-010.4–8 |
| `app/pipelines/source_text_resolver.py` | **New** — FR-010.1 `@component` |
| `app/pipelines/need_decomposer_component.py` | **New** — FR-010.2 `@component` |
| `app/pipelines/expand_quantity.py` | **New** — FR-010.3 / FR-006 `@component` |
| `app/pipelines/intake_front.py` | **New** — Pipeline factory `resolve → decompose → expand` |
| `app/pipelines/__init__.py` | Export front pipeline helpers |
| `app/core/errors.py` | Request validation → HTTP **400** shared error shape |
| `pyproject.toml` / `uv.lock` | Add `python-multipart` |

### Tests added on this branch

| Path | Coverage |
|------|----------|
| `tests/test_recommendations_intake.py` | HTTP happy path, empty/missing body, bad dates, multipart file, singular `item`, quantity expansion & multi-need via injected decomposer, no quantity on item schema |
| `tests/test_pipeline_intake_front.py` | Standalone components + full intake-front graph (resolve order, expand ids, empty source) |

### Runtime behaviour snapshot (default live path)

| Behaviour | Default live | Notes |
|-----------|--------------|--------|
| `POST .../from-project-spec` JSON | Works | Stub decomposer → typically one unit-need |
| Multipart `.txt` / `.md` | Works | Requires `python-multipart` |
| `item` populated with equipment/price | **No** | FR-010.4–8 stub |
| Multi-need from natural language alone | **No** | Stub = whole text as one need; pytest injects multi-need |

---

## 1. Purpose

This specification defines the **HR-65 stage** of equipment recommendation in `haystack-fast-api`:

1. Accept **unstructured project input** — single free-text box (`project_text`) and/or uploaded **file** of unstructured text — plus optional rental **start/end dates**.
2. Implement **pipeline structure FR-010 steps 1–3** under `app/pipelines/` as Haystack 2.0 **components** composed with `Pipeline.add_component` / `.connect` / `.run`:
   1. **Resolve source text**
   2. **Decompose** unstructured text → internal needs (quantity allowed only on internal need)
   3. **Expand quantity** → unit-needs (**FR-006**)
3. Return **`results_by_need`** with **exactly one** singular **`item`** per unit-need (`RecommendationItem | null`).
4. Leave **FR-010 steps 4–8** (Asset SQL, availability, price, rank/rationale, assemble real item) **out of this stage**, with an honest stub until a later SDD/implementation phase.

**Product intent (locked):** MVP UI is **not** a repeatable structured “add another need” form. Structured needs exist only **after** decomposition (internal).

---

## 2. Outcomes

When this specification is implemented and the as-built code remains compliant:

- Clients can submit free-text and/or a text file (+ optional ISO dates) via a documented REST endpoint.
- Empty source text / empty decompose / empty unit-need list → HTTP **400** with shared `{"error","message"}`.
- Successful responses include `recommendation_id`, echoed dates, and `results_by_need`.
- Each `results_by_need` entry has singular **`item`** — never a multi-rank `items[]` alternative list.
- Quantity *N* from decomposition yields *N* unit-need rows with FR-006 id scheme; **`RecommendationItem` has no `quantity`**.
- Steps 1–3 run as a Haystack **pipeline-first** subgraph under `app/pipelines/`; routers stay thin (**FR-015**, **NFR-004**).
- Steps 4–8 do not block intake: each unit-need may return `item: null` with an explicit stub warning until those stages land.
- Automated tests cover HTTP intake and pipeline components; manual verification is documented (companion intake SPEC §8).

---

## 3. Scope

### 3.1 In scope (this stage)

| Area | Requirement |
|------|-------------|
| **HTTP** | `POST /api/v1/recommendations/from-project-spec` — JSON and/or multipart |
| **FR-010.1** | `SourceTextResolver` component — merge file then project text |
| **FR-010.2** | `NeedDecomposerComponent` — protocol + stub (LLM-ready inject) |
| **FR-010.3** | `ExpandQuantityComponent` — unit-need expansion (**FR-006**) |
| **Pipeline graph** | `build_intake_front_pipeline` / `run_intake_front` — resolve → decompose → expand |
| **Service** | `RecommendationService` runs front pipeline; maps unit-needs to response envelope |
| **Response envelope** | Singular `item` per unit-need; stub when 4–8 not wired |
| **Validation** | Dates, non-empty source, shared error JSON; validation → **400** |
| **Layering** | Routers thin; no SQL/Haystack graph construction in route handlers |
| **Tests** | `tests/test_recommendations_intake.py`, `tests/test_pipeline_intake_front.py` |
| **Deps** | `python-multipart` for multipart file upload |

### 3.2 Out of scope (this stage)

| Area | Owner / later stage |
|------|---------------------|
| **FR-010.4** SQL `Asset` candidate filter | Parent SPEC / future implementation |
| **FR-010.5** Booking / BookingItem availability | Parent SPEC |
| **FR-010.6** `predict_price()` | Parent + [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) |
| **FR-010.7** Rank / rationale (PromptBuilder + Generator) | Parent SPEC |
| **FR-010.8** Assemble production-quality ranked `item` | Parent SPEC (after 4–7) |
| PDF/DOCX converters | Target; MVP = `text/plain`, `text/markdown` |
| Auth, cart, payment, booking writes | Project / future SDDs |
| Knowledge graph, LangGraph agent loop | Parent target sections |

### 3.3 Stub behaviour (normative until 4–8 land)

Until FR-010.4–8 are implemented under a later change set:

- Default decomposer MAY be **stub** (entire source text → one need, `quantity = 1`) for CI without LLM credentials.
- Production SHOULD use an LLM decomposer when ranking goes live (parent FR-010.2 intent); interface MUST remain injectable.
- Per unit-need: **`item` MUST be `null`** and **`warnings` MUST** state that candidate selection, availability, pricing, and ranking are not wired (stub pipeline).
- Removing the warning without providing a real ranked `item` is non-compliant once those stages are claimed complete.

---

## 4. Actors & user stories

| Actor | Goal |
|-------|------|
| **Customer / portal** | Submit free-text or file (+ optional dates) → recommendation envelope |
| **Intake pipeline** | Resolve text → decompose → expand quantity |
| **Recommendation implementer** | Keep FR-010.1–3 testable as components without Asset/LLM credentials |
| **Downstream pipeline (future)** | Consume unit-needs for FR-010.4–8 |

### User stories

1. **As a customer**, I paste a project description into one free-text box so that I receive recommendations without a multi-row needs form.
2. **As a customer**, I upload a plain-text project file so that the same pipeline processes it.
3. **As the system**, when decomposition implies quantity 2, I emit **two** unit-need rows, each with at most one `item` and **no** quantity on the item.
4. **As an implementer**, I run FR-010.1–3 as a Haystack Pipeline under `app/pipelines/` so later SQL/rank stages plug in without rewriting intake.

---

## 5. Functional requirements

### 5.1 Intake & API (stage)

| ID | Requirement | Maps to |
|----|-------------|---------|
| **FR-PF-001** | The service MUST accept `POST /api/v1/recommendations/from-project-spec` as JSON (`project_text`) and/or multipart (`file` ± `project_text`) plus optional `start_date` / `end_date`. | Parent FR-001/002; intake SPEC |
| **FR-PF-002** | At least one non-empty source of text after resolve is required; otherwise **400**. Empty decompose / empty unit-needs after expand → **400**. | Parent FR-004 |
| **FR-PF-003** | MVP file types: `text/plain`, `text/markdown` (and plain UTF-8 by extension). Unsupported types → **400**. | Parent FR-002 |
| **FR-PF-004** | If both dates present, `end_date` ≥ `start_date`; else **400**. | Intake SPEC |
| **FR-PF-005** | Errors use `{"error","message"}`; validation failures → HTTP **400**. | Parent FR-042/043 |
| **FR-PF-006** | Response MUST use `results_by_need[]` with singular **`item`** (`RecommendationItem \| null`), not top-N `items[]`. | Parent FR-007 |
| **FR-PF-007** | **`RecommendationItem` MUST NOT include `quantity`.** | Parent FR-006/012 |
| **FR-PF-008** | Routers MUST stay thin; pipeline and orchestration live in services/pipelines. | Parent FR-015, NFR-004 |
| **FR-PF-009** | Snake_case JSON request/response. | Parent NFR-005 |

### 5.2 Pipeline structure (FR-010.1–3 only)

| ID | Requirement | Maps to |
|----|-------------|---------|
| **FR-PF-010** | Orchestration for this stage MUST implement FR-010 steps **1–3** under `app/pipelines/` / services. Steps **4–8** MUST NOT be required for this stage to ship. | Parent FR-010 (partial) |
| **FR-PF-011** | **Step 1 — Resolve source text:** merge `file_text` then `project_text` (separator `\n\n` when both non-empty). Empty → empty string for upstream 400 handling. | FR-010.1 |
| **FR-PF-012** | **Step 2 — Decompose:** map `source_text` → internal needs (`need_id`, `description`, optional `equipment_hints`, optional `quantity` ≥ 1). Empty text → empty needs list. | FR-010.2 |
| **FR-PF-013** | **Step 3 — Expand quantity:** for each need with quantity *N*, emit *N* unit-needs. *N* = 1 → `need_id = base_id`; *N* &gt; 1 → `need_id = {base_id}__u{i}` for *i* = 1..*N*. Immutable processing of inputs. | FR-010.3, FR-006 |
| **FR-PF-014** | Steps 1–3 MUST be Haystack **`@component`** classes with typed sockets, `run()` returning a **dict**, lightweight `__init__`. | Parent FR-016–017b |
| **FR-PF-015** | Components MUST be runnable **standalone** before pipeline connect. Empty needs/unit lists MUST not raise unhandled exceptions. | Parent FR-018a, FR-018b |
| **FR-PF-016** | Front subgraph MUST be assembled with explicit `.add_component` / `.connect` / `.run` (resolve → decompose → expand). | Parent FR-019c |
| **FR-PF-017** | Decomposer MUST be injectable via protocol so tests can supply multi-need / quantity &gt; 1 without a live LLM. | Testability / NFR-007 |
| **FR-PF-018** | After expansion, each unit-need MUST be represented independently in `results_by_need` (order preserved). | Parent FR-005 |

### 5.3 Explicit non-requirements of this stage

| ID | Statement |
|----|-----------|
| **FR-PF-N01** | This stage MUST NOT require real `Asset` SQL filtering to return 200 after valid intake. |
| **FR-PF-N02** | This stage MUST NOT require Bedrock/ranking to return 200 after valid intake. |
| **FR-PF-N03** | This stage MUST NOT expose public structured `needs[]` client form as the MVP intake contract. |

---

## 6. Design

### 6.1 Architecture

```text
  Client
      │
      ▼
  POST /api/v1/recommendations/from-project-spec
  app/api/recommendations.py          # thin: decode upload → file_text
      │
      ▼
  RecommendationService
      │
      ▼
  Haystack Pipeline (intake_front)     # FR-010.1–3 ONLY
      │
      ├─ resolve   SourceTextResolver
      ├─ decompose NeedDecomposerComponent  (+ NeedDecomposer protocol)
      └─ expand    ExpandQuantityComponent
      │
      ▼
  unit_needs[]
      │
      │  per unit-need (service loop)
      ▼
  FR-010.4–8 STUB → item=null + warnings
      │
      ▼
  RecommendFromProjectSpecResponse
```

### 6.2 Pipeline composition (normative)

```python
pipeline = Pipeline()
pipeline.add_component("resolve", SourceTextResolver(...))
pipeline.add_component("decompose", NeedDecomposerComponent(...))
pipeline.add_component("expand", ExpandQuantityComponent())
pipeline.connect("resolve.source_text", "decompose.source_text")
pipeline.connect("decompose.needs", "expand.needs")
# run: inputs keyed by "resolve" with project_text / file_text
```

Factory: `app/pipelines/intake_front.py` — `build_intake_front_pipeline`, `run_intake_front`.

### 6.3 Component sockets (as-built)

| Component | Inputs | Outputs |
|-----------|--------|---------|
| `SourceTextResolver` | `project_text`, `file_text` | `source_text: str` |
| `NeedDecomposerComponent` | `source_text` | `needs: list` (dicts with quantity) |
| `ExpandQuantityComponent` | `needs` | `unit_needs: list` (dicts, no quantity) |

### 6.4 As-built file map

See also **As-built delivery (this branch)** for the full branch inventory (specs + deps).

| Path | Role |
|------|------|
| `app/api/recommendations.py` | Thin HTTP adapter |
| `app/api/__init__.py` | Router registration |
| `app/schemas/recommendations.py` | Pydantic I/O + internal need types |
| `app/services/need_decomposer.py` | Protocol + `StubNeedDecomposer` |
| `app/services/recommendations.py` | Pipeline run + stub tail + envelope |
| `app/pipelines/source_text_resolver.py` | FR-010.1 |
| `app/pipelines/need_decomposer_component.py` | FR-010.2 |
| `app/pipelines/expand_quantity.py` | FR-010.3 / FR-006 |
| `app/pipelines/intake_front.py` | Graph assembly |
| `app/pipelines/__init__.py` | Package exports |
| `app/core/errors.py` | Shared error handlers (validation → 400) |
| `pyproject.toml` / `uv.lock` | `python-multipart` |
| `tests/test_recommendations_intake.py` | HTTP acceptance |
| `tests/test_pipeline_intake_front.py` | Component + graph acceptance |
| `specification/00-overview.md` | Foundation vision (updated) |
| `specification/01-domain.md` | Domain language (updated) |
| `specification/SPEC-agentic-equipment-recommendation-and-pricing.md` | Parent SDD |
| `specification/SPEC-recommendation-intake.md` | Intake API + Postman |
| `specification/SPEC-recommendation-intake-and-pipeline-front.md` | This stage SDD |

### 6.5 Layering (project constitution)

```text
routers → services → pipelines / repositories
```

No SQL, no pipeline graph construction, and no decomposer business rules in route handlers.

---

## 7. API contract (summary)

Normative field-level tables and Postman runbook: [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) §6–§8.

**Path:** `POST /api/v1/recommendations/from-project-spec`  
**Auth:** none (until shared auth SDD)

**JSON body (minimum):**

```json
{
  "project_text": "Indoor elevated work about 8m; need scissors lifts for fit-out.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "options": { "include_pricing": true }
}
```

**Success envelope (this stage, stub 4–8):**

```json
{
  "recommendation_id": "rec_...",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "results_by_need": [
    {
      "need_id": "need_1",
      "item": null,
      "warnings": [
        "Intake accepted; candidate selection, availability, pricing, and ranking are not wired yet (stub pipeline)."
      ]
    }
  ]
}
```

**Error:** HTTP **400** — `{"error":"bad_request","message":"..."}`.

---

## 8. Non-functional requirements (stage)

| ID | Requirement |
|----|-------------|
| **NFR-PF-001** | Default CI path MUST pass without Bedrock/LLM credentials (stub decomposer). |
| **NFR-PF-002** | Intake endpoint MUST remain import-safe without pricing or KG optional packages. |
| **NFR-PF-003** | Prefer pipeline-first unit tests for components without a full HTTP stack (**NFR-007**). |
| **NFR-PF-004** | No secrets in code; future LLM keys via environment only. |

---

## 9. Acceptance criteria

### 9.1 HTTP / intake

1. **Given** non-empty `project_text` and valid dates, **when** `POST .../from-project-spec`, **then** `200`, `recommendation_id` starts with `rec_`, dates echoed, each `results_by_need` entry has key **`item`** (not `items`).
2. **Given** empty/whitespace `project_text` and no file, **when** posted, **then** `400` shared error shape.
3. **Given** `end_date` before `start_date`, **when** posted, **then** `400`.
4. **Given** plain-text multipart file with content, **when** posted, **then** `200` and at least one unit-need result.
5. **Given** this stage’s stub, **when** recommend succeeds, **then** each `item` is `null` and `warnings` is non-empty.

### 9.2 Pipeline FR-010.1–3

6. **Given** only `project_text`, **when** `SourceTextResolver` runs, **then** `source_text` is the stripped text.
7. **Given** both file and project text, **when** resolver runs, **then** output is file text, separator, then project text.
8. **Given** a decomposer returning one need with `quantity = 2`, **when** expand runs (or full front pipeline runs), **then** unit-need ids are `need_*__u1` and `need_*__u2` and unit dicts have no `quantity` field.
9. **Given** a decomposer returning two needs with quantity 1, **when** front pipeline runs, **then** two independent `need_id`s appear in order.
10. **Given** empty source text, **when** front pipeline runs, **then** unit_needs is empty (service maps to 400 on the public path).
11. **Given** custom components for steps 1–3, **when** composed in a Pipeline, **then** connections use typed sockets via `.connect` and each `run()` returns a dict matching output types.

---

## 10. Verification & branch testing guide

This section is the **testing guide for the HR-65 branch** (intake + pipeline front). Detailed Postman screenshots-style steps also live in [`SPEC-recommendation-intake.md` §8](./SPEC-recommendation-intake.md#8-manual-testing-postman--swagger).

### 10.1 Prerequisites

```bash
cd haystack-fast-api   # application module (pyproject.toml, app/)
uv sync --all-groups
```

- No auth required on recommend routes.
- Postgres is **not** required for this stage’s happy path (stub after expand). Health may show `degraded` if DB is down.

### 10.2 Automated (pytest)

```bash
# Intake HTTP API (Postman-equivalent cases)
uv run pytest tests/test_recommendations_intake.py -v

# Pipeline FR-010.1–3 components + graph
uv run pytest tests/test_pipeline_intake_front.py -v

# Full suite
uv run pytest tests/ -v
```

| Test file | What it proves |
|-----------|----------------|
| `tests/test_recommendations_intake.py` | Free-text 200; empty/missing body 400; bad dates 400; multipart `.txt` 200; singular `item` (not `items`); quantity expansion & multi-need via **injected** decomposer; no `quantity` on `RecommendationItem` schema |
| `tests/test_pipeline_intake_front.py` | `SourceTextResolver` (project-only, file-then-project, empty); expand qty 1 / qty 2 → `__u1`/`__u2`; empty needs; stub decomposer; full `intake_front` pipeline run |

CI MUST stay green with default **stub** decomposer (no Bedrock credentials) — **NFR-PF-001**.

### 10.3 Start the server (manual)

```bash
cd haystack-fast-api
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| Resource | URL |
|----------|-----|
| Base | `http://localhost:8000` |
| Health | `GET http://localhost:8000/health` |
| OpenAPI / Swagger | `http://localhost:8000/docs` |
| Recommend | `POST http://localhost:8000/api/v1/recommendations/from-project-spec` |

### 10.4 Manual — free-text (JSON / Postman)

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `http://localhost:8000/api/v1/recommendations/from-project-spec` |
| Header | `Content-Type: application/json` |

**Body:**

```json
{
  "project_text": "Indoor elevated work about 8m; need scissors lifts for fit-out.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "options": { "include_pricing": true }
}
```

**curl:**

```bash
curl -s -X POST http://localhost:8000/api/v1/recommendations/from-project-spec \
  -H 'Content-Type: application/json' \
  -d '{
    "project_text": "Indoor elevated work about 8m; need scissors lifts for fit-out.",
    "start_date": "2026-09-01",
    "end_date": "2026-09-12",
    "options": { "include_pricing": true }
  }'
```

**Expect (this branch, stub 4–8):**

- Status **200**
- `recommendation_id` starts with `rec_`
- Dates echoed
- `results_by_need[]` with singular **`item`** (not `items`)
- Default stub: often **one** row (`need_1`), `item: null`, non-empty `warnings` about stub pipeline

### 10.5 Manual — file upload (multipart / Postman)

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | same as §10.4 |
| Body | **form-data** (do not force JSON Content-Type) |

| Key | Type | Value |
|-----|------|--------|
| `file` | File | `.txt` or `.md` (UTF-8) |
| `start_date` | Text | optional, e.g. `2026-09-01` |
| `end_date` | Text | optional |
| `project_text` | Text | optional supplement |
| `include_pricing` | Text | optional, default true |

**Expect:** **200**, same envelope shape. PDF/DOCX → **400** until converters land.

### 10.6 Manual — negative cases

| Case | Request | Expect |
|------|---------|--------|
| Empty text | `{"project_text": "   "}` | **400** `{"error":"bad_request","message":"..."}` |
| Missing body fields | `{}` | **400** |
| Bad dates | `start_date` after `end_date` + non-empty text | **400** |
| Empty multipart | no file, no project_text | **400** |

### 10.7 Suggested Postman collection

1. `GET Health`  
2. `POST From Project Spec (JSON)` — §10.4  
3. `POST From Project Spec (file)` — §10.5  
4. `POST Empty text (400)`  
5. `POST Bad dates (400)`  

Environment: `baseUrl` = `http://localhost:8000` → `{{baseUrl}}/api/v1/recommendations/from-project-spec`.

### 10.8 Swagger UI alternative

1. Open `http://localhost:8000/docs`  
2. **POST** `/api/v1/recommendations/from-project-spec`  
3. **Try it out** with the JSON body from §10.4  

### 10.9 Live vs automated expectations (this branch)

| Behaviour | Live default (stub) | Automated |
|-----------|---------------------|-----------|
| Free-text / `.txt` intake | Yes | Yes |
| Multipart markdown/text | Yes | Yes |
| Singular `item` with type/rank/rationale/pricing | Yes (when catalog matches) | Yes |
| No-match → `item: null` + warnings | Yes | Yes |
| Multi-need / qty expansion from English alone | Needs `NEED_DECOMPOSER=llm` | Yes via injected decomposer |
| Real Spring SQL fleet | No (seed) | Seed in tests |
| Experimental ML model.pkl | Optional | Fallback table if missing |

### 10.10 What testers should not expect yet

- Real Spring-owned fleet rows (seed fleet only)  
- Trained `model.pkl` unless present under `ml-experiments/artifacts/` (fallback pricing still works)  
- Automatic multi-need split from English without `NEED_DECOMPOSER=llm`  
- PDF/DOCX project files  

---

## 11. Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SDD pipeline MVP | Full FR-010.1–8 with seed fleet | Prototype without Spring schema; SQL swap later |
| Intake UX | Free-text/file, not multi-need form | Product correction |
| Response | Singular `item` | Exactly one ranked choice per unit-need |
| Quantity | Expand to unit-needs | No quantity on `RecommendationItem` |
| Decomposer default | Stub + injectable protocol | CI without LLM; tests control multi-need |
| Pipeline home | `app/pipelines/` | Parent FR-010 / FR-016–019c |
| Public path | `.../from-project-spec` | Unifies text and file |
| LLM placement | Protocol inject into FR-010.2; not in router | Layering; testability |

---

## 12. Open questions

| # | Question | Resolve by |
|---|----------|------------|
| 1 | Production LLM provider/model for need decompose | §13 implementation; parent Day 4 |
| 2 | When to remove stub warnings | When FR-010.4–8 produce real items |
| 3 | PDF/DOCX in first demo | SHOULD later; text/md MVP locked |
| 4 | LLM failure: fail-fast vs fall back to stub | Prefer fail-fast in prod when `NEED_DECOMPOSER=llm`; document choice when implementing |
| 5 | Share lifespan-warmed `LlmNeedDecomposer` with route/service (avoid per-request client leak) | Before sustained production LLM traffic; see §13.1 ASGI note |

---

## 13. LLM integration guidance

This section is **implementation guidance** for integrating an LLM with the **as-built extension points**. It does **not** claim the LLM is already shipped on this branch.

### 13.1 Two LLM slots in the parent recommender

| Slot | FR | Role | This branch |
|------|-----|------|-------------|
| **A. Need decomposer** | FR-010.**2** | Free-text/file → internal needs (+ quantity) | **Scaffolded** — `LlmNeedDecomposer` + factory; default still stub |
| **B. Rank / rationale** | FR-010.**7** | Candidates → one `item` + honest rationale | **Out of stage** — after FR-010.4–6 |

Do **not** call the LLM from FastAPI route handlers. Layering: **router → service → pipelines/components**.

**ASGI note (as-built):** the async recommend route still **awaits** `run_in_threadpool(service.recommend_from_project_spec, ...)` so sync pipeline work and sync LLM HTTP (`LlmNeedDecomposer` + `httpx.Client`) do not block the event loop. That is not the same as calling the LLM in the router—the decomposer stays behind the service/component boundary.

**Follow-up before production `NEED_DECOMPOSER=llm` traffic:** lifespan may warm an LLM client, but per-request `RecommendationService()` construction does not reuse it (dead warm-up + possible connection leak). Share the decomposer via `app.state` (or DI) and close on shutdown.

### 13.2 As-built extension point (slot A)

```text
source_text
    → NeedDecomposerComponent  (@component)
          → NeedDecomposer.decompose(source_text)   ← implement LLM here
    → needs[]  { need_id, description, equipment_hints, quantity }
    → ExpandQuantityComponent
    → unit_needs[]
```

Protocol (`app/services/need_decomposer.py`):

```python
class NeedDecomposer(Protocol):
    def decompose(self, source_text: str) -> list[DecomposedNeed]: ...
```

Default: `StubNeedDecomposer` (whole text → one need, `quantity = 1`).  
Haystack wrapper: `NeedDecomposerComponent` injects any `NeedDecomposer`.  
Factory: `build_intake_front_pipeline(decomposer=...)`.

### 13.3 Recommended integration steps (slot A)

**1. Configuration (env only — no secrets in code)**

Document in `.env.example` when implementing:

```text
NEED_DECOMPOSER=stub|llm          # default: stub (CI)
LLM_PROVIDER=bedrock|openai|...
NEED_DECOMPOSE_MODEL=...
# provider credentials via existing secrets pattern
```

**2. Implement `LlmNeedDecomposer`** (suggested path: `app/services/llm_need_decomposer.py`)

MUST:

1. Accept unstructured `source_text`.
2. Prompt the LLM to return a **JSON array** of needs.
3. Parse/validate into `list[DecomposedNeed]`.
4. On empty text, empty model output, or invalid JSON → return `[]` (service maps to **400** on the public path).

**Target JSON shape** (internal; not the public HTTP body):

```json
[
  {
    "need_id": "need_1",
    "description": "Indoor elevated work ~8m for multiple workers",
    "equipment_hints": ["scissors lift"],
    "quantity": 2
  },
  {
    "need_id": "need_2",
    "description": "Trench excavation near site",
    "equipment_hints": ["excavator"],
    "quantity": 1
  }
]
```

Prompt SHOULD:

- Bias toward approved types: Boom Lift, Scissors Lift, Fork Lift, Excavator  
- Treat `quantity` as number of **units** (expanded later; never on `RecommendationItem`)  
- Prefer raw JSON (strip markdown fences if the model adds them)  
- Assign stable `need_id` values (`need_1`, `need_2`, …) when missing  

Prefer Haystack **`PromptBuilder` + `Generator`** (e.g. Bedrock) for consistency with parent FR-019 ranking later.

**3. Life cycle (Haystack / FR-017)**

- `__init__`: config only (model id, thresholds)  
- `warm_up()`: create LLM client once (app lifespan preferred)  
- `decompose` / `run`: no client construction per request  

**4. Wire selection**

```text
if NEED_DECOMPOSER=llm → LlmNeedDecomposer (+ warm_up)
else                 → StubNeedDecomposer

build_intake_front_pipeline(decomposer=...)
RecommendationService(decomposer=...) or inject prebuilt Pipeline
```

Prefer process lifespan / DI so the pipeline is not rebuilt on every HTTP request.

**5. Tests when LLM is added**

| Case | Approach |
|------|----------|
| Default CI | `NEED_DECOMPOSER=stub` still green without credentials |
| LLM success | Mock generator → multi-need + quantity 2 → assert `__u1` / `__u2` rows |
| Bad JSON | Empty needs → API **400** |
| Empty text | **400** (unchanged) |

**6. Failure behaviour**

| Case | Expected |
|------|----------|
| Empty / unparseable LLM output | `[]` → public **400** |
| Provider down | Controlled error (document status code when implementing) |
| Missing credentials with `NEED_DECOMPOSER=llm` | Prefer fail-fast at startup in production; optional logged fallback only if product accepts it |

### 13.4 Rank / rationale LLM (slot B — later)

After FR-010.4–6 exist:

```text
unit-need → Asset SQL → availability → predict_price
         → PromptBuilder + Generator → exactly one item + rationale
```

That LLM MUST select **one** best match (singular `item`), emit honest rationale, and MUST NOT invent availability or prices. **Out of scope for this stage SPEC’s as-built delivery.**

### 13.5 Anti-patterns

| Avoid | Why |
|-------|-----|
| LLM calls in `app/api/recommendations.py` | Breaks thin routers (**FR-PF-008**) |
| LLM inventing fleet units without SQL | Violates later availability/catalog truth |
| `quantity` on `RecommendationItem` | **FR-PF-007** / FR-006 |
| Hardcoded API keys | **NFR-PF-004** |
| Requiring live LLM for all pytest | **NFR-PF-001** |

### 13.6 Mental model

```text
TODAY (stub)   text ──► StubNeedDecomposer ──► 1 need ──► expand ──► envelope (item=null)

WITH LLM       text ──► LlmNeedDecomposer ──► N needs (+qty) ──► expand ──► envelope

LATER          each unit-need ──► SQL ──► avail ──► price ──► LLM rank ──► item
```

### 13.7 Implementation checklist (future PR)

- [ ] `LlmNeedDecomposer` implements `NeedDecomposer`
- [ ] Prompt → JSON → validated `DecomposedNeed` list
- [ ] Settings + `.env.example` (`NEED_DECOMPOSER`, model, credentials)
- [ ] Factory/lifespan: stub vs LLM
- [ ] `warm_up()` for client/model
- [ ] Unit tests with mocked LLM
- [ ] Manual: Postman free-text implying two units → two `results_by_need` rows when LLM enabled
- [ ] Resolve open question §12 #1 (model id) in parent/this SPEC change control

---

## 14. Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-05 | Initial branch notes (non-normative) |
| **1.0.0** | 2026-08-05 | **SDD rewrite:** feature SDD for intake + pipeline front FR-010.1–3; purpose/outcomes/scope/FRs/design/AC/verification/change control; stub boundary for 4–8 |
| **1.1.0** | 2026-08-05 | **Branch delivery map:** document as-built inventory for HR-65 (specs, code, tests, deps, runtime snapshot); expand file map; branch/base metadata in header |
| **1.1.1** | 2026-08-05 | Renamed file to `SPEC-recommendation-intake-and-pipeline-front.md` (SDD naming); updated cross-links |
| **1.2.0** | 2026-08-05 | Expanded **§10 branch testing guide** (Postman/curl/negatives/collection); added **§13 LLM integration guidance** (slot A decomposer, slot B ranking later, checklist) |
| **1.3.0** | 2026-08-05 | Scaffolded `LlmNeedDecomposer` + factory (`NEED_DECOMPOSER=llm`); DigitalOcean OpenAI-compatible env in `.env.example`; mocked unit tests |
| **2.0.0** | 2026-08-05 | **Full FR-010.1–8 MVP:** seed `AssetCandidateFilter`, `BookingAvailabilityFilter`, `PredictPriceAdapter` (ml-experiments + fallback), `RankRationaleGenerator`, assemble non-null `item`; e2e tests |
| **2.1.0** | 2026-08-06 | **PR review docs:** threadpool offload for async recommend + LLM path; warm-up DI open Q #5; pricing field contract lives in pipeline/intake SPECs (`total_price`, no `weekly_rate`) |

When public intake behaviour or FR-010 pipeline contracts change, update **this SPEC**, the companion intake SPEC as needed, and as-built code/tests in the **same change set**. When the branch gains or drops deliverables, update **As-built delivery (this branch)** in the same change set.

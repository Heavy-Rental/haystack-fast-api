# Historical SPEC: Recommendation Intake & Pipeline Front (FR-010.1–3 → full FR-010)

> **Archived HR-65 stage document.** Preserved verbatim-in-spirit from `specification/SPEC-recommendation-intake-and-pipeline-front.md` so no detail is lost.  
> **Public route superseded (2026-08-07)** by indexing: [`../../../specs/indexing/spec.md`](../../../specs/indexing/spec.md).  
> See [`proposal.md`](./proposal.md) for supersession table.

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (stage slice) — **historical** |
| **Status** | **Historical HR-65 stage** — FR-010.1–8 service path shipped. **Public route superseded** by indexing. |
| **Feature id** | `recommendation-intake-pipeline-front` |
| **Tracking** | HR-65 |
| **Branch** | `HR-65-implement-intake-stage-for-recommender-system` |
| **Intended merge base** | `develop` |
| **As-built modules** | `app/api/recommendations.py`, `app/schemas/recommendations.py`, `app/services/recommendations.py`, `app/services/need_decomposer.py`, `app/services/pricing_client.py`, `app/pipelines/*` |
| **Tests** | `tests/test_recommendations_intake.py`, `tests/test_pipeline_intake_front.py`, `tests/test_recommend_pipeline_mvp.py`, `tests/test_llm_need_decomposer.py` |
| **Parent** | [`../../../specs/equipment-recommendation/spec.md`](../../../specs/equipment-recommendation/spec.md) |
| **Companion intake** | [`../../../specs/recommendation-intake/spec.md`](../../../specs/recommendation-intake/spec.md) |
| **Pipeline FR-010** | [`../../../specs/recommendation-pipeline/spec.md`](../../../specs/recommendation-pipeline/spec.md) |

---

## Supersession (2026-08-07)

| Topic | Current authority |
|-------|-------------------|
| Sequential reading map | [`../../../AGENTS.md`](../../../AGENTS.md) |
| Live `POST .../from-project-spec` | [`../../../specs/indexing/spec.md`](../../../specs/indexing/spec.md) (`user_id` required) |
| Mandatory KG after joiner + Stage-1 multi-agent | [`../../../specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md) |
| FR-010.1–8 service graph | [`../../../specs/recommendation-pipeline/spec.md`](../../../specs/recommendation-pipeline/spec.md) |
| Deferred recommend HTTP envelope | [`../../../specs/recommendation-intake/spec.md`](../../../specs/recommendation-intake/spec.md) |
| Live Postman | [`../../../../postman/README.md`](../../../../postman/README.md) |

---

## Document roles (historical)

| Document | Owns |
|----------|------|
| **This archive** | HR-65 stage narrative: original public intake + FR-010 steps 1–3 design; LLM integration notes; historical delivery map |
| Indexing capability | **Live** public route |
| Recommendation-intake | Request shapes + deferred recommend response |
| Parent equipment-recommendation | End-to-end recommender, FR-010.4–8 targets, KG, deployment |
| Dynamic pricing | Production `predict_price()` |

**Conflict rule:** Live HTTP → indexing. FR-010.1–3 component structure → pipeline capability + this archive. Deferred recommend API tables → intake capability.

---

## As-built delivery (this branch)

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
| PDF/DOCX ingest | **Not shipped** — text/markdown MVP (live indexing later broader) |
| Foundation + feature SPECs for SDD | **Shipped** |

### Application code added or updated

| Path | Change |
|------|--------|
| `app/api/recommendations.py` | **New** — thin `POST .../from-project-spec` (JSON + multipart) |
| `app/api/__init__.py` | Register recommendations router |
| `app/schemas/recommendations.py` | **New** — request/response + `DecomposedNeed` / `UnitNeed` |
| `app/services/need_decomposer.py` | **New** — protocol + `StubNeedDecomposer` |
| `app/services/recommendations.py` | **New** — run intake front pipeline; later FR-010.4–8 |
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
| `tests/test_pipeline_intake_front.py` | Standalone components + full intake-front graph |

### Runtime behaviour snapshot

> **Historical HR-65 snapshot** (recommend path). **Current live HTTP** is indexing ingest.

| Behaviour | HR-65 era | Current live (2026-08-07+) |
|-----------|-----------|----------------------------|
| `POST .../from-project-spec` | Recommend envelope (`results_by_need`) | **Ingest** (`ingest_id`, `data_kind`, `documents_written`) |
| Multipart files | `.txt` / `.md` MVP | Broader MIME map via indexing |
| Ranked `item` on HTTP | Stub / later seed fleet | **Not on default route** (service-level only) |
| Multi-need from NL alone | Stub = one need | N/A on HTTP until reattach |

---

## 1. Purpose

HR-65 stage of equipment recommendation in `haystack-fast-api`:

1. Accept **unstructured project input** — single free-text box (`project_text`) and/or uploaded **file** — plus optional rental **start/end dates**.
2. Implement **pipeline structure FR-010 steps 1–3** under `app/pipelines/` as Haystack 2.0 **components**:
   1. **Resolve source text**
   2. **Decompose** unstructured text → internal needs
   3. **Expand quantity** → unit-needs (**FR-006**)
3. Return **`results_by_need`** with **exactly one** singular **`item`** per unit-need.
4. Leave **FR-010 steps 4–8** out of the *initial* stage, with an honest stub until later (later shipped as full FR-010.1–8 MVP on same branch family).

**Product intent (locked):** MVP UI is **not** a repeatable structured “add another need” form. Structured needs exist only **after** decomposition (internal).

---

## 2. Outcomes

- Clients can submit free-text and/or a text file (+ optional ISO dates) via a documented REST endpoint.
- Empty source text / empty decompose / empty unit-need list → HTTP **400** with shared `{"error","message"}`.
- Successful responses include `recommendation_id`, echoed dates, and `results_by_need`.
- Each `results_by_need` entry has singular **`item`** — never multi-rank `items[]`.
- Quantity *N* yields *N* unit-need rows; **`RecommendationItem` has no `quantity`**.
- Steps 1–3 run as Haystack pipeline-first subgraph; routers stay thin.
- Steps 4–8 do not block intake in early stage: each unit-need may return `item: null` with stub warning until those stages land (later: real seed-based items).

---

## 3. Scope

### 3.1 In scope (this stage)

| Area | Requirement |
|------|-------------|
| **HTTP** | `POST /api/v1/recommendations/from-project-spec` — JSON and/or multipart |
| **FR-010.1** | `SourceTextResolver` — merge file then project text |
| **FR-010.2** | `NeedDecomposerComponent` — protocol + stub (LLM-ready inject) |
| **FR-010.3** | `ExpandQuantityComponent` — unit-need expansion (**FR-006**) |
| **Pipeline graph** | `build_intake_front_pipeline` / `run_intake_front` |
| **Service** | `RecommendationService` runs front pipeline; maps unit-needs to response envelope |
| **Response envelope** | Singular `item` per unit-need; stub when 4–8 not wired |
| **Validation** | Dates, non-empty source, shared error JSON; validation → **400** |
| **Layering** | Routers thin; no SQL/Haystack graph construction in route handlers |
| **Tests** | `tests/test_recommendations_intake.py`, `tests/test_pipeline_intake_front.py` |
| **Deps** | `python-multipart` |

### 3.2 Out of scope (initial stage)

| Area | Owner / later stage |
|------|---------------------|
| **FR-010.4** SQL `Asset` candidate filter | Parent / later (seed later shipped) |
| **FR-010.5** Booking availability | Parent |
| **FR-010.6** `predict_price()` | Parent + dynamic-pricing |
| **FR-010.7** Rank / rationale | Parent |
| **FR-010.8** Assemble production ranked `item` | Parent |
| PDF/DOCX converters | Target; MVP = text/plain, text/markdown |
| Auth, cart, payment, booking writes | Project / future SDDs |
| Knowledge graph, LangGraph agent loop | Parent target sections |

### 3.3 Stub behaviour (normative until 4–8 land)

- Default decomposer MAY be **stub** (entire source text → one need, `quantity = 1`) for CI without LLM credentials.
- Production SHOULD use an LLM decomposer when ranking goes live; interface MUST remain injectable.
- Per unit-need early stage: **`item` MUST be `null`** and **`warnings` MUST** state that candidate selection, availability, pricing, and ranking are not wired.
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
| **FR-PF-001** | MUST accept `POST .../from-project-spec` as JSON and/or multipart plus optional dates. | Parent FR-001/002 |
| **FR-PF-002** | At least one non-empty source after resolve; empty decompose / empty unit-needs → **400**. | Parent FR-004 |
| **FR-PF-003** | MVP file types: `text/plain`, `text/markdown`. Unsupported → **400**. | Parent FR-002 |
| **FR-PF-004** | If both dates present, `end_date` ≥ `start_date`; else **400**. | Intake |
| **FR-PF-005** | Errors use `{"error","message"}`; validation → **400**. | Parent FR-042/043 |
| **FR-PF-006** | Response MUST use `results_by_need[]` with singular **`item`**. | Parent FR-007 |
| **FR-PF-007** | **`RecommendationItem` MUST NOT include `quantity`.** | Parent FR-006/012 |
| **FR-PF-008** | Routers MUST stay thin. | Parent FR-015, NFR-004 |
| **FR-PF-009** | Snake_case JSON request/response. | Parent NFR-005 |

### 5.2 Pipeline structure (FR-010.1–3 only)

| ID | Requirement | Maps to |
|----|-------------|---------|
| **FR-PF-010** | Implement FR-010 steps **1–3**. Steps **4–8** not required for initial stage ship. | Parent FR-010 partial |
| **FR-PF-011** | **Step 1 — Resolve:** merge `file_text` then `project_text` (separator `\n\n` when both non-empty). | FR-010.1 |
| **FR-PF-012** | **Step 2 — Decompose:** `source_text` → needs (`need_id`, `description`, optional hints, optional `quantity` ≥ 1). | FR-010.2 |
| **FR-PF-013** | **Step 3 — Expand:** quantity *N* → *N* unit-needs. *N* = 1 → `base_id`; *N* > 1 → `{base_id}__u{i}`. Immutable. | FR-010.3, FR-006 |
| **FR-PF-014** | Steps 1–3 MUST be `@component` with typed sockets, `run()` → dict, lightweight `__init__`. | Parent FR-016–017b |
| **FR-PF-015** | Components runnable standalone; empty lists MUST not raise. | Parent FR-018a/b |
| **FR-PF-016** | Front subgraph: explicit `.add_component` / `.connect` / `.run`. | Parent FR-019c |
| **FR-PF-017** | Decomposer injectable via protocol for tests. | NFR-007 |
| **FR-PF-018** | Each unit-need independent in `results_by_need` (order preserved). | Parent FR-005 |

### 5.3 Explicit non-requirements of this stage

| ID | Statement |
|----|-----------|
| **FR-PF-N01** | MUST NOT require real Asset SQL to return 200 after valid intake. |
| **FR-PF-N02** | MUST NOT require Bedrock/ranking to return 200 after valid intake. |
| **FR-PF-N03** | MUST NOT expose public structured `needs[]` client form as MVP intake. |

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
  (later: real seed filter/avail/price/rank)
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

| Path | Role |
|------|------|
| `app/api/recommendations.py` | Thin HTTP adapter |
| `app/schemas/recommendations.py` | Pydantic I/O + internal need types |
| `app/services/need_decomposer.py` | Protocol + `StubNeedDecomposer` |
| `app/services/recommendations.py` | Pipeline run + envelope |
| `app/pipelines/source_text_resolver.py` | FR-010.1 |
| `app/pipelines/need_decomposer_component.py` | FR-010.2 |
| `app/pipelines/expand_quantity.py` | FR-010.3 / FR-006 |
| `app/pipelines/intake_front.py` | Graph assembly |
| `tests/test_recommendations_intake.py` | HTTP acceptance |
| `tests/test_pipeline_intake_front.py` | Component + graph acceptance |

### 6.5 Layering

```text
routers → services → pipelines / repositories
```

No SQL, no pipeline graph construction, and no decomposer business rules in route handlers.

---

## 7. API contract (summary)

Normative field-level tables: [`../../../specs/recommendation-intake/spec.md`](../../../specs/recommendation-intake/spec.md).

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

**Success envelope (historical stage, stub 4–8):**

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
| **NFR-PF-003** | Prefer pipeline-first unit tests without full HTTP stack. |
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
8. **Given** a decomposer returning one need with `quantity = 2`, **when** expand runs, **then** unit-need ids are `need_*__u1` and `need_*__u2` and unit dicts have no `quantity`.
9. **Given** a decomposer returning two needs with quantity 1, **when** front pipeline runs, **then** two independent `need_id`s appear in order.
10. **Given** empty source text, **when** front pipeline runs, **then** unit_needs is empty (service maps to 400 on public path).
11. **Given** custom components for steps 1–3, **when** composed in a Pipeline, **then** connections use typed sockets and each `run()` returns a dict matching output types.

---

## 10. Verification & branch testing guide

### 10.1 Prerequisites

```bash
cd haystack-fast-api
uv sync --all-groups
```

- No auth required on recommend routes (historical).
- Postgres not required for stub happy path.

### 10.2 Automated (pytest)

```bash
uv run pytest tests/test_recommendations_intake.py -v
uv run pytest tests/test_pipeline_intake_front.py -v
uv run pytest tests/ -v
```

| Test file | What it proves |
|-----------|----------------|
| `tests/test_recommendations_intake.py` | Free-text 200; empty/missing 400; bad dates 400; multipart; singular `item`; quantity expansion via injected decomposer |
| `tests/test_pipeline_intake_front.py` | Resolver, expand, stub decomposer, full intake_front graph |

CI MUST stay green with default **stub** decomposer — **NFR-PF-001**.

### 10.3 Start the server (manual)

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| Resource | URL |
|----------|-----|
| Health | `GET http://localhost:8000/health` |
| OpenAPI | `http://localhost:8000/docs` |
| Recommend | `POST http://localhost:8000/api/v1/recommendations/from-project-spec` |

> **Note:** Live route now expects `user_id` and returns **ingest**, not recommend envelope. Historical curl below is for reattach / service-era behaviour.

### 10.4 Manual — free-text (historical)

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

**Expect (historical HR-65, stub 4–8):** 200, `recommendation_id` starts with `rec_`, singular `item` (often null with stub warnings).

### 10.5 Manual — file upload (multipart)

form-data: `file` (.txt/.md), optional dates, optional `project_text`, optional `include_pricing`.

### 10.6 Negative cases

| Case | Expect |
|------|--------|
| Empty text | **400** |
| Missing body | **400** |
| Bad dates | **400** |
| Empty multipart | **400** |

### 10.7 Suggested Postman collection (historical)

1. GET Health  
2. POST From Project Spec (JSON)  
3. POST From Project Spec (file)  
4. POST Empty text (400)  
5. POST Bad dates (400)  

### 10.8 Live vs automated expectations (historical branch)

| Behaviour | Live default (stub) | Automated |
|-----------|---------------------|-----------|
| Free-text / `.txt` intake | Yes | Yes |
| Singular `item` | Yes | Yes |
| Multi-need / qty from English alone | Needs `NEED_DECOMPOSER=llm` | Yes via injected decomposer |
| Real Spring SQL fleet | No (seed) | Seed in tests |

### 10.9 What testers should not expect yet (historical)

- Real Spring-owned fleet rows (seed only)  
- Trained `model.pkl` unless present (fallback works)  
- Automatic multi-need without `NEED_DECOMPOSER=llm`  
- PDF/DOCX project files  

---

## 11. Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SDD pipeline MVP | Full FR-010.1–8 with seed fleet (later on branch) | Prototype without Spring schema |
| Intake UX | Free-text/file, not multi-need form | Product correction |
| Response | Singular `item` | One ranked choice per unit-need |
| Quantity | Expand to unit-needs | No quantity on RecommendationItem |
| Decomposer default | Stub + injectable protocol | CI without LLM |
| Pipeline home | `app/pipelines/` | Parent FR-010 / FR-016–019c |
| Public path | `.../from-project-spec` | Unifies text and file |
| LLM placement | Protocol inject into FR-010.2; not in router | Layering; testability |

---

## 12. Open questions

| # | Question | Resolve by |
|---|----------|------------|
| 1 | Production LLM provider/model for need decompose | Parent Day 4 |
| 2 | When to remove stub warnings | When FR-010.4–8 produce real items |
| 3 | PDF/DOCX in first demo | SHOULD later; text/md MVP locked |
| 4 | LLM failure: fail-fast vs fall back to stub | Prefer fail-fast when `NEED_DECOMPOSER=llm` |
| 5 | Share lifespan-warmed `LlmNeedDecomposer` with route/service | Before sustained production LLM traffic |

---

## 13. LLM integration guidance

Implementation guidance for as-built extension points. Does **not** claim LLM shipped by default.

### 13.1 Two LLM slots

| Slot | FR | Role | HR-65 branch |
|------|-----|------|--------------|
| **A. Need decomposer** | FR-010.**2** | Free-text/file → internal needs (+ quantity) | Scaffolded — `LlmNeedDecomposer` + factory; default stub |
| **B. Rank / rationale** | FR-010.**7** | Candidates → one `item` + rationale | Out of early stage; template rank later shipped |

Do **not** call the LLM from FastAPI route handlers. Layering: **router → service → pipelines/components**.

**ASGI note:** async recommend route **awaits** `run_in_threadpool(service.recommend_from_project_spec, ...)` so sync pipeline/LLM HTTP do not block the event loop.

**Follow-up:** share lifespan-warmed decomposer via `app.state` and close on shutdown (open Q #5).

### 13.2 As-built extension point (slot A)

```text
source_text
    → NeedDecomposerComponent  (@component)
          → NeedDecomposer.decompose(source_text)
    → needs[]  { need_id, description, equipment_hints, quantity }
    → ExpandQuantityComponent
    → unit_needs[]
```

Protocol:

```python
class NeedDecomposer(Protocol):
    def decompose(self, source_text: str) -> list[DecomposedNeed]: ...
```

Default: `StubNeedDecomposer` (whole text → one need, `quantity = 1`).  
Factory: `build_intake_front_pipeline(decomposer=...)`.

### 13.3 Recommended integration steps (slot A)

**1. Configuration (env only)**

```text
NEED_DECOMPOSER=stub|llm          # default: stub (CI)
LLM_PROVIDER=bedrock|openai|...
NEED_DECOMPOSE_MODEL=...
```

**2. Implement `LlmNeedDecomposer`**

MUST:

1. Accept unstructured `source_text`.
2. Prompt LLM for **JSON array** of needs.
3. Parse/validate into `list[DecomposedNeed]`.
4. On empty text, empty model output, or invalid JSON → return `[]` (service → **400**).

**Target JSON shape** (internal):

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

Prompt SHOULD bias to approved types; treat `quantity` as units; prefer raw JSON; assign stable `need_id`s.

Prefer Haystack **PromptBuilder + Generator** for consistency with ranking later.

**3. Life cycle**

- `__init__`: config only  
- `warm_up()`: create LLM client once  
- `decompose` / `run`: no per-request client construction  

**4. Wire selection**

```text
if NEED_DECOMPOSER=llm → LlmNeedDecomposer (+ warm_up)
else                 → StubNeedDecomposer
```

**5. Tests when LLM is added**

| Case | Approach |
|------|----------|
| Default CI | stub green without credentials |
| LLM success | Mock → multi-need + qty 2 → `__u1`/`__u2` |
| Bad JSON | Empty needs → API **400** |
| Empty text | **400** |

**6. Failure behaviour**

| Case | Expected |
|------|----------|
| Empty / unparseable LLM output | `[]` → public **400** |
| Provider down | Controlled error (document status when implementing) |
| Missing credentials with llm mode | Prefer fail-fast at startup in production |

### 13.4 Rank / rationale LLM (slot B — later)

```text
unit-need → Asset SQL → availability → predict_price
         → PromptBuilder + Generator → exactly one item + rationale
```

MUST select **one** best match; MUST NOT invent availability or prices.

### 13.5 Anti-patterns

| Avoid | Why |
|-------|-----|
| LLM calls in router | Breaks thin routers (**FR-PF-008**) |
| LLM inventing fleet without SQL | Violates catalog/availability truth |
| `quantity` on `RecommendationItem` | **FR-PF-007** / FR-006 |
| Hardcoded API keys | **NFR-PF-004** |
| Requiring live LLM for all pytest | **NFR-PF-001** |

### 13.6 Mental model

```text
TODAY (stub)   text ──► StubNeedDecomposer ──► 1 need ──► expand ──► envelope

WITH LLM       text ──► LlmNeedDecomposer ──► N needs (+qty) ──► expand ──► envelope

LATER          each unit-need ──► SQL ──► avail ──► price ──► LLM rank ──► item
```

### 13.7 Implementation checklist (future PR)

- [ ] `LlmNeedDecomposer` implements `NeedDecomposer`
- [ ] Prompt → JSON → validated `DecomposedNeed` list
- [ ] Settings + `.env.example`
- [ ] Factory/lifespan: stub vs LLM
- [ ] `warm_up()` for client/model
- [ ] Unit tests with mocked LLM
- [ ] Manual: free-text implying two units → two rows when LLM enabled
- [ ] Resolve open question §12 #1 (model id)

---

## 14. Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-05 | Initial branch notes |
| **1.0.0** | 2026-08-05 | SDD rewrite: intake + pipeline front FR-010.1–3 |
| **1.1.0** | 2026-08-05 | Branch delivery map |
| **1.1.1** | 2026-08-05 | Renamed SPEC file |
| **1.2.0** | 2026-08-05 | Branch testing guide; LLM integration guidance |
| **1.3.0** | 2026-08-05 | Scaffolded `LlmNeedDecomposer` + factory |
| **2.0.0** | 2026-08-05 | Full FR-010.1–8 MVP with seed fleet |
| **2.1.0** | 2026-08-06 | Threadpool offload; warm-up DI open Q; pricing field contract |
| **archive** | 2026-08-07 | Public route superseded by indexing; content preserved in OpenSpec archive |
| **openspec** | 2026-08-10 | Migrated into `openspec/changes/archive/2026-08-07-hr-65-intake-front/` |

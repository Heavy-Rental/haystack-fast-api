# Specification: Recommendation Pipeline (FR-010 MVP Structure)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (pipeline stage) |
| **Status** | As-built MVP — full FR-010.1–8 **service-level** orchestration; seed fleet/bookings; experimental or fallback pricing; template rank/rationale. **Not** the default HTTP path for `/from-project-spec` (see indexing SPEC). |
| **Feature id** | `recommendation-pipeline-mvp` |
| **Tracking** | HR-65 (pipeline structure completion) |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` |
| **Python package** | `app` |
| **Spec location** | `specification/SPEC-recommendation-pipeline.md` |
| **Parent feature** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) |
| **Related stage SPECs** | [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) (**live HTTP**); [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md); [`SPEC-recommendation-intake-and-pipeline-front.md`](./SPEC-recommendation-intake-and-pipeline-front.md) |
| **Depends on** | [`SPEC-project.md`](./SPEC-project.md), [`SPEC-project-setup.md`](./SPEC-project-setup.md), [`01-domain.md`](./01-domain.md) |
| **Pricing** | [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) (production service later); prototype `ml-experiments/predict_price.py` |
| **As-built modules** | See [§6 File map](#6-as-built-file-map) |
| **Tests** | `tests/test_pipeline_intake_front.py`, `tests/test_recommend_pipeline_mvp.py` (service e2e), `tests/test_llm_need_decomposer.py`; HTTP ingest: `tests/test_recommendations_intake.py` (indexing, not this graph) |
| **Testing guide** | [`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md) · Live Postman: [`../postman/README.md`](../postman/README.md) · Deferred recommend Postman: [`SPEC-recommendation-postman-testing-guide.md`](./SPEC-recommendation-postman-testing-guide.md) |
| **Audience** | Engineers and agents implementing or verifying the recommendation pipeline |

**Read project + setup SPECs first.** Domain language: [`01-domain.md`](./01-domain.md). Parent SPEC owns end-to-end product vision, demo scenarios A/B/C, KG/agent targets, and deployment.

This document is a **normative feature specification** under Specification Driven Development (SDD). When behaviour here and the codebase diverge, update them in the **same change set**.

---

## Document roles

| Document | Owns |
|----------|------|
| **This SPEC** | As-built **FR-010.1–8** pipeline structure: components, seed data rules, pricing adapter, rank/assemble, stage acceptance & verification (**service-level**) |
| [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) | **Live** public route (indexing ingest) |
| Parent agentic SPEC | Full product SDD, FRs FR-001+, target SuperComponents/Tools/KG, Day 1–6 schedule |
| Intake SPEC | Request shapes; **deferred** recommend response for reattach |
| Intake + pipeline front SPEC | Historical HR-65 stage notes, LLM integration guide |
| Dynamic pricing SPEC | Production `app/services/pricing/` (not yet required for this MVP) |

**Conflict rule:** Pipeline step behaviour and component contracts for FR-010 → **this SPEC**. **Live** HTTP response for `/from-project-spec` → **indexing SPEC**. Broader product policy (catalog of four types, deposit 30%, SGD) → parent + this SPEC restatement.

**As-built note (2026-08-07):** `app/api/recommendations.py` calls `IndexingIngestService`, not `RecommendationService`. FR-010 remains callable via `RecommendationService.recommend_from_project_spec` in tests and for future reattach.

---

## 1. Purpose

Define and record the **MVP recommendation pipeline** inside `haystack-fast-api` that:

1. Accepts unstructured project input (via existing intake API).
2. Runs **FR-010 steps 1–8** under `app/pipelines/` / `app/services/`:
   1. Resolve source text  
   2. Decompose needs (stub or LLM)  
   3. Expand quantity → unit-needs  
   4. Filter candidates (approved catalog / seed fleet)  
   5. Filter availability (seed booking overlap)  
   6. Attach prices via `predict_price()` (experimental or fallback)  
   7. Rank and emit rationale — **exactly one** pick per unit-need  
   8. Assemble singular `item` (`RecommendationItem | null`)
3. Keeps routers thin (**FR-015**); implements domain steps as Haystack **`@component`** units (**FR-016–018**).

---

## 2. Outcomes

When this specification is followed and as-built code remains compliant:

- A valid free-text or file request can return **non-null** `item` values with equipment type, `asset_id`, `rank`, `rationale`, `pricing`, and `availability` when the seed catalog matches.
- No-match / empty availability paths return `item: null` with warnings (Scenario C style).
- Responses only recommend **Boom Lift, Scissors Lift, Fork Lift, Excavator** (**FR-011**).
- `RecommendationItem` has **no `quantity`**; multi-unit requests are multiple unit-need rows (**FR-006**).
- Pricing comes from **`predict_price` integration** (not ad-hoc rate invention in the ranker) (**FR-020**).
- Default CI path works without Bedrock and without `model.pkl` (template rank; category fallback pricing).

---

## 3. Scope

### 3.1 In scope (MVP as-built)

| Area | Implementation |
|------|----------------|
| FR-010.1–3 | Haystack graph `intake_front`: resolve → decompose → expand |
| FR-010.4 | `AssetCandidateFilter` + in-memory **seed fleet** |
| FR-010.5 | `BookingAvailabilityFilter` + in-memory **seed bookings** |
| FR-010.6 | `PredictPriceAdapter` + `pricing_client` → `ml-experiments` or fallback |
| FR-010.7 | `RankRationaleGenerator` (deterministic score + template rationale) |
| FR-010.8 | Assemble in `RecommendationService` |
| Catalog hard filter | Four approved types only |
| Tests | Component + e2e pytest |

### 3.2 Out of scope (this SPEC / deferred)

| Area | Notes |
|------|--------|
| Spring-owned SQLAlchemy Asset/Booking models | Seed data until a future SDD/models PR |
| Production `app/services/pricing/` | Swap import in `pricing_client` when ready |
| LLM rank rationale / Bedrock-only rank | Template default; optional LLM later |
| SuperComponents, Tools, LangGraph, KG | Parent target sections |
| PDF/DOCX converters | Intake MVP is text/markdown |
| Auth, cart, payment | Project constitution |

### 3.3 Prototype data policy

- **Seed fleet** is acceptable for MVP (parent Day-1 “seeded subset”).
- Seed bookings exist to exercise overlap (e.g. `AST-EX-002` booked Sept 2026).
- Replacing seed sources with repositories/SQL MUST preserve component **sockets** where practical.

---

## 4. Functional requirements (pipeline)

### 4.1 FR-010 step mapping

| Step | Requirement | As-built owner |
|------|-------------|----------------|
| **1** | Resolve free-text and/or file extract → `source_text` | `SourceTextResolver` |
| **2** | Decompose → internal needs (+ quantity) | `NeedDecomposerComponent` + stub/LLM |
| **3** | Expand quantity → unit-needs (`base` / `base__u{i}`) | `ExpandQuantityComponent` |
| **4** | Filter candidates for unit-need against fleet/catalog | `AssetCandidateFilter` |
| **5** | Availability for date window before rank when dates set | `BookingAvailabilityFilter` |
| **6** | Call `predict_price()` path for candidates | `PredictPriceAdapter` / `pricing_client` |
| **7** | Select **one** best match + rationale | `RankRationaleGenerator` |
| **8** | Assemble `NeedResult` with singular `item` | `RecommendationService` |

### 4.2 Additional pipeline FRs

| ID | Requirement |
|----|-------------|
| **FR-P-001** | Domain steps 4–7 MUST be Haystack `@component` classes with `run()` → `dict` and typed `@component.output_types`. |
| **FR-P-002** | Empty candidate/available/priced lists MUST not raise unhandled exceptions. |
| **FR-P-003** | When both dates present, availability filtering MUST run before ranking for that unit-need. |
| **FR-P-004** | Responses MUST only include approved equipment types. |
| **FR-P-005** | Each `RecommendationItem` MUST include type/identity, rank, rationale, pricing (when include_pricing), availability; MUST NOT include `quantity`. |
| **FR-P-006** | Pricing MUST go through `pricing_client` (single swap point for production `predict_price`). |
| **FR-P-007** | Deposit default **0.30**, currency default **SGD** on pricing payload. |
| **FR-P-008** | Rationale MUST mention assumptions and schema-gap (terrain/operator-required) in template form. |
| **FR-P-009** | Routers MUST remain thin; no SQL/rank logic in handlers. |
| **FR-P-010** | Per unit-need processing MUST be independent (multi-need / quantity expansion). |
| **FR-P-011** | When `include_pricing` is true and a match is selected, `item.pricing` MUST expose: `daily_rate` (predicted for the **requested duration window** — duration is a model input), `total_price` (= `daily_rate × duration_days` for that window), `currency`, `deposit_rate`, `model_version`, `explanation`. MUST NOT expose a fabricated `weekly_rate` (e.g. `daily × 7`). A different date window requires a fresh `predict_price()` call — clients MUST NOT re-scale `daily_rate` by multiplying/dividing days. |
| **FR-P-012** | Async HTTP handlers (`async def`) MUST NOT run the full sync service path on the event loop. Offload via `fastapi.concurrency.run_in_threadpool` (or equivalent) for **both** JSON and multipart success paths. **Live route:** offload `IndexingIngestService`. **When recommend is reattached:** offload `RecommendationService` (and LLM HTTP) the same way. |

---

## 5. Design

### 5.1 Architecture

#### A. Live HTTP path (indexing — normative for the route)

```text
POST /api/v1/recommendations/from-project-spec
        │
        ▼
async router (app/api/recommendations.py)
        │
        ▼
run_in_threadpool(IndexingIngestService.ingest_from_project_spec)
        │
        ▼
indexing Pipeline: classify → convert → clean → split → embed → write
        │
        ▼
IngestFromProjectSpecResponse
```

Detail: [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md).

#### B. Recommend service path (FR-010 — not default HTTP)

```text
RecommendationService.recommend_from_project_spec(...)   # service / tests / future reattach
        │
        ├─► intake_front Pipeline (Haystack)
        │     resolve → decompose → expand
        │             │
        │             ▼
        │       unit_needs[]
        │
        └─► for each unit_need:
              AssetCandidateFilter
                    │
              BookingAvailabilityFilter   (if dates)
                    │
              PredictPriceAdapter
                    │
              RankRationaleGenerator      → one selected + rationale
                    │
              Assemble RecommendationItem | null
                    │
                    ▼
              results_by_need[{ need_id, item, warnings }]
```

**Pricing payload (when selected + `include_pricing`):** see **FR-P-011** / §5.6 — `daily_rate` + `total_price`, not `weekly_rate`.

### 5.2 Component inventory (MVP)

| Component | Inputs | Outputs | Notes |
|-----------|--------|---------|--------|
| `SourceTextResolver` | `project_text`, `file_text` | `source_text` | File then text |
| `NeedDecomposerComponent` | `source_text` | `needs` | Stub or LLM |
| `ExpandQuantityComponent` | `needs` | `unit_needs` | FR-006 ids |
| `AssetCandidateFilter` | `unit_need` | `candidates` | Seed fleet + keywords |
| `BookingAvailabilityFilter` | `candidates`, dates | `available_candidates` | Overlap remove |
| `PredictPriceAdapter` | `candidates`, `duration_days`, `include_pricing` | `priced_candidates` | FR-020 |
| `RankRationaleGenerator` | `unit_need`, `priced_candidates` | `selected`, `rationale` | Top-1 only |

### 5.3 Seed fleet (prototype)

- Types: Boom Lift, Scissors Lift, Fork Lift, Excavator (multiple units each).
- Fields: `asset_id`, `equipment_type`, `category` (ml-experiments slug), `condition`, `capacity`, `platform_height`, rate bounds.
- Bookings: at least one full-window booking to force unavailability of a specific asset (e.g. excavator unit in Sept 2026).

### 5.4 Candidate matching

- Infer model categories from `equipment_hints` + `description` keywords (`catalog.py`).
- Only approved display types retained.
- No signal → empty candidates → assemble `item=null`.

### 5.5 Availability

- Missing start or end date → all candidates available.
- With dates: drop assets whose seed booking overlaps the inclusive window.

### 5.6 Pricing

1. Prefer `ml-experiments/predict_price.predict_price` when `artifacts/model.pkl` loads.
2. Else **category fallback** table (still structured pricing payload; model_version indicates fallback).
3. Payload: `daily_rate` (scoped to the requested duration window), `total_price` (= `daily_rate × duration_days`), `currency=SGD`, `deposit_rate=0.30`, `model_version`, `explanation`. Do **not** fabricate a weekly rate as `daily × 7` — duration is a model input; a different window needs a fresh `predict_price()` call.
4. Production swap: change **only** `app/services/pricing_client.py`.

### 5.7 Rank & rationale

- Score: condition ordinal + hint match + capacity tie-break.
- Select **one** candidate (`rank=1`).
- Template rationale includes assumption + refinement + schema-gap (terrain/operator-required).
- Empty priced list → empty selection → `item=null` + warning.

### 5.8 Duration for pricing

- If both dates set: `duration_days = (end - start).days + 1` (minimum 1).
- Else default **7** days.

---

## 6. As-built file map

| Path | Role |
|------|------|
| `app/pipelines/source_text_resolver.py` | FR-010.1 |
| `app/pipelines/need_decomposer_component.py` | FR-010.2 |
| `app/pipelines/expand_quantity.py` | FR-010.3 |
| `app/pipelines/intake_front.py` | Graph 1–3 |
| `app/pipelines/catalog.py` | Approved types + keywords |
| `app/pipelines/seed_fleet.py` | Seed assets/bookings |
| `app/pipelines/asset_candidate_filter.py` | FR-010.4 |
| `app/pipelines/booking_availability_filter.py` | FR-010.5 |
| `app/pipelines/predict_price_adapter.py` | FR-010.6 |
| `app/pipelines/rank_rationale_generator.py` | FR-010.7 |
| `app/services/pricing_client.py` | predict_price import/fallback |
| `app/services/recommendations.py` | Orchestration + assemble (FR-010.8) |
| `app/services/need_decomposer.py` | Protocol + stub |
| `app/services/llm_need_decomposer.py` | Optional LLM decompose |
| `app/services/need_decomposer_factory.py` | stub \| llm factory |
| `app/api/recommendations.py` | Thin HTTP → **indexing** service (live) |
| `app/services/indexing.py` | Live ingest orchestration |
| `app/schemas/indexing.py` | Live ingest response |
| `app/schemas/recommendations.py` | Recommend I/O models (service / deferred HTTP) |
| `tests/test_recommend_pipeline_mvp.py` | Steps 4–8 + **service** e2e |
| `tests/test_pipeline_intake_front.py` | Steps 1–3 |
| `tests/test_recommendations_intake.py` | **HTTP ingest** e2e (indexing) |
| `tests/test_llm_need_decomposer.py` | LLM parse/mock |

---

## 7. API behaviour (pipeline outcomes)

Public contract details: [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md).

**Path:** `POST /api/v1/recommendations/from-project-spec`

**Happy path (scissors):** `item` non-null, e.g.:

```json
{
  "need_id": "need_1",
  "item": {
    "equipment_type": "Scissors Lift",
    "asset_id": "AST-SL-002",
    "rank": 1,
    "rationale": "Selected Scissors Lift ... schema does not capture terrain/operator-required).",
    "pricing": {
      "daily_rate": 180.0,
      "total_price": 1260.0,
      "currency": "SGD",
      "deposit_rate": 0.3,
      "model_version": "fallback-category-table",
      "explanation": "..."
    },
    "availability": "available"
  },
  "warnings": []
}
```

**No match:** `item: null`, non-empty `warnings`.

---

## 8. Acceptance criteria

1. **Given** free-text describing a scissors lift need, **when** recommend runs, **then** `item` is non-null with `equipment_type` in the approved catalog, `rank=1`, non-empty rationale, and pricing fields when `include_pricing` is true.
2. **Given** a need that matches no catalog keywords, **when** recommend runs, **then** `item` is null and warnings explain no match.
3. **Given** dates that overlap a seed booking for an asset, **when** filter runs, **then** that asset is not in available candidates.
4. **Given** quantity 2 for scissors, **when** expand + recommend run, **then** two unit-need rows each may receive an item (sufficient seed units).
5. **Given** empty priced candidates, **when** rank runs, **then** selection is empty and assemble yields `item=null`.
6. **Given** components for steps 4–7, **when** unit-tested standalone, **then** empty inputs return empty outputs without exceptions.
7. **Given** `include_pricing=false`, **when** price adapter runs, **then** candidates pass through without requiring model load success for pricing attachment (pricing null).

---

## 9. Verification

**Full step-by-step testing guide (pytest, curl, Postman, Swagger, negatives, DigitalOcean LLM):**  
[`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md)

### 9.1 Automated (summary)

```bash
cd haystack-fast-api
uv sync --all-groups
uv run pytest tests/test_pipeline_intake_front.py tests/test_recommend_pipeline_mvp.py tests/test_recommendations_intake.py -v
uv run pytest tests/ -v
```

### 9.2 Manual (summary)

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# POST /api/v1/recommendations/from-project-spec — see testing guide §3–§7
```

### 9.3 Optional LLM decompose

See testing guide §8 and intake-and-pipeline-front SPEC §13.

---

## 10. Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fleet source MVP | In-memory seed | No Spring models yet; SPEC allows seed subset |
| Pricing source MVP | ml-experiments + fallback | FR-021; no block if pkl missing |
| Public pricing fields | `daily_rate` + `total_price` (not `weekly_rate = daily × 7`) | Duration is a model input; fabricated weekly misquotes; mockup “Estimated total” |
| Async route + sync service | `run_in_threadpool` at router | FR-P-012 / parent NFR-008; LLM sync httpx must not block ASGI loop |
| Rank MVP | Deterministic + template rationale | CI without LLM; honest schema-gap text |
| Unit loop vs one giant graph | Service loop for 4–8 | Matches parent §8.1; easier testing |
| Production pricing swap | Single `pricing_client` module | FR-022 |

---

## 11. Open questions

| # | Question | Resolve by |
|---|----------|------------|
| 1 | Map seed assets to real Spring `Asset` tables | When ORM models land |
| 2 | Train/commit `model.pkl` for CI experimental pricing | Pricing team / artifact policy |
| 3 | LLM-generated rank rationale | Optional follow-on; template is MVP |
| 4 | AsyncPipeline for price ∥ availability | Parent open question; serial MVP is fine |
| 5 | **LLM warm-up DI:** lifespan may warm an `LlmNeedDecomposer`, but routes still construct a fresh `RecommendationService` (and decomposer) per request — warmed client unused; potential connection leak under sustained `NEED_DECOMPOSER=llm` | Before production LLM traffic: store decomposer on `app.state`, inject into service, `close()` on shutdown |

---

## 12. Change control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-05 | Initial SDD for as-built full FR-010.1–8 MVP pipeline (seed fleet, availability, pricing adapter, rank/assemble, verification) |
| **1.1.0** | 2026-08-06 | **PR review:** pricing payload `total_price` (not fabricated `weekly_rate`); duration-scoped `daily_rate` (**FR-P-011**); async route offloads sync service via `run_in_threadpool` (**FR-P-012**); open Q #5 warm-up DI follow-up |
| **1.2.0** | 2026-08-07 | **Spec reconcile:** dual architecture (live HTTP indexing vs service FR-010); conflict rule; FR-P-012 wording; file map + tests clarified |

When pipeline component contracts, seed data semantics, or assemble rules change, update **this SPEC** and as-built code/tests in the **same change set**. Live HTTP contract changes go to the indexing SPEC first.

# Recommendation Pipeline Specification

| Field | Value |
|-------|--------|
| **Status** | As-built MVP — full FR-010.1–8 **service-level** orchestration; **NOT** default HTTP for `/submitprojectspecification` |
| **Feature id** | `recommendation-pipeline-mvp` |
| **Tracking** | HR-65 (pipeline structure completion) |
| **Standards** | OpenSpec · Spec-kit user stories · OpenSPDD (see [`design.md`](./design.md)) |
| **Parent** | [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) |
| **Reading map** | [`../../AGENTS.md`](../../AGENTS.md) Path C (deferred recommend) |
| **Related** | [`../indexing/spec.md`](../indexing/spec.md) (**live HTTP**); [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md); [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md); [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md) |
| **Tests** | `tests/test_pipeline_intake_front.py`, `tests/test_recommend_pipeline_mvp.py` (service e2e), `tests/test_llm_need_decomposer.py`; HTTP ingest: `tests/test_recommendations_intake.py` (indexing, not this graph) |
| **Testing guide** | [`../../../docs/testing/recommendation-pipeline-testing-guide.md`](../../../docs/testing/recommendation-pipeline-testing-guide.md) |
| **Legacy source** | `specification/SPEC-recommendation-pipeline.md` |

**Read** project + setup first. Domain: [`../domain/spec.md`](../domain/spec.md). Parent owns end-to-end product vision, demo scenarios A/B/C, KG/agent targets, and deployment.

**Conflict rule:** Pipeline step behaviour and component contracts for FR-010 → **this capability**. **Live** HTTP response for `/submitprojectspecification` → **indexing**. Broader product policy (catalog of four types, deposit 30%, SGD) → parent + this restatement.

**As-built note (2026-08-07):** `app/api/recommendations.py` calls `IndexingIngestService`, not `RecommendationService`. FR-010 remains callable via `RecommendationService.recommend_from_project_spec` in tests and for future reattach.

---

## Purpose

Define and record the **MVP recommendation pipeline** inside `haystack-fast-api` that:

1. Accepts unstructured project input (via existing intake API shapes / service).
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

## Outcomes

- A valid free-text or file request can return **non-null** `item` values with equipment type, `asset_id`, `rank`, `rationale`, `pricing`, and `availability` when the seed catalog matches (service path).
- No-match / empty availability paths return `item: null` with warnings (Scenario C style).
- Responses only recommend **Boom Lift, Scissors Lift, Fork Lift, Excavator** (**FR-011**).
- `RecommendationItem` has **no `quantity`**; multi-unit requests are multiple unit-need rows (**FR-006**).
- Pricing comes from **`predict_price` integration** (not ad-hoc rate invention in the ranker) (**FR-020**).
- Default CI path works without Bedrock and without `model.pkl` (template rank; category fallback pricing).

---

## Scope

### In scope (MVP as-built)

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

### Out of scope (this capability / deferred)

| Area | Notes |
|------|--------|
| Spring-owned SQLAlchemy Asset/Booking models | Seed data until a future SDD/models PR |
| Production `app/services/pricing/` | Swap import in `pricing_client` when ready |
| LLM rank rationale / Bedrock-only rank | Template default; optional LLM later |
| SuperComponents, Tools, LangGraph, KG | Parent target sections |
| PDF/DOCX converters | Intake MVP is text/markdown (live indexing broader) |
| Auth, cart, payment | Project constitution |

### Prototype data policy

- **Seed fleet** is acceptable for MVP (parent Day-1 “seeded subset”).
- Seed bookings exist to exercise overlap (e.g. `AST-EX-002` booked Sept 2026).
- Replacing seed sources with repositories/SQL MUST preserve component **sockets** where practical.

---

## User Scenarios & Testing

### User Story 1 - Happy-path scissors recommendation (Priority: P1)

As the recommendation service, when free-text describes a scissors lift need, I return a non-null ranked item with pricing when requested.

**Independent Test:** `tests/test_recommend_pipeline_mvp.py` scissors-style free-text e2e.

**Acceptance Scenarios:**

1. **Given** free-text describing a scissors lift need, **When** recommend runs, **Then** `item` is non-null with `equipment_type` in the approved catalog, `rank=1`, non-empty rationale, and pricing fields when `include_pricing` is true.

### User Story 2 - No-match path (Priority: P1)

As the recommendation service, when a need matches no catalog keywords, I return `item: null` with warnings.

**Independent Test:** need with no catalog signal.

**Acceptance Scenarios:**

1. **Given** a need that matches no catalog keywords, **When** recommend runs, **Then** `item` is null and warnings explain no match.

### User Story 3 - Availability overlap (Priority: P1)

As the pipeline, when dates overlap a seed booking for an asset, that asset is not available.

**Independent Test:** `BookingAvailabilityFilter` with Sept 2026 seed booking.

**Acceptance Scenarios:**

1. **Given** dates that overlap a seed booking for an asset, **When** filter runs, **Then** that asset is not in available candidates.

### User Story 4 - Quantity expansion independence (Priority: P2)

As the pipeline, quantity 2 for scissors yields two unit-need rows that each may receive an item.

**Independent Test:** inject decomposer with quantity 2.

**Acceptance Scenarios:**

1. **Given** quantity 2 for scissors, **When** expand + recommend run, **Then** two unit-need rows each may receive an item (sufficient seed units).

### User Story 5 - Empty candidates and include_pricing off (Priority: P2)

**Acceptance Scenarios:**

1. **Given** empty priced candidates, **When** rank runs, **Then** selection is empty and assemble yields `item=null`.
2. **Given** components for steps 4–7, **When** unit-tested standalone, **Then** empty inputs return empty outputs without exceptions.
3. **Given** `include_pricing=false`, **When** price adapter runs, **Then** candidates pass through without requiring model load success for pricing attachment (pricing null).

---

## Requirements

### Requirement: FR-010 step 1 — Resolve source text

Resolve free-text and/or file extract → `source_text`. As-built owner: `SourceTextResolver`. File then project text when both present.

#### Scenario: Project text only
- **WHEN** only `project_text` is provided
- **THEN** `source_text` is the stripped project text

#### Scenario: File then project text
- **WHEN** both `file_text` and `project_text` are non-empty
- **THEN** `source_text` is file text, separator, then project text

### Requirement: FR-010 step 2 — Decompose needs

Decompose → internal needs (+ quantity). As-built: `NeedDecomposerComponent` + stub/LLM.

#### Scenario: Stub one need
- **WHEN** stub decomposer runs on non-empty source
- **THEN** one internal need is emitted with quantity ≥ 1

### Requirement: FR-010 step 3 — Expand quantity

Expand quantity → unit-needs (`base` / `base__u{i}`). As-built: `ExpandQuantityComponent`. Aligns with parent **FR-006**.

#### Scenario: Expand quantity two
- **GIVEN** a need with base id and `quantity = 2`
- **WHEN** expand runs
- **THEN** two unit-needs with ids `__u1` and `__u2` are emitted and unit dicts have no `quantity`

### Requirement: FR-010 step 4 — Filter candidates

Filter candidates for unit-need against fleet/catalog. As-built: `AssetCandidateFilter` + seed fleet.

#### Scenario: Approved types only
- **WHEN** candidates are filtered
- **THEN** only Boom Lift, Scissors Lift, Fork Lift, Excavator remain

#### Scenario: No signal empty
- **WHEN** need has no keyword/hint signal
- **THEN** candidates are empty (assemble `item=null` later)

### Requirement: FR-010 step 5 — Availability filter

Availability for date window before rank when dates set. As-built: `BookingAvailabilityFilter` + seed bookings.

#### Scenario: Missing dates all available
- **WHEN** start or end date is missing
- **THEN** all candidates are treated as available

#### Scenario: Overlap removes asset
- **WHEN** both dates set and a seed booking overlaps the inclusive window
- **THEN** that asset is dropped from available candidates

### Requirement: FR-010 step 6 — Price via predict_price

Call `predict_price()` path for candidates. As-built: `PredictPriceAdapter` / `pricing_client`.

#### Scenario: Prefer experimental model
- **WHEN** `ml-experiments/artifacts/model.pkl` loads
- **THEN** pricing uses experimental `predict_price`

#### Scenario: Category fallback
- **WHEN** model.pkl is missing
- **THEN** category fallback table still produces structured pricing payload with fallback `model_version`

### Requirement: FR-010 step 7 — Rank and rationale

Select **one** best match + rationale. As-built: `RankRationaleGenerator` (deterministic score + template rationale).

#### Scenario: Top-1 only
- **WHEN** priced candidates exist
- **THEN** exactly one candidate is selected with `rank=1` and non-empty rationale mentioning assumptions and schema-gap

#### Scenario: Empty priced list
- **WHEN** priced candidates are empty
- **THEN** selection is empty → `item=null` + warning

### Requirement: FR-010 step 8 — Assemble NeedResult

Assemble `NeedResult` with singular `item`. As-built: `RecommendationService`.

#### Scenario: Singular item key
- **WHEN** assemble completes for a unit-need
- **THEN** result has `need_id`, singular `item` (`RecommendationItem | null`), and `warnings`

### Requirement: Domain steps as Haystack components (FR-P-001)

Domain steps 4–7 MUST be Haystack `@component` classes with `run()` → `dict` and typed `@component.output_types`.

#### Scenario: Component contract
- **WHEN** a domain step component is unit-tested
- **THEN** `run()` returns a dict matching declared output types

### Requirement: Empty lists do not raise (FR-P-002)

Empty candidate/available/priced lists MUST not raise unhandled exceptions.

#### Scenario: Empty input safe
- **WHEN** empty lists are passed to steps 4–7
- **THEN** outputs are empty structured results without exceptions

### Requirement: Availability before ranking (FR-P-003)

When both dates present, availability filtering MUST run before ranking for that unit-need.

#### Scenario: Order with dates
- **GIVEN** both start and end dates
- **WHEN** a unit-need is processed
- **THEN** availability runs before rank/select

### Requirement: Approved equipment types only (FR-P-004)

Responses MUST only include approved equipment types.

#### Scenario: Catalog hard filter
- **WHEN** an item is selected
- **THEN** `equipment_type` is one of Boom Lift, Scissors Lift, Fork Lift, Excavator

### Requirement: RecommendationItem fields without quantity (FR-P-005)

Each `RecommendationItem` MUST include type/identity, rank, rationale, pricing (when include_pricing), availability; MUST NOT include `quantity`.

#### Scenario: No quantity field
- **WHEN** a RecommendationItem is serialized
- **THEN** it has no `quantity` field

### Requirement: Pricing through pricing_client (FR-P-006)

Pricing MUST go through `pricing_client` (single swap point for production `predict_price`).

#### Scenario: Single swap point
- **WHEN** production pricing lands
- **THEN** only `app/services/pricing_client.py` needs import change

### Requirement: Deposit and currency defaults (FR-P-007)

Deposit default **0.30**, currency default **SGD** on pricing payload.

#### Scenario: Defaults on payload
- **WHEN** pricing is attached to a selected item
- **THEN** `deposit_rate` defaults to 0.30 and `currency` defaults to SGD

### Requirement: Template rationale honesty (FR-P-008)

Rationale MUST mention assumptions and schema-gap (terrain/operator-required) in template form.

#### Scenario: Schema-gap text
- **WHEN** template rank runs for a selected item
- **THEN** rationale includes assumption / refinement / schema-gap phrasing

### Requirement: Thin routers (FR-P-009)

Routers MUST remain thin; no SQL/rank logic in handlers.

#### Scenario: No SQL in handlers
- **WHEN** HTTP handlers run
- **THEN** they delegate orchestration to services/pipelines

### Requirement: Independent per unit-need (FR-P-010)

Per unit-need processing MUST be independent (multi-need / quantity expansion).

#### Scenario: Multi-need independence
- **WHEN** multiple unit-needs are processed
- **THEN** rankings do not merge/confuse across unit-needs

### Requirement: Pricing payload shape (FR-P-011)

When `include_pricing` is true and a match is selected, `item.pricing` MUST expose: `daily_rate` (predicted for the **requested duration window** — duration is a model input), `total_price` (= `daily_rate × duration_days` for that window), `currency`, `deposit_rate`, `model_version`, `explanation`. MUST NOT expose a fabricated `weekly_rate` (e.g. `daily × 7`). A different date window requires a fresh `predict_price()` call — clients MUST NOT re-scale `daily_rate` by multiplying/dividing days.

#### Scenario: Daily and total without weekly
- **GIVEN** include_pricing and a selected match with duration_days D
- **WHEN** pricing is attached
- **THEN** `total_price = daily_rate × D` and no `weekly_rate` field is fabricated

### Requirement: Threadpool offload for async routes (FR-P-012)

Async HTTP handlers (`async def`) MUST NOT run the full sync service path on the event loop. Offload via `fastapi.concurrency.run_in_threadpool` (or equivalent) for **both** JSON and multipart success paths. **Live route:** offload `IndexingIngestService`. **When recommend is reattached:** offload `RecommendationService` (and LLM HTTP) the same way.

#### Scenario: Live offload
- **WHEN** live async `POST .../submitprojectspecification` succeeds
- **THEN** `IndexingIngestService` ran via threadpool

#### Scenario: Recommend reattach offload
- **WHEN** recommend is reattached on an async route
- **THEN** `RecommendationService` is offloaded the same way

---

## API behaviour (pipeline outcomes)

Public contract details: [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md).

**Service path:** `RecommendationService.recommend_from_project_spec(...)` (tests / future reattach of `POST /internal/v1/recommendations/submitprojectspecification`).

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

### Duration for pricing

- If both dates set: `duration_days = (end - start).days + 1` (minimum 1).
- Else default **7** days.

---

## Verification

**Full step-by-step testing guide:**  
[`../../../docs/testing/recommendation-pipeline-testing-guide.md`](../../../docs/testing/recommendation-pipeline-testing-guide.md)

### Automated (summary)

```bash
cd haystack-fast-api
uv sync --all-groups
uv run pytest tests/test_pipeline_intake_front.py tests/test_recommend_pipeline_mvp.py tests/test_recommendations_intake.py -v
uv run pytest tests/ -v
```

### Manual (summary)

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Live HTTP = indexing ingest (user_id). Service FR-010 via pytest / future reattach.
```

### Optional LLM decompose

See testing guide and historical HR-65 archive for DigitalOcean LLM notes.

---

## Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fleet source MVP | In-memory seed | No Spring models yet; SPEC allows seed subset |
| Pricing source MVP | ml-experiments + fallback | FR-021; no block if pkl missing |
| Public pricing fields | `daily_rate` + `total_price` (not `weekly_rate = daily × 7`) | Duration is a model input; fabricated weekly misquotes; mockup “Estimated total” |
| Async route + sync service | `run_in_threadpool` at router | FR-P-012 / parent NFR-008; LLM sync httpx must not block ASGI loop |
| Rank MVP | Deterministic + template rationale | CI without LLM; honest schema-gap text |
| Unit loop vs one giant graph | Service loop for 4–8 | Matches parent architecture; easier testing |
| Production pricing swap | Single `pricing_client` module | FR-022 |

---

## Open questions

| # | Question | Resolve by |
|---|----------|------------|
| 1 | Map seed assets to real Spring `Asset` tables | When ORM models land |
| 2 | Train/commit `model.pkl` for CI experimental pricing | Pricing team / artifact policy |
| 3 | LLM-generated rank rationale | Optional follow-on; template is MVP |
| 4 | AsyncPipeline for price ∥ availability | Parent open question; serial MVP is fine |
| 5 | **LLM warm-up DI:** lifespan may warm an `LlmNeedDecomposer`, but routes still construct a fresh `RecommendationService` (and decomposer) per request — warmed client unused; potential connection leak under sustained `NEED_DECOMPOSER=llm` | Before production LLM traffic: store decomposer on `app.state`, inject into service, `close()` on shutdown |

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-05 | Initial SDD for as-built full FR-010.1–8 MVP pipeline (seed fleet, availability, pricing adapter, rank/assemble, verification) |
| **1.1.0** | 2026-08-06 | **PR review:** pricing payload `total_price` (not fabricated `weekly_rate`); duration-scoped `daily_rate` (**FR-P-011**); async route offloads sync service via `run_in_threadpool` (**FR-P-012**); open Q #5 warm-up DI follow-up |
| **1.2.0** | 2026-08-07 | Spec reconcile: live HTTP indexing vs service FR-010 |
| **1.2.1** | 2026-08-07 | Sequential README; live path notes user_id + mandatory KG |
| **2.0.0** | 2026-08-10 | Migrated to OpenSpec Requirement/Scenario + design REASONS under `openspec/specs/recommendation-pipeline/` |

When pipeline contracts change, update this SPEC + tests. Live HTTP → indexing/KG first.

**Reading order:** [← Intake (deferred)](../recommendation-intake/spec.md) · [`../../AGENTS.md`](../../AGENTS.md) · [Next: Pricing →](../dynamic-pricing/spec.md) · [Design →](./design.md)

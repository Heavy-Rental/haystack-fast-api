# Recommendation Pipeline Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, Outcomes, FR-010.1–8, and FR-P-001..014.  
Call 1 live path is indexing. Call 2 quote HTTP is as-built (`getassetrecommendations`).
Call 2 quote collapse of unit-need siblings that share `equipment.id` is
**FR-P-013** (quote envelope only; [ADR-0010](../../adrs/0010-call2-quote-quantity-collapse.md)).
Merged `quantity` is the duplicate count (3 copies → `quantity: 3`).
LLM timeout recovery is **FR-P-014** ([ADR-0011](../../adrs/0011-llm-need-decompose-timeout-retry.md)).

## E — Entities

| Concept | Role |
|---------|------|
| Source text | Resolved free-text and/or file extract |
| DecomposedNeed | Internal need with optional quantity |
| UnitNeed | One ranking unit after quantity expansion (no quantity field) |
| Candidate asset | Seed fleet / future Asset row |
| Priced candidate | Candidate + pricing payload |
| NeedResult | `{ need_id, item, warnings }` |
| RecommendationItem | Singular ranked choice (or null) |
| RecommendQuoteItem | Portal quote line (`quantity`, `needId`, `equipment`) |
| Parent need id | `{base}` extracted from `{base}__u{i}` |

## A — Approach

### Live HTTP path (indexing — normative for the route)

```text
POST /submitprojectspecification (user_id required)
  → IndexingIngestService
  → dual-branch index → final_doc_joiner → embed → write
  → mandatory KG after post-join chunks
  → IngestFromProjectSpecResponse
```

Detail: [`../indexing/spec.md`](../indexing/spec.md) · [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) · map [`../../AGENTS.md`](../../AGENTS.md).

### Recommend service path (FR-010 — not default HTTP)

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

map_recommend_to_quote (Call 2 only)
  → RecommendQuoteItem per NeedResult (quantity=1)
  → collapse_duplicate_equipment_quotes by (parent_need_id, equipment.id)
  → confidenceScore on collapsed items
```

**Pricing payload (when selected + `include_pricing`):** FR-P-011 — `daily_rate` + `total_price`, not `weekly_rate`.

Pipeline-first Haystack for steps 1–3; service loop for steps 4–8 (testable, matches parent §8.1). Production pricing swaps only via `pricing_client`.

## S — Structure

### Component inventory (MVP)

| Component | Inputs | Outputs | Notes |
|-----------|--------|---------|--------|
| `SourceTextResolver` | `project_text`, `file_text` | `source_text` | File then text |
| `NeedDecomposerComponent` | `source_text` | `needs` | Stub or LLM |
| `ExpandQuantityComponent` | `needs` | `unit_needs` | FR-006 ids |
| `AssetCandidateFilter` | `unit_need` | `candidates` | Seed fleet + keywords |
| `BookingAvailabilityFilter` | `candidates`, dates | `available_candidates` | Overlap remove |
| `PredictPriceAdapter` | `candidates`, `duration_days`, `include_pricing` | `priced_candidates` | FR-020 |
| `RankRationaleGenerator` | `unit_need`, `priced_candidates` | `selected`, `rationale` | Top-1 only |

### Seed fleet (prototype)

- Types: Boom Lift, Scissors Lift, Fork Lift, Excavator (multiple units each).
- Fields: `asset_id`, `equipment_type`, `category` (ml-experiments slug), `condition`, `capacity`, `platform_height`, rate bounds.
- Bookings: at least one full-window booking to force unavailability of a specific asset (e.g. excavator unit in Sept 2026).

### Candidate matching

- Infer model categories from `equipment_hints` + `description` keywords (`catalog.py`).
- Only approved display types retained.
- No signal → empty candidates → assemble `item=null`.

### Availability

- Missing start or end date → all candidates available.
- With dates: drop assets whose seed booking overlaps the inclusive window.

### Pricing

1. Prefer `ml-experiments/predict_price.predict_price` when `artifacts/model.pkl` loads.
2. Else **category fallback** table (still structured pricing payload; model_version indicates fallback).
3. Payload: `daily_rate` (scoped to the requested duration window), `total_price` (= `daily_rate × duration_days`), `currency=SGD`, `deposit_rate=0.30`, `model_version`, `explanation`. Do **not** fabricate a weekly rate as `daily × 7`.
4. Production swap: change **only** `app/services/pricing_client.py`.

### Rank & rationale

- Score: condition ordinal + hint match + capacity tie-break.
- Select **one** candidate (`rank=1`).
- Template rationale includes assumption + refinement + schema-gap (terrain/operator-required).
- Empty priced list → empty selection → `item=null` + warning.

### Duration for pricing

- If both dates set: `duration_days = (end - start).days + 1` (minimum 1).
- Else default **7** days.

### As-built file map

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
| `app/services/session_recommend.py` | Call 2 quote map + FR-P-013 collapse |
| `app/schemas/recommend_quote.py` | Quote envelope (`quantity`, `needId`) |
| `tests/test_quote_duplicate_collapse.py` | FR-P-013 merge / non-merge |

## O — Operations

```bash
cd haystack-fast-api
uv sync --all-groups
uv run pytest tests/test_pipeline_intake_front.py tests/test_recommend_pipeline_mvp.py -v
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Optional LLM: `NEED_DECOMPOSER=llm` (+ provider env). Default CI stays on stub.
LLM timeouts: connect 10s, read `LLM_TIMEOUT_SECONDS` (default 120); one retry
then keyword fallback (**FR-P-014**).

## N — Norms

- Pipeline-first validation: components testable without agent loop.
- Seed fleet OK until Spring ORM; preserve component sockets on swap.
- Pricing always via `pricing_client`; never invent rates in the ranker.
- Singular `item` per unit-need; no `quantity` on RecommendationItem.
- Call 2 MAY raise `quantity` on the quote envelope by collapsing unit-need
  siblings that share `equipment.id` (FR-P-013). Merged `quantity` equals the
  number of grouped duplicates (3 copies → `quantity: 3`). Parent extraction
  is `{base}__u{i}`, not `split("_")`.
- Live HTTP conflict: indexing wins over this capability’s deferred envelope.

## S — Safeguards

- Do not treat service FR-010 response as live HTTP without reattach decision.
- Do not fabricate `weekly_rate = daily × 7`.
- Do not block ASGI with sync LLM/pipeline work (FR-P-012).
- Do not require Bedrock or model.pkl for CI green.
- Do not put SQL/rank logic in routers.
- Do not merge quote lines across different parent needs or distinct equipment ids.
- Do not collapse on empty/missing `equipment.id`.
- Do not mark quantity > 1 of one `assets.id` as available.
- Quantity-1 availability uses `bookings` + `return_records.returned_at`.

## Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fleet source MVP | In-memory seed | No Spring models yet |
| Pricing source MVP | ml-experiments + fallback | Non-blocking if pkl missing |
| Public pricing fields | `daily_rate` + `total_price` | Duration is model input |
| Async + sync service | `run_in_threadpool` | NFR-008 / FR-P-012 |
| Rank MVP | Deterministic + template | CI without LLM |
| Unit loop for 4–8 | Service loop | Easier testing |
| Production pricing swap | `pricing_client` only | FR-022 |
| Call 2 duplicate equipment | Collapse by parent need + `equipment.id` | FR-P-013; commercial quote, not ranking |

## Open questions

| # | Question | Resolve by |
|---|----------|------------|
| 1 | Map seed assets to real Spring `Asset` tables | When ORM models land |
| 2 | Train/commit `model.pkl` for CI experimental pricing | Pricing team / artifact policy |
| 3 | LLM-generated rank rationale | Optional follow-on |
| 4 | AsyncPipeline for price ∥ availability | Serial MVP is fine |
| 5 | LLM warm-up DI (app.state + close on shutdown) | Before production `NEED_DECOMPOSER=llm` traffic |

# Domain Specification

| Field | Value |
|-------|--------|
| **Status** | as-built (product-aligned) |
| **Standards** | OpenSpec requirements · Spec-kit key entities · OpenSPDD Entities layer |
| **SPDD Ready** | Yes |

This capability owns **concepts and invariants**. Behaviour, APIs, and acceptance criteria live in feature capabilities—especially equipment-recommendation and dynamic-pricing.

## Purpose

Provide ubiquitous language and product invariants for heavy machinery / equipment rental so all capability specs share the same domain vocabulary without restating full industry research.

## User Scenarios & Testing

### User Story 1 - Shared vocabulary for implementers (Priority: P1)

Engineers and agents use consistent names for Need, Asset, unit-need, RecommendationItem, and catalog constraints when implementing or reviewing APIs.

**Independent Test:** Review any live or deferred capability spec; domain terms match this document.

**Acceptance Scenarios:**

1. **Given** a recommendation or ingest feature, **When** it refers to equipment types, **Then** only approved catalog types are allowed unless policy expands.
2. **Given** quantity on an internal need, **When** ranking runs, **Then** quantity is expanded to unit-needs and RecommendationItem has no quantity field.

## Requirements

### Requirement: Approved equipment catalog
The product SHALL hard-filter ranking and responses to **Boom Lift**, **Scissors Lift**, **Fork Lift**, and **Excavator** unless product policy expands later.  
(Trace: domain product constraint)

#### Scenario: Catalog membership
- **WHEN** a recommendation or ranking outcome is produced
- **THEN** selected equipment types are within the approved catalog

### Requirement: Asset is schema-backed fleet unit
An **Asset** SHALL represent a fleet unit from the real Asset schema used for SQL candidate filtering (category/type, condition, capacity, platform height for scissor/boom, rate bounds). Recommendation filters candidates from Assets; it does not invent fleet units.

#### Scenario: Candidates come from Asset
- **WHEN** the recommendation path selects candidates
- **THEN** candidates are drawn from Asset records, not fabricated inventory

### Requirement: Free-text or file intake
Customer intake SHALL accept a **single free-text box** and/or an **uploaded file** of unstructured text (not a multi-row structured “add need” form). An LLM need decomposer turns text into one or more internal Needs.

#### Scenario: Unstructured intake shape
- **WHEN** a portal submits project needs for recommend (product target)
- **THEN** input is free-text and/or file, not a multi-row structured need form

### Requirement: Need and unit-need expansion
A **Need** SHALL be a structured demand after decomposition (`need_id`, description, optional equipment hints, optional quantity). Quantity N SHALL expand into N **unit-needs** (`need_id` or `need_id__u1`…`__uN`) processed independently.

#### Scenario: Quantity expansion
- **GIVEN** an internal need with quantity 3
- **WHEN** quantity expansion runs
- **THEN** three unit-needs are produced and processed independently

### Requirement: Shared rental window
Optional `start_date` / `end_date` (ISO 8601) on a recommendation request SHALL be shared across unit-needs for availability checks when provided.

#### Scenario: Window shared
- **GIVEN** start_date and end_date on the request
- **WHEN** availability is checked for multiple unit-needs
- **THEN** the same window applies to each

### Requirement: Booking availability is read-only
**Booking** / **BookingItem** SHALL be the source of availability truth via date-window overlap queries. This service SHALL treat bookings as **read-only**: recommend and filter; do not lock, mutate inventory, or own booking lifecycle.

#### Scenario: No booking mutation
- **WHEN** recommendation or availability filtering runs
- **THEN** no booking rows are created or modified by this service

### Requirement: One RecommendationItem per unit-need
Each unit-need SHALL receive **exactly one** selected recommendation (`item` singular) or null—not a top-N list. A RecommendationItem carries equipment identity (optional `asset_id`), rank/score (typically 1), rationale, pricing payload, and availability outcome. **No `quantity` field.**

#### Scenario: Singular item
- **WHEN** a unit-need is ranked successfully
- **THEN** the response for that need exposes a singular `item`, not a list of alternatives

### Requirement: Honest rationales
Rationale text SHALL support: **assumptions** when specs were inferred; **refinement suggestions** when the customer should supply more detail; **schema-gap** callouts when product cares about factors data does not capture (e.g. terrain, operator-required).

#### Scenario: Schema gap acknowledgement
- **GIVEN** a factor such as terrain that is product-relevant but not in schema
- **WHEN** rationale is generated
- **THEN** the system can acknowledge the schema gap in rationale text

### Requirement: Pricing via predict_price
Price SHALL be obtained by calling **`predict_price()`**—experimental under `ml-experiments/` during prototype, production `app/services/pricing/` when ready. Recommendation **calls** pricing; it does not re-implement the model. Ownership: [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md).

#### Scenario: Pricing call boundary
- **WHEN** a ranked item includes pricing
- **THEN** the value comes from `predict_price()` (or its production package), not a hand-written local stub once the function exists

### Requirement: Deposit and currency defaults
Deposit guidance default SHALL be **30%** (unless policy config overrides). Currency default SHALL be **SGD**.

#### Scenario: Defaults on product surfaces
- **WHEN** deposit or currency guidance is shown without override
- **THEN** deposit is 30% and currency is SGD

### Requirement: Knowledge graph layers
The product MAY use offline/batch structure over catalog and historical project text (**KG-2**, Stage 2). As-built Stage 1: **mandatory** user-scoped **KG-1** from project-spec upload and multi-agent Q&A — see [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md). KG SHALL NOT replace Asset SQL, Booking availability, or `predict_price()` on the recommend path unless a later SDD promotes those as live agent tools.

#### Scenario: KG does not replace SQL recommend
- **WHEN** the FR-010 recommend service path runs
- **THEN** candidates and availability still come from Asset/Booking models unless a later SDD changes that

### Requirement: Industry context non-goals for MVP
Utilization targets, fleet optimization, maintenance scheduling, and multi-branch logistics remain industry drivers but SHALL NOT be primary online entities for the recommendation MVP API.

#### Scenario: MVP entity boundary
- **WHEN** implementing the 6-day recommendation MVP
- **THEN** maintenance events and multi-branch logistics are not required online entities

## Key entities (Spec-kit)

| Entity | Meaning |
|--------|---------|
| **Equipment / Asset (industry)** | Physical machines; lifecycle acquisition → on-rent/available/maintenance/transit → disposal |
| **Utilization** | Fleet performance metric; healthy ~65–75% |
| **Fleet** | Collection of assets (often multi-branch) |
| **Maintenance Event** | Scheduled vs unplanned cost + lost rental days |
| **Customer** | Contractor / industrial / municipality with project pipeline uncertainty |
| **Branch / Yard** | Storage, maintenance, dispatch location |
| **Rental Transaction (industry)** | Time-based rates + ancillaries; this service does not own booking lifecycle or payment |
| **Asset (product)** | Schema-backed fleet unit for SQL filter + pricing bounds |
| **Need / unit-need** | Internal demand after LLM decompose + quantity expansion |
| **RecommendationItem** | Singular selected match per unit-need |
| **KG-1 / KG-2** | Project vs equipment knowledge graphs |

## Entity relationships

```text
Customer / portal / intake
        │
        ▼
Recommendation request
  • project_text and/or file
  • optional start_date / end_date
        │
        ▼
  LLM NeedDecomposer → internal Needs
        │
        ▼
  Expand quantity → unit-needs
        │  per unit-need
        ▼
   Asset candidates  ──SQL + catalog──►
        │
        ├─► Booking / BookingItem overlap  (read-only)
        └─► predict_price()
        │
        ▼
   Rank + Rationale → item: RecommendationItem | null
```

Ownership: booking writes/payment → Spring/portal; pricing model → pricing capability; recommendation orchestration → this app.

## Pain points mapped

| Pain point | Domain concepts | Product address (high level) |
|------------|-----------------|------------------------------|
| Wrong or slow equipment match | Need, Asset, catalog | Ranked recommendations |
| Availability uncertainty | Asset, Booking, window | Date-window overlap; empty path |
| Pricing leakage | Pricing prediction, rate bounds | `predict_price()` + guardrails |
| Opaque recommendations | Rationale, schema gaps | Assumptions, refinements, gaps |
| Low utilization / maintenance / logistics / capital | Industry concepts | Context; not primary MVP API |

## Open questions (foundation only)

Resolved: building agentic equipment recommendation + pricing in `haystack-fast-api`; primary API user is customer/portal intake; pricing team produces `predict_price()`.

| Question | Where to resolve |
|----------|------------------|
| Refine/reject, cart persistence, schema-gap wording, Bedrock model ids, DocumentStore choice | equipment-recommendation open questions |
| Shared Spring schema / seed data | Future seed-data SDD; pricing minimal read models |
| Multi-tenant auth / JWT | Deferred until shared auth SDD |

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-10 | Migrated from `specification/01-domain.md` to OpenSpec + Spec-kit entities |

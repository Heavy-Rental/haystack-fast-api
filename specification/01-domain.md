# Domain Model — Heavy Machinery / Equipment Rental

| Field | Value |
|-------|--------|
| **Document type** | SDD foundation (ubiquitous language) |
| **Status** | Product-aligned with agentic recommendation & dynamic pricing (August 2026) |
| **SPDD Ready** | Yes |

Synthesized from industry research and product constraints in the feature SDDs. This file owns **concepts and invariants**. Behaviour, APIs, and acceptance criteria live in feature SPECs—especially [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) and [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md).

---

## Purpose & document ownership

| Concern | Owner |
|---------|--------|
| Domain language, entities, relationships, business invariants | **This file** |
| Recommendation pipeline, rationale rules, demo scenarios, API sketch | Feature SDD (agentic recommendation) |
| `predict_price()` productionization, guardrails, feature schema | Feature SDD (dynamic pricing) |
| Stack, DB session, layering | [`SPEC-project-setup.md`](./SPEC-project-setup.md) |

---

## Core Concepts

### Industry concepts (context)

#### Equipment / Asset (industry view)

- Physical machines across a broad rental catalog (excavators, loaders, aerial lifts, generators, compressors, trenchers, cranes, specialty).
- Lifecycle: acquisition → on-rent / available / in-maintenance / in-transit → disposal or redeployment.
- Economics: ownership cost, depreciation, utilization contribution.

#### Utilization

- Primary fleet performance metric.
- Healthy target: ~65–75% time utilization.
- Below ~55% typically destroys value; above ~85% risks deferred maintenance and lost opportunities.

#### Fleet

- Collection of assets managed by a rental company (often multi-branch).
- Optimization problem: right machine, right place, right time.

#### Maintenance Event

- Scheduled vs unplanned; direct cost + lost rental days; linked to condition and utilization.

#### Customer (Contractor / Industrial / Municipality)

- Project pipeline uncertainty drives rental preference over ownership.
- Sensitive to availability, reliability, delivery performance, and billing accuracy.

#### Branch / Yard

- Physical location for storage, maintenance, and dispatch; logistics cost center.

#### Rental Transaction (industry view)

- Time-based rates (daily / weekly / monthly) plus ancillaries (delivery, fuel, damage waiver, overtime, attachments).
- **This service does not own booking lifecycle or payment**; it recommends and prices candidates for intake.

> **Note:** Utilization, fleet optimization, maintenance scheduling, and multi-branch logistics remain industry drivers. They are **not** primary online entities for the 6-day recommendation MVP; later features may re-surface them.

---

### Product concepts (authoritative for current build)

#### Approved equipment types (catalog constraint)

Hard product filter for ranking and responses:

- **Boom Lift**
- **Scissors Lift**
- **Fork Lift**
- **Excavator**

Industry breadth above is research context; **responses MUST stay within this catalog** unless product policy expands later.

#### Asset (product / schema)

- Fleet unit exposed via the real **`Asset`** schema used for SQL candidate filtering.
- Attributes relevant to match and pricing include category/type, condition, capacity, and—for scissor/boom lifts—platform height; rate bounds (`minDailyRate` / `maxDailyRate`) constrain ML price guardrails (see pricing SDD).
- Recommendation filters candidates from Assets; it does not invent fleet units.

#### Project specification / free-text intake (MVP)

- Customer submits a **single free-text box** and/or an **uploaded file** of unstructured text (not a multi-row structured “add need” form).
- An **LLM need decomposer** turns that text into one or more **internal Needs**.

#### Need (internal, after LLM)

- Structured expression of equipment demand **produced by decomposition**: identity (`need_id`), description, optional equipment hints, optional **quantity**.
- **Quantity** is expanded into **unit-needs** before ranking (`need_id` or `need_id__u1`…`__uN`). Each unit-need is processed **independently**.

#### Rental window

- Optional `start_date` / `end_date` (ISO 8601 dates) on the recommendation request.
- When provided, the window is **shared** across unit-needs for availability checks.

#### Booking / BookingItem

- Source of **availability truth** via date-window **overlap** queries.
- This service treats bookings as **read-only**: recommend and filter; do not lock, mutate inventory, or own booking lifecycle (Spring / portal own write path).

#### Recommendation request

- Intake unit: free-text and/or file (+ optional rental window).
- After decompose + quantity expansion, outcomes are grouped **by unit-need**.

#### RecommendationItem

- **Exactly one** selected recommendation for a unit-need (response field singular `item`; **not** a top-N list). At product level it carries at least:
  - Equipment type / identity (and optional `asset_id` when unit-level)
  - Rank (or score)—typically `1` for the selected choice
  - **Rationale** (see below)
  - **Pricing** payload from `predict_price()`
  - **Availability** outcome
- **No `quantity` field**—quantity was expanded into separate unit-need rows.

#### Rationale

- Honest explainability attached to each item:
  - **Assumptions** stated when specs were inferred
  - **Refinement suggestions** when the customer should supply more detail
  - **Schema-gap** callouts when the product cares about factors the data does not capture (e.g. terrain, operator-required)

#### Pricing prediction

- Price is obtained by calling **`predict_price()`**—experimental module during prototype (`ml_experiments/` / `ml-experiments/`), production `app/services/pricing/` when ready.
- Pricing model ownership, feature schema, and guardrail clamping: [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md).
- Recommendation path **calls** pricing; it does not re-implement the model or expose raw model predictions on arbitrary renter-facing routes outside the agreed recommendation response.

#### Deposit & currency defaults (product alignment)

- Deposit guidance default: **30%** (unless policy config overrides).
- Currency default: **SGD**.

#### Knowledge graph (target)

- Offline / batch structure over catalog and historical project text (e.g. Ragas `KnowledgeGraph`) for multi-hop suitability, richer rationales, and evaluation aids.
- **Does not replace** Asset SQL filtering, Booking availability, or `predict_price()` on the online path unless a later SDD promotes graph traversal to a live tool.

---

## Entity relationships

```text
Customer / portal / intake
        │
        ▼
Recommendation request
  • project_text and/or file  (unstructured; single free-text box UX)
  • optional start_date / end_date  (shared rental window)
        │
        ▼
  LLM NeedDecomposer → internal Needs (may include quantity)
        │
        ▼
  Expand quantity → unit-needs (no quantity on RecommendationItem)
        │
        │  per unit-need (independent loop)
        ▼
   Asset candidates  ──SQL filter on real Asset schema + approved catalog──►
        │
        ├─► Booking / BookingItem overlap  (read-only availability)
        └─► predict_price()                (pricing workstream)
        │
        ▼
   Rank + Rationale  (Haystack generation) — select ONE best match
        │
        ▼
   item: RecommendationItem | null   // exactly one per unit-need
        (type/asset, rank, rationale, pricing, availability)

Ownership boundaries
  • Booking writes / payment / cart lifecycle → Spring REST / portal (not this service)
  • Pricing model artifacts & train logic     → pricing SDD / pricing team
  • Recommendation orchestration             → this app’s pipelines/services
```

---

## Key Business Rules & Invariants

### Industry (from research)

- Utilization is the primary driver of profitability for a given asset class.
- Revenue leakage occurs through missed ancillary charges and complex rate structures.
- Capital intensity makes accurate TCO / ROI calculations essential but data-dependent.
- National players compete with local/regional operators; scale vs relationship trade-offs apply.

### Product (from current feature SDDs)

- **Catalog hard filter:** only Boom Lift, Scissors Lift, Fork Lift, Excavator unless policy expands.
- **Unit-need independence:** each unit-need gets **exactly one** ranked `item` (or null); do not merge lists or return top-N alternatives per need.
- **Quantity expansion:** internal quantity *N* becomes *N* unit-need rows; never a quantity field on `RecommendationItem`.
- **Availability before presentation:** when dates are provided, booking overlap filtering runs before final ranking presentation for that need.
- **Read-only availability:** this service does not lock units or own booking lifecycle.
- **Honest rationales:** assumptions, refinements, and schema gaps (e.g. terrain, operator-required) must be acknowledgeable in rationale text.
- **Pricing integration:** use `predict_price()` (experimental then production); avoid hand-written local price stubs once the experimental function exists.
- **Deposit / currency defaults:** 30% deposit guidance; SGD default currency.
- **No payment gateway / multi-tenant auth** in the current recommendation scope (deferred until shared auth / portal SDDs).

---

## Pain Points Mapped to Domain & Product

| Pain point | Primary domain concepts | How the current product addresses (high level) |
|------------|-------------------------|-----------------------------------------------|
| Wrong or slow equipment match | Need, Asset, approved catalog | Ranked recommendations from structured needs |
| Availability uncertainty | Asset, Booking, BookingItem, rental window | Date-window overlap filter; empty / no-match path |
| Pricing leakage / ad-hoc rates | Pricing prediction, Asset rate bounds | `predict_price()` with production guardrails (pricing SDD) |
| Opaque recommendations | Rationale, schema gaps | Explicit assumptions, refinement suggestions, gap callouts |
| Low utilization (industry) | Equipment, Fleet, Demand | Better match quality supports utilization; not a direct MVP API |
| Maintenance / downtime | Equipment, Maintenance Event | Industry context; not primary recommendation entities |
| Visibility & tracking | Asset location/status, Branch | Context; online path uses Asset + Booking read models |
| Logistics complexity | Equipment, Branch, job site | Industry context for later features |
| Capital allocation / ROI | Asset cost, Utilization | Industry context; ML pricing is a related but separate concern |

---

## Related specs

| Spec | Role relative to this domain model |
|------|-------------------------------------|
| [`00-overview.md`](./00-overview.md) | Vision, problem space, product focus |
| [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) | Normative recommendation behaviour, pipeline, API, acceptance |
| [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) | `predict_price()`, features, guardrails, retrain |
| [`SPEC-project.md`](./SPEC-project.md) / [`SPEC-project-setup.md`](./SPEC-project-setup.md) | As-built service and environment |

---

## Open questions (foundation only)

Resolved at foundation level by the agentic recommendation SDD:

- **What are we building first?** Agentic equipment recommendation + pricing recommender in `haystack-fast-api`.
- **Who is the primary user?** Customer / portal / intake UI (API consumer); pricing team as producer of `predict_price()`.

Still open or owned elsewhere:

| Question | Where to resolve |
|----------|------------------|
| Refine/reject flow, “add to cart” persistence, exact schema-gap wording, Bedrock model ids, DocumentStore choice, etc. | Feature SDD §14 open questions (agentic recommendation) |
| Shared Spring schema ownership details / seed data | Future seed-data or integration SDDs; pricing notes minimal read models on Spring-owned schema |
| Multi-tenant auth / JWT | Deferred until a shared auth SDD exists |

Do not re-litigate product identity here; keep new foundation questions limited to cross-feature domain language.

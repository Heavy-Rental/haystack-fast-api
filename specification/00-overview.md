# Project Overview — Heavy Machinery Rental Domain

| Field | Value |
|-------|--------|
| **Document type** | SDD foundation (vision & problem space) |
| **Status** | Research foundation complete; first product focus defined (August 2026) |
| **SPDD Ready** | Yes |
| **Application** | `haystack-fast-api` |

<<<<<<< HEAD
**Related specs:** [`01-domain.md`](./01-domain.md) · [`SPEC-project.md`](./SPEC-project.md) · [`SPEC-project-setup.md`](./SPEC-project-setup.md) · [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) · [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) · [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) · [`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md) · [`SPEC-recommendation-postman-testing-guide.md`](./SPEC-recommendation-postman-testing-guide.md) · [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md)
=======
**Related specs:** [`01-domain.md`](./01-domain.md) · [`SPEC-project.md`](./SPEC-project.md) · [`SPEC-project-setup.md`](./SPEC-project-setup.md) · [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) · [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) · [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md)
>>>>>>> develop

## Vision

Build software that addresses core economic and operational challenges of the heavy equipment rental industry—high utilization, accurate pricing, asset visibility, and sound capital decisions—grounded in real industry economics and case research.

**Product expression in this repository:** `haystack-fast-api` is a **FastAPI** service that exposes **Haystack** pipelines for **agentic equipment recommendation**, with **ML-assisted pricing** (`predict_price()`) for a rental portal / intake experience. The service ranks suitable, available equipment against structured needs and returns honest rationales—not opaque black-box matches.

## Core Problem Space

The industry is capital-intensive. Success depends on:

- High fleet utilization (target 65–75%)
- Minimizing unplanned downtime
- Accurate pricing & billing (revenue leakage is common)
- Real-time visibility of assets across yards and job sites
- Efficient logistics for large machines
- Sound capital allocation / ROI decisions

**Software problem this product targets first:** customers and intake UIs struggle to turn equipment **needs** (and optional rental dates or project text) into **ranked, available assets with data-driven prices and clear reasons**. Manual matching is slow; availability is easy to get wrong; pricing is often ad-hoc; recommendations rarely admit assumptions or schema limits (e.g. terrain, operator-required).

## Product Focus (current)

| Aspect | Value |
|--------|--------|
| **Feature** | Agentic Equipment Recommendation & Pricing Recommender |
| **Feature id** | `agentic-equipment-recommendation-pricing` |
| **Normative SDD** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) |
| **Pricing companion** | [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) — productionizes `predict_price()` for the recommendation path |
| **Approved catalog** | Boom Lift, Scissors Lift, Fork Lift, Excavator |

**MVP shape (summary only):** free-text and/or project file (+ optional rental window) → LLM need decompose → quantity expansion to unit-needs → `Asset` SQL candidates → `Booking` / `BookingItem` availability → `predict_price()` → Haystack rank & rationale → **exactly one** `RecommendationItem` **per unit-need** (singular `item`).

**Target (post–6-day MVP, detail in feature SDD):** richer file converters, SuperComponents/Tools, optional LangGraph orchestration, offline knowledge graph enrichment, async ML training trigger. Normative behaviour, API contract, and acceptance criteria live **only** in the feature SPECs—not here.

## Primary Stakeholders

| Role | Interest in this product |
|------|---------------------------|
| **Customer / portal / intake UI** | Submit needs (+ optional dates/spec) → ranked available equipment with prices and rationales |
| **Recommendation pipeline / implementers** | Orchestrate filter → availability → price → rank under Haystack 2.0 contracts |
| **Pricing team** | Own `predict_price()` and model training; recommendation **calls** pricing, does not re-own it |
| **Ops / data scientist** (target) | Trigger or schedule ML training; poll job status |
| **Spring REST API / portal** (adjacent) | May call this service or share DB read models for assets/bookings; booking **write** path is not owned here |
| **Rental operators** (fleet / branch / finance) | Domain beneficiaries of better match, utilization, and pricing discipline |

Contractors, mechanics, yard staff, and capital teams remain industry stakeholders; the first build’s primary *user* of the API is the customer / portal intake path.

## SDD Document Map

Read in this order for new work:

1. **This file** — vision, problem space, current product focus  
2. [`01-domain.md`](./01-domain.md) — ubiquitous language, entities, invariants  
3. [`SPEC-project.md`](./SPEC-project.md) — project identity, as-built structure  
4. [`SPEC-project-setup.md`](./SPEC-project-setup.md) — stack, Postgres, uv, layering (normative environment)  
5. Feature SPECs — behaviour, APIs, acceptance criteria  

| Document layer | Owns |
|----------------|------|
| `00-overview` / `01-domain` | Vision, domain language, product focus at a glance |
| `SPEC-project` / `SPEC-project-setup` | Repo identity, stack, layout, runbooks |
| `SPEC-<feature>.md` | Normative requirements, contracts, acceptance |

Do **not** duplicate FR tables, OpenAPI sketches, or day-by-day plans in foundation docs.

## Existing Research Assets

Prior industry research (domain knowledge base for SDD; may live outside this application module):

- `Heavy_Machinery_Rental_Research_Synthesis.md` — full industry model, pain points, case elaborations  
- `Heavy_Machinery_Rental_and_Ownership_Case_Studies.md` — detailed case studies (United Rentals, etc.)

Treat these as **authoritative industry context** when present. Product behaviour is still governed by feature SPECs under `specification/`.

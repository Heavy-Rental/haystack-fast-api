# Project Overview — Heavy Machinery Rental Domain

| Field | Value |
|-------|--------|
| **Document type** | SDD foundation (vision & problem space) |
| **Status** | Research foundation complete; first product focus defined (August 2026) |
| **SPDD Ready** | Yes |
| **Application** | `haystack-fast-api` |

**Reading order (start here):** [`specification/README.md`](./README.md) — sequential paths matching runtime flow.

**Related specs:** [`01-domain.md`](./01-domain.md) · [`SPEC-project.md`](./SPEC-project.md) · [`SPEC-project-setup.md`](./SPEC-project-setup.md) · [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) · [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md) · [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) · [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) · [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) · [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) · testing guides
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

**MVP shape (product target):** free-text and/or project file (+ optional rental window) → LLM need decompose → quantity expansion to unit-needs → `Asset` SQL candidates → `Booking` / `BookingItem` availability → `predict_price()` → Haystack rank & rationale → **exactly one** `RecommendationItem` **per unit-need** (singular `item`).

**As-built public route (2026-08-07+):** `POST /api/v1/recommendations/from-project-spec` requires **`user_id`**, runs **Packt dual-branch indexing** through `final_doc_joiner` → embed → **`InMemoryDocumentStore`**, then **always** builds a **user-scoped knowledge graph** (hard-fail on failure; see [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md)), and returns **`IngestFromProjectSpecResponse`**. Normative live contract: [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md). FR-010 recommend remains **service-level** for tests and reattach.

**Target (later):** reattach recommend HTTP; Naive/hybrid RAG query; multi-agent fusion of store + KG; async ML training. Normative detail lives in feature SPECs—not here.

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

**Full sequential map (paths A–D + runtime diagram):** [`README.md`](./README.md).

Short onboard order:

1. [`README.md`](./README.md) — reading paths & live flow  
2. **This file** — vision, as-built vs target  
3. [`01-domain.md`](./01-domain.md) — ubiquitous language  
4. [`SPEC-project.md`](./SPEC-project.md) · [`SPEC-project-setup.md`](./SPEC-project-setup.md)  
5. **Live path:** [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) → [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md)  

| Document layer | Owns |
|----------------|------|
| `README` | Sequential reading order |
| `00-overview` / `01-domain` | Vision, domain language |
| `SPEC-project` / `SPEC-project-setup` | Repo identity, stack, env |
| Indexing + knowledge-graph SPECs | **Live** project-spec HTTP flow |
| Recommend / pricing SPECs | Deferred recommend + service FR-010 |
| Parent agentic SPEC | Full product SDD |

Do **not** duplicate FR tables in foundation docs.

---

**Reading order:** [← Map](./README.md) · [Next: Domain →](./01-domain.md)

## Existing Research Assets

Prior industry research (domain knowledge base for SDD; may live outside this application module):

- `Heavy_Machinery_Rental_Research_Synthesis.md` — full industry model, pain points, case elaborations  
- `Heavy_Machinery_Rental_and_Ownership_Case_Studies.md` — detailed case studies (United Rentals, etc.)

Treat these as **authoritative industry context** when present. Product behaviour is still governed by feature SPECs under `specification/`.

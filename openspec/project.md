# Project — haystack-fast-api

| Field | Value |
|-------|--------|
| **Document type** | OpenSpec project context + Spec-kit project overview |
| **Status** | As-built living context |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` (uv project root) |
| **Python package** | `app` |
| **Spec root** | `openspec/` |
| **Standards** | OpenSpec · GitHub Spec-kit · OpenSPDD |
| **SPDD Ready** | Yes |

**Reading order:** [`AGENTS.md`](./AGENTS.md). **Constitution:** [`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

---

## Vision

Build software that addresses core economic and operational challenges of the heavy equipment rental industry—high utilization, accurate pricing, asset visibility, and sound capital decisions—grounded in real industry economics and case research.

**Product expression in this repository:** `haystack-fast-api` is a **FastAPI** service that exposes **Haystack** pipelines for **agentic equipment recommendation**, with **ML-assisted pricing** (`predict_price()`) for a rental portal / intake experience. The service ranks suitable, available equipment against structured needs and returns honest rationales—not opaque black-box matches.

---

## Core problem space

The industry is capital-intensive. Success depends on:

- High fleet utilization (target 65–75%)
- Minimizing unplanned downtime
- Accurate pricing & billing (revenue leakage is common)
- Real-time visibility of assets across yards and job sites
- Efficient logistics for large machines
- Sound capital allocation / ROI decisions

**Software problem this product targets first:** customers and intake UIs struggle to turn equipment **needs** (and optional rental dates or project text) into **ranked, available assets with data-driven prices and clear reasons**. Manual matching is slow; availability is easy to get wrong; pricing is often ad-hoc; recommendations rarely admit assumptions or schema limits (e.g. terrain, operator-required).

---

## Product focus (current)

| Aspect | Value |
|--------|--------|
| **Feature** | Agentic Equipment Recommendation & Pricing Recommender |
| **Feature id** | `agentic-equipment-recommendation-pricing` |
| **Normative product capability** | [`specs/equipment-recommendation/spec.md`](./specs/equipment-recommendation/spec.md) |
| **Pricing companion** | [`specs/dynamic-pricing/spec.md`](./specs/dynamic-pricing/spec.md) |
| **Approved catalog** | Boom Lift, Scissors Lift, Fork Lift, Excavator |

**MVP shape (product target):** free-text and/or project file (+ optional rental window) → LLM need decompose → quantity expansion to unit-needs → `Asset` SQL candidates → `Booking` / `BookingItem` availability → `predict_price()` → Haystack rank & rationale → **exactly one** `RecommendationItem` **per unit-need** (singular `item`).

**As-built public routes (S1a):** `POST /internal/v1/recommendations/submitprojectspecification` requires **`user_id`**, runs **Packt dual-branch indexing** through `final_doc_joiner` → embed → **`InMemoryDocumentStore`**, then **always** builds a **user-scoped knowledge graph** (hard-fail on failure; see [`specs/knowledge-graph/`](./specs/knowledge-graph/)), registers a project knowledge session, and returns **lean** `IngestFromProjectSpecResponse` (`ingest_id`, `user_id`, `user_requirement_summary`, `warnings[]`). Stage-1 multi-agent Q&A: `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` over project store + KG-1 (`query` required). Normative live ingest: [`specs/indexing/`](./specs/indexing/). FR-010 recommend remains **service-level** for tests and reattach.

**Target (later):** reattach recommend HTTP; equipment KG-2 + stockpile tools; Naive/hybrid RAG over manuals; async ML training. Normative detail lives in capability specs—not here.

---

## Product identity (as-built service)

| Aspect | State |
|--------|--------|
| Packaging | **uv** project (`pyproject.toml` + `uv.lock`), Python **≥ 3.12** |
| Runtime entry | `app.main:app` (Uvicorn), port **8000** |
| Public API (baseline) | `GET /health`; `POST /internal/v1/recommendations/submitprojectspecification` (lean body); `POST .../project-knowledge/getassetrecommendations` |
| Persistence (runtime) | PostgreSQL on host **`db`**; SQLAlchemy **sync** + **psycopg** |
| Auth | None (deferred) |
| Pipelines | Haystack under `app/pipelines/` (indexing, kg, recommend components) |
| Agents | LangGraph Stage-1 under `app/agents/`; prompts OpenSPDD-first |

Environment, packaging, database host defaults, layering rules, and runbooks: [`specs/project-setup/`](./specs/project-setup/).

---

## Primary stakeholders

| Role | Interest in this product |
|------|---------------------------|
| **Customer / portal / intake UI** | Submit needs (+ optional dates/spec) → ranked available equipment with prices and rationales; today also project-spec ingest + Q&A |
| **Recommendation pipeline / implementers** | Orchestrate filter → availability → price → rank under Haystack 2.0 contracts |
| **Pricing team** | Own `predict_price()` and model training; recommendation **calls** pricing |
| **Ops / data scientist** (target) | Trigger or schedule ML training; poll job status |
| **Spring REST API / portal** (adjacent) | May call this service or share DB read models; booking **write** path is not owned here |
| **Rental operators** | Domain beneficiaries of better match, utilization, and pricing discipline |

---

## Document map

| Layer | Owns |
|-------|------|
| `AGENTS.md` | Sequential reading order, conflict rules, agent workflow |
| `project.md` (this file) | Vision, product focus, identity |
| `specs/domain` | Ubiquitous language & product invariants |
| `specs/project-setup` | Stack, env, layering, runbooks |
| `specs/indexing` + `knowledge-graph` | **Live** project-spec HTTP flow |
| Recommend / pricing specs | Deferred recommend + service FR-010 |
| `specs/equipment-recommendation` | Full product capability |
| `.specify/memory/constitution.md` | Immutable process principles |
| `docs/testing/` | Verification guides (not behaviour SoT) |

Do **not** duplicate FR tables in foundation docs.

---

## Existing research assets

Prior industry research (domain knowledge base; may live outside this application module):

- `Heavy_Machinery_Rental_Research_Synthesis.md` — full industry model, pain points, case elaborations  
- `Heavy_Machinery_Rental_and_Ownership_Case_Studies.md` — detailed case studies (United Rentals, etc.)

Treat these as **authoritative industry context** when present. Product behaviour is governed by capability specs under `openspec/specs/`.

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-10 | Migrated from `specification/00-overview.md` + `SPEC-project.md` into OpenSpec project context |

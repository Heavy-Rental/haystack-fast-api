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

**Product expression in this repository:** `haystack-fast-api` is a **FastAPI** service that exposes **Haystack** pipelines for **agentic equipment recommendation**, with **ML-assisted pricing** (`predict_price()` / agent tool `predict_asset_price`) for a rental portal / intake experience. The service ranks suitable, available equipment against structured needs and returns honest rationales—not opaque black-box matches.

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

**As-built public routes:** Call 1 `POST .../submitprojectspecification` (lean FR-IX-023 + S2a idempotency/correlation + optional **S3** Coordinator gate behind `INDEXING_VIA_AGENT_GATE`, default off). **Call 2 recommend:** `POST .../project-knowledge/getassetrecommendations` (quote / `items[]` via session + `RecommendationService` MVP). **Call 3 chatbot Q&A:** `POST .../project-knowledge/query` (`answer` + hits). **Portal:** React `project-spec` → Call 1 → Call 2 quote → React. Mapping: `Feasibility_Study_Spring/portal-to-haystack-mapping.md`.

**As-built DocumentStore (S5-I0 + S5-I1):** `INDEXING_DOCUMENT_STORE` + `build_document_store()` / `create_session_document_store()` (`memory` default = fresh InMemory per ingest \| `pgvector` = shared table). Call 1 wires factory into writer + session registry. Retrieval tools filter `user_id` + `ingest_id`. Optional `INDEXING_CHUNK_TTL_SECONDS` + delete helpers. Dual-mode tests: default CI memory; optional `@pytest.mark.pgvector` (FR-IX-027/028).

**Target (later):** I2 production default `pgvector`; production default `RECOMMEND_VIA_AGENT_GRAPH`; align config sync table names with haystack ORM; S8.2 T4 + **S8.3** live Neo4j tools; Naive/hybrid RAG over manuals; async ML training. Phase 7 **S7.0–S7.7 as-built**. **S4 as-built.** **S8.1 T3 as-built (config):** `neo4j-populate`. Normative detail lives in capability specs—not here.

---

## Product identity (as-built service)

| Aspect | State |
|--------|--------|
| Packaging | **uv** project (`pyproject.toml` + `uv.lock`), Python **≥ 3.12** |
| Runtime entry | `app.main:app` (Uvicorn), port **8000** |
| Public API (baseline) | `GET /health`; Call 1 ingest; Call 2 `.../getassetrecommendations` (recommend); Call 3 `.../project-knowledge/query` (Q&A) |
| Persistence (runtime) | PostgreSQL on host **`db`**; SQLAlchemy **sync** + **psycopg** |
| Auth | None (deferred) |
| Pipelines | Haystack under `app/pipelines/` (indexing, kg, recommend components) |
| Agents | LangGraph under `app/agents/`: Stage-1 Q&A + **S3** indexing gate (`indexing_gate.py`); prompts OpenSPDD-first |

Environment, packaging, database host defaults, layering rules, and runbooks: [`specs/project-setup/`](./specs/project-setup/).

---

## Primary stakeholders

| Role | Interest in this product |
|------|---------------------------|
| **Customer / portal / intake UI** | Submit project-spec via React → Spring; today: ingest + Q&A saga; later ranked equipment + prices |
| **Recommendation pipeline / implementers** | Orchestrate filter → availability → price → rank under Haystack 2.0 contracts |
| **Pricing team** | Own `predict_price()` and model training; recommendation **calls** pricing |
| **Ops / data scientist** (target) | Trigger or schedule ML training; poll job status |
| **Spring REST API / portal** (adjacent) | Owns `POST /api/recommendations/project-spec`; calls haystack Call 1 then Call 2; booking **write** path is not owned here |
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

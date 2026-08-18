# Agent & engineer guide — haystack-fast-api SDD

This folder is the **SDD source of truth**. Standards:

| Standard | Role |
|----------|------|
| **OpenSpec** | Capability behaviour in `specs/<cap>/spec.md` |
| **GitHub Spec-kit** | Constitution (`.specify/memory/constitution.md`), user stories, contracts, tasks, converge |
| **OpenSPDD** | REASONS Canvas in `design.md`; structured prompts; **fix prompt/spec first, then code** |

**Start here**, then follow a path. Do not treat all capabilities as equally “live.”

**Call 1 → Call 2 process (full steps, planes, checklist):**  
[`specs/portal-dual-hop/spec.md`](./specs/portal-dual-hop/spec.md) (FR-PDH-001…011).

**Multi-agent architecture (readable guide under docs/):**  
[`../docs/multi-agent-architecture.md`](../docs/multi-agent-architecture.md).

---

## Runtime flow (as-built)

```text
React web portal
  POST /api/recommendations/project-spec   ← user submits project specs (Spring public API)
       │
       ▼
Spring Boot (RestClient / WebClient saga)
  │  optional: Idempotency-Key, X-Correlation-Id, traceparent (S2a) on Call 1
  │
  ├─ Call 1 ──────────────────────────────────────────────────────────
  │  POST /internal/v1/recommendations/submitprojectspecification
  │    user_id (required) + project_text | file
  │    correlation middleware → log + echo X-Correlation-Id
  │    if Idempotency-Key: process-local store hit → same ingest_id
  │
  │  ┌─────────────────────────────────────────────────────────────┐
  │  │ INDEXING  (specs/indexing)                                  │
  │  │  Default: IndexingIngestService (direct)                    │
  │  │  Optional S3 gate: INDEXING_VIA_AGENT_GATE=true             │
  │  │    → START→index_gate→END (forced non-LLM Coordinator [4])  │
  │  │    → tool run_indexing_from_request → same service          │
  │  │  FileTypeRouter → convert → dual clean/split                │
  │  │       text_splitter ──┐                                     │
  │  │       csv_splitter  ──┴→ final_doc_joiner                   │
  │  │                            │                                │
  │  │              ┌─────────────┴─────────────┐                  │
  │  │              ▼                           ▼                  │
  │  │       doc_embedder → writer      KNOWLEDGE GRAPH            │
  │  │       InMemoryDocumentStore      (specs/knowledge-graph)    │
  │  │                                  Part A: mandatory KG after │
  │  │                                  joiner + JSON artifact     │
  │  │                                  Part B: session registry   │
  │  │                                  for multi-agent tools      │
  │  └─────────────────────────────────────────────────────────────┘
  │  ▼
  │  IngestFromProjectSpecResponse (lean public body — FR-IX-023 as-built S1a–S1e)
  │    ingest_id, user_id, user_requirement_summary,
  │    tentative_start/end_date, needs_summary[], expected_budget | null, warnings[]
  │    S2a: Idempotency-Key replay (FR-IX-024); correlation echo (FR-IX-025)
  │    S3: optional agent gate (flag default off); same lean DTO
  │    Spring persists user_id + ingest_id
  │
  └─ Call 2 RECOMMEND (portal project-spec submit second hop) ───────
     POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
       body: user_id + ingest_id + optional query
       SessionRecommendService → RecommendationService
         FLEET_BACKEND=sql: assets table (quote equipment.id = assets.id)
         FLEET_BACKEND=fake (CI): seed catalog
         optional S7.5: RECOMMEND_VIA_AGENT_GRAPH=true
           → run_recommend_graph → same quote DTO (gate refuse → 400)
       → quote envelope: quoteRef, items[].equipment, rates, estimatedTotal
       → Spring maps Call 2 body back to React as primary response
       → S2b as-built (Spring): HaystackRecommenderClient + Resilience4j + saga
         (no re-ingest on Call 2 fail)
       → MUST NOT invent asset_id or rates
       → MUST NOT put tool_traces on this body (S7.6 stays on graph state)

  └─ Call 3 CHATBOT Q&A (optional follow-ups) ───────────────────────
     POST /internal/v1/recommendations/project-knowledge/query
       body: user_id + ingest_id + query (required)
       LangGraph: research → graph → synthesis
       tools: project_vector_search + project_kg_query
       prompts: app/agents/prompts.py (OpenSPDD)

        ─ ─ ─ ─ multi-agent recommend building blocks ─ ─ ─ ─
S7.0 as-built: RecommendAgentState + F-2 partition validation
S7.1 as-built: fleet/needs allowlisted tools + DI factory (fake/SQL)
S4 as-built (app): FLEET_BACKEND=sql → LiveSqlFleetBackend / FleetRepository (D0); fake default
S4 as-built (config): T0–T2 60s postgres-haystack-sync + SYNC_TABLE_ALLOWLIST + METRICS (pack develop)
S7.2 as-built: neo4j_cypher_read (templates) + trigger_neo4j_populate (fake / no-op); K-3 skip
S7.3 as-built: recommend LangGraph DAG (gate → [5] → Delegator → ([6]→[7])×N)
S7.4 as-built: tool-free stub Coordinator synthesis [8]
S7.5 as-built: Call 2 HTTP enrich behind RECOMMEND_VIA_AGENT_GRAPH (default off)
S7.6 as-built: tool_traces role / need_id / duration_ms (not on quote DTO)
S7.7 as-built: A–L recommend prompts (`app/agents/recommend_prompts.py`) + tool DI / Delegator allowlist
S7.8 as-built: Worker [5] live project_vector_search + project_kg_query (session KG-1) then decompose
S8.1 T3 as-built (config): neo4j-populate SQL→Cypher MERGE; fleet labels isolated
S8.2 T4 as-built (config): post-sync POST + admin HTTP :8089; scoped delete; KG-1 preserved
S8.3 as-built: live neo4j_cypher_read + trigger_neo4j_populate (NEO4J_BACKEND=bolt; default fake)
KG-2 FR-KG-011 as-built: persist = pack T3/T4; load = app S8.3
```

**Portal mapping (Spring handoff):** `Feasibility_Study_Spring/portal-to-haystack-mapping.md`  
**Call 2 = recommend** (quote/items). **Call 3 = chatbot Q&A**. Technical `documents[]` / `kg_*` stay internal.

---

## Path A — Onboard (always)

| Step | Document | Role |
|------|----------|------|
| **0** | [This file](./AGENTS.md) | Map, conflict rules, workflow |
| **1** | [`project.md`](./project.md) | Vision, identity, as-built vs target |
| **2** | [`specs/domain/spec.md`](./specs/domain/spec.md) | Ubiquitous language & invariants |
| **3** | [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) | Immutable principles |
| **4** | [`specs/project-setup/spec.md`](./specs/project-setup/spec.md) | Stack, env, layering (behaviour); **default pytest isolation** |
| **5** | [`specs/project-setup/design.md`](./specs/project-setup/design.md) | Layout, uv runbooks, `conftest` isolation table |

**Pytest (as-built):** `uv run pytest` / `uv run pytest tests/ -q` is the full default suite — **no** optional markers or external prereqs. `tests/conftest.py` forces `INDEXING_EMBEDDER=mock`, `INDEXING_EMBEDDING_DIM=384`, `INDEXING_DOCUMENT_STORE=memory`, `RECOMMEND_VIA_AGENT_GRAPH=false`, `FLEET_BACKEND=fake`, `NEED_DECOMPOSER=stub`, `PRICING_SCHEMA=primary_snapshot`, `PROJECT_AGENT_MODE=stub`, `NEO4J_BACKEND=fake`, and a temp `KG_ARTIFACT_DIR`. Query embedders for vector tools must match the session store dimension (see knowledge-graph + indexing specs).

---

## Path B — Live project-spec pipeline ★ primary

| Step | Document | Runtime step |
|------|----------|--------------|
| **6** | [`specs/indexing/spec.md`](./specs/indexing/spec.md) | Live HTTP index dual-branch; **`user_id` required** |
| **7** | [`specs/indexing/contracts/ingest-from-project-spec.md`](./specs/indexing/contracts/ingest-from-project-spec.md) | Request/response field tables |
| **8** | [`specs/knowledge-graph/spec.md`](./specs/knowledge-graph/spec.md) | Mandatory KG + Stage-1 multi-agent |
| **9** | [`.env.example`](../.env.example) | `INDEXING_*` (incl. `INDEXING_DOCUMENT_STORE`, `INDEXING_CHUNK_TTL_SECONDS`), `KG_*`, `PROJECT_AGENT_*` |
| **10** | [`../postman/README.md`](../postman/README.md) | Manual live HTTP |

**Design / prompts:** [`specs/indexing/design.md`](./specs/indexing/design.md) · [`specs/knowledge-graph/design.md`](./specs/knowledge-graph/design.md) · [`../app/agents/prompts.py`](../app/agents/prompts.py)

**Archived tasks:** [`changes/archive/`](./changes/archive/)

---

## Path C — Deferred recommend (service / reattach)

| Step | Document | Status |
|------|----------|--------|
| **11** | [`specs/recommendation-intake/spec.md`](./specs/recommendation-intake/spec.md) | Deferred `results_by_need` envelope |
| **12** | [`specs/recommendation-pipeline/spec.md`](./specs/recommendation-pipeline/spec.md) | FR-010.1–8 **service-level** |
| **13** | [`specs/dynamic-pricing/spec.md`](./specs/dynamic-pricing/spec.md) | `predict_price` for recommend; S6 tool `predict_asset_price` (US-5) |
| **13.5** | [`specs/domain-seed-data/spec.md`](./specs/domain-seed-data/spec.md) | Seed-data richness required for §13 to be verifiable — executed on the Spring Boot side, not this repo |

---

## Path D — Parent product + verification

| Step | Document | Role |
|------|----------|------|
| **14** | [`specs/equipment-recommendation/spec.md`](./specs/equipment-recommendation/spec.md) | Full product SDD |
| **15** | [`../docs/testing/recommendation-pipeline-testing-guide.md`](../docs/testing/recommendation-pipeline-testing-guide.md) | Pytest / curl (live = ingest + `user_id`) |
| **16** | [`../docs/testing/recommendation-postman-testing-guide.md`](../docs/testing/recommendation-postman-testing-guide.md) | **Deferred** recommend Postman |

---

## Conflict rules

| Concern | Wins |
|---------|------|
| Live `POST .../submitprojectspecification` fields & index graph | **`specs/indexing/`** |
| Mandatory KG after joiner / multi-agent Stage 1 | **`specs/knowledge-graph/`** |
| FR-010 components / seed fleet | **`specs/recommendation-pipeline/`** (service) |
| Deferred recommend JSON envelope | **`specs/recommendation-intake/`** (deferred) |

---

## How agents should work (Spec-kit + OpenSPDD + OpenSpec)

1. **Read** constitution + Path B specs for live work (or Path C if reattach).
2. **Propose** changes under `openspec/changes/<name>/` with:
   - `proposal.md` (why/scope)
   - `specs/<cap>/spec.md` deltas (`## ADDED|MODIFIED|REMOVED Requirements`)
   - `design.md` as **REASONS Canvas** (Requirements, Entities, Approach, Structure, Operations, Norms, Safeguards)
   - `tasks.md` checkbox list
3. **Structured prompts:** if agents change, edit `app/agents/prompts.py` (or `openspec/spdd/prompts/`) **before** or **with** code — never only in chat.
4. **Implement** tasks; keep specs/prompts/code in the same change set.
5. **Converge:** verify tests + scenarios; on mismatch, fix spec/prompt first.
6. **Archive** completed changes into `changes/archive/` and merge requirements into `specs/`.

### Suggested first read (new engineer)

1. This file (flow)  
2. `project.md`  
3. `specs/indexing/spec.md`  
4. `specs/knowledge-graph/spec.md`  
5. `.env.example` + `postman/README`  

---

## Legacy path

The old flat `specification/` tree was **removed on 2026-08-13**. Do not recreate it. Capability behaviour lives under `specs/`. Historical filename map: [`TRACEABILITY.md`](./TRACEABILITY.md). Spring JPA schema read-copy: [`specs/spring-entity-repository/spec.md`](./specs/spring-entity-repository/spec.md).

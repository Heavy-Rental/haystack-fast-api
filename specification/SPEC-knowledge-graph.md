# Specification: Knowledge Graph Assembly & Multi-Agent Orchestration

| Field | Value |
|-------|--------|
| **Document type** | Feature / Architecture SDD (Spec-kit) |
| **Status** | **Stage 1 as-built** — mandatory post-join KG assembly (HR-76) + project DocumentStore/KG-1 multi-agent Q&A; **Stage 2** (KG-2 / equipment) pending |
| **Feature ids** | `knowledge-graph` (HR-76 assembly) · `kg-multi-agent-orchestration` (agents) |
| **Tracking** | **HR-76** (assembly) |
| **Application** | `haystack-fast-api` |
| **Spec location** | `specification/SPEC-knowledge-graph.md` |
| **Reading map** | [`README.md`](./README.md) Path B step 6 |
| **Previous** | [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) |
| **Tasks** | [`tasks-knowledge-graph.md`](./tasks-knowledge-graph.md) (assembly) · [`tasks-kg-multi-agent-stage1.md`](./tasks-kg-multi-agent-stage1.md) (Stage 1 agents) |
| **Parent** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) §11.1 / hybrid architecture |
| **Related** | [`00-overview.md`](./00-overview.md), [`01-domain.md`](./01-domain.md), [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) |
| **Methodology** | OpenSPDD (Structured Prompt-Driven Development) + GitHub Spec Kit |
| **Haystack reference** | *Building Natural Language and LLM Pipelines* — Ch. 4 (Indexing / Naive RAG), Ch. 5 (Custom components, Ragas KnowledgeGraph) |
| **Depends on** | Haystack 2.0, Ragas KnowledgeGraph, LangGraph, InMemoryDocumentStore, optional Neo4j (later) |
| **Env** | [`.env.example`](../.env.example) — `KG_*`, `PROJECT_AGENT_*`, `INDEXING_*` |
| **Tests** | §10 Testing — `tests/test_knowledge_graph.py`, `tests/test_project_knowledge_*.py` |
| **Postman (live HTTP)** | [`../postman/README.md`](../postman/README.md) — folder **04 Stage-1 multi-agent Q&A** |
| **Audience** | Engineers and coding agents implementing project-spec ingest, knowledge graphs, and multi-agent Q&A |

> **Spec Kit alignment:** This document is the **Specify** artifact (What & Why) for both KG assembly and multi-agent access.  
> When reality diverges, **fix the prompt / spec first** — then update the code (OpenSPDD).

---

## Conflict rule

| Concern | Owner |
|---------|--------|
| Live HTTP field list for ingest (including `kg_*` on response) | Indexing SPEC + **this SPEC Part A** |
| When KG runs, transforms location, artifact path | **This SPEC Part A** |
| Multi-agent tools, session registry, Q&A route | **This SPEC Part B** |
| Parent §11 product vision | Parent; as-built = this child |

---

## 1. Purpose (What & Why)

### 1.1 Problem

The recommendation path can accept free-text or a project file, but agents need **structured, multi-hop knowledge** about:

1. The **project specification** the user uploaded (requirements, constraints, site conditions, capacities, timeline).
2. (Target) The **equipment stockpile** available for rental (machines, capacities, availability, attachments, rates).

Without both layers, the agent cannot reliably answer questions that require:

- Semantic similarity over project text **and**
- Precise entity/relationship reasoning (“project needs ≥20 t excavator on soft clay within 8 weeks” ↔ “which machines satisfy this?”).

### 1.2 Goal

Define a clear, testable architecture that:

1. Uses a **Haystack indexing-style pipeline** to produce:
   - An `InMemoryDocumentStore` (or equivalent) of project-spec chunks.
   - A **Knowledge Graph** (Ragas-style) of that project specification (**KG-1**).
2. Separately maintains an equipment-side vector store + **Knowledge Graph** (**KG-2**) derived from Postgres (or equivalent) — **Stage 2**.
3. Exposes knowledge sources as **tools**.
4. Uses a **LangGraph multi-agent system** to orchestrate research over those sources and produce grounded answers / rationales.

### 1.3 Non-goals

- Replacing the existing 6-day MVP recommendation pipeline (SQL filter → availability → `predict_price` → rank).
- Owning booking or payment.
- Mandatory Neo4j in Stage 1 (JSON / in-memory is acceptable).
- Training the pricing model.

---

## 2. Methodology Notes (Spec Kit + OpenSPDD)

| Source | Principle applied here |
|--------|------------------------|
| **GitHub Spec Kit** | Spec first (this document). Plan → Tasks → Implement → Converge. |
| **OpenSPDD** | Structured prompts for agents; when behaviour is wrong, edit prompts/SPEC first. |
| **Haystack Ch. 3–5** | Pipeline-first tool layer; LangGraph for stateful multi-agent orchestration; Ragas KnowledgeGraph as a first-class component. |

---

## 3. Core Concepts & Decisions

### 3.1 Indexing Pipeline vs Knowledge Graph assembly

| Concept | Role | Order |
|---------|------|-------|
| **Indexing Pipeline** (Ch. 4) | Convert → clean → split → embed → write to DocumentStore | **First** (shared head) |
| **Knowledge Graph assembly** (Ch. 5) | After shared cleaner/splitter (post-`final_doc_joiner` chunks): extract DOCUMENT nodes + optional Ragas transforms | Sibling path; **not** a consumer of a finished vector write |

**Decision:** Share converters/cleaner/splitter. Branch after join:

- Branch A → embedder → `DocumentWriter` → `InMemoryDocumentStore`.
- Branch B → bridge → `KnowledgeGraphGenerator` → KG-1 (in-memory session + JSON artifact).

Preferred KG input: documents that *would* be written (post-join chunks), not a re-read from the store.

### 3.2 Two Knowledge Graphs

| Graph | Content | Source | Lifetime | Storage |
|-------|---------|--------|----------|---------|
| **KG-1 – Project Specification** | Entities & relations (or document nodes) from the user-uploaded project file | User upload → converters → KG generator | Session / request scoped | **In-memory** for agents + **JSON artifact** on every successful ingest (as-built) |
| **KG-2 – Equipment Stockpile** | Machines, models, capacities, availability, attachments, rates | Postgres → extractor → KG generator | Shared, longer-lived | **Persistent** (JSON minimum; Neo4j optional) — Stage 2 |

**Decision:** Different *file types* do **not** require different KG *variants*. Only the pipeline head (converters) changes; `KnowledgeGraphGenerator` stays shared.

### 3.3 InMemoryDocumentStore vs Knowledge Graph

| | InMemoryDocumentStore | Knowledge Graph (Ragas) |
|--|-----------------------|-------------------------|
| **Stores** | Text chunks + embeddings | Entities + relationships (or document nodes) |
| **Best for** | “Which passages are most similar?” | “How are these things connected?” / multi-hop |
| **Built from** | Cleaned/split Documents → embed → write | Same Documents → generator (+ optional transforms) |
| **Relationship** | Siblings. Prefer branching after splitter rather than “DocumentStore feeds KG”. | |

A multi-agent system SHALL be able to call tools against **both**.

### 3.4 Persistence policy (as-built aligned)

- **KG-1 (Project):** Online agents use the **in-memory** graph held in the project knowledge session. Every successful ingest **also** saves JSON under `{KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json` (hard-fail if save fails). Optional hydrate-from-artifact after process restart (vector store remains empty until re-ingest).
- **KG-2 (Equipment):** Must be persisted (Stage 2). JSON minimum; Neo4j optional.
- **Neo4j temporary graphs:** Not required for KG-1 Stage 1.

### 3.5 Haystack vs LangGraph responsibilities

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **Data / knowledge pipelines** | Haystack | Indexing, cleaning, splitting, embedding, KG generation, vector retrieval, tool packaging |
| **Agent orchestration** | LangGraph | Multi-step planning, tool selection, state, synthesis |

**Decision:** Haystack = reliable tool layer. LangGraph = complex agent steps.

---

## 4. Part A — KG assembly after indexing (HR-76 as-built)

### 4.1 Placement (after indexing step 5)

```text
[5 indexing] … → final_doc_joiner
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
 doc_embedder → writer         [6 this SPEC Part A — mandatory]
 InMemoryDocumentStore         bridge → KnowledgeGraphGenerator
                                        ├─ DOCUMENT nodes
                                        └─ full Ragas transforms
                                           only if KG_APPLY_TRANSFORMS
                                   → saver
                                   {KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json
                                   → register ProjectKnowledgeSession (Part B)
```

### 4.2 Functional requirements (assembly)

| ID | Requirement |
|----|-------------|
| **FR-KG-001** | `user_id` required on ingest (indexing SPEC). |
| **FR-KG-002** | KG chunks MUST carry `user_id` + `ingest_id` meta. |
| **FR-KG-003** | After successful index write, **MUST** build KG from **post-join** chunks and save under user-scoped path. |
| **FR-KG-004** | Full Ragas transforms **only** in `KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true`. |
| **FR-KG-005** | Default transforms **off** (document nodes). |
| **FR-KG-006** | KG failure **MUST** fail the ingest request (hard-fail; no soft-fail path). |
| **FR-KG-007** | Response: `kg_built`, `kg_node_count`, `kg_relationship_count`, `kg_artifact_path`, `kg_transform_applied`. On success `kg_built` is always `true`. |
| **FR-KG-008** | Sanitize `user_id` for filesystem paths. |

### 4.3 Config (assembly)

| Env | Default | Notes |
|-----|---------|--------|
| `KG_ARTIFACT_DIR` | `artifacts/kg` | User-scoped subdirs |
| `KG_APPLY_TRANSFORMS` | `false` | Document nodes only unless true |

`KG_ENABLED` / `KG_STRICT` are **removed** — creation is always on and hard-fail is always on.

### 4.4 Modules (assembly)

| Path | Role |
|------|------|
| `app/pipelines/kg/bridge.py` | Haystack → LangChain |
| `app/pipelines/kg/generator.py` | Nodes + optional full Ragas transforms |
| `app/pipelines/kg/saver.py` | User-scoped JSON |
| `app/pipelines/kg/runner.py` | `run_knowledge_graph` (returns in-memory graph + artifact path) |
| `app/services/indexing.py` | Always runs KG after index; hard-fails on error; registers session |

### 4.5 Acceptance criteria (assembly)

1. Successful ingest → `kg_built=true`, artifact under `{user_id}/`, `kg_transform_applied=false` when transforms off, nodes ≥ 1.
2. KG build/save failure → request fails (not 200 with warnings only).
3. Two users → two paths.
4. Missing `user_id` → 400 (indexing).

---

## 5. Part B — Multi-agent orchestration

### 5.1 Functional requirements (orchestration)

| ID | Requirement | Legacy id |
|----|-------------|-----------|
| **FR-KG-010** | Project-spec indexing + KG assembly per Part A; session exposes both DocumentStore and KG-1. | was FR-KG-01 |
| **FR-KG-011** | Equipment stockpile knowledge (KG-2) from Postgres (or approved source); persisted independently of user sessions. | was FR-KG-02 — **Stage 2** |
| **FR-KG-012** | No file-type-specific KG variants; only converters/extractors at the head differ. | was FR-KG-03 |
| **FR-KG-013** | LangGraph multi-agent system can call vector retrieval tool(s) and KG query tool(s) and synthesize a grounded answer. | was FR-KG-04 |
| **FR-KG-014** | Haystack retrieval / KG query pipelines SHALL be exposable as tools (name + natural-language description) for LangGraph. | was FR-KG-05 |

### 5.2 Architecture sketch

```text
┌─────────────────────────────────────────────────────────────┐
│  Offline / on-upload                                        │
│                                                             │
│  Project file ──► Haystack indexing head                    │
│                      │                                      │
│                      ├──► Embed + write ──► InMemoryDocStore│
│                      │         (project chunks)             │
│                      └──► KnowledgeGraphGenerator ──► KG-1  │
│                               (in-memory + JSON artifact)   │
│                                                             │
│  Postgres equipment ──► Extractor ──► Embed + write         │  Stage 2
│                              │         (equipment vectors)  │
│                              └──► KnowledgeGraphGenerator   │
│                                       ──► KG-2 (persisted)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Online Q&A (Stage 1 as-built)                              │
│                                                             │
│  User query + user_id + ingest_id                           │
│       │                                                     │
│       ▼                                                     │
│  ProjectKnowledgeSessionRegistry                            │
│       │                                                     │
│       ▼                                                     │
│  LangGraph (fixed sequential)                               │
│       │                                                     │
│       ├── Research Agent ──► project_vector_search          │
│       │                      (InMemoryDocumentStore)        │
│       │                                                     │
│       ├── Graph Agent ────► project_kg_query                │
│       │                      (KG-1)                         │
│       │                                                     │
│       └── Synthesis Agent ─► grounded answer + traces       │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Stage 1 as-built (project sources only)

**Scope:** Agents may only use (1) project `InMemoryDocumentStore` and (2) project **KG-1**. No equipment KG-2.

| Topic | Decision |
|-------|----------|
| Topology | Fixed sequential: `research_agent` → `graph_agent` → `synthesis_agent` |
| DocumentStore | Per-ingest `InMemoryDocumentStore` in session registry |
| KG-1 online | In-memory on session + JSON artifact from Part A |
| Agent mode | `PROJECT_AGENT_MODE=stub` (default, CI-safe) \| `llm` |
| HTTP | `POST /api/v1/recommendations/project-knowledge/query` after `/from-project-spec` |

#### 5.3.1 Session registry

After successful ingest + KG build, register `ProjectKnowledgeSession` keyed by `(user_id, ingest_id)` holding:

- document store handle  
- in-memory knowledge graph  
- `kg_artifact_path`  
- meta (chunk counts, filenames, …)

Discard via registry `delete` without affecting other sessions (and later KG-2).

#### 5.3.2 Tools

| Tool name | Backing |
|-----------|---------|
| `project_vector_search` | Query embedder + `InMemoryEmbeddingRetriever` over session store |
| `project_kg_query` | Substring / property match over KG-1 nodes (+ optional 1-hop neighbors) |

#### 5.3.3 Modules (orchestration)

| Path | Role |
|------|------|
| `app/services/project_knowledge_session.py` | Session + registry + artifact load |
| `app/pipelines/indexing/retrieval.py` | Vector retrieval pipeline |
| `app/pipelines/kg/query.py` | KG-1 query helper |
| `app/agents/` | State, prompts, tools, nodes, LangGraph compile |
| `app/services/project_knowledge_qa.py` | Service facade |
| `app/schemas/project_knowledge.py` | Request/response |
| `app/api/recommendations.py` | Q&A route |

#### 5.3.4 Config (orchestration)

| Env | Default | Notes |
|-----|---------|--------|
| `PROJECT_AGENT_MODE` | `stub` | `stub` \| `llm` |
| `PROJECT_AGENT_TOP_K` | `5` | Default retrieval depth |
| `INDEXING_EMBEDDER` / dim | mock / 384 | Query embedder must match index |

#### 5.3.5 Tasks

[`tasks-kg-multi-agent-stage1.md`](./tasks-kg-multi-agent-stage1.md)

### 5.4 Stage 2+ backlog

1. **KG-2** equipment stockpile graph + refresh from Postgres.  
2. Equipment vector store / manuals retrieval tool.  
3. Supervisor / dynamic routing (research, graph, pricing, availability).  
4. Reattach full recommend pipeline tools (`check_availability`, `recommend_prices`, …).  
5. Neo4j optional backend.  
6. Persist project DocumentStore snapshots for true dual-source resume after restart.

### 5.5 Acceptance criteria (orchestration)

- [x] Uploading a project specification produces both a usable `InMemoryDocumentStore` of chunks **and** a KG-1 with identifiable entities/relations. *(Part A + session registry)*
- [x] A LangGraph multi-agent graph can invoke a vector-search tool and a KG-query tool in the same run. *(Stage 1 sequential agents)*
- [x] Synthesis output demonstrably uses information from **both** sources (tool-call traces / `sources_used` / rationale). *(stub synthesis)*
- [ ] KG-2 can be loaded from persistent storage without re-querying Postgres on every request. *(Stage 2)*
- [x] KG-1 can be discarded at end of session without affecting KG-2. *(registry delete; KG-2 not present yet)*
- [x] Changing only the converter head allows the same KG generator to process PDF vs text vs HTML project specs. *(as-built indexing)*

---

## 6. Implementation Guidance

### 6.1 Preferred pipeline shape (project side)

```text
Converters (FileTypeRouter / specific converters)
  → DocumentCleaner
  → DocumentSplitter
       ├── DocumentEmbedder → DocumentWriter → InMemoryDocumentStore
       └── DocumentToLangChainConverter → KnowledgeGraphGenerator → KG-1
              → KnowledgeGraphSaver (JSON)
              → ProjectKnowledgeSessionRegistry
```

### 6.2 Multi-agent pattern

- **Research Agent** — bound to `project_vector_search` only.  
- **Graph Agent** — bound to `project_kg_query` only.  
- **Synthesis Agent** — no tools; structured answer (Vector + Graph evidence).  
- Stage 1: fixed sequential edges. Stage 2+: supervisor / dynamic routing.

### 6.3 Open questions (Stage 2 / clarify)

1. Exact Ragas transform set and entity schema for project vs equipment.  
2. Whether equipment vector store is required with KG-2 or only the graph.  
3. JSON vs Neo4j timeline for KG-2.  
4. Whether project DocumentStore should be snapshotted for full resume.

---

## 7. Alignment with Parent SPEC

This document **extends** the target (post–6-day) sections of  
`SPEC-agentic-equipment-recommendation-and-pricing.md` regarding:

- Offline / batch KnowledgeGraphGenerator (Ragas).  
- LangGraph as the preferred stateful orchestrator.  
- Project-spec ingest using Chapter 4-style routing and converters.

It does **not** change the normative 6-day MVP behaviour (SQL candidates, availability, `predict_price()`, one `RecommendationItem` per unit-need).

---

## 8. Next SPDD / Spec Kit Steps

| Phase | Suggested action |
|-------|------------------|
| **Converge (Stage 1)** | Keep Part A + Stage 1 ACs green; treat this SPEC as normative. |
| **Clarify / Plan (Stage 2)** | Resolve §6.3; entity schema for KG-2; Postgres extractor design. |
| **Tasks / Implement** | Equipment extractor + KG-2, equipment tools, supervisor optional. |
| **Converge (Stage 2)** | Dual-graph multi-agent ACs. |

---

## 9. References

- Parent feature SPEC: `SPEC-agentic-equipment-recommendation-and-pricing.md`
- Indexing (live HTTP): `SPEC-indexing-file-type-router.md`
- Tasks: `tasks-knowledge-graph.md`, `tasks-kg-multi-agent-stage1.md`
- Live Postman ops: [`../postman/README.md`](../postman/README.md)
- Broader pipeline testing guide (ingest + deferred recommend): [`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md)
- GitHub Spec Kit: https://github.com/github/spec-kit
- Haystack book: Chapters 4–5

---

## 10. Testing

Normative **how to verify** Part A (KG assembly) and Part B (Stage-1 multi-agent).  
Operational Postman import/fixture detail: [`../postman/README.md`](../postman/README.md).

### 10.1 Prerequisites

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm: `GET http://localhost:8000/health` and OpenAPI at `/docs`.

**CI-safe defaults** (no LLM / embedder API keys required):

| Env | Default | Purpose |
|-----|---------|---------|
| `INDEXING_EMBEDDER` | `mock` | Deterministic embeddings for store + retrieval |
| `KG_APPLY_TRANSFORMS` | `false` | Document nodes only (full Ragas transforms optional) |
| `PROJECT_AGENT_MODE` | `stub` | Deterministic synthesis from tool hits |
| `PROJECT_AGENT_TOP_K` | `5` | Retrieval depth |
| `KG_ARTIFACT_DIR` | `artifacts/kg` | User-scoped JSON snapshots |

Working directory for all commands: **`haystack-fast-api/`** (app root).

### 10.2 Automated tests (pytest)

```bash
cd haystack-fast-api

# Part A — mandatory KG after final_doc_joiner (hard-fail, artifacts, multi-user paths)
uv run pytest tests/test_knowledge_graph.py -v

# Part B — session registry, tools, LangGraph agents, HTTP Q&A
uv run pytest \
  tests/test_project_knowledge_session.py \
  tests/test_project_vector_tool.py \
  tests/test_project_kg_query_tool.py \
  tests/test_project_knowledge_agents.py \
  tests/test_project_knowledge_api.py -v

# Full suite (includes indexing + recommend service tests)
uv run pytest tests/ -v
```

| Test file | Proves |
|-----------|--------|
| `tests/test_knowledge_graph.py` | Bridge/generator/saver; ingest always builds KG; hard-fail on KG error; per-user artifact paths |
| `tests/test_project_knowledge_session.py` | Registry put/get/delete; load KG from JSON artifact |
| `tests/test_project_vector_tool.py` | Dense retrieval over ingest-scoped `InMemoryDocumentStore` |
| `tests/test_project_kg_query_tool.py` | KG-1 substring / document-node query |
| `tests/test_project_knowledge_agents.py` | One LangGraph run invokes **both** tools; synthesis cites Vector + Graph |
| `tests/test_project_knowledge_api.py` | HTTP ingest → Q&A 200 dual-source; missing session **404** |

**Expect:** all listed tests pass with `PROJECT_AGENT_MODE=stub` and mock embedder.

### 10.3 Manual HTTP — curl

Use distinctive project text so vector + KG hits are obvious under mock embeddings.

**1) Ingest (Part A)**

```bash
curl -s -X POST http://localhost:8000/api/v1/recommendations/from-project-spec \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_demo",
    "user_name": "Demo User",
    "project_text": "Site preparation for foundation work. Requires a 20-ton excavator operating on soft clay soil. Project timeline is 8 weeks from mobilisation."
  }'
```

**Expect (ingest):** HTTP 200; `ingest_id` starts with `ing_`; `kg_built=true`; `kg_node_count ≥ 1`; `kg_artifact_path` non-empty; `documents_written ≥ 1`; `documents[0].has_embedding=true`; no `recommendation_id` / `results_by_need`.

**2) Multi-agent Q&A (Part B)** — same process; paste `ingest_id` from step 1:

```bash
curl -s -X POST http://localhost:8000/api/v1/recommendations/project-knowledge/query \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_demo",
    "ingest_id": "ing_REPLACE_ME",
    "query": "What excavator capacity and soil conditions are required?",
    "top_k": 5
  }'
```

**Expect (Q&A):** HTTP 200; body shape:

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_…",
  "query": "…",
  "answer": "## Answer\n…\n## Evidence\n- Vector: …\n- Graph: …\n## Gaps\n…",
  "sources_used": ["project_vector_search", "project_kg_query"],
  "research_hits": [],
  "graph_hits": [],
  "tool_traces": [
    { "agent": "research", "tool": "project_vector_search", "query": "…", "hit_count": 1 },
    { "agent": "graph", "tool": "project_kg_query", "query": "…", "hit_count": 1 }
  ]
}
```

**Negatives**

| Case | Call | Expect |
|------|------|--------|
| Missing session | Q&A with unknown `ingest_id` | **404** `{"error":"not_found",…}` |
| Empty query | Q&A with `"query": ""` | **422** or **400** |
| Missing `user_id` on ingest | Ingest without `user_id` | **400** |
| KG failure | (simulated in pytest) | Ingest **400** (hard-fail) |

### 10.4 Manual HTTP — Postman

1. Import:
   - `postman/Indexing-Pipeline.postman_collection.json`
   - `postman/Indexing-Pipeline-Local.postman_environment.json`
2. Select environment **Indexing Pipeline Local**.
3. Start uvicorn (same process for the multi-agent pair).
4. Folder **04 Stage-1 multi-agent Q&A**:

| # | Request | Expect |
|---|---------|--------|
| **15** | Ingest project-spec for multi-agent | 200; Tests save `ingestId` / `userId` |
| **16** | Project-knowledge query (multi-agent) | 200; both tools in `sources_used` + `tool_traces` |
| 17 | Missing session | **404** |
| 18 | Empty query | **422** or **400** |

**Run 15 then 16 without restarting the server.** Sessions are process-local; a restart invalidates in-memory DocumentStore + session even if `ingestId` remains in the environment.

Fixture/import detail: [`../postman/README.md`](../postman/README.md).

### 10.5 Acceptance mapping (test → AC)

| Acceptance criterion | Proof |
|----------------------|--------|
| Ingest produces DocumentStore chunks **and** KG-1 | `test_knowledge_graph.py`; curl/Postman **15**; ingest response `kg_*` + `documents_written` |
| LangGraph invokes vector tool **and** KG tool in one run | `test_project_knowledge_agents.py`; Postman **16**; `sources_used` / `tool_traces` |
| Synthesis uses both sources | Stub answer contains Vector + Graph evidence; agent + API tests |
| KG-1 discard without affecting other sessions | `test_project_knowledge_session.py` registry delete |
| Converter-only file-type variance | Indexing suite + `test_indexing_*` (shared generator) |
| KG-2 persistence without re-query Postgres | **Stage 2** — not tested yet |

### 10.6 Known limitations (when testing)

| Limitation | Implication |
|------------|-------------|
| Process-local sessions | Ingest and Q&A must hit the **same** uvicorn process |
| Vector store not snapshotted | After restart, optional `kg_artifact_path` reloads KG-1 only; dual-source needs re-ingest |
| `PROJECT_AGENT_MODE=stub` | Synthesis is template-based from tool hits (stable CI); use `llm` only with `LLM_*` configured |
| Mock embeddings | Prefer distinctive fixture phrases (e.g. “20-ton excavator”, “soft clay”); do not judge ranking quality |
| No KG-2 / fleet tools | Answers must not claim live equipment inventory or availability |

---

## 11. Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-07 | HR-76 as-built (optional KG) |
| **0.1.1** | 2026-08-07 | Sequential map; expanded AC/modules |
| **0.2.0** | 2026-08-07 | Mandatory KG + hard-fail; remove `KG_ENABLED` / `KG_STRICT` |
| **0.3.0** | 2026-08-08 | Multi-agent architecture SPEC drafted (separate file) |
| **0.4.0** | 2026-08-08 | Stage 1 multi-agent as-built (session, tools, LangGraph, Q&A route) |
| **0.5.0** | 2026-08-08 | **Merge** HR-76 SPEC + multi-agent SPEC into this single document |
| **0.5.1** | 2026-08-08 | Remove retired multi-agent filename redirect stub |
| **0.5.2** | 2026-08-08 | §10 Testing (pytest, curl, Postman, AC map) |

---

**Reading order:** [← Indexing](./SPEC-indexing-file-type-router.md) · [Map](./README.md) · [Next: .env.example →](../.env.example) · [Postman](../postman/README.md) · **Testing: §10 above**

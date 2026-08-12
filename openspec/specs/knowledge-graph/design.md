# Knowledge Graph Design (OpenSPDD REASONS Canvas)

| Field | Value |
|-------|--------|
| **Capability** | `knowledge-graph` |
| **Status** | Stage 1 as-built; Stage 2 pending |
| **Behaviour** | [`spec.md`](./spec.md) |
| **Contract** | [`contracts/project-knowledge-query.md`](./contracts/project-knowledge-query.md) |
| **Structured prompts** | [`../../../app/agents/prompts.py`](../../../app/agents/prompts.py) · index [`../../spdd/prompts/project-knowledge-agents.md`](../../spdd/prompts/project-knowledge-agents.md) |

---

## R — Requirements

See [`spec.md`](./spec.md) Purpose, User Scenarios, and Requirements (FR-KG-001…008, FR-KG-010…014).

**Outcomes:**

1. After shared indexing join, always build **KG-1** from post-join chunks, hard-fail on error, save user-scoped JSON.
2. Register a process-local **ProjectKnowledgeSession** holding DocumentStore + KG-1 for multi-agent tools.
3. Stage-1 LangGraph sequential agents answer project questions with dual-source grounding (vector + graph).
4. Stage-2 equipment KG-2 and supervisor routing remain backlog.

---

## E — Entities

| Concept | Role |
|---------|------|
| **KG-1 – Project Specification** | Entities/relations or document nodes from the user-uploaded project file. Session/request scoped. In-memory for agents + JSON artifact on every successful ingest. |
| **KG-2 – Equipment Stockpile** | Machines, models, capacities, availability, attachments, rates from Postgres (or equivalent). Shared, longer-lived, persisted. **Stage 2.** |
| **InMemoryDocumentStore** | Text chunks + embeddings of project-spec. Sibling of KG, not upstream feeder for KG assembly. |
| **Knowledge Graph (Ragas)** | Entities + relationships (or document nodes). Best for multi-hop / “how are these connected?” |
| **ProjectKnowledgeSession** | Registry entry keyed by `(user_id, ingest_id)`: document store handle, in-memory KG, `kg_artifact_path`, meta. |
| **project_vector_search** | Tool: query embedder + InMemoryEmbeddingRetriever over session store. |
| **project_kg_query** | Tool: substring / property match over KG-1 nodes (+ optional 1-hop neighbors). |
| **Research / Graph / Synthesis agents** | Fixed sequential LangGraph nodes with OpenSPDD structured prompts. |

### Core concept: Indexing Pipeline vs Knowledge Graph assembly

| Concept | Role | Order |
|---------|------|-------|
| **Indexing Pipeline** (Ch. 4) | Convert → clean → split → embed → write to DocumentStore | **First** (shared head) |
| **Knowledge Graph assembly** (Ch. 5) | After shared cleaner/splitter (post-`final_doc_joiner` chunks): extract DOCUMENT nodes + optional Ragas transforms | Sibling path; **not** a consumer of a finished vector write |

**Decision:** Share converters/cleaner/splitter. Branch after join:

- Branch A → embedder → `DocumentWriter` → `InMemoryDocumentStore`.
- Branch B → bridge → `KnowledgeGraphGenerator` → KG-1 (in-memory session + JSON artifact).

Preferred KG input: documents that *would* be written (post-join chunks), not a re-read from the store.

### Core concept: Two Knowledge Graphs

| Graph | Content | Source | Lifetime | Storage |
|-------|---------|--------|----------|---------|
| **KG-1 – Project Specification** | Entities & relations (or document nodes) from the user-uploaded project file | User upload → converters → KG generator | Session / request scoped | **In-memory** for agents + **JSON artifact** on every successful ingest (as-built) |
| **KG-2 – Equipment Stockpile** | Machines, models, capacities, availability, attachments, rates | Postgres → extractor → KG generator | Shared, longer-lived | **Persistent** (JSON minimum; Neo4j optional) — Stage 2 |

**Decision:** Different *file types* do **not** require different KG *variants*. Only the pipeline head (converters) changes; `KnowledgeGraphGenerator` stays shared.

### Core concept: InMemoryDocumentStore vs Knowledge Graph

| | InMemoryDocumentStore | Knowledge Graph (Ragas) |
|--|-----------------------|-------------------------|
| **Stores** | Text chunks + embeddings | Entities + relationships (or document nodes) |
| **Best for** | “Which passages are most similar?” | “How are these things connected?” / multi-hop |
| **Built from** | Cleaned/split Documents → embed → write | Same Documents → generator (+ optional transforms) |
| **Relationship** | Siblings. Prefer branching after splitter rather than “DocumentStore feeds KG”. | |

A multi-agent system SHALL be able to call tools against **both**.

### Core concept: Haystack vs LangGraph

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **Data / knowledge pipelines** | Haystack | Indexing, cleaning, splitting, embedding, KG generation, vector retrieval, tool packaging |
| **Agent orchestration** | LangGraph | Multi-step planning, tool selection, state, synthesis |

**Decision:** Haystack = reliable tool layer. LangGraph = complex agent steps.

### Persistence policy (as-built aligned)

- **KG-1 (Project):** Online agents use the **in-memory** graph held in the project knowledge session. Every successful ingest **also** saves JSON under `{KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json` (hard-fail if save fails). Optional hydrate-from-artifact after process restart (vector store remains empty until re-ingest).
- **KG-2 (Equipment):** Must be persisted (Stage 2). JSON minimum; Neo4j optional.
- **Neo4j temporary graphs:** Not required for KG-1 Stage 1.

---

## A — Approach

### Placement after indexing (Part A)

```text
[5 indexing] … → final_doc_joiner
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
 doc_embedder → writer         [6 this capability Part A — mandatory]
 InMemoryDocumentStore         bridge → KnowledgeGraphGenerator
                                        ├─ DOCUMENT nodes
                                        └─ full Ragas transforms
                                           only if KG_APPLY_TRANSFORMS
                                   → saver
                                   {KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json
                                   → register ProjectKnowledgeSession (Part B)
```

### Multi-agent architecture sketch (Part B)

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

### Preferred pipeline shape (project side)

```text
Converters (FileTypeRouter / specific converters)
  → DocumentCleaner
  → DocumentSplitter
       ├── DocumentEmbedder → DocumentWriter → InMemoryDocumentStore
       └── DocumentToLangChainConverter → KnowledgeGraphGenerator → KG-1
              → KnowledgeGraphSaver (JSON)
              → ProjectKnowledgeSessionRegistry
```

### Multi-agent pattern

- **Research Agent** — bound to `project_vector_search` only.
- **Graph Agent** — bound to `project_kg_query` only.
- **Synthesis Agent** — no tools; structured answer (Vector + Graph evidence).
- Stage 1: fixed sequential edges. Stage 2+: supervisor / dynamic routing.

### Stage 1 as-built decisions

| Topic | Decision |
|-------|----------|
| Topology | Fixed sequential: `research_agent` → `graph_agent` → `synthesis_agent` |
| DocumentStore | Per-ingest `InMemoryDocumentStore` in session registry |
| KG-1 online | In-memory on session + JSON artifact from Part A |
| Agent mode | `PROJECT_AGENT_MODE=stub` (default, CI-safe) \| `llm` |
| HTTP Q&A (Call 3) | `POST /internal/v1/recommendations/project-knowledge/query` |
| HTTP recommend (Call 2) | `POST .../project-knowledge/getassetrecommendations` (quote; not this capability’s Q&A) |
| Code path Q&A | prefix `/internal/v1/recommendations` + `"/project-knowledge/query"` |
| Scope | Project sources only — no equipment KG-2 |
| Portal submit | Call 1 then **Call 2 recommend** → React; Call 3 optional chatbot |
| Headers | Correlation on Call 2/3; no Idempotency-Key |

### Portal dual-hop (Spring → haystack)

```text
React  POST /api/recommendations/project-spec
  → Call 1  submitprojectspecification
  → Call 2  getassetrecommendations  → quote (primary to React)
  → Call 3  project-knowledge/query   → chatbot Q&A (optional)
```

### Alignment with parent product

This capability **extends** the target (post–6-day) sections of the equipment-recommendation product regarding:

- Offline / batch KnowledgeGraphGenerator (Ragas).
- LangGraph as the preferred stateful orchestrator.
- Project-spec ingest using Chapter 4-style routing and converters.

It does **not** change the normative 6-day MVP behaviour (SQL candidates, availability, `predict_price()`, one `RecommendationItem` per unit-need).

---

## S — Structure

### Modules (assembly — Part A)

| Path | Role |
|------|------|
| `app/pipelines/kg/bridge.py` | Haystack → LangChain |
| `app/pipelines/kg/generator.py` | Nodes + optional full Ragas transforms |
| `app/pipelines/kg/saver.py` | User-scoped JSON |
| `app/pipelines/kg/runner.py` | `run_knowledge_graph` (returns in-memory graph + artifact path) |
| `app/services/indexing.py` | Always runs KG after index; hard-fails on error; registers session |

### Modules (orchestration — Part B)

| Path | Role |
|------|------|
| `app/services/project_knowledge_session.py` | Session + registry + artifact load |
| `app/pipelines/indexing/retrieval.py` | Vector retrieval pipeline |
| `app/pipelines/kg/query.py` | KG-1 query helper |
| `app/agents/` | State, prompts, tools, nodes, LangGraph compile |
| `app/agents/prompts.py` | **OpenSPDD structured prompts** (Research / Graph / Synthesis) |
| `app/services/project_knowledge_qa.py` | Service facade |
| `app/schemas/project_knowledge.py` | Request/response |
| `app/api/recommendations.py` | Q&A route |

### Config tables

#### Assembly

| Env | Default | Notes |
|-----|---------|--------|
| `KG_ARTIFACT_DIR` | `artifacts/kg` | User-scoped subdirs |
| `KG_APPLY_TRANSFORMS` | `false` | Document nodes only unless true |

`KG_ENABLED` / `KG_STRICT` are **removed** — creation is always on and hard-fail is always on.

#### Orchestration

| Env | Default | Notes |
|-----|---------|--------|
| `PROJECT_AGENT_MODE` | `stub` | `stub` \| `llm` |
| `PROJECT_AGENT_TOP_K` | `5` | Default retrieval depth |
| `INDEXING_EMBEDDER` / dim | mock / 384 | Query embedder must match index |

---

## O — Operations

### Testing & verification

Full runbook (pytest, curl, Postman, AC mapping, known limitations):

→ [`../../../docs/testing/knowledge-graph-testing-guide.md`](../../../docs/testing/knowledge-graph-testing-guide.md)

### Quick commands

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Part A
uv run pytest tests/test_knowledge_graph.py -v

# Part B
uv run pytest \
  tests/test_project_knowledge_session.py \
  tests/test_project_vector_tool.py \
  tests/test_project_kg_query_tool.py \
  tests/test_project_knowledge_agents.py \
  tests/test_project_knowledge_api.py -v
```

### Live HTTP (same process)

1. `POST /internal/v1/recommendations/submitprojectspecification` → obtain `ingest_id` and `kg_*`.
2. `POST /internal/v1/recommendations/project-knowledge/query` with same `user_id` + `ingest_id` + `query`.

Contract: [`contracts/project-knowledge-query.md`](./contracts/project-knowledge-query.md).  
Postman folder **04 Stage-1 multi-agent Q&A**: [`../../../postman/README.md`](../../../postman/README.md).

### Spec Kit / OpenSPDD workflow phases

| Phase | Suggested action |
|-------|------------------|
| **Converge (Stage 1)** | Keep Part A + Stage 1 ACs green; treat this design + `spec.md` as normative. |
| **Clarify / Plan (Stage 2)** | Resolve open questions; entity schema for KG-2; Postgres extractor design. |
| **Tasks / Implement** | Equipment extractor + KG-2, equipment tools, supervisor optional. |
| **Converge (Stage 2)** | Dual-graph multi-agent ACs. |

---

## N — Norms

- Spec process: OpenSpec capability requirements; Spec-kit constitution; OpenSPDD REASONS + structured prompts.
- **Fix prompt/spec first**, then code when multi-agent behaviour is wrong.
- Layering: thin routers; services orchestrate; Haystack under `app/pipelines`; LangGraph under `app/agents`.
- Conflict ownership: indexing owns live ingest field list jointly with this Part A for `kg_*`; this capability owns when KG runs, tools, and Q&A route.
- Prefer distinctive fixture phrases under mock embeddings (e.g. “20-ton excavator”, “soft clay”).

---

## S — Safeguards

Forbidden without a dedicated Stage-2 (or later) SDD change:

- Soft-fail KG assembly or reintroducing `KG_ENABLED` / `KG_STRICT` as the default path
- Stage-1 answers that invent equipment fleet inventory, rates, or live availability
- File-type-specific `KnowledgeGraphGenerator` variants
- Mandatory Neo4j for KG-1 Stage 1
- Claiming dual-source resume after process restart without DocumentStore snapshots
- Replacing Asset SQL / Booking / `predict_price()` with KG on the default recommend path

---

## Explicit OpenSPDD section — structured prompts

| Item | Detail |
|------|--------|
| **Location** | [`app/agents/prompts.py`](../../../app/agents/prompts.py) |
| **Index** | [`openspec/spdd/prompts/project-knowledge-agents.md`](../../spdd/prompts/project-knowledge-agents.md) |
| **Rule** | When behaviour is wrong, **edit prompts first**, then code (and update this design/spec if contracts change). |

| Intent constant | Agent | Tools allowlist | Role |
|-----------------|-------|-----------------|------|
| `RESEARCH_AGENT_INTENT` | Research | `project_vector_search` only | Retrieve project-spec passages; research notes only (no final answer) |
| `GRAPH_AGENT_INTENT` | Graph | `project_kg_query` only | Query KG-1 nodes/relations; graph notes only |
| `SYNTHESIS_AGENT_INTENT` | Synthesis | **none** | Grounded answer from Vector + Graph evidence; cite source type; state gaps |

**Stage-1 tool boundary:** only `project_vector_search` and `project_kg_query`. No equipment inventory / KG-2 tools.

**Modes:**

- `PROJECT_AGENT_MODE=stub` — deterministic `stub_synthesis_answer(...)` from tool hits (CI-safe).
- `PROJECT_AGENT_MODE=llm` — LLM uses system prompts above; requires `LLM_*` configured.

Output contracts (markdown sections) are normative in the prompts:

- Research: `## Research notes`, `## Passages`
- Graph: `## Graph notes`, `## Nodes`
- Synthesis: `## Answer`, `## Evidence` (Vector / Graph), `## Gaps`

---

## Stage 2 backlog

1. **KG-2** equipment stockpile graph + refresh from Postgres.
2. Equipment vector store / manuals retrieval tool.
3. Supervisor / dynamic routing (research, graph, pricing, availability).
4. Reattach full recommend pipeline tools (`check_availability`, `recommend_prices`, …).
5. Neo4j optional backend.
6. Persist project DocumentStore snapshots for true dual-source resume after restart.

---

## Open questions (Stage 2 / clarify)

1. Exact Ragas transform set and entity schema for project vs equipment.
2. Whether equipment vector store is required with KG-2 or only the graph.
3. JSON vs Neo4j timeline for KG-2.
4. Whether project DocumentStore should be snapshotted for full resume.

---

## Key decisions

| Decision | Rationale |
|----------|-----------|
| Sibling branch after joiner | KG consumes same post-join chunks as embed path; store does not feed KG |
| Mandatory KG + hard-fail | Always produce artifact + session; no silent skip |
| Default transforms off | Fast CI; document nodes sufficient for Stage 1 |
| Fixed sequential agents Stage 1 | Deterministic dual-source evidence without supervisor complexity |
| Stub agent mode default | CI without LLM keys |
| JSON artifact for KG-1 | Persist graph without Neo4j; optional reload after restart |
| No file-type KG variants | Shared generator; converters only at head |

## Change control

See [`spec.md`](./spec.md) change-control table (includes historical 0.1.0–0.5.2 from SPEC-knowledge-graph and 1.0.0 OpenSpec migration).

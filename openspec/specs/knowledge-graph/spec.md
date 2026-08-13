# Knowledge Graph Specification

| Field | Value |
|-------|--------|
| **Status** | **Stage 1 as-built** — mandatory post-join KG assembly (HR-76) + project DocumentStore/KG-1 multi-agent Q&A; **Stage 2** (KG-2 / equipment) pending |
| **Capability** | `knowledge-graph` (HR-76 assembly) · `kg-multi-agent-orchestration` (agents) |
| **Tracking** | **HR-76** (assembly) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD |
| **Depends on** | Haystack 2.0, Ragas KnowledgeGraph, LangGraph, InMemoryDocumentStore, optional Neo4j (later) |
| **Env** | [`.env.example`](../../../.env.example) — `KG_*`, `PROJECT_AGENT_*`, `INDEXING_*` |
| **Contracts** | [`contracts/project-knowledge-query.md`](./contracts/project-knowledge-query.md) |
| **Design** | [`design.md`](./design.md) |
| **Testing** | [`../../../docs/testing/knowledge-graph-testing-guide.md`](../../../docs/testing/knowledge-graph-testing-guide.md) |
| **Archived tasks** | [`../../changes/archive/2026-08-07-knowledge-graph-hr-76/`](../../changes/archive/2026-08-07-knowledge-graph-hr-76/) · [`../../changes/archive/2026-08-08-kg-multi-agent-stage1/`](../../changes/archive/2026-08-08-kg-multi-agent-stage1/) |
| **Related** | [`../indexing/spec.md`](../indexing/spec.md), [`../domain/spec.md`](../domain/spec.md), [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) |
| **Audience** | Engineers and coding agents implementing project-spec ingest, knowledge graphs, and multi-agent Q&A |

> **Spec Kit alignment:** This document is the **Specify** artifact (What & Why) for both KG assembly and multi-agent access.  
> When reality diverges, **fix the prompt / spec first** — then update the code (OpenSPDD).

---

## Purpose

### Problem

The recommendation path can accept free-text or a project file, but agents need **structured, multi-hop knowledge** about:

1. The **project specification** the user uploaded (requirements, constraints, site conditions, capacities, timeline).
2. (Target) The **equipment stockpile** available for rental (machines, capacities, availability, attachments, rates).

Without both layers, the agent cannot reliably answer questions that require:

- Semantic similarity over project text **and**
- Precise entity/relationship reasoning (“project needs ≥20 t excavator on soft clay within 8 weeks” ↔ “which machines satisfy this?”).

### Goal

Define a clear, testable architecture that:

1. Uses a **Haystack indexing-style pipeline** to produce:
   - An `InMemoryDocumentStore` (or equivalent) of project-spec chunks.
   - A **Knowledge Graph** (Ragas-style) of that project specification (**KG-1**).
2. Separately maintains an equipment-side vector store + **Knowledge Graph** (**KG-2**) derived from Postgres (or equivalent) — **Stage 2**.
3. Exposes knowledge sources as **tools**.
4. Uses a **LangGraph multi-agent system** to orchestrate research over those sources and produce grounded answers / rationales.

### Non-goals

- Replacing the existing 6-day MVP recommendation pipeline (SQL filter → availability → `predict_price` → rank).
- Owning booking or payment.
- Mandatory Neo4j in Stage 1 (JSON / in-memory is acceptable).
- Training the pricing model.

---

## Methodology

| Source | Principle applied here |
|--------|------------------------|
| **GitHub Spec Kit** | Spec first (this document). Plan → Tasks → Implement → Converge. |
| **OpenSPDD** | Structured prompts for agents; when behaviour is wrong, edit prompts/SPEC first. |
| **OpenSpec** | Capability behaviour as Requirements + Scenarios; design as REASONS Canvas. |
| **Haystack Ch. 3–5** | Pipeline-first tool layer; LangGraph for stateful multi-agent orchestration; Ragas KnowledgeGraph as a first-class component. |

**OpenSPDD rule:** When agent behaviour is wrong, edit structured prompts in [`app/agents/prompts.py`](../../../app/agents/prompts.py) (and this spec) **first**, then code. See [`../../spdd/prompts/project-knowledge-agents.md`](../../spdd/prompts/project-knowledge-agents.md).

---

## Conflict rule

| Concern | Owner |
|---------|--------|
| Live HTTP field list for ingest (including `kg_*` on response) | Indexing SPEC + **this SPEC Part A** |
| When KG runs, transforms location, artifact path | **This SPEC Part A** |
| Multi-agent tools, session registry, Q&A route | **This SPEC Part B** |
| Parent product vision (equipment-recommendation) | Parent; as-built = this child |

---

## User Scenarios & Testing

### User Story A — Part A: Mandatory KG assembly after indexing (Priority: P1)

An engineer or portal uploads a project specification (`user_id` + text/file). After the shared indexing head joins cleaned/split chunks, the system **always** builds KG-1 from **post-join** chunks, saves a user-scoped JSON artifact, and returns `kg_*` fields on the ingest response.

**Independent Test:** Ingest via `POST /internal/v1/recommendations/submitprojectspecification` with distinctive project text; assert `kg_built=true`, artifact path under `{user_id}/`, and `tests/test_knowledge_graph.py` green. Full runbook: [knowledge-graph-testing-guide.md](../../../docs/testing/knowledge-graph-testing-guide.md).

**Acceptance Scenarios:**

1. **Given** a successful index write with valid `user_id`, **When** ingest completes, **Then** `kg_built=true`, `kg_node_count ≥ 1`, `kg_artifact_path` non-empty under user-scoped path, and `kg_transform_applied=false` when transforms are off.
2. **Given** KG build or save fails, **When** ingest is attempted, **Then** the request fails (not 200 with warnings only); hard-fail.
3. **Given** two different users ingest, **When** both succeed, **Then** artifacts land under two distinct user-scoped paths.
4. **Given** ingest without `user_id`, **When** the request is validated, **Then** HTTP **400** (indexing ownership).

### User Story B — Part B: Stage-1 multi-agent project-knowledge Q&A (Priority: P1)

After a successful ingest, a client asks a natural-language question with the same `user_id` and `ingest_id`. A fixed sequential LangGraph (`research_agent` → `graph_agent` → `synthesis_agent`) queries the project DocumentStore and KG-1 and returns a grounded answer with tool traces.

**Independent Test:** Same-process ingest then `POST .../project-knowledge/query` (Call 3); assert both tools in `sources_used` / `tool_traces`. Recommend: `POST .../getassetrecommendations` (Call 2) returns quote `items`.

**Acceptance Scenarios:**

1. **Given** a registered project knowledge session, **When** Q&A runs, **Then** LangGraph invokes `project_vector_search` and `project_kg_query` in the same run.
2. **Given** both tools return hits, **When** synthesis completes, **Then** the answer demonstrably uses Vector and Graph evidence (`sources_used`, tool traces, and/or evidence sections).
3. **Given** an unknown `ingest_id`, **When** Q&A is called, **Then** HTTP **404** `not_found`.
4. **Given** an empty `query`, **When** Q&A is validated, **Then** HTTP **422** or **400**.

### User Story C — Stage 2 equipment stockpile (Priority: P2 — deferred)

Product target: equipment-side vector store + **KG-2** from Postgres, available as tools alongside project sources, with optional supervisor routing and Neo4j backend.

**Independent Test:** Not required until Stage 2 requirements are promoted from deferred.

**Acceptance Scenarios:**

1. **Given** Stage 2 is implemented, **When** KG-2 is needed online, **Then** it can be loaded from persistent storage without re-querying Postgres on every request.

---

## Requirements

### Part A — KG assembly after indexing (HR-76 as-built)

### Requirement: FR-KG-001 user_id required on ingest
`user_id` SHALL be required on project-spec ingest. Ownership of the HTTP validation is the indexing capability; this capability depends on it for user-scoped KG artifacts and session keys.  
(Trace: source FR-KG-001; indexing SPEC)

#### Scenario: Missing user_id rejected
- **WHEN** a client calls ingest without `user_id`
- **THEN** the request is rejected with HTTP **400**

### Requirement: FR-KG-002 KG chunks carry user and ingest meta
KG input chunks MUST carry `user_id` and `ingest_id` in document meta so artifacts and sessions remain attributable.  
(Trace: source FR-KG-002)

#### Scenario: Meta stamped on KG chunks
- **GIVEN** a successful ingest for a known user and generated `ingest_id`
- **WHEN** KG assembly runs on post-join chunks
- **THEN** those chunks include `user_id` and `ingest_id` meta

### Requirement: FR-KG-003 Mandatory KG build from post-join chunks
After a successful index write, the system MUST build KG-1 from **post-join** chunks (documents that would be written after `final_doc_joiner`) and save under the user-scoped artifact path. Preferred input is post-join chunks, not a re-read from the DocumentStore.  
(Trace: source FR-KG-003)

#### Scenario: Successful ingest always builds KG
- **GIVEN** indexing completed successfully for a project-spec
- **WHEN** the KG runner executes
- **THEN** a knowledge graph is built from post-join chunks and a JSON artifact is saved under `{KG_ARTIFACT_DIR}/{user_id}/kg_{ingest_id}.json`

#### Scenario: Branch after final_doc_joiner
- **WHEN** the shared indexing head finishes at `final_doc_joiner`
- **THEN** Branch A embeds and writes to InMemoryDocumentStore and Branch B bridges to KnowledgeGraphGenerator (sibling paths)

### Requirement: FR-KG-004 Full Ragas transforms only when flagged
Full Ragas transforms SHALL run only inside `KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true`.  
(Trace: source FR-KG-004)

#### Scenario: Transforms gated by config
- **GIVEN** `KG_APPLY_TRANSFORMS=true`
- **WHEN** KG generation runs
- **THEN** full Ragas transforms are applied and `kg_transform_applied` reflects that application

### Requirement: FR-KG-005 Default transforms off (document nodes)
Default transforms SHALL be **off**. With the default, the generator produces document nodes (no full Ragas transform pass).  
(Trace: source FR-KG-005)

#### Scenario: Default document-node mode
- **GIVEN** `KG_APPLY_TRANSFORMS=false` (default)
- **WHEN** KG generation succeeds
- **THEN** `kg_transform_applied=false` and the graph contains document nodes with `kg_node_count ≥ 1`

### Requirement: FR-KG-006 KG failure hard-fails the ingest
KG build or save failure MUST fail the ingest request. There is no soft-fail path. `KG_ENABLED` / `KG_STRICT` are **removed** — creation is always on and hard-fail is always on.  
(Trace: source FR-KG-006)

#### Scenario: KG error fails request
- **GIVEN** the KG runner or saver raises an error
- **WHEN** ingest is processed
- **THEN** the HTTP request fails (not 200 with warnings only)

### Requirement: FR-KG-007 Ingest response exposes kg_* fields
The ingest response SHALL include: `kg_built`, `kg_node_count`, `kg_relationship_count`, `kg_artifact_path`, `kg_transform_applied`. On success `kg_built` is always `true`.  
(Trace: source FR-KG-007; field list shared with indexing SPEC)

#### Scenario: Success response kg fields
- **WHEN** ingest and KG succeed
- **THEN** `kg_built` is `true`, `kg_node_count` and `kg_relationship_count` are present, `kg_artifact_path` is non-empty, and `kg_transform_applied` reflects config

### Requirement: FR-KG-008 Sanitize user_id for filesystem paths
`user_id` SHALL be sanitized for filesystem paths when writing user-scoped KG artifacts.  
(Trace: source FR-KG-008)

#### Scenario: Safe path segment
- **GIVEN** a `user_id` containing characters unsafe for paths
- **WHEN** the artifact is saved
- **THEN** the path uses a sanitized user segment under `KG_ARTIFACT_DIR`

---

### Part B — Multi-agent orchestration

### Requirement: FR-KG-010 Project-spec indexing + KG session exposure
Project-spec indexing + KG assembly SHALL follow Part A. The project knowledge session SHALL expose both the ingest-scoped `InMemoryDocumentStore` and in-memory KG-1 (plus `kg_artifact_path` and meta).  
(Trace: source FR-KG-010; was FR-KG-01)

#### Scenario: Session holds both sources
- **GIVEN** successful ingest + KG build
- **WHEN** a `ProjectKnowledgeSession` is registered for `(user_id, ingest_id)`
- **THEN** the session holds a document store handle, in-memory knowledge graph, `kg_artifact_path`, and meta (chunk counts, filenames, …)

#### Scenario: Registry delete is session-scoped
- **WHEN** a session is discarded via registry `delete`
- **THEN** other sessions (and later KG-2) are unaffected

### Requirement: FR-KG-011 Equipment stockpile knowledge KG-2 (Stage 2 — deferred)
Equipment stockpile knowledge (**KG-2**) SHALL be derived from Postgres (or an approved source) and persisted independently of user sessions.  
(Trace: source FR-KG-011; was FR-KG-02)  
**Status:** **Stage 2 — deferred** for in-app persist/load tools. **S8.1–S8.2 as-built (config pack):** `neo4j-populate` MERGEs fleet labels; post-sync + admin HTTP trigger; DocumentStore `:Document` never dropped. **S7.2 as-built** still ships fake `neo4j_cypher_read` / `trigger_neo4j_populate` (K-3 skip). App live tools remain **S8.3**. See [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md).

#### Scenario: Deferred — persistent load without per-request Postgres (Stage 2)
- **WHEN** Stage 2 is implemented and KG-2 is required online
- **THEN** KG-2 can be loaded from persistent storage without re-querying Postgres on every request

### Requirement: FR-KG-012 No file-type-specific KG variants
There SHALL be no file-type-specific KG *variants*. Only converters/extractors at the pipeline head differ; `KnowledgeGraphGenerator` stays shared.  
(Trace: source FR-KG-012; was FR-KG-03)

#### Scenario: Shared generator across file types
- **WHEN** PDF, text, or HTML project specs are processed
- **THEN** only the converter head changes; the same KG generator produces KG-1

### Requirement: FR-KG-013 LangGraph multi-agent synthesis over tools
A LangGraph multi-agent system SHALL be able to call vector retrieval tool(s) and KG query tool(s) and synthesize a grounded answer.  
(Trace: source FR-KG-013; was FR-KG-04)

#### Scenario: Stage-1 sequential dual-tool run
- **GIVEN** a registered project knowledge session
- **WHEN** the Stage-1 graph runs (`research_agent` → `graph_agent` → `synthesis_agent`)
- **THEN** both `project_vector_search` and `project_kg_query` are invoked and synthesis produces a grounded answer

#### Scenario: Stage-1 source scope
- **WHEN** Stage-1 agents run
- **THEN** they may use only project InMemoryDocumentStore and project KG-1 (no equipment KG-2)

### Requirement: FR-KG-014 Haystack pipelines exposable as tools
Haystack retrieval / KG query pipelines SHALL be exposable as tools (name + natural-language description) for LangGraph.  
(Trace: source FR-KG-014; was FR-KG-05)

#### Scenario: Tool packaging
- **WHEN** tools are bound to agents
- **THEN** `project_vector_search` is backed by query embedder + `InMemoryEmbeddingRetriever` over the session store
- **AND** `project_kg_query` is backed by substring / property match over KG-1 nodes (optional 1-hop neighbors)
- **AND** each tool has a stable name and natural-language description

#### Scenario: Vector tool embedder matches session store
- **GIVEN** the session DocumentStore was populated with embeddings of mode M and dimension D (from indexing settings at ingest)
- **WHEN** `project_vector_search` runs
- **THEN** the query-side text embedder uses the same M and D from settings (or an explicit test `Settings` with matching values)
- **AND** a host/env dim mismatch MUST NOT be left untested — default pytest isolates `INDEXING_EMBEDDER=mock` and `INDEXING_EMBEDDING_DIM=384` via `tests/conftest.py`

### Requirement: Call 3 chatbot Q&A route after Call 1 session
Live route: `POST /internal/v1/recommendations/project-knowledge/query`  
(code: router prefix `/internal/v1/recommendations` + relative `"/project-knowledge/query"`).

Stage-1 multi-agent **chatbot Q&A** **SHALL** be available on this Call **3** path with `user_id` + `ingest_id` + required `query`, after successful Call 1. Response **SHALL** be project-knowledge Q&A (`answer` + evidence). This route **SHALL NOT** perform ingest and **SHALL NOT** return commercial quote `items[]` / invent fleet rates.  
**Call 2** recommend is a separate path: `.../project-knowledge/getassetrecommendations` (quote envelope).  
Portal submit primary body is **Call 2 recommend**, not Call 3.  
(Trace: Feasibility_Study §1.2.0 · portal-to-haystack-mapping v2)  
**Status:** **as-built**.

#### Scenario: Chatbot Q&A after ingest
- **GIVEN** a successful Call 1 for `user_id` U yielding `ingest_id` I
- **WHEN** client POSTs Call 3 with U, I, and non-empty `query`
- **THEN** response is **200** with `answer` when tools can ground
- **AND** body MUST NOT require quote `items[]` / `quoteRef`

#### Scenario: Call 3 is not ingest
- **WHEN** Call 3 is invoked without a session for `(user_id, ingest_id)`
- **THEN** server returns **404** and MUST NOT create a new index/KG

---

### Stage 2 deferred requirements (backlog labels)

The following product targets are **not** Stage-1 acceptance criteria. They remain normative backlog until a Stage-2 change promotes them:

| Deferred item | Related requirement / note |
|---------------|----------------------------|
| KG-2 equipment stockpile graph + refresh from Postgres | FR-KG-011 |
| Equipment vector store / manuals retrieval tool | Stage 2 backlog |
| Supervisor / dynamic routing (research, graph, pricing, availability) | Stage 2+ topology |
| Reattach full recommend pipeline tools (`check_availability`, `recommend_prices`, …) | Stage 2+ |
| Neo4j optional backend | Persistence policy Stage 2 |
| Persist project DocumentStore snapshots for dual-source resume after restart | Stage 2 backlog |

---

## Norms (OpenSPDD)

- Prefer branching after splitter/joiner rather than “DocumentStore feeds KG”.
- Haystack owns data/knowledge pipelines; LangGraph owns multi-step agent orchestration.
- Structured agent prompts live in `app/agents/prompts.py`; fix prompts/spec before code when behaviour is wrong.
- Default CI-safe modes: mock embedder, `KG_APPLY_TRANSFORMS=false`, `PROJECT_AGENT_MODE=stub`.
- Sessions are process-local; ingest and Q&A must hit the same process unless artifact reload is used (KG-only partial resume).
- Chatbot Q&A is **Call 3** `.../query`. Portal submit uses Call 1 then **Call 2 recommend** (quote).
- Vector retrieval and ingest must share embedder mode/dim; pytest conftest isolates host indexing env.

## Safeguards (OpenSPDD)

- Do not soft-fail KG assembly (`KG_ENABLED` / `KG_STRICT` remain removed).
- Do not invent equipment fleet inventory, rates, or bookings in Stage-1 synthesis (no KG-2).
- Do not add file-type-specific KG generator variants.
- Do not claim dual-source resume after process restart without DocumentStore snapshot (Stage 2).
- Do not replace Asset SQL, Booking availability, or `predict_price()` with KG on the recommend path unless a later SDD promotes those tools.
- Do not treat Call 3 `query` or Call 2 `getassetrecommendations` as project-spec **ingest**.
- Do not require `Idempotency-Key` on Call 2/3 (S2a applies to Call 1 only).
- Do not return quote `items[]` on Call 3 Q&A (that is Call 2).
- Do not hardcode a store embedding dimension that differs from the settings-backed query embedder in vector-tool tests.

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| **1.3.2** | 2026-08-13 | FR-KG-011: config **S8.2 T4** post-sync + admin HTTP as-built; app tools still S8.3 |
| **1.3.1** | 2026-08-13 | FR-KG-011: config **S8.1 T3** `neo4j-populate` as-built; in-app persist/tools still Stage 2 / S8.3 |
| **1.3.0** | 2026-08-13 | FR-KG-011 still Stage 2; pointer that S7.2 ships fake `neo4j_cypher_read` / populate no-op (live persist = S8) |
| **1.2.1** | 2026-08-12 | Vector tool: query/store embedding dim match; pytest conftest mock+384 isolation; no optional prereq markers for default suite |
| **1.2.0** | 2026-08-12 | Call 3 = chatbot Q&A route; Call 2 recommend separate |
| **1.1.0** | 2026-08-12 | Portal dual-hop (Call 2 was Q&A; superseded) |
| **0.1.0** | 2026-08-07 | HR-76 as-built (optional KG) |
| **0.1.1** | 2026-08-07 | Sequential map; expanded AC/modules |
| **0.2.0** | 2026-08-07 | Mandatory KG + hard-fail; remove `KG_ENABLED` / `KG_STRICT` |
| **0.3.0** | 2026-08-08 | Multi-agent architecture SPEC drafted (separate file) |
| **0.4.0** | 2026-08-08 | Stage 1 multi-agent as-built (session, tools, LangGraph, Q&A route) |
| **0.5.0** | 2026-08-08 | **Merge** HR-76 SPEC + multi-agent SPEC into single document |
| **0.5.1** | 2026-08-08 | Remove retired multi-agent filename redirect stub |
| **0.5.2** | 2026-08-08 | §10 Testing (pytest, curl, Postman, AC map) |
| **1.0.0** | 2026-08-10 | Migrated to OpenSpec + Spec-kit + OpenSPDD under `openspec/specs/knowledge-graph/`; testing → `docs/testing/`; tasks archived |

---

**Reading order:** [← Indexing](../indexing/spec.md) · [Design](./design.md) · [Q&A contract](./contracts/project-knowledge-query.md) · [Testing](../../../docs/testing/knowledge-graph-testing-guide.md) · [Prompts index](../../spdd/prompts/project-knowledge-agents.md) · [Postman](../../../postman/README.md)

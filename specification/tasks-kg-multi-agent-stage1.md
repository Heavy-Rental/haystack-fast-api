# Tasks: Multi-Agent Orchestration — Stage 1 (Project Spec Sources)

**Input:** [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md) Part B

**Stage scope:** Agents use only (1) project `InMemoryDocumentStore` and (2) project **KG-1**. No equipment KG-2.

## Key decisions (Stage 1)

| Topic | Decision |
|-------|----------|
| Topology | Fixed sequential: research → graph → synthesis |
| DocumentStore | Per-ingest `InMemoryDocumentStore` in session registry |
| KG-1 | In-memory on session + existing JSON artifact |
| Agent mode | `PROJECT_AGENT_MODE=stub` (default) \| `llm` |
| HTTP | `POST /api/v1/recommendations/project-knowledge/query` |

## Phase A — SPDD scaffolding

- [x] T001 SPEC tasks file
- [x] T002 Structured prompts (`app/agents/prompts.py`)
- [x] T003 Stage-1 key decisions locked (this file)

## Phase B — Session registry

- [x] T010 `ProjectKnowledgeSession` + registry
- [x] T011 Per-ingest DocumentStore on ingest
- [x] T012 Register session after KG build
- [x] T013 Load KG from JSON artifact when registry miss (path known)

## Phase C — Haystack tools

- [x] T020 `project_vector_search`
- [x] T021 `project_kg_query`
- [x] T022 Tool wrappers (name + description)

## Phase D — LangGraph multi-agent

- [x] T030 State schema
- [x] T031 Research node
- [x] T032 Graph node
- [x] T033 Synthesis node (stub + llm)
- [x] T034 Compiled graph
- [x] T035 `ProjectKnowledgeQAService`

## Phase E — HTTP

- [x] T040 Schemas
- [x] T041 Route
- [x] T042 Threadpool wiring
- [x] T043 Postman notes

## Phase F — Tests & converge

- [x] T050–T054 Automated tests
- [x] T055 SPEC Stage-1 notes

## Out of scope (Stage 2+)

KG-2, equipment vectors, supervisor routing, pricing/availability tools, Neo4j.

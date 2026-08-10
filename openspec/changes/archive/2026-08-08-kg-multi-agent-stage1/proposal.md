# Proposal: Multi-agent orchestration — Stage 1 (project sources)

| Field | Value |
|-------|--------|
| **Change id** | `2026-08-08-kg-multi-agent-stage1` |
| **Status** | **Archived** — Stage 1 Part B as-built |
| **Capability** | `knowledge-graph` (Part B multi-agent) |
| **Depends on** | [`../2026-08-07-knowledge-graph-hr-76/`](../2026-08-07-knowledge-graph-hr-76/) (mandatory KG + artifact) |
| **Normative now** | [`openspec/specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md) · [`design.md`](../../../specs/knowledge-graph/design.md) · [`contracts/project-knowledge-query.md`](../../../specs/knowledge-graph/contracts/project-knowledge-query.md) |
| **Prompts** | [`app/agents/prompts.py`](../../../../app/agents/prompts.py) · index [`openspec/spdd/prompts/project-knowledge-agents.md`](../../../spdd/prompts/project-knowledge-agents.md) |
| **Tasks** | [`tasks.md`](./tasks.md) |

## Why

After HR-76 produces DocumentStore chunks and KG-1, clients need a grounded Q&A path that can use **both** semantic retrieval and graph query. Stage 1 delivers a fixed sequential LangGraph (research → graph → synthesis) over **project sources only**, with CI-safe stub synthesis and OpenSPDD structured prompts.

## What changes

- `ProjectKnowledgeSession` + registry keyed by `(user_id, ingest_id)`.
- Tools: `project_vector_search`, `project_kg_query` (name + NL description).
- LangGraph nodes: research, graph, synthesis (`stub` | `llm`).
- HTTP: `POST /api/v1/recommendations/project-knowledge/query`.
- Schemas, service facade, Postman folder **04 Stage-1 multi-agent Q&A**.
- Structured prompts in `app/agents/prompts.py` (OpenSPDD: fix prompts first).

## Scope

| In scope | Out of scope (Stage 2+) |
|----------|-------------------------|
| Project InMemoryDocumentStore + KG-1 only | KG-2 equipment stockpile |
| Fixed sequential topology | Supervisor / dynamic routing |
| FR-KG-010, FR-KG-012…014 (Stage 1) | Pricing / availability tools, Neo4j |
| Session delete without affecting other sessions | DocumentStore snapshot resume |

## Key decisions (Stage 1)

| Topic | Decision |
|-------|----------|
| Topology | Fixed sequential: research → graph → synthesis |
| DocumentStore | Per-ingest `InMemoryDocumentStore` in session registry |
| KG-1 | In-memory on session + existing JSON artifact |
| Agent mode | `PROJECT_AGENT_MODE=stub` (default) \| `llm` |
| HTTP | `POST /api/v1/recommendations/project-knowledge/query` |

## Impact

- Live path: ingest then same-process Q&A.
- Process-local sessions; restart invalidates dual-source until re-ingest.
- Does not change 6-day recommend MVP HTTP behaviour.

## Non-goals

- Equipment tools or inventing fleet inventory in Stage-1 answers.
- Replacing Asset SQL / Booking / `predict_price` on recommend path.

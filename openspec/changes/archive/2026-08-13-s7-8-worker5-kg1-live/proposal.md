# Proposal: S7.8 Worker [5] live KG-1 tools

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** |
| **Date** | 2026-08-13 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 7 follow-up |
| **Trace** | C/W/D §10.4 Worker [5]; S7.7 explicit leftover |
| **Tasks** | [`./tasks.md`](./tasks.md) |

## Why

S7.7 shipped A–L prompts and DI but left Worker [5] on `decompose_project_needs` only. C/W/D §10.4 requires `project_vector_search` + `project_kg_query` (KG-1 / session plane) before decompose so needs are grounded in the uploaded spec.

## What this change ships

| Item | Behaviour |
|------|-----------|
| Catalog | When a `ProjectKnowledgeSession` is available, register session-bound `project_vector_search` and `project_kg_query`. |
| Worker [5] | Call vector → KG-1 → decompose. Write `project.research_notes`, `project.graph_notes`, optional hits, then `needs[]`. |
| Soft-fail | Missing tools, empty hits, or tool errors → explicit empty/skip notes; decompose still runs; no fleet invent. |
| Default CI | No session → tools not registered; existing graph tests unchanged. |
| Prompts | `PROJECT_WORKER_SYSTEM` names the three allowlisted tools. |

## Out of scope

- Flip `RECOMMEND_VIA_AGENT_GRAPH` default
- Call 3 Q&A changes (already live)
- KG-2 / Neo4j (S8.3)
- Inventing needs from empty retrieval

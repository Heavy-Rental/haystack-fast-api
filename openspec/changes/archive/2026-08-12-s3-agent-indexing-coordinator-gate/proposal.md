# Proposal: Agent indexing tool + Coordinator gate [4] (S3 / Phase 3 R1)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S3) |
| **Date** | 2026-08-12 |
| **Trace** | FR-IX-026 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 3 / stage **S3** |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |
| **Ticket / branch** | HR-117 · `HR-117-implement-plan-execution-s-3-agent-indexing-tool-and-coordinator-gate` |

## Why

Multi-agent recommend (later S7) needs a **forced non-LLM indexing edge** so project files never enter LLM context as raw bytes and recommend Workers only run after index+KG succeed. Dual-plane R1 and C/W/D **[4]** specify an in-process tool behind a feature flag, defaulting to the as-built direct service path.

## What shipped

| Item | Behaviour |
|------|-----------|
| Tool `run_indexing_from_request` | In-process wrap of `IndexingIngestService` (meta, KG hard-fail, session registry) |
| Coordinator gate [4] | Forced LangGraph `START → index_gate → END` (not an LLM Worker) |
| Flag `INDEXING_VIA_AGENT_GATE` | Default **false** = direct service; **true** = gate path |
| Lean body | Unchanged FR-IX-023 on both paths |
| Failures | MIME / KG → 400; gate sets `indexing_ok=false` |
| Traces | `role=coordinator`, `node=index_gate`, `tool=run_indexing_from_request` |
| SuperComponent (S3.3) | **Deferred** (optional packaging) |

## Spec / design / contract

- `openspec/specs/indexing/spec.md` — FR-IX-026 + scenarios + change control **0.8.0**
- `openspec/specs/indexing/contracts/ingest-from-project-spec.md` — execution path table
- `openspec/specs/indexing/design.md` — diagram branch, modules, tests
- `openspec/TRACEABILITY.md` — FR-IX-026 map
- `openspec/AGENTS.md` — Call 1 flow gate note
- `openspec/project.md` — as-built identity

## Code

- `app/agents/tools.py` — `TOOL_RUN_INDEXING`, `run_indexing_from_request`
- `app/agents/indexing_gate.py` — state, node, graph, `run_indexing_gate`
- `app/api/recommendations.py` — flag wire (idempotency preserved)
- `app/config.py` — `indexing_via_agent_gate`
- `.env.example` — documented flag
- `tests/test_indexing_tool.py` — S3 pack (9 cases)

## Out of scope

- SuperComponent (S3.3)
- Full recommend C/W/D graph (S7)
- Pgvector DocumentStore cutover (S5)
- Changing Spring public/internal DTO fields

# Specification (legacy path)

**SDD source of truth has moved to [`../openspec/`](../openspec/).**

| Standard | Role |
|----------|------|
| **OpenSpec** | `openspec/specs/<capability>/spec.md` |
| **GitHub Spec-kit** | `.specify/memory/constitution.md`, user stories, contracts, tasks |
| **OpenSPDD** | REASONS Canvas designs + structured prompts; fix prompt/spec first |

**Start here:** [`../openspec/AGENTS.md`](../openspec/AGENTS.md)

**Portal dual-hop (React → Spring → haystack):**  
React `POST /api/recommendations/project-spec` → Call 1 ingest → **Call 2 recommend** (`getassetrecommendations` quote) → React. **Call 3** chatbot: `project-knowledge/query`.  
SoT: [`../openspec/AGENTS.md`](../openspec/AGENTS.md) · [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md).

## Old → new map

| Legacy file | New location |
|-------------|--------------|
| `README.md` (this map) | [`openspec/AGENTS.md`](../openspec/AGENTS.md) |
| `00-overview.md` | [`openspec/project.md`](../openspec/project.md) |
| `01-domain.md` | [`openspec/specs/domain/spec.md`](../openspec/specs/domain/spec.md) |
| `SPEC-project.md` | [`openspec/project.md`](../openspec/project.md) |
| `SPEC-project-setup.md` | [`openspec/specs/project-setup/`](../openspec/specs/project-setup/) · constitution [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) |
| `SPEC-indexing-file-type-router.md` | [`openspec/specs/indexing/`](../openspec/specs/indexing/) |
| `SPEC-knowledge-graph.md` | [`openspec/specs/knowledge-graph/`](../openspec/specs/knowledge-graph/) · testing [`docs/testing/knowledge-graph-testing-guide.md`](../docs/testing/knowledge-graph-testing-guide.md) |
| `SPEC-recommendation-intake.md` | [`openspec/specs/recommendation-intake/spec.md`](../openspec/specs/recommendation-intake/spec.md) |
| `SPEC-recommendation-pipeline.md` | [`openspec/specs/recommendation-pipeline/`](../openspec/specs/recommendation-pipeline/) |
| `SPEC-dynamic-pricing.md` | [`openspec/specs/dynamic-pricing/`](../openspec/specs/dynamic-pricing/) |
| `SPEC-agentic-equipment-recommendation-and-pricing.md` | [`openspec/specs/equipment-recommendation/`](../openspec/specs/equipment-recommendation/) |
| `SPEC-recommendation-intake-and-pipeline-front.md` | [`openspec/changes/archive/2026-08-07-hr-65-intake-front/`](../openspec/changes/archive/2026-08-07-hr-65-intake-front/) |
| `SPEC-recommendation-pipeline-testing-guide.md` | [`docs/testing/recommendation-pipeline-testing-guide.md`](../docs/testing/recommendation-pipeline-testing-guide.md) |
| `SPEC-recommendation-postman-testing-guide.md` | [`docs/testing/recommendation-postman-testing-guide.md`](../docs/testing/recommendation-postman-testing-guide.md) |
| `tasks-indexing-file-type-router.md` | [`openspec/changes/archive/2026-08-07-indexing-file-type-router/tasks.md`](../openspec/changes/archive/2026-08-07-indexing-file-type-router/tasks.md) |
| `tasks-knowledge-graph.md` | [`openspec/changes/archive/2026-08-07-knowledge-graph-hr-76/tasks.md`](../openspec/changes/archive/2026-08-07-knowledge-graph-hr-76/tasks.md) |
| `tasks-kg-multi-agent-stage1.md` | [`openspec/changes/archive/2026-08-08-kg-multi-agent-stage1/tasks.md`](../openspec/changes/archive/2026-08-08-kg-multi-agent-stage1/tasks.md) |
| Traceability | [`openspec/TRACEABILITY.md`](../openspec/TRACEABILITY.md) |

Stub files in this directory keep old relative links working.

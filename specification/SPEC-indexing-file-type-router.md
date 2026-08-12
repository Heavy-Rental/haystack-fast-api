# Indexing Pipeline (moved)

> **This document has moved.** Canonical location: [../openspec/specs/indexing/spec.md](../openspec/specs/indexing/spec.md)

Standards: **OpenSpec** · **GitHub Spec-kit** · **OpenSPDD**

See also: [specification/README.md](./README.md) · [openspec/AGENTS.md](../openspec/AGENTS.md)

### Pointer — Call 1 response (2026-08-10)

| Topic | Canonical |
|-------|-----------|
| As-built ingest DTO | [ingest-from-project-spec contract](../openspec/specs/indexing/contracts/ingest-from-project-spec.md) |
| **As-built** needs + dates + budget summary (FR-IX-023 S1a–S1e) | Same contract + [indexing spec](../openspec/specs/indexing/spec.md) |
| **As-built S3** agent indexing gate (FR-IX-026) | [indexing spec](../openspec/specs/indexing/spec.md) · [design](../openspec/specs/indexing/design.md) · [contract execution path](../openspec/specs/indexing/contracts/ingest-from-project-spec.md) · archive [s3-agent-indexing-coordinator-gate](../openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/) |
| Feasibility | [call1-ingest-response-project-summary.md](../Feasibility_Study/call1-ingest-response-project-summary.md) · [implementation-plan Phase 3](../Feasibility_Study/implementation-plan.md) |
| Change proposal (Call 1 summary) | [openspec/changes/2026-08-10-call1-project-spec-summary/](../openspec/changes/2026-08-10-call1-project-spec-summary/) |
| Change archive (S3 gate) | [openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/](../openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/) |

**Not** ranked assets on Call 1 — that is **Call 2** `getassetrecommendations` (recommend quote).

**Portal:** React `project-spec` → **Call 1 first** (this capability), then Call 2 recommend; Call 3 chatbot optional.  
Optional Call 1 path: `INDEXING_VIA_AGENT_GATE=true` → forced non-LLM Coordinator gate (same lean DTO).  
See [openspec/AGENTS.md](../openspec/AGENTS.md) · [portal-to-haystack-mapping.md](../Feasibility_Study_Spring/portal-to-haystack-mapping.md).

### How to test (pointer — S3 / FR-IX-026)

Canonical instructions live under OpenSpec (do not fork long runbooks here):

| Topic | Link |
|-------|------|
| **Full runbook** (pytest + curl + Postman) | [openspec indexing design — How to test](../openspec/specs/indexing/design.md#how-to-test-this-capability-runbook) |
| Spec verification table | [openspec indexing spec — How to test FR-IX-026](../openspec/specs/indexing/spec.md#how-to-test-fr-ix-026--s3--verification-instructions) |
| Contract verification | [ingest contract — Verification](../openspec/specs/indexing/contracts/ingest-from-project-spec.md#verification-s3--fr-ix-026) |
| Task checklist | [S3 archive tasks](../openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/tasks.md) |
| Postman | [postman/README.md](../postman/README.md) |

**Quick start:**

```bash
cd haystack-fast-api
# Automated S3 pack
uv run pytest tests/test_indexing_tool.py -q

# Manual flag on
export INDEXING_VIA_AGENT_GATE=true
export INDEXING_EMBEDDER=mock
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# then POST .../submitprojectspecification (same lean body as flag off)
```

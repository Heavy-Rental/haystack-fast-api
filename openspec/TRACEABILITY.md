# Traceability matrix — legacy `specification/` → OpenSpec

Migration date: **2026-08-10**. Standards: **OpenSpec** · **GitHub Spec-kit** · **OpenSPDD**.

## File map

| Legacy path | New path | Notes |
|-------------|----------|--------|
| `specification/README.md` | `openspec/AGENTS.md` + `openspec/README.md` | Runtime flow, paths A–D, conflict rules |
| `specification/00-overview.md` | `openspec/project.md` | Vision, product focus, stakeholders |
| `specification/SPEC-project.md` | `openspec/project.md` | Merged identity |
| `specification/01-domain.md` | `openspec/specs/domain/spec.md` | 12 requirements + scenarios |
| `specification/SPEC-project-setup.md` | `openspec/specs/project-setup/spec.md` + `design.md` | Runbooks → design; principles → constitution |
| — | `.specify/memory/constitution.md` | Spec-kit constitution (new) |
| `specification/SPEC-indexing-file-type-router.md` | `openspec/specs/indexing/spec.md` + `design.md` + `contracts/ingest-from-project-spec.md` | FR-IX-001…022 + MIME map |
| `specification/SPEC-knowledge-graph.md` | `openspec/specs/knowledge-graph/spec.md` + `design.md` + `contracts/project-knowledge-query.md` | FR-KG-001…014 |
| `specification/SPEC-knowledge-graph.md` §10 | `docs/testing/knowledge-graph-testing-guide.md` | Verification only |
| `specification/SPEC-recommendation-intake.md` | `openspec/specs/recommendation-intake/spec.md` | FR-I-001…015 live/deferred |
| `specification/SPEC-recommendation-pipeline.md` | `openspec/specs/recommendation-pipeline/spec.md` + `design.md` | FR-010.1–8 + FR-P-001…012 |
| `specification/SPEC-dynamic-pricing.md` | `openspec/specs/dynamic-pricing/spec.md` + `design.md` | US-1…3 + feature schema in design |
| `specification/SPEC-agentic-equipment-recommendation-and-pricing.md` | `openspec/specs/equipment-recommendation/spec.md` + `design.md` | Parent FR-001…053 + design REASONS |
| `specification/SPEC-recommendation-intake-and-pipeline-front.md` | `openspec/changes/archive/2026-08-07-hr-65-intake-front/` | Historical full capture |
| `specification/SPEC-recommendation-pipeline-testing-guide.md` | `docs/testing/recommendation-pipeline-testing-guide.md` | |
| `specification/SPEC-recommendation-postman-testing-guide.md` | `docs/testing/recommendation-postman-testing-guide.md` | Deferred |
| `specification/tasks-indexing-file-type-router.md` | `openspec/changes/archive/2026-08-07-indexing-file-type-router/tasks.md` | |
| `specification/tasks-knowledge-graph.md` | `openspec/changes/archive/2026-08-07-knowledge-graph-hr-76/tasks.md` | |
| `specification/tasks-kg-multi-agent-stage1.md` | `openspec/changes/archive/2026-08-08-kg-multi-agent-stage1/tasks.md` | |
| — (S2a new) | `openspec/changes/archive/2026-08-12-s2a-ingest-idempotency-correlation/` | FR-IX-024/025 proposal + tasks |
| — (S3 new) | `openspec/changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/` | FR-IX-026 proposal + tasks |
| `app/agents/prompts.py` | `openspec/spdd/prompts/project-knowledge-agents.md` (index) | OpenSPDD first-class prompts |

## FR / requirement ID map

| Legacy ID range | Capability | OpenSpec home |
|-----------------|------------|---------------|
| FR-IX-001 … FR-IX-022 | Indexing | `specs/indexing/spec.md` |
| FR-IX-017 lean (as-built S1a) | Indexing — Call 1 lean body (`ingest_id`, `user_id`, `user_requirement_summary`) | `specs/indexing/spec.md` + contract |
| FR-IX-023 dates echo (as-built S1b) | Indexing — `tentative_*` echo request dates | `specs/indexing/spec.md` + contract |
| FR-IX-023 S1c (as-built) | Indexing — `needs_summary[]` | `specs/indexing/spec.md` + contract; impl-plan **1.4** |
| FR-IX-023 S1d (as-built) | Indexing — `expected_budget` | `specs/indexing/spec.md` + contract; impl-plan **1.5** |
| FR-IX-023 S1e (as-built) | Indexing — free-text/file date extract | `specs/indexing/spec.md` + contract; impl-plan **1.6** |
| FR-IX-023 Call 1 summary (as-built) | Full lean summary S1a–S1e | `specs/indexing/spec.md` + contract; impl-plan **1.7** |
| FR-IX-024 (as-built S2a) | Indexing — `Idempotency-Key` process-local store; same key → same `ingest_id` | `specs/indexing/spec.md` + contract; impl-plan **2.3** / S2a |
| FR-IX-025 (as-built S2a) | Indexing — `X-Correlation-Id` / `traceparent` log + echo (all routes incl. Call 2) | `specs/indexing/spec.md` + contract; impl-plan **2.4** / S2a |
| FR-IX-026 (as-built S3) | Indexing — optional Coordinator gate **[4]** + `run_indexing_from_request` behind `INDEXING_VIA_AGENT_GATE` (default off); lean body parity | `specs/indexing/spec.md` + contract + design; `app/agents/indexing_gate.py` · `app/agents/tools.py`; impl-plan **Phase 3 / S3** · **test runbook:** `specs/indexing/design.md#how-to-test-this-capability-runbook` |
| S3 agent gate (as-built) | Same as FR-IX-026 | `changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/` |
| Portal dual-hop (docs) | React project-spec → Call 1 → **Call 2 recommend quote** → React; Call 3 = chatbot Q&A | `AGENTS.md` · recommend + KG contracts · `portal-to-haystack-mapping.md` v2 · impl-plan §1.2.0 |
| S2a change archive | Idempotency + correlation tasks | `changes/archive/2026-08-12-s2a-ingest-idempotency-correlation/` |
| S3 change archive | Agent indexing tool + Coordinator gate | `changes/archive/2026-08-12-s3-agent-indexing-coordinator-gate/` |
| Portal dual-hop (superseded) | Earlier Call 2 = Q&A wording | `changes/2026-08-12-portal-dual-hop-docs/` (**superseded**) |
| Call 2 recommend + Call 3 Q&A | Breaking renumber | `changes/2026-08-12-call2-recommend-call3-qa/` |
| FR-I-016 (as-built alignment) | Intake — FR-IX-023 summary ≠ recommend | `specs/recommendation-intake/spec.md` |
| MIME map §3 | Indexing | Requirement: MIME classification map |
| FR-KG-001 … FR-KG-008 | KG Part A | `specs/knowledge-graph/spec.md` |
| FR-KG-010 … FR-KG-014 | KG Part B (011 Stage 2) | same |
| FR-I-001 … FR-I-015 | Intake | `specs/recommendation-intake/spec.md` |
| FR-010.1 … FR-010.8 | Pipeline | `specs/recommendation-pipeline/spec.md` |
| FR-P-001 … FR-P-012 | Pipeline | same |
| US-1 … US-3 + pricing FRs | Dynamic pricing | `specs/dynamic-pricing/spec.md` |
| FR-001 … FR-053 (+ NFR, demo) | Equipment recommendation parent | `specs/equipment-recommendation/spec.md` |
| Domain invariants | Domain | `specs/domain/spec.md` |
| Setup / layering / stack | Project setup | `specs/project-setup/spec.md` |
| Default pytest isolation (as-built) | Project setup + indexing FR-IX-015 + KG FR-KG-014 | `specs/project-setup/spec.md` · `tests/conftest.py` forces mock embedder dim 384; vector query/store dim match |
| FR-IX-015 embedder (query/store dim) | Indexing | `specs/indexing/spec.md` (0.8.1) |

## Standards compliance checklist

| Check | Status |
|-------|--------|
| OpenSpec `openspec/specs/<cap>/spec.md` for all capabilities | Yes |
| `### Requirement:` + `#### Scenario:` with WHEN/THEN | Yes (~119 req, ~141 scenarios) |
| Design as REASONS Canvas (OpenSPDD) for major caps | Yes |
| Spec-kit constitution | Yes (`.specify/memory/constitution.md`) |
| User stories on product-facing caps | Yes |
| Contracts for live HTTP | Yes (ingest + project-knowledge query) |
| Structured agent prompts indexed (OpenSPDD) | Yes |
| Testing guides not mislabeled as behaviour SoT | Yes (`docs/testing/`) |
| Historical HR-65 archived | Yes |
| Legacy path stubs | Yes (`specification/*.md` redirects) |

## Soft-compat

Old paths under `specification/` remain as **redirect stubs** so bookmarks and relative links resolve.

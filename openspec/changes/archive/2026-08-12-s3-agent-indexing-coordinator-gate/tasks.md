# Tasks: S3 agent indexing tool + Coordinator gate (FR-IX-026)

| Field | Value |
|-------|--------|
| **Status** | **Complete / as-built** |
| **Date** | 2026-08-12 |
| **Proposal** | [`./proposal.md`](./proposal.md) |
| **Process** | TDD red→green→refactor · BDD G/W/T in `tests/test_indexing_tool.py` |

## Spec / design first

- [x] OpenSpec FR-IX-026 + scenarios in `specs/indexing/spec.md`
- [x] Contract execution path (default vs gate) in `contracts/ingest-from-project-spec.md`
- [x] Design diagram + modules + tests table in `specs/indexing/design.md`
- [x] TRACEABILITY + AGENTS + project.md as-built notes
- [x] Archive this change set

## Implementation

- [x] Config `INDEXING_VIA_AGENT_GATE` default false + `.env.example`
- [x] Tool `run_indexing_from_request` wrapping `IndexingIngestService`
- [x] Gate graph `START → index_gate → END` (non-LLM)
- [x] API wire under flag; S2a idempotency outside producer
- [x] Failure parity MIME / KG → 400; `indexing_ok=false`

## Test pack (S3)

- [x] Tool vs service lean-field parity + session register
- [x] Tool DI uses injected service
- [x] Flag off HTTP unchanged
- [x] Flag on HTTP same lean DTO + session
- [x] Graph has `index_gate` only (no Q&A agent nodes); coordinator traces
- [x] Tool MIME hard-fail `BadRequestError`
- [x] Gate failure `indexing_ok=false` + re-raise
- [x] Flag on HTTP MIME → 400
- [x] Flag defaults false
- [x] Full default suite regression green

## Explicitly not done (follow-up)

- [ ] S3.3 SuperComponent packaging
- [ ] S7 recommend graph consuming `indexing_ok`
- [ ] Default-on gate in production

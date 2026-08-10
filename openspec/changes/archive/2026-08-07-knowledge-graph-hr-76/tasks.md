# Tasks: Knowledge Graph (HR-76)

**Input:** Knowledge-graph Part A (HR-76 assembly). Multi-agent Stage 1 is Part B — see [`../2026-08-08-kg-multi-agent-stage1/`](../2026-08-08-kg-multi-agent-stage1/).

**Normative capability:** [`openspec/specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md)

- [x] T001 SPEC + tasks
- [x] T002 Config `KG_*`
- [x] T003 `user_id` / `user_name` on request/response
- [x] T004 Stamp meta on chunks
- [x] T005 `app/pipelines/kg` bridge + generator + saver
- [x] T006 Full Ragas transforms only inside generator when flagged
- [x] T007 Hook after indexing (post-join chunks)
- [x] T008 Tests + Postman user fields
- [x] T009 Mandatory KG + hard-fail; remove `KG_ENABLED` / `KG_STRICT`

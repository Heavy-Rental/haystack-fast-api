# OpenSpec — haystack-fast-api

Behaviour source of truth for this service, aligned to:

- **OpenSpec** — `specs/<capability>/spec.md`
- **GitHub Spec-kit** — constitution, user stories, contracts, tasks
- **OpenSPDD** — REASONS Canvas designs + structured prompts
- **MADR** — numbered ADRs in [`adrs/`](./adrs/)

**Start:** [`AGENTS.md`](./AGENTS.md) (reading order, runtime flow, conflict rules).

**Portal dual-hop:** React `project-spec` → Call 1 ingest → **Call 2 recommend** (`getassetrecommendations` quote) → React. **Call 3** chatbot: `.../project-knowledge/query`. See [`AGENTS.md`](./AGENTS.md) · [`specs/portal-dual-hop/spec.md`](./specs/portal-dual-hop/spec.md) · [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) · [ADR-0003](./adrs/0003-dual-hop-call1-ingest-call2-recommend-call3-qa.md).

| Path | Purpose |
|------|---------|
| [`project.md`](./project.md) | Product identity & vision |
| [`specs/portal-dual-hop/spec.md`](./specs/portal-dual-hop/spec.md) | **Call 1 → Call 2 process** (as-built dual-hop, FR-PDH-*) |
| [`specs/`](./specs/) | Current capability behaviour |
| [`adrs/`](./adrs/) | MADR architectural decision log |
| [`changes/`](./changes/) | Active + archived change proposals |
| [`spdd/`](./spdd/) | OpenSPDD canvas index & prompt indexes |
| [`config.yaml`](./config.yaml) | Agent/project context (Spec-kit) |
| [`TRACEABILITY.md`](./TRACEABILITY.md) | Legacy path → new path FR map |
| [`../.specify/memory/constitution.md`](../.specify/memory/constitution.md) | Spec-kit constitution |

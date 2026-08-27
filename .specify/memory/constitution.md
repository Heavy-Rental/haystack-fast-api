# Constitution — haystack-fast-api

Immutable principles governing how specifications become code.  
**Stack:** GitHub Spec-kit (process gates) · OpenSpec (behavior source of truth) · OpenSPDD (design contracts & structured prompts) · MADR (architectural decisions).

## Article I — Spec-first

Specifications are the source of truth for behavior. Code implements specs; specs do not chase code after the fact.  
When behaviour is wrong: **fix the OpenSpec requirement / OpenSPDD prompt first, then update the code** (OpenSPDD).

## Article II — Behavior vs design vs tasks

| Artifact | Owns |
|----------|------|
| `openspec/specs/<cap>/spec.md` | WHAT & WHY — OpenSpec Requirements + Scenarios (testable) |
| `openspec/specs/<cap>/design.md` | HOW — OpenSPDD REASONS Canvas (Requirements, Entities, Approach, Structure, Operations, Norms, Safeguards) |
| `openspec/changes/<name>/tasks.md` | Ordered implementation checklist (Spec-kit tasks) |
| `openspec/adrs/` | WHY we chose this alternative — MADR (one decision per file) |
| Structured prompts (`app/agents/prompts.py`, `openspec/spdd/prompts/`) | Agent intent contracts (OpenSPDD) |

## Article III — Layering (non-negotiable)

1. **Routers stay thin** — no Haystack pipeline construction or SQL beyond DI and service calls.
2. **Services own orchestration** — raise `AppError` types that map to shared error JSON.
3. **Haystack pipelines live under `app.pipelines`** — not scattered across routers.
4. **New public endpoints** require an explicit feature/capability decision in OpenSpec.
5. Prefer existing error codes: `bad_request`, `unauthorized`, `not_found`, `conflict`, `internal_error`.

## Article IV — Package & runtime

1. **uv** is the only primary package manager (`pyproject.toml` + `uv.lock`).
2. Python **≥ 3.12**; ASGI entry `app.main:app` via Uvicorn.
3. **PostgreSQL** on host `postgres-haystack` is the default DB; hostname `db` MUST NOT be used. No SQLite/Compose as primary path without a constitution amendment + OpenSpec change.
4. Sync SQLAlchemy + psycopg is the running default until an explicit SDD switches to async.

## Article V — Test discipline

1. Prefer automated tests for new behaviour before or with implementation.
2. CI-safe defaults: mock embedders, stub agent modes, no required live LLM keys for default test paths.
3. Contract/integration tests for public HTTP shapes documented under `contracts/`.

## Article VI — Conflict ownership

When documents disagree on live behaviour:

| Concern | Wins |
|---------|------|
| Live `POST .../submitprojectspecification` ingest | `openspec/specs/indexing/` |
| Mandatory KG + Stage-1 multi-agent Q&A (Call 3) | `openspec/specs/knowledge-graph/` |
| Call 1 → Call 2 saga / dual-plane order | `openspec/specs/portal-dual-hop/` |
| Call 2 quote DTO + FR-010 service | `openspec/specs/recommendation-pipeline/` |
| Deferred `results_by_need` on Call 1 | `openspec/specs/recommendation-intake/` (Status: deferred) |
| Domain catalog / unit-need product rules | `openspec/specs/domain/` + `equipment-recommendation/` |
| Architectural choice among alternatives | `openspec/adrs/` |

## Article VII — OpenSPDD Norms & Safeguards

**Norms**

- Use RFC 2119 (SHALL/MUST/SHOULD/MAY) in requirements.
- Every OpenSpec requirement has ≥1 scenario (WHEN/THEN).
- Agent prompts declare Intent, Tools (allowlist), Rules, Output contract.
- Keep FR-IDs as trace tags when migrating legacy SPECs.

**Safeguards (negative space)**

- Do not invent equipment inventory, prices, or availability in Stage-1 project-knowledge agents.
- Do not treat the deferred `results_by_need` Call 1 envelope as live HTTP; Call 2 quote is the live recommend route.
- Do not add alternate primary DB, Poetry/Pipenv, or auth stacks without OpenSpec change + this constitution update.
- Do not put implementation file paths into OpenSpec requirements unless they are observable API contracts.

## Article VIII — Simplicity

Start with the lightest rigor that keeps behaviour verifiable. Scale REASONS Canvas Operations detail when risk, cross-boundary, or multi-agent work demands it.

## Article IX — Change process

1. Propose change under `openspec/changes/<name>/` (proposal → delta specs → design/REASONS → tasks; `adr.md` + numbered `openspec/adrs/` file when choosing among architectural alternatives).
2. Implement against tasks; keep prompts and specs in the same change set as code.
3. Archive: merge deltas into `openspec/specs/`; preserve change folder under `changes/archive/`.
4. Spec-kit converge: after implement, verify code against specs/tasks; fix gaps at the source.

## Amendment

Changes to this constitution require explicit rationale, maintainer review, and a recorded date in the change-control log below.

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-10 | Initial constitution from SPEC-project-setup + Spec-kit/OpenSpec/OpenSPDD alignment |
| 1.1.0 | 2026-08-27 | Host `postgres-haystack`; Call 2 quote is live HTTP; MADR ADRs in Article II/VI/IX |

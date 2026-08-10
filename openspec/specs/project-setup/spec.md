# Project Setup Specification

| Field | Value |
|-------|--------|
| **Status** | as-built |
| **Standards** | OpenSpec · Spec-kit constitution companion · OpenSPDD Norms/Safeguards |

## Purpose

Capture normative environment and setup contracts so feature work reuses PostgreSQL on host `db`, uv packaging, layering, shared errors, and env-backed configuration—without each capability restating the full stack.

## User Scenarios & Testing

### User Story 1 - Clone and run health (Priority: P1)

An engineer clones the app module, syncs with uv, runs the API, and sees health reflect Postgres connectivity.

**Independent Test:** `uv sync --all-groups` then `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` and `GET /health`.

**Acceptance Scenarios:**

1. **Given** Postgres on `db` is up, **When** `GET /health`, **Then** `{"status":"ok","database":"up"}`.
2. **Given** Postgres is unreachable, **When** `GET /health`, **Then** HTTP 200 with `status=degraded` and `database=down`.

## Requirements

### Requirement: uv is primary package manager
The project SHALL use **uv** with `pyproject.toml` + `uv.lock` as the normative installer and runner. Poetry, pip-tools, or Pipenv SHALL NOT be introduced as the primary workflow without updating this capability and the constitution.  
(Trace: setup §4.2)

#### Scenario: Install from lockfile
- **WHEN** dependencies are installed for local dev
- **THEN** `uv sync --all-groups` is the preferred command and `uv.lock` is committed

### Requirement: Python and ASGI stack
The service SHALL run on Python **≥ 3.12**, expose **FastAPI** as the ASGI app at `app.main:app`, and be served by **Uvicorn** on port **8000** by default.

#### Scenario: Default serve path
- **WHEN** the API is started for development
- **THEN** `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` is a valid invocation

### Requirement: PostgreSQL on host db
The API SHALL use the project’s existing **PostgreSQL** on hostname **`db`**. Default credentials/db name are `postgres` unless overridden via `POSTGRES_*` or `DATABASE_URL`.  
Sync SQLAlchemy + **psycopg** is the running default; **asyncpg** MAY be installed but SHALL NOT be primary without an explicit SDD.

#### Scenario: Connectivity host
- **WHEN** the app builds its default database URL
- **THEN** the host is `db` (or `DATABASE_URL` override) and the scheme matches engine type (`+psycopg` sync)

#### Scenario: Forbidden alternate primary DBs
- **WHEN** default runtime or default tests are configured
- **THEN** SQLite or other embedded databases SHALL NOT be the primary path
- **AND** Docker Compose SHALL NOT be the primary Postgres provisioner for this workspace

### Requirement: Env-backed configuration
Application settings SHALL come from environment variables (optional local `.env`; never commit production secrets). Baseline keys include `APP_NAME`, `APP_ENV`, `LOG_LEVEL`, `DATABASE_URL`, need-decomposer and LLM keys, `INDEXING_*`, and `KG_*`. Full defaults: [`.env.example`](../../../.env.example).

#### Scenario: Secrets not in VCS
- **WHEN** production secrets are required
- **THEN** they are supplied via environment, not committed as production values

### Requirement: Thin layering
Routers SHALL NOT embed Haystack pipeline construction or SQL beyond dependency injection and service calls. Services own orchestration and raise errors mapped to shared JSON. Haystack pipelines live under `app.pipelines`. New public endpoints require an explicit capability decision.

#### Scenario: Router responsibility
- **WHEN** a new HTTP endpoint is added
- **THEN** the handler delegates to a service (or equivalent) and does not construct pipelines or SQL inline

### Requirement: Shared error JSON
Error responses SHALL use `{"error":"<code>","message":"<human-readable reason>"}` via central handlers (`AppError`, validation, HTTP, unhandled 500).

#### Scenario: Validation error shape
- **WHEN** a client sends an invalid request body
- **THEN** the response includes `error` and `message` fields

### Requirement: Health endpoint
The service SHALL expose public `GET /health` reporting `status` (`ok`/`degraded`) and `database` (`up`/`down`) via sync DB check.

#### Scenario: Healthy
- **GIVEN** Postgres is reachable
- **WHEN** `GET /health`
- **THEN** response is `{"status":"ok","database":"up"}`

### Requirement: Auth deferred
No JWT/OAuth stack is required for current public health and live ingest routes until an explicit auth capability is specified. Secrets remain env-only.

#### Scenario: Health without auth
- **WHEN** a client calls `GET /health` without credentials
- **THEN** the request is accepted (public)

### Requirement: Technology stack baseline
The normative stack SHALL include: FastAPI, Uvicorn, haystack-ai, langgraph, SQLAlchemy 2.x, psycopg, asyncpg (installed), pydantic-settings, XGBoost, joblib, scikit-learn, SHAP (+ numba/llvmlite pins for Py3.12/NumPy 2.x), NumPy, Pandas, Matplotlib, Seaborn; dev: pytest, httpx, ruff, faker.

#### Scenario: Stack change requires update
- **WHEN** a dependency or primary DB strategy changes intentionally
- **THEN** this capability and change-control are updated in the same change set

## Norms (OpenSPDD)

- Prefer `uv add` / `uv sync` / `uv run` over ad-hoc pip.
- Prefer reusing existing error codes: `bad_request`, `unauthorized`, `not_found`, `conflict`, `internal_error`.
- Schema management starts simple; **Alembic** requires an explicit feature SDD.

## Safeguards (OpenSPDD)

- Do not introduce Poetry/Pipenv as primary package manager without constitution + this spec update.
- Do not switch default runtime driver from psycopg to asyncpg silently.
- Do not add GraphQL (or a second public API style) without an environment decision.
- Do not commit production secrets.

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0–1.9.0 | 2026-08-03…04 | Historical versions from SPEC-project-setup (stack, health, uv, SHAP, sklearn) |
| 2.0.0 | 2026-08-10 | Migrated to OpenSpec Requirement/Scenario + OpenSPDD Norms/Safeguards; runbooks → design.md |

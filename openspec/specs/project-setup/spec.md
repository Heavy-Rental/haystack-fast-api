# Project Setup Specification

| Field | Value |
|-------|--------|
| **Status** | as-built |
| **Standards** | OpenSpec · Spec-kit constitution companion · OpenSPDD Norms/Safeguards |

## Purpose

Capture normative environment and setup contracts so feature work reuses PostgreSQL on host `postgres-haystack` (DB `heavy_rental`), uv packaging, layering, shared errors, and env-backed configuration—without each capability restating the full stack.

## User Scenarios & Testing

### User Story 1 - Clone and run health (Priority: P1)

An engineer clones the app module, syncs with uv, runs the API, and sees health reflect Postgres connectivity.

**Independent Test:** `uv sync --all-groups` then `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` and `GET /health`.

**Acceptance Scenarios:**

1. **Given** Postgres on `postgres-haystack` is up, **When** `GET /health`, **Then** `{"status":"ok","database":"up"}`.
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

### Requirement: PostgreSQL on host postgres-haystack
The API SHALL use the project’s existing **PostgreSQL** on hostname **`postgres-haystack`** (hyphen — confirmed via DNS on 2026-08-10; hostname `db` is ambiguous on this Docker network and resolves to either `postgres-haystack` or the Spring Boot primary depending on the connection, and MUST NOT be used). Default database name is **`heavy_rental`**; default credentials are user/password `postgres` unless overridden via `POSTGRES_*` or `DATABASE_URL`.  
Sync SQLAlchemy + **psycopg** (v3) is the running default; the default constructed URL SHALL use scheme **`postgresql+psycopg://`**. **asyncpg** MAY be installed but SHALL NOT be primary without an explicit SDD.

When `DATABASE_URL` is set with a bare scheme (`postgresql://` or `postgres://`), settings SHALL normalize it to **`postgresql+psycopg://`** before engine creation. Explicit SQLAlchemy dialects (`+psycopg`, `+asyncpg`, `+psycopg2`, and other `+driver` forms) SHALL be left unchanged. Bare `postgresql://` maps to SQLAlchemy’s legacy **psycopg2** dialect; this project depends on **psycopg** v3 only and SHALL NOT require `psycopg2` as a workaround for bare URLs.

#### Scenario: Connectivity host
- **WHEN** the app builds its default database URL
- **THEN** the host is `postgres-haystack`, the database is `heavy_rental` (or `DATABASE_URL` override), and the scheme matches engine type (`+psycopg` sync)

#### Scenario: Bare DATABASE_URL uses psycopg v3
- **WHEN** `DATABASE_URL` is `postgresql://user:pass@host:5432/db` (or `postgres://…`)
- **THEN** the effective SQLAlchemy URL is `postgresql+psycopg://user:pass@host:5432/db`
- **AND** explicit schemes such as `postgresql+asyncpg://…` are not rewritten

#### Scenario: Forbidden alternate primary DBs
- **WHEN** default runtime or default tests are configured
- **THEN** SQLite or other embedded databases SHALL NOT be the primary path
- **AND** Docker Compose SHALL NOT be the primary Postgres provisioner for this workspace

### Requirement: Env-backed configuration
Application settings SHALL come from environment variables (optional local `.env`; never commit production secrets). Baseline keys include `APP_NAME`, `APP_ENV`, `LOG_LEVEL`, `DATABASE_URL`, need-decomposer and LLM keys, `INDEXING_*`, `KG_*`, `FLEET_BACKEND`, `PRICING_SCHEMA`, `PRICING_RETRAIN_*`, and `NEO4J_*`. Full defaults: [`.env.example`](../../../.env.example).

Live (non-pytest) profile MAY set `FLEET_BACKEND=sql`, `NEED_DECOMPOSER=llm`, `PRICING_SCHEMA=public`, `NEO4J_BACKEND=bolt`, `NEO4J_URI=bolt://neo4j:7687`. Those values MUST NOT leak into the default pytest suite (see isolation table). `PRICING_SCHEMA` remaps fleet + pricing ORM reads only (`schema_translate_map`); it does not change KG-1 / pgvector.

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
The normative stack SHALL include: FastAPI, Uvicorn, haystack-ai, langgraph, SQLAlchemy 2.x, psycopg, asyncpg (installed), pydantic-settings, **APScheduler 3.x** (default-disabled in-process dynamic-pricing retrain), **pgvector-haystack** (DocumentStore factory + optional I1 backend; default path is InMemory), XGBoost, joblib, scikit-learn, SHAP (+ numba/llvmlite pins for Py3.12/NumPy 2.x), NumPy, Pandas, Matplotlib, Seaborn; dev: pytest, httpx, ruff, faker.

#### Scenario: Stack change requires update
- **WHEN** a dependency or primary DB strategy changes intentionally
- **THEN** this capability and change-control are updated in the same change set

### Requirement: Academy/paid deploy vendors pack sync workers
Academy/paid Haystack compose SHALL run `postgres-haystack-sync` and `neo4j-populate` from scripts copied by Ansible (`deploy-pipeline/ansible/roles/haystack/files/`) onto `{{ compose_dir }}/workers/`. Those services SHALL NOT invoke `python -m postgres_haystack_sync` or `python -m neo4j_populate` from the FastAPI uvicorn image. Compose SHALL NOT start a `neo4j:` service on the Haystack host. Local/devcontainer compose remains the config pack. FastAPI request handlers SHALL NOT run merge-sync or SQL→Cypher ETL. **ADR-0012.**

#### Scenario: Sidecars use vendored pack scripts
- **WHEN** the Ansible haystack role is applied
- **THEN** `sync-from-primary.sh`, `populate_neo4j.py`, and `populate-neo4j-from-haystack.sh` exist under `{{ compose_dir }}/workers/`
- **AND** `postgres-haystack-sync` uses a Postgres image + bash entrypoint
- **AND** `neo4j-populate` uses a Python image + the populate wrapper
- **AND** `GET :8000/health` remains the ALB gate; worker `ps` does not fail the play

### Requirement: Default pytest suite is CI-safe and env-isolated
Default automated tests SHALL run with `uv run pytest` (or `uv run pytest tests/`) without requiring live LLM keys, external embedder APIs, or a live Pgvector connection. Shared fixtures in `tests/conftest.py` SHALL isolate host/`.env` overrides that would otherwise make the suite host-dependent. Optional `@pytest.mark.pgvector` tests MAY exist but MUST skip unless `RUN_PGVECTOR_TESTS=1` (and Postgres is available). Optional `@pytest.mark.neo4j` tests MAY exist but MUST skip unless `RUN_NEO4J_TESTS=1`.

As-built isolation (autouse fixture):

| Env forced in pytest | Value | Why |
|----------------------|-------|-----|
| `KG_ARTIFACT_DIR` | temp path under `tmp_path` | Keep KG writes out of repo `artifacts/` |
| `PROJECT_AGENT_MODE` | `stub` | Deterministic multi-agent synthesis |
| `INDEXING_EMBEDDER` | `mock` | No OpenAI / sentence-transformers at test time |
| `INDEXING_EMBEDDING_DIM` | `384` | Match mock default; avoid host dim (e.g. 768) breaking retrieval |
| `INDEXING_DOCUMENT_STORE` | `memory` (runtime default; I0+I1) | Default suite never opens Pgvector; host `pgvector` only when tests opt in |
| `RECOMMEND_VIA_AGENT_GRAPH` | `false` | Call 2 stays on MVP unless a test opts in |
| `FLEET_BACKEND` | `fake` | Default suite never opens live fleet SQL |
| `NEED_DECOMPOSER` | `stub` | Default suite never calls a live LLM decomposer |
| `PRICING_SCHEMA` | `primary_snapshot` | Default suite never translates fleet/pricing to `public` |
| `PRICING_RETRAIN_ENABLED` | `false` | Test lifespans never start a real model-training background job |
| `NEO4J_BACKEND` | `fake` | Default suite never opens live Bolt |

**As-built:** default suite needs no live Pgvector/Neo4j/LLM. `@pytest.mark.pgvector` skips unless `RUN_PGVECTOR_TESTS=1`. `@pytest.mark.neo4j` skips unless `RUN_NEO4J_TESTS=1`.  
(Trace: design.md Test runbook; knowledge-graph vector tool dim match; FR-IX-028)

#### Scenario: Full suite without host embedder env
- **GIVEN** a developer shell or `.env` sets `INDEXING_EMBEDDING_DIM` (or non-mock `INDEXING_EMBEDDER`) for local API work
- **WHEN** `uv run pytest tests/ -q` runs
- **THEN** the suite still uses mock embedder + dim **384** via conftest isolation
- **AND** tests that build query embedders from settings keep the same mode/dim as documents they write

#### Scenario: Default suite does not require live pgvector
- **WHEN** an engineer runs `uv run pytest tests/ -q` without Postgres
- **THEN** default CI has no `-m` filter requirement and live `@pytest.mark.pgvector` tests skip (or are not selected)
- **AND** `/health` tests accept both `database=up` and `database=down` without skipping

## Norms (OpenSPDD)

- Prefer `uv add` / `uv sync` / `uv run` over ad-hoc pip.
- Prefer reusing existing error codes: `bad_request`, `unauthorized`, `not_found`, `conflict`, `internal_error`.
- Schema management starts simple; **Alembic** requires an explicit feature SDD.
- Prefer host-env isolation in `tests/conftest.py` over requiring developers to unset local embedder/LLM vars before pytest.

## Safeguards (OpenSPDD)

- Do not introduce Poetry/Pipenv as primary package manager without constitution + this spec update.
- Do not switch default runtime driver from psycopg to asyncpg silently.
- Do not treat installing `psycopg2` as the fix for bare `postgresql://` URLs; normalize to `+psycopg` instead.
- Do not add GraphQL (or a second public API style) without an environment decision.
- Do not commit production secrets.
- Do not add optional pytest markers that gate default CI green without updating this capability and the CI job matrix.
- Do not write tests that hardcode an embedder dimension different from the settings the code under test reads, unless the test passes an explicit matching `Settings` (or equivalent) object.

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0–1.9.0 | 2026-08-03…04 | Historical versions from SPEC-project-setup (stack, health, uv, SHAP, sklearn) |
| 2.0.0 | 2026-08-10 | Migrated to OpenSpec Requirement/Scenario + OpenSPDD Norms/Safeguards; runbooks → design.md |
| 2.0.1 | 2026-08-10 | Document bare `DATABASE_URL` → `postgresql+psycopg` normalization (psycopg v3) |
| 2.0.2 | 2026-08-10 | Corrected hostname throughout: **`postgres-haystack`** (hyphen), not `postgres_haystack` (underscore) — confirmed via DNS on `HR-87-ml-2-d-production-db-wiring-for-period-utilization` (legacy `specification/SPEC-project-setup.md`, before it was stubbed to point here); `db` is ambiguous on this network and MUST NOT be used. `.env.example`/`app/config.py` `POSTGRES_HOSTNAME` default updated to match. |
| 2.1.0 | 2026-08-12 | **Pytest isolation as-built:** conftest forces mock embedder + dim 384 (+ stub agents / temp KG dir); default suite has no optional prereq markers; vector-tool tests must match query/store embedding dim |
| 2.2.0 | 2026-08-12 | **S5-I0:** `INDEXING_DOCUMENT_STORE` default `memory`; `pgvector-haystack` on stack for factory; default suite still no live Pgvector |
| 2.5.0 | 2026-08-13 | **Docs:** conftest also forces `NEED_DECOMPOSER=stub` + `PRICING_SCHEMA=primary_snapshot`; live `PRICING_SCHEMA=public` is host-only |
| 2.4.0 | 2026-08-13 | **S8.3:** conftest forces `NEO4J_BACKEND=fake`; optional `@pytest.mark.neo4j` (`RUN_NEO4J_TESTS=1`) |
| 2.3.0 | 2026-08-12 | **S5-I1:** optional `@pytest.mark.pgvector` + `INDEXING_CHUNK_TTL_SECONDS`; default suite still no live Pgvector |
| 2.6.0 | 2026-08-19 | **Dynamic-pricing Phase 3d:** APScheduler 3.x added to the runtime stack; `PRICING_RETRAIN_*` env controls documented; pytest forces the default-disabled scheduler off so host settings cannot start background training. |
| 2.7.0 | 2026-08-28 | **ADR-0012:** academy/paid compose vendors pack `postgres-haystack-sync` and `neo4j-populate` scripts; not `python -m` from the uvicorn image. |

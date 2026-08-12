# Project Setup Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose and Requirements. Outcomes: feature SDDs do not restate full stack; Postgres on `postgres-haystack` (DB `heavy_rental`); uv-centric install; thin routers; sync DB default until explicit async SDD.

## E — Entities

| Concept | Role |
|---------|------|
| Application module | Directory with `pyproject.toml` and `app/` |
| Settings | pydantic-settings env-backed config |
| Health check | Liveness + DB readiness |

## A — Approach

Co-locate SDD under `openspec/` next to the uv app. External shared Postgres (host `postgres-haystack`, DB `heavy_rental`) avoids Compose. Dual drivers installed (psycopg primary, asyncpg ready) without forcing async migration.

## S — Structure

```text
haystack-fast-api/                         # application module (uv root)
├── openspec/                              # SDD source of truth
├── .specify/memory/constitution.md
├── pyproject.toml / uv.lock / .python-version
├── .env.example
├── app/
│   ├── main.py, config.py
│   ├── api/          # thin routers
│   ├── core/         # db, deps, errors, exceptions
│   ├── services/
│   ├── schemas/
│   ├── pipelines/    # Haystack
│   ├── agents/       # LangGraph + OpenSPDD prompts
│   ├── models/, repositories/
│   └── …
├── tests/
├── postman/
├── ml-experiments/
└── docs/testing/
```

### Package responsibilities

| Package | Responsibility |
|---------|----------------|
| `app.main` | App factory, router inclusion, lifespan, logging |
| `app.config` | Env-backed settings; default sync `database_url` |
| `app.api` | HTTP routers only |
| `app.services` | Business orchestration |
| `app.pipelines` | Haystack pipeline construction |
| `app.schemas` | Pydantic I/O (snake_case JSON) |
| `app.models` | SQLAlchemy ORM / Base |
| `app.repositories` | DB access |
| `app.core.db` | Sync engine, session, connectivity |
| `app.core.errors` | Exception handlers → shared error JSON |
| `app.agents` | LangGraph + structured prompts (OpenSPDD) |

## O — Operations

### Install

```bash
cd haystack-fast-api
uv sync --all-groups
```

### Run (dev)

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Test

```bash
uv run pytest
# equivalent:
uv run pytest tests/ -q
```

**Default suite (as-built):** one job, no markers, no external LLM/embedder APIs, no Testcontainers. Host `.env` values for production-like embedder/LLM MUST NOT break pytest — isolation lives in `tests/conftest.py`.

| Test module | Coverage |
|-------------|----------|
| `tests/test_config.py` | Default sync `database_url`; override |
| `tests/test_health.py` | Health shape; ok/degraded (does not skip if Postgres is down) |
| `tests/conftest.py` | `TestClient` via `create_app()`; **autouse** env isolation |
| Full tree `tests/` | Capability packs (indexing, KG, pricing, recommend service, …) |

#### `tests/conftest.py` isolation (autouse)

| Env | Forced value | Purpose |
|-----|--------------|---------|
| `KG_ARTIFACT_DIR` | `tmp_path / "kg"` | Do not write into repo `artifacts/kg` |
| `PROJECT_AGENT_MODE` | `stub` | Deterministic Stage-1 synthesis |
| `INDEXING_EMBEDDER` | `mock` | Override host `openai` / `sentence-transformers` |
| `INDEXING_EMBEDDING_DIM` | `384` | Override host dims (e.g. 768); keep mock store/query aligned |

Also resets process-local ingest idempotency store and project-knowledge session registry per test, and clears `get_settings` cache.

#### Optional / future CI (TARGET only)

Feasibility docs may list `@pytest.mark.pgvector`, `@pytest.mark.neo4j`, `@pytest.mark.integration`. Those markers are **not** registered or used in the current suite. Do not document them as required prereqs for `uv run pytest` until implemented.

### Manual smoke

```bash
curl -s http://localhost:8000/health
# docs: http://localhost:8000/docs
```

### SQLAlchemy URL schemes

| Mode | Default construction | Used today? |
|------|----------------------|-------------|
| Sync | `postgresql+psycopg://…@postgres-haystack:5432/heavy_rental` | **Yes** |
| Async | `postgresql+asyncpg://…` | No (future SDD) |

`Settings.database_url` (and `_normalize_database_url` in `app/config.py`) owns the effective URL passed to `create_engine`. Bare container-style overrides are rewritten so SQLAlchemy loads **psycopg** v3, not the default **psycopg2** dialect:

| Input scheme | Effective scheme |
|--------------|------------------|
| `postgresql+psycopg://…` | Unchanged (default path) |
| `postgresql://…` / `postgres://…` | Rewritten to `postgresql+psycopg://…` |
| `postgresql+asyncpg://…` (and other explicit `+driver`) | Unchanged (async still not primary) |

Do not document installing `psycopg2` as the fix for bare URLs.

## N — Norms

- Layering rules in constitution Article III and [`spec.md`](./spec.md).
- Spec process: OpenSpec capabilities; Spec-kit constitution; OpenSPDD REASONS for design; fix prompt/spec first.
- Agent read order: `openspec/AGENTS.md` → project → constitution → capability.

## S — Safeguards

Forbidden without dedicated SDD + constitution update:

- Compose Postgres as primary; SQLite default tests; non-uv primary package managers
- Cookie-session primary auth; second API style (GraphQL); secrets in VCS
- Silent async driver switch; mandatory Alembic without feature SDD
- Requiring `psycopg2` for bare `postgresql://` `DATABASE_URL` values (normalize to `+psycopg` instead)

## Key decisions

| Decision | Rationale |
|----------|-----------|
| External Postgres on `postgres-haystack` / `heavy_rental` | Shared network already provides DB |
| uv | Fast lockfile workflow |
| FastAPI + Uvicorn | Framework + ASGI server |
| Specs under app module | Co-located agent context |
| Auth deferred | Minimal setup; feature SDD later |

## Change control

See [`spec.md`](./spec.md) change-control table (includes historical 1.0.0–1.9.0 from SPEC-project-setup).

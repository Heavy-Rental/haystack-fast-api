# Project Setup Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose and Requirements. Outcomes: feature SDDs do not restate full stack; Postgres on `db`; uv-centric install; thin routers; sync DB default until explicit async SDD.

## E — Entities

| Concept | Role |
|---------|------|
| Application module | Directory with `pyproject.toml` and `app/` |
| Settings | pydantic-settings env-backed config |
| Health check | Liveness + DB readiness |

## A — Approach

Co-locate SDD under `openspec/` next to the uv app. External shared Postgres (host `db`) avoids Compose. Dual drivers installed (psycopg primary, asyncpg ready) without forcing async migration.

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
```

| Test module | Coverage |
|-------------|----------|
| `tests/test_config.py` | Default sync `database_url`; override |
| `tests/test_health.py` | Health shape; ok/degraded |
| `tests/conftest.py` | `TestClient` via `create_app()` |

### Manual smoke

```bash
curl -s http://localhost:8000/health
# docs: http://localhost:8000/docs
```

### SQLAlchemy URL schemes

| Mode | Default construction | Used today? |
|------|----------------------|-------------|
| Sync | `postgresql+psycopg://…@db:5432/postgres` | **Yes** |
| Async | `postgresql+asyncpg://…` | No (future SDD) |

## N — Norms

- Layering rules in constitution Article III and [`spec.md`](./spec.md).
- Spec process: OpenSpec capabilities; Spec-kit constitution; OpenSPDD REASONS for design; fix prompt/spec first.
- Agent read order: `openspec/AGENTS.md` → project → constitution → capability.

## S — Safeguards

Forbidden without dedicated SDD + constitution update:

- Compose Postgres as primary; SQLite default tests; non-uv primary package managers
- Cookie-session primary auth; second API style (GraphQL); secrets in VCS
- Silent async driver switch; mandatory Alembic without feature SDD

## Key decisions

| Decision | Rationale |
|----------|-----------|
| External Postgres on `db` | Shared network already provides DB |
| uv | Fast lockfile workflow |
| FastAPI + Uvicorn | Framework + ASGI server |
| Specs under app module | Co-located agent context |
| Auth deferred | Minimal setup; feature SDD later |

## Change control

See [`spec.md`](./spec.md) change-control table (includes historical 1.0.0–1.9.0 from SPEC-project-setup).

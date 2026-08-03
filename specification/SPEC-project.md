# Specification: Project Overview

| Field | Value |
|-------|--------|
| **Document type** | SDD project overview (not a feature spec) |
| **Status** | As-built living context |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` (uv project root; this repo’s app directory) |
| **Python package** | `app` |
| **Spec location** | `specification/` (inside the application module) |
| **Audience** | Engineers and agents writing subsequent feature specs |

**Read this document first**, then the setup constitution, before implementing any new work under Specification Driven Development (SDD).

Related documents:

- [`SPEC-project-setup.md`](./SPEC-project-setup.md) — environment, stack, layout, uv workflow, Postgres, layering (normative)
- Future feature specs: `SPEC-<feature-kebab-case>.md` in this directory

---

## 1. Purpose

This specification captures the **project identity** for `haystack-fast-api` so later SDD work:

1. Knows what the repository is for at a product level.
2. Knows the **current high-level structure** and where code and specs live.
3. Knows which document owns environment and tooling truth ([`SPEC-project-setup.md`](./SPEC-project-setup.md)).
4. Keeps feature specs focused on behavior rather than restating project basics.

When this document and the codebase diverge, update them in the same change set.

---

## 2. Outcomes

When this context is followed:

- New feature SDDs do not restate project purpose unless they intentionally change it.
- Implementers and agents load the setup constitution for stack, Postgres, and uv commands.
- Domain-specific APIs and pipelines are introduced only through feature specs.
- Specs stay co-located with the application module under `specification/`.

---

## 3. Product identity

`haystack-fast-api` is a **FastAPI HTTP service** that exposes **Haystack** pipelines (for example retrieval-augmented generation, indexing, and search) over a REST API. **LangGraph** is available for graph/agent workflows. Data and visualization libraries (NumPy, Pandas, Matplotlib, Seaborn) are installed for analysis and future reporting.

### 3.1 Current product state (as-built)

| Aspect | State |
|--------|--------|
| Packaging | **uv** project (`pyproject.toml` + `uv.lock`), Python **≥ 3.12** (`.python-version` = 3.12) |
| Runtime entry | `app.main:app` (Uvicorn), port **8000** |
| Public API | `GET /health` — liveness/readiness with Postgres check (`status`, `database`) |
| Persistence (runtime) | PostgreSQL on host **`db`**; app uses **SQLAlchemy sync** + **psycopg** |
| Persistence (installed) | **asyncpg** + SQLAlchemy **asyncio** API available; not yet wired as primary session path |
| Auth | None (deferred to a future feature SDD) |
| Domain / RAG / agents | Not implemented yet; placeholders under `app/pipelines` (and LangGraph as a dependency only) |
| ML libs | **XGBoost**, **joblib** installed (no model APIs yet) |
| Explainability / viz | **SHAP**, **Matplotlib**, **Seaborn** installed (no plot/explain endpoints yet) |
| ASGI | **Uvicorn** required to serve FastAPI (already a direct dep) |

Business features (index documents, query, chat, auth, multi-tenant rules, and so on) require dedicated `SPEC-<feature>.md` documents.

Environment, packaging details, database host defaults, layering rules, and runbooks are normative in the setup constitution—not restated fully here.

---

## 4. Current project structure (summary)

Workspace path: `/workspaces/haystack-fast-api`. Application code, lockfile, and specs live in the nested application module:

```text
haystack-fast-api/                         # workspace root
└── haystack-fast-api/                     # application module (uv project root)
    ├── specification/                     # SDD specs (this directory)
    │   ├── SPEC-project.md                # this file
    │   └── SPEC-project-setup.md          # environment constitution
    ├── pyproject.toml
    ├── uv.lock
    ├── .python-version                    # 3.12
    ├── .env.example
    ├── .gitignore
    ├── README.md / BLANK_README.md / CHANGELOG.md
    ├── LICENSE.txt
    ├── images/
    ├── app/                               # installable Python package
    │   ├── __init__.py
    │   ├── main.py                        # FastAPI factory + ASGI app
    │   ├── config.py                      # pydantic-settings (env)
    │   ├── api/                           # routers (health)
    │   ├── core/                          # db, deps, exceptions, error handlers
    │   ├── services/                      # business logic (health)
    │   ├── schemas/                       # Pydantic I/O models
    │   ├── models/                        # SQLAlchemy Base (domain TBD)
    │   ├── repositories/                  # DB access (placeholder)
    │   └── pipelines/                     # Haystack pipelines (placeholder)
    └── tests/
        ├── conftest.py
        ├── test_config.py
        └── test_health.py
```

### 4.1 Package map (as-built)

| Path | Role |
|------|------|
| `app/main.py` | App factory, lifespan, router registration, ASGI `app` |
| `app/config.py` | Env-backed settings (`APP_*`, `POSTGRES_*`, optional `DATABASE_URL`); default URL uses `postgresql+psycopg://` |
| `app/api/` | Thin FastAPI routers (`GET /health`) |
| `app/api/health.py` | Health route; injects sync `Session` via `get_db` |
| `app/services/` | Orchestration (`HealthService`) |
| `app/schemas/` | Response/request models (`HealthResponse`, snake_case JSON) |
| `app/core/db.py` | Sync SQLAlchemy engine, `SessionLocal`, `get_db`, `check_database_connection` |
| `app/core/deps.py` | Shared FastAPI dependency re-exports |
| `app/core/errors.py` | Shared `{"error","message"}` exception handlers |
| `app/core/exceptions.py` | `AppError` and HTTP-mapped subclasses |
| `app/pipelines/` | Haystack wiring (empty until feature SDDs) |
| `app/models/`, `app/repositories/` | Persistence placeholders for feature work |
| `tests/` | pytest + TestClient; same Postgres defaults as the app |
| `specification/` | SDD markdown (project, setup, future features) |

Full technology stack, env tables, layering rules, and build/run commands: see [`SPEC-project-setup.md`](./SPEC-project-setup.md).

---

## 5. Document ownership

| Concern | Owner document |
|---------|----------------|
| Project purpose, structure summary, SDD entrypoint | This file (`SPEC-project.md`) |
| Stack, detailed layout, Postgres, uv, layering, non-goals | [`SPEC-project-setup.md`](./SPEC-project-setup.md) |
| Feature contracts and acceptance criteria | `SPEC-<feature-kebab-case>.md` |

Do **not** duplicate full technology tables or runbooks in this file. Link to the setup constitution instead.

---

## 6. How to run (quick reference)

Work from the application module (`haystack-fast-api/`, where `pyproject.toml` and `app/` live).

**Uvicorn** hosts the process (HTTP server). **FastAPI** exposes the endpoints on that process. Use a single **uv** command so the project venv and lockfile are used:

```bash
cd haystack-fast-api
uv sync --all-groups   # first time / after dependency changes
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000/health | Public health endpoint |
| http://localhost:8000/docs | OpenAPI / Swagger UI |
| http://localhost:8000/redoc | ReDoc |

Without `--reload` (production-style):

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Full prerequisites, command breakdown, tests, and smoke checks: see [`SPEC-project-setup.md`](./SPEC-project-setup.md) §8.

---

## 7. SDD entry workflow

Work from the application module (`haystack-fast-api/`):

```text
1. Read specification/SPEC-project.md          (this file)
2. Read specification/SPEC-project-setup.md    (environment constitution)
3. Read the relevant SPEC-<feature>.md         (when implementing a feature)
4. Implement under app/ (and tests/) against environment + feature requirements
5. Run: uv sync --all-groups && uv run pytest
6. Serve: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
7. Smoke: GET /health (and /docs) — Postgres on host db for database:up
8. Update specs if behavior or structure deliberately changes
```

---

## 8. Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-03 | Initial target-state project overview for haystack-fast-api SDD; thin identity, defers stack to SPEC-project-setup |
| 1.1.0 | 2026-08-03 | Setup implemented per SPEC-project-setup; status → as-built living context |
| 1.2.0 | 2026-08-03 | Aligned with as-built tree: specs under `haystack-fast-api/specification/`; structure summary, package map, product state (`GET /health`, Postgres on `db`) |
| 1.3.0 | 2026-08-03 | As-built refresh: dual DB drivers noted (psycopg runtime / asyncpg installed), data+LangGraph stack summary, package map detail, agent workflow |
| 1.4.0 | 2026-08-03 | Note XGBoost/joblib and Uvicorn-as-ASGI in product state; detail in SPEC-project-setup |
| 1.5.0 | 2026-08-03 | Quick-run section: uv + Uvicorn hosts FastAPI endpoints; link to setup §8 |
| 1.6.0 | 2026-08-03 | Product state: SHAP + Matplotlib/Seaborn; detail in SPEC-project-setup |

When changing project purpose, module naming, layout summary, or the SDD document set, bump this table and update dependent specs.

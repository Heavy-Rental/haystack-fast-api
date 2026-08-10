# Specification: Project Environment & Setup

| Field | Value |
|-------|--------|
| **Document type** | SDD baseline / environment constitution (not a feature spec) |
| **Status** | As-built living context |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` |
| **Python package root** | `app` (under the application module) |
| **Spec location** | `specification/` (inside the application module) |
| **Audience** | Engineers and agents writing subsequent feature specs |

**Read [`SPEC-project.md`](./SPEC-project.md) and this document** before implementing any new feature under Specification Driven Development (SDD). Feature specs assume the environment, stack, and conventions described here.

Related documents:

- [`SPEC-project.md`](./SPEC-project.md) — project identity and SDD entrypoint
- Future feature specs: `SPEC-<feature-kebab-case>.md` in this directory

---

## 1. Purpose

This specification captures the **as-built project environment and setup** so later SDD work:

1. Knows where the code lives and how packages are organized.
2. Uses the **existing PostgreSQL** service (host `postgres-haystack` — not `db`, ambiguous on this network, §5.2) and does not reintroduce Compose or embedded databases as the primary path.
3. Reuses established **layering, configuration, and error-handling** patterns.
4. Respects **configuration via environment variables**.
5. Knows how to **install dependencies with uv**, **test**, and **run** the API.

When this document and the codebase diverge, update them in the same change set.

---

## 2. Outcomes

When this context is followed:

- New feature SDDs do not restate the full stack unless they intentionally change it.
- Implementers do not add alternate databases or Docker Compose as the primary DB path for this workspace.
- Package management remains **uv**-centric (`pyproject.toml` + `uv.lock`).
- Routers stay thin; services own business rules; Haystack pipelines live under a dedicated package; shared error JSON remains consistent.
- Sync Postgres access remains the running default until an SDD wires async sessions as primary.

---

## 3. Repository layout

**As-built layout** (specs live inside the application module):

```text
haystack-fast-api/                         # workspace root
└── haystack-fast-api/                     # application module (uv project root)
    ├── specification/
    │   ├── SPEC-project.md                # project overview
    │   └── SPEC-project-setup.md          # this file (SDD baseline)
    ├── pyproject.toml                     # uv project metadata & dependencies
    ├── uv.lock                            # locked dependency graph
    ├── .python-version                    # 3.12
    ├── .env.example                       # non-secret defaults documentation
    ├── .gitignore
    ├── README.md / BLANK_README.md / CHANGELOG.md
    ├── LICENSE.txt
    ├── images/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py                        # FastAPI application entry
    │   ├── config.py                      # settings (pydantic-settings / env)
    │   ├── api/                           # FastAPI routers (health)
    │   │   ├── __init__.py                # api_router aggregation
    │   │   └── health.py
    │   ├── core/                          # exceptions, errors, deps, db (sync)
    │   │   ├── db.py
    │   │   ├── deps.py
    │   │   ├── errors.py
    │   │   └── exceptions.py
    │   ├── pipelines/                     # Haystack pipeline wiring (placeholder)
    │   ├── models/                        # SQLAlchemy Base re-export (domain TBD)
    │   ├── repositories/                  # database access (placeholder)
    │   ├── schemas/                       # Pydantic request/response models
    │   │   └── health.py
    │   └── services/                      # business services (health)
    │       └── health.py
    └── tests/
        ├── conftest.py
        ├── test_config.py
        └── test_health.py
```

**There is no `compose.yaml` as the primary database provisioner.** The database is an external shared PostgreSQL instance (host `postgres-haystack` — not `db`, ambiguous on this network, §5.2).

---

## 4. Technology stack (normative)

| Layer | Choice |
|-------|--------|
| Language | Python **3.12** (`requires-python >= 3.12`, `.python-version` = 3.12) |
| Package manager | **uv** (`pyproject.toml` + `uv.lock`) |
| Web framework | **FastAPI** |
| ASGI server | **Uvicorn** (`uvicorn[standard]`) — required to serve the FastAPI ASGI app |
| LLM / RAG framework | **deepset Haystack** (`haystack-ai`) |
| Agent graphs | **LangGraph** (`langgraph`) — dependency present; no app wiring yet |
| ML | **XGBoost**, **joblib**, **scikit-learn** |
| Model explainability | **SHAP** (`shap`) — with **numba** / **llvmlite** pins for Python 3.12 + NumPy 2.x |
| Numerical / data | **NumPy**, **Pandas** |
| Visualization | **Matplotlib**, **Seaborn** |
| Validation models | **Pydantic** (direct dep; also used by FastAPI / settings) |
| Settings | **pydantic-settings** (env-backed; optional `.env`) |
| Test data (dev) | **Faker** |
| Persistence | **SQLAlchemy 2.x** (sync runtime + **asyncio** API available) |
| Database drivers | **psycopg** (sync, **app default**) + **asyncpg** (async, installed) |
| Database | **PostgreSQL** (host `postgres-haystack` — not `db`, ambiguous on this network, §5.2) |
| HTTP testing | **httpx** + pytest / FastAPI `TestClient` |
| Lint / format | **ruff** (dev dependency) |

### 4.1 Key uv dependencies (as declared in `pyproject.toml`)

**Runtime / main**

- `fastapi`
- `uvicorn[standard]` (ASGI server; required to run the API over HTTP)
- `pydantic` (explicit direct pin; FastAPI depends on it)
- `pydantic-settings`
- `haystack-ai`
- `langgraph`
- `xgboost`
- `joblib`
- `scikit-learn` (train/test split + regression metrics; used by the dynamic-pricing model's offline training scripts under `ml-experiments/`)
- `shap`
- `numba>=0.61` (required so `shap` resolves on Python 3.12 + NumPy 2.x; bare `uv add shap` may pull ancient numba)
- `llvmlite>=0.44` (paired with modern numba)
- `numpy`
- `pandas`
- `matplotlib`
- `seaborn`
- `sqlalchemy` (includes asyncio API; `greenlet` pulled transitively)
- `psycopg[binary]` (sync driver — used by `app/core/db.py`)
- `asyncpg` (async driver — available for `create_async_engine`; not yet used by app code)

**Dev / test** (`[dependency-groups] dev`)

- `pytest`
- `httpx`
- `ruff`
- `faker`

### 4.2 Package manager constraints

1. **uv** is the normative installer and runner for this workspace.
2. Do **not** introduce Poetry, pip-tools, or Pipenv as the primary workflow without updating this document.
3. Commit `uv.lock` so environments are reproducible.
4. Prefer `uv add` / `uv sync` / `uv run` over ad-hoc `pip install`.
5. Install all groups for local dev: `uv sync --all-groups`.

---

## 5. Runtime environment

### 5.1 Application process

| Setting | Value |
|---------|--------|
| ASGI app path | `app.main:app` |
| App factory | `app.main.create_app()` |
| HTTP port | `8000` |
| Config source | Environment variables (optional local `.env`; never commit secrets) |
| Settings module | `app/config.py` (pydantic-settings) |

### 5.2 PostgreSQL (existing shared service)

The API **must** use the project's existing PostgreSQL. Connectivity is expected on hostname **`postgres-haystack`** — **not** `db`: `db` is ambiguous on this Docker network and can resolve to either `postgres-haystack` or the Spring Boot primary, depending on the connection (confirmed via DNS, 2026-08-10). Use `postgres-haystack` explicitly, or set `POSTGRES_HOSTNAME`/`DATABASE_URL` accordingly.

**Verified shared defaults** (also documented in `.env.example`):

| Setting | Env | Default |
|---------|-----|---------|
| Host | `POSTGRES_HOSTNAME` | `db` |
| Port | `POSTGRES_PORT` | `5432` |
| Database | `POSTGRES_DB` | `postgres` |
| Username | `POSTGRES_USER` | `postgres` |
| Password | `POSTGRES_PASSWORD` | `postgres` |
| Full URL (optional override) | `DATABASE_URL` | See URL schemes below |

> **Known-stale default (flagged 2026-08-10, not yet fixed):** the `POSTGRES_HOSTNAME` default above is still `db` in `.env.example` and `app/config.py` — this table documents the *current* default, not a recommendation. Until that default is corrected (a behavior change, tracked separately from this doc fix), set `POSTGRES_HOSTNAME=postgres-haystack` (or a full `DATABASE_URL`) explicitly rather than relying on it.

#### SQLAlchemy URL schemes

| Mode | Engine API | Default URL construction | Used by app today? |
|------|------------|--------------------------|--------------------|
| Sync | `create_engine` / `Session` | `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOSTNAME}:${POSTGRES_PORT}/${POSTGRES_DB}` | **Yes** (`app.config.Settings.database_url`, `app.core.db`) |
| Async | `create_async_engine` / `AsyncSession` | `postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOSTNAME}:${POSTGRES_PORT}/${POSTGRES_DB}` | **No** (dependency only; for future SDD) |

Notes:

- SQLAlchemy **async** is not a separate package; use `sqlalchemy.ext.asyncio` with the **asyncpg** driver.
- `DATABASE_URL` may override either form; the scheme must match the engine type (`+psycopg` for sync, `+asyncpg` for async).
- Connectivity check: resolve host `postgres-haystack` (not `db` — ambiguous, see above), TCP `postgres-haystack:5432`, or `SELECT 1` via either driver.

#### Environment constraints (binding for future SDD)

1. **Do not** add SQLite or other embedded databases for the default app or default tests in this environment.
2. **Do not** reintroduce Docker Compose as the primary way to provision Postgres for this workspace.
3. **Do not** hardcode a different host without updating this spec; prefer `POSTGRES_HOSTNAME=postgres-haystack` (the default, `db`, is ambiguous on this network — see §5.2 above), or a single `DATABASE_URL` override.
4. Schema management starts simple (create tables via SQLAlchemy metadata or equivalent for early iteration). Introducing **Alembic** (or another migration tool) requires an explicit feature SDD and an update to this document.
5. Switching the app’s primary session path to **async** requires an explicit feature/setup SDD update and code changes in `app/core/db.py` (and callers).

### 5.3 Application configuration (baseline)

| Setting | Env | Purpose |
|---------|-----|---------|
| Application name | `APP_NAME` | Process / OpenAPI title default (`haystack-fast-api`) |
| Environment label | `APP_ENV` | e.g. `local`, `dev`, `prod` |
| Log level | `LOG_LEVEL` | Logging verbosity (`INFO` default) |
| Database URL | `DATABASE_URL` | Optional full SQLAlchemy URL override (see 5.2) |
| Need decomposer | `NEED_DECOMPOSER` | `stub` \| `llm` (recommend path) |
| LLM | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, … | OpenAI-compatible client |
| Indexing embedder | `INDEXING_EMBEDDER` | `mock` \| `openai` \| `sentence-transformers` |
| Indexing split | `INDEXING_SPLIT_LENGTH`, `INDEXING_SPLIT_OVERLAP` | Chunking |
| Indexing models | `INDEXING_OPENAI_EMBEDDING_MODEL`, `INDEXING_ST_MODEL`, `INDEXING_EMBEDDING_DIM` | Embed config |
| Knowledge graph | `KG_ARTIFACT_DIR`, `KG_APPLY_TRANSFORMS` | Mandatory post-join KG (HR-76); transforms optional |

Full commented defaults: [`.env.example`](../.env.example). Feature detail: [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md), [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md). Sequential map: [`README.md`](./README.md).

### 5.4 Security model (summary)

Full auth contracts live in feature specs. Environment-level baseline:

| Aspect | Behavior |
|--------|----------|
| Primary style | Stateless HTTP API |
| Auth (current) | **None required** for the public health endpoint; no JWT stack until a feature SDD adds it |
| CSRF | Not applicable for pure Bearer/stateless JSON API clients once auth exists |
| Secrets | Via environment variables only; never commit production secrets |
| Public routes (current) | `GET /health` |
| Protected routes | Defined by future feature SDDs |

---

## 6. Package responsibilities

| Package / module | Responsibility |
|------------------|----------------|
| `app.main` | FastAPI app factory / entry, router inclusion, lifespan hooks, logging setup |
| `app.config` | Env-backed settings (`pydantic-settings`); builds default sync `database_url` |
| `app.api` | HTTP routers only (thin); aggregates routers into `api_router` |
| `app.services` | Business logic and orchestration (`HealthService`) |
| `app.pipelines` | Haystack pipeline construction and execution helpers (placeholder) |
| `app.schemas` | Pydantic request/response models (**snake_case** JSON by default) |
| `app.models` | SQLAlchemy ORM models / domain persistence types (`Base` re-export) |
| `app.repositories` | Database access and queries (placeholder) |
| `app.core.db` | Sync engine, session factory, `get_db`, connectivity check |
| `app.core.deps` | Shared FastAPI dependency helpers |
| `app.core.exceptions` | `AppError` hierarchy (`bad_request`, `unauthorized`, `not_found`, `conflict`, …) |
| `app.core.errors` | Central exception handlers → shared error JSON |

### 6.1 Layering rules (constitution)

1. Routers must not embed Haystack pipeline construction or SQL beyond dependency injection and calling services.
2. Services own orchestration; they raise exceptions that map to the shared error JSON.
3. Haystack components and pipelines live under `app.pipelines` (or are injected from there), not scattered across routers.
4. New **public** endpoints require an explicit decision in a feature SDD (and, once auth exists, an explicit allowlist entry).
5. Prefer reusing existing schemas and error codes (`bad_request`, `unauthorized`, `not_found`, `conflict`, `internal_error`, …).

---

## 7. Current API inventory

| Method | Path | Auth | Role |
|--------|------|------|------|
| `GET` | `/health` | Public | Liveness / readiness; reports `status` (`ok`/`degraded`) and `database` (`up`/`down`) via sync DB session |

**Example response (healthy):**

```json
{"status": "ok", "database": "up"}
```

**Example response (DB unreachable):**

```json
{"status": "degraded", "database": "down"}
```

Implementation path: `app.api.health` → `HealthService.check` → `check_database_connection` (sync).

Index, query, chat, and other RAG endpoints are **out of scope** for this setup document; they require feature SDDs.

### 7.1 Shared error response shape

```json
{
  "error": "<code>",
  "message": "<human-readable reason>"
}
```

Produced by handlers registered in `app.core.errors.register_exception_handlers` (`AppError`, validation errors, HTTP exceptions, unhandled 500).

### 7.2 Domain seed

No mandatory seed data for the initial setup. Feature SDDs may introduce seeders, document corpora, or default configuration rows.

---

## 8. Build, test, and run

Work from the **application module** (directory that contains `pyproject.toml` and `app/`):

```bash
cd haystack-fast-api
```

### 8.1 Prerequisites

1. Python **3.12** available (uv can install via `.python-version`).
2. **uv** installed and on `PATH`.
3. PostgreSQL reachable on host **`postgres-haystack`** (TCP `postgres-haystack:5432`), with defaults user/password/db `postgres` unless overridden — **not** `db`, which is ambiguous on this network (§5.2).
4. Env vars optional if defaults match the shared instance (`POSTGRES_*` / `DATABASE_URL`).

### 8.2 Install dependencies (uv)

```bash
# Create venv + install runtime and dev dependencies from lockfile
uv sync --all-groups
```

### 8.3 Run the API with uv + Uvicorn (primary)

**FastAPI** defines the ASGI application and HTTP endpoints. **Uvicorn** is the ASGI server that binds a host/port and hosts that app. **uv run** executes Uvicorn inside the project environment (no need to activate `.venv` manually).

#### Development (auto-reload)

```bash
cd haystack-fast-api

uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Production-style (no reload)

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Command breakdown

| Part | Meaning |
|------|--------|
| `uv run` | Use project venv and locked dependencies from `uv.lock` |
| `uvicorn` | ASGI server process (listens for HTTP) |
| `app.main:app` | Import path: module `app.main`, ASGI object `app` (FastAPI instance) |
| `--host 0.0.0.0` | Accept connections beyond localhost (useful in containers / devcontainers) |
| `--port 8000` | HTTP port (project default) |
| `--reload` | Restart on code changes (development only; omit in production-style runs) |

#### Once the server is running

| URL | Purpose |
|-----|---------|
| http://localhost:8000/health | Health endpoint (as-built public API) |
| http://localhost:8000/docs | OpenAPI / Swagger UI (FastAPI auto-generated) |
| http://localhost:8000/redoc | ReDoc UI |
| http://localhost:8000/openapi.json | OpenAPI schema JSON |

FastAPI exposes routes registered on `app` (today: `GET /health` via `app.api`). New routers included in `app.main` appear under the same host/port automatically.

### 8.4 First-time / clone setup

```bash
cd haystack-fast-api

# Install from committed lockfile (preferred after clone)
uv sync --all-groups

# If recreating deps from scratch (reference only; prefer lockfile):
# uv add fastapi "uvicorn[standard]" haystack-ai langgraph numpy pandas matplotlib seaborn \
#   sqlalchemy "psycopg[binary]" asyncpg pydantic-settings
# uv add --dev pytest httpx ruff

# Start the server (Uvicorn hosts; FastAPI exposes endpoints)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The **layout in section 3** and **stack in section 4** remain normative. Direct dependency versions are pinned by ranges in `pyproject.toml` and fully locked in `uv.lock`.

### 8.5 Testing notes (as-built)

```bash
uv run pytest
```

| Test module | Coverage |
|-------------|----------|
| `tests/test_config.py` | Default sync `database_url`; `DATABASE_URL` override |
| `tests/test_health.py` | `GET /health` response shape; ok/degraded when DB up/down |
| `tests/conftest.py` | `TestClient` via `create_app()` |

- Integration tests that touch persistence use the **same PostgreSQL configuration** as the app (no SQLite default).
- Health returns HTTP 200 with `degraded`/`down` when Postgres is unreachable (does not fail the process).

### 8.6 Manual smoke (examples)

With the server running (`uv run uvicorn …` in another terminal):

```bash
# Health
curl -s http://localhost:8000/health
# Expected when Postgres on postgres-haystack is up:
# {"status":"ok","database":"up"}

# OpenAPI (optional)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs

# Optional: verify Postgres with SQLAlchemy (sync)
# uv run python -c "from sqlalchemy import create_engine, text; \
#   e=create_engine('postgresql+psycopg://postgres:postgres@postgres-haystack:5432/postgres'); \
#   print(e.connect().execute(text('SELECT 1')).scalar())"

# Optional: verify asyncpg path
# uv run python -c "import asyncio; from sqlalchemy.ext.asyncio import create_async_engine; \
#   from sqlalchemy import text; \
#   async def m():
#     e=create_async_engine('postgresql+asyncpg://postgres:postgres@postgres-haystack:5432/postgres');
#     async with e.connect() as c: print((await c.execute(text('SELECT 1'))).scalar());
#     await e.dispose();
#   asyncio.run(m())"
```

---

## 9. SDD process conventions for this repository

### 9.1 Spec files

| Kind | Location | Naming |
|------|----------|--------|
| Project overview | `haystack-fast-api/specification/` | `SPEC-project.md` |
| Environment / setup constitution | `haystack-fast-api/specification/` | `SPEC-project-setup.md` (this file) |
| Feature | `haystack-fast-api/specification/` | `SPEC-<feature-kebab-case>.md` |

### 9.2 Recommended feature-spec sections

Feature SDDs should include at least:

1. Meta table (feature, status, module, related paths)
2. Outcomes
3. Scope (in / out)
4. Requirements with user stories and **GIVEN / WHEN / THEN** acceptance criteria
5. Design (API contract, components, security notes)
6. Verification (checklist, tests, manual smoke)
7. Implementation tasks
8. Key decisions / non-goals
9. Change control version table

### 9.3 Rules for feature work

1. **Load the project overview and this environment spec** before drafting or implementing a feature.
2. Do not restate stack/DB defaults unless the feature **changes** them—then update **this** file in the same PR.
3. Align with existing layering, error JSON, and package layout unless the feature SDD explicitly replaces them.
4. Prefer incremental, independently testable changes.
5. Keep feature specs as the contract; keep this file as environment truth.

### 9.4 How agents should use these docs

```text
1. Read specification/SPEC-project.md
2. Read specification/SPEC-project-setup.md
3. Read the relevant SPEC-<feature>.md
4. Implement against both (environment constraints + feature requirements)
5. Run: uv sync --all-groups && uv run pytest  (Postgres on db)
6. Serve: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
7. Smoke GET /health (and /docs) as needed
8. Update specs if behavior or environment deliberately changes
```

---

## 10. Explicit non-goals / forbidden drift

Unless a dedicated SDD says otherwise:

- No Docker Compose Postgres as the primary database for this workspace
- No SQLite (or other embedded DB) for default runtime or default tests
- No Poetry / pip-tools / Pipenv as the primary package manager (uv is normative)
- No cookie-session primary auth (when auth is introduced, prefer Bearer/token patterns unless an SDD decides otherwise)
- No second public API style (e.g. GraphQL) without an environment decision
- No secrets committed as production values; use env overrides
- No full JWT / OAuth stack until an explicit feature SDD introduces it
- No mandatory Alembic/migrations until an explicit feature SDD introduces them
- No silent switch of default runtime driver from psycopg to asyncpg without updating this document and app code

---

## 11. Key decisions (environment)

| Decision | Rationale |
|----------|-----------|
| External Postgres on host `postgres-haystack` (not `db` — ambiguous on this network, §5.2) | Shared project network already provides DB; avoid Compose conflict |
| Defaults user/password/db `postgres` | Match shared service; override via env in non-dev environments |
| uv as package manager | Fast, lockfile-based, modern Python workflow |
| FastAPI + Uvicorn | FastAPI is the framework; Uvicorn is the ASGI server needed to bind host/port and serve the app |
| XGBoost + joblib | ML training/inference and joblib utilities as direct runtime deps |
| scikit-learn added | Train/test split + regression metrics (MAE/RMSE/R²) for the dynamic-pricing model's offline training scripts under `ml-experiments/` |
| SHAP + modern numba/llvmlite | Model explainability; explicit numba/llvmlite lower bounds so resolution works with Python 3.12 and NumPy ≥ 2.5 |
| Faker as dev dependency | Fake data for tests/fixtures without shipping in production runtime by default |
| Pydantic as direct dependency | Explicit pin for models/validation; aligns with FastAPI and pydantic-settings |
| Haystack for pipelines | Project purpose: expose Haystack pipelines over HTTP |
| LangGraph coexists with Haystack | Graph/agent workflows without replacing Haystack pipelines |
| NumPy / Pandas / Matplotlib / Seaborn | Explicit data and visualization stack for analysis and future reporting |
| SQLAlchemy + psycopg as app default | Mature sync Postgres access for current health and early features |
| asyncpg installed but not primary | Unblocks SQLAlchemy asyncio without forcing a runtime migration yet |
| Specs under application `specification/` | Co-located with code; easy agent context |
| Thin project vs setup split | Overview stays short; this file owns technical truth |
| Port `8000` | FastAPI / Uvicorn convention |
| Env-overridable settings | Same artifact works across local/shared environments |
| Auth deferred | Keep initial setup minimal; introduce via feature SDD |
| Shared error JSON | Consistent client contract across handlers |

---

## 12. Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-03 | Initial target-state environment context: Python 3.12, uv, FastAPI, Haystack, Uvicorn, Postgres on `db`, SDD conventions, no Compose |
| 1.1.0 | 2026-08-03 | Setup implemented: uv project + lockfile, `app/` package layout, `GET /health`, SQLAlchemy/psycopg to Postgres on `db`, shared error handlers, pytest suite; status → as-built |
| 1.2.0 | 2026-08-03 | Layout corrected: SDD specs co-located under application module `specification/` (not workspace root) |
| 1.3.0 | 2026-08-03 | Direct runtime deps via uv: `numpy`, `pandas`, `matplotlib`, `seaborn`, `langgraph` |
| 1.4.0 | 2026-08-03 | Add `asyncpg`; document SQLAlchemy asyncio API + dual drivers (psycopg sync / asyncpg async); verified against Postgres on `db` |
| 1.5.0 | 2026-08-03 | Full as-built refresh: detailed layout, core module map, runtime vs installed async status, test inventory, clone/sync commands, Postgres defaults, non-goals for driver switch |
| 1.6.0 | 2026-08-03 | Add runtime `xgboost`, `joblib`, `pydantic`; add dev `faker`; document Uvicorn as required ASGI server for FastAPI |
| 1.7.0 | 2026-08-03 | Expand §8 runbook: uv + Uvicorn host FastAPI endpoints; command breakdown, URLs, dev vs production-style |
| 1.8.0 | 2026-08-03 | Add runtime `shap` (+ `numba>=0.61`, `llvmlite>=0.44` for Py3.12/NumPy 2.x); matplotlib/seaborn already direct |
| 1.9.0 | 2026-08-04 | Add runtime `scikit-learn` — train/test split + regression metrics for the dynamic-pricing model's Phase 1b offline training scripts (`ml-experiments/train.py`, `category_metrics.py`) |
| 1.10.0 | 2026-08-10 | Corrected Postgres connectivity guidance throughout (§1, §3, §4, §5.2, §8, §11): hostname `db` is ambiguous on this Docker network (confirmed via DNS — resolves to either `postgres-haystack` or the Spring Boot primary) and must not be used; normative guidance and example commands now say `postgres-haystack`. **`POSTGRES_HOSTNAME`'s actual default is unchanged** — `.env.example`/`app/config.py` still default to `db`; flagged inline in §5.2 as a known-stale default requiring a separate decision, not fixed in this pass. No stack/dependency change. |

When changing stack, database strategy, package manager, default security model, layout, or SDD file locations, bump this table and notify dependent feature specs.

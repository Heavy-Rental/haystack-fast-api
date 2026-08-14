# Quickstart — haystack-fast-api

FastAPI service that turns a project specification into a **lean ingest summary** (Call 1) and an **equipment quote** (Call 2). Optional Call 3 is chatbot Q&A on the same session.

This file is the short path: install → configure `.env` → start → test. Contracts live under [`openspec/`](./openspec/).

Run every command from this directory (the uv project root: `pyproject.toml`, `.env`, `app/`).

---

## Prerequisites

| Need | Notes |
|------|--------|
| Python **3.12** | See `.python-version` |
| [uv](https://docs.astral.sh/uv/) | Package manager and runner |
| Compose network (live only) | Hosts `postgres-haystack` (DB `heavy_rental`) and optionally `neo4j`. Not required for pytest or a fake-fleet smoke. |

Install uv if needed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## 1. Install

```bash
cp .env.example .env
uv sync --all-groups
```

Edit `.env` next. Never commit secrets. Optional live Neo4j driver:

```bash
uv sync --all-groups --extra neo4j
```

---

## 2. Configure `.env`

Copy [`.env.example`](./.env.example) and pick **one profile**. Process environment variables override the file.

`FLEET_BACKEND==sql` (accidental double `=`) is treated as `sql`.

### Profile A — fastest (no live DB, no LLM)

Enough for `uv run pytest`, `/health`, Call 1 ingest, and a **seed** Call 2 quote (`equipment.id` looks like `AST-*`).

| Variable | Value | Why |
|----------|--------|-----|
| `NEED_DECOMPOSER` | `stub` | Deterministic needs; no LLM key |
| `INDEXING_EMBEDDER` | `mock` | No embedding API |
| `INDEXING_DOCUMENT_STORE` | `memory` | Fresh in-memory store per ingest |
| `INDEXING_EMBEDDING_DIM` | `384` | Must match the mock embedder |
| `FLEET_BACKEND` | `fake` | Seed catalog |
| `PRICING_SCHEMA` | `primary_snapshot` | Unused on the fake path |
| `NEO4J_BACKEND` | `fake` | No Bolt |
| `RECOMMEND_VIA_AGENT_GRAPH` | `false` | Service MVP quote |
| `PROJECT_AGENT_MODE` | `stub` | Deterministic Call 3 |
| `KG_APPLY_TRANSFORMS` | `false` | Document nodes only |

Leave `POSTGRES_*` at the example defaults. Health may report `database=down` if `postgres-haystack` is not on the network; the API still starts.

### Profile B — live compose (real `assets` for Spring / Postman)

Requires `postgres-haystack` on the Docker network. Quote `equipment.id` is `assets.id` (integer PK as a string). `equipment.name` is `assets.name`. A missing assets row is omitted — the live path never invents seed `AST-*` ids.

| Variable | Typical live value | Why |
|----------|-------------------|-----|
| `POSTGRES_HOSTNAME` | `postgres-haystack` | **Not** `db` (ambiguous on this network) |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_DB` | `heavy_rental` | |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | from compose | Or set `DATABASE_URL` (`postgresql+psycopg://…`) |
| `FLEET_BACKEND` | `sql` | Read `assets` / `bookings` / `booking_items` |
| `PRICING_SCHEMA` | `public` | Fleet + pricing tables only (`schema_translate_map`). Does **not** change KG-1 or pgvector |
| `NEED_DECOMPOSER` | `llm` | One need per equipment type; requires `LLM_API_KEY` + `LLM_MODEL` |
| `LLM_BASE_URL` | `https://inference.do-ai.run/v1` | OpenAI-compatible (e.g. DigitalOcean) |
| `LLM_API_KEY` | your key | Never commit |
| `LLM_MODEL` | `router:…` or a model slug | |
| `NEO4J_BACKEND` | `bolt` | Optional KG-2 fleet graph |
| `NEO4J_URI` | `bolt://neo4j:7687` | Compose service name |
| `NEO4J_USER` / `NEO4J_PASSWORD` | from compose | Defaults in the example are `neo4j` / `neo4j` |
| `NEO4J_POPULATE_URL` | `http://neo4j-populate:8089/v1/populate` | Pack admin trigger |
| `RECOMMEND_VIA_AGENT_GRAPH` | `true` | Same quote DTO via the recommend graph; `false` stays on the service MVP |

Optional live indexing (not required for a first quote):

| Variable | When to change |
|----------|----------------|
| `INDEXING_EMBEDDER` | `openai` or `sentence-transformers` instead of `mock` |
| `INDEXING_DOCUMENT_STORE` | `pgvector` if you want a shared chunk table (`INDEXING_EMBEDDING_DIM` must match the column) |
| `KG_APPLY_TRANSFORMS` | `true` only if you want full Ragas transforms (LLM cost) |

### What each group does

| Group | Keys | Effect |
|-------|------|--------|
| App | `APP_NAME`, `APP_ENV`, `LOG_LEVEL` | Logging / identity |
| Postgres | `POSTGRES_*` or `DATABASE_URL` | Fleet, pricing, optional pgvector |
| Needs | `NEED_DECOMPOSER`, `LLM_*` | Call 1 `needs_summary[]` |
| Indexing | `INDEXING_*` | File/text → chunks → DocumentStore |
| Fleet | `FLEET_BACKEND`, `PRICING_SCHEMA` | Call 2 candidates + price reads |
| Neo4j | `NEO4J_*` | KG-2 tools (`:Asset` / `:Booking` only; never `:Document`) |
| Recommend graph | `RECOMMEND_VIA_AGENT_GRAPH` | Call 2 path (same HTTP body) |
| KG-1 files | `KG_ARTIFACT_DIR`, `KG_APPLY_TRANSFORMS` | Mandatory after ingest |

### Pytest ignores your `.env`

`tests/conftest.py` forces `FLEET_BACKEND=fake`, `NEED_DECOMPOSER=stub`, `INDEXING_EMBEDDER=mock`, `INDEXING_DOCUMENT_STORE=memory`, `PRICING_SCHEMA=primary_snapshot`, `NEO4J_BACKEND=fake`, `RECOMMEND_VIA_AGENT_GRAPH=false`. A live host `.env` will not break `uv run pytest`.

---

## 3. Start the API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| Check | URL |
|-------|-----|
| Health | http://localhost:8000/health |
| OpenAPI | http://localhost:8000/docs |

Sessions are **process-local**. Restarting uvicorn drops Call 1 `ingest_id` sessions — run Call 2 against the same process.

---

## 4. Automated tests

```bash
uv run pytest tests/ -q
```

HTML report (always written): open **`reports/pytest-report.html`** in a browser.  
Config: `pyproject.toml` → `addopts` (`pytest-html`, self-contained).  
Eval pack only: `uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q`

No live Postgres, Neo4j, or LLM required.

Optional live packs (skipped unless you opt in):

```bash
RUN_PGVECTOR_TESTS=1 uv run pytest tests/ -q -m pgvector
RUN_NEO4J_TESTS=1 uv run pytest tests/ -q -m neo4j
```

---

## 5. Manual smoke (Call 1 → Call 2)

Same uvicorn process. Replace the `ingest_id` from Call 1 in Call 2.

**Call 1 — ingest**

```bash
curl -sS -X POST http://localhost:8000/internal/v1/recommendations/submitprojectspecification \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: local-smoke' \
  -d '{
    "user_id": "user_demo",
    "project_text": "Need a forklift and a scissors lift for indoor work ~8m. Budget SGD 15000. From 1 Sep 2026 to 30 Sep 2026."
  }'
```

Expect `200` with `ingest_id`, `user_requirement_summary`, `needs_summary[]`, optional `tentative_*` / `expected_budget`, and `warnings`.

**Call 2 — quote**

```bash
curl -sS -X POST http://localhost:8000/internal/v1/recommendations/project-knowledge/getassetrecommendations \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: local-smoke' \
  -d '{
    "user_id": "user_demo",
    "ingest_id": "ing_PASTE_FROM_CALL_1"
  }'
```

Expect `200` with `quoteRef` and `items[]` (no chatbot `answer`). Live SQL: `equipment.id` is `assets.id`. Fake: seed catalog ids.

Full collection (multipart files, negatives, Call 3): [`postman/README.md`](./postman/README.md).

---

## 6. Next reading

| Doc | When |
|-----|------|
| [`openspec/AGENTS.md`](./openspec/AGENTS.md) | Reading order |
| [`docs/call1-call2-endpoint-process.md`](./docs/call1-call2-endpoint-process.md) | Full Call 1 → Call 2 process guide |
| [`docs/multi-agent-architecture.md`](./docs/multi-agent-architecture.md) | Multi-agent (indexing gate, Call 3 Q&A, Call 2 C/W/D) |
| [`docs/README.md`](./docs/README.md) | Docs index |
| [`openspec/specs/portal-dual-hop/spec.md`](./openspec/specs/portal-dual-hop/spec.md) | OpenSpec dual-hop (FR-PDH-*) |
| [`openspec/specs/indexing/contracts/ingest-from-project-spec.md`](./openspec/specs/indexing/contracts/ingest-from-project-spec.md) | Call 1 fields |
| [`openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`](./openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md) | Call 2 quote + identity |
| [`docs/testing/recommendation-pipeline-testing-guide.md`](./docs/testing/recommendation-pipeline-testing-guide.md) | Pipeline tests |
| [`Feasibility_Study_Spring/portal-to-haystack-mapping.md`](./Feasibility_Study_Spring/portal-to-haystack-mapping.md) | Spring / React hops |

---

## Pitfalls

- Hostname is **`postgres-haystack`**, not `db`.
- `PRICING_SCHEMA` remaps fleet/pricing SQL only. It does not point vectors or KG-1 at `public`.
- Live Call 2 does not fall back to seed `AST-*` when an assets row is missing.
- Do not invent fleet ids, rates, dates, or budgets in tests or fixtures.
- Call 2 without a prior Call 1 on the **same process** returns `404`.

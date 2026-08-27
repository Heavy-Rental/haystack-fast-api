# haystack-fast-api

FastAPI service that turns a project specification into a **lean ingest summary** (Call 1) and an **equipment quote** (Call 2). Optional Call 3 is chatbot Q&A on the same session.

```text
React  POST /api/recommendations/project-spec     (Spring public API)
  → Call 1  POST /internal/v1/recommendations/submitprojectspecification
  → Call 2  POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
  → optional Call 3  POST /internal/v1/recommendations/project-knowledge/query
```

## Start here

| Doc | Role |
|-----|------|
| [`QUICKSTART.md`](./QUICKSTART.md) | Install, `.env` profiles, pytest, Call 1 → Call 2 curl |
| [`openspec/AGENTS.md`](./openspec/AGENTS.md) | Spec-driven reading order, runtime flow, conflict rules |
| [`openspec/adrs/`](./openspec/adrs/) | Architectural decisions (MADR) |
| [`docs/README.md`](./docs/README.md) | Engineer guides (not behaviour SoT) |

**Normative behaviour** lives under [`openspec/specs/`](./openspec/specs/) (OpenSpec). Designs are OpenSPDD REASONS canvases in each capability `design.md`. Constitution: [`.specify/memory/constitution.md`](./.specify/memory/constitution.md).

## Stack

- Python ≥ 3.12, **uv**, FastAPI / Uvicorn (`app.main:app`, port 8000)
- Haystack 2.0 pipelines, LangGraph agents
- PostgreSQL host **`postgres-haystack`** (DB `heavy_rental`) — not `db`
- Production pricing in `app/services/pricing/` (no public renter `/predict-price`; no retrain HTTP)

## Spec standards

| Standard | Where |
|----------|--------|
| OpenSpec | `openspec/specs/<capability>/spec.md` |
| OpenSPDD | `openspec/specs/<capability>/design.md` + `openspec/spdd/` |
| MADR | `openspec/adrs/` |
| Spec-kit | `.specify/memory/constitution.md` |

When behaviour is wrong: **fix the spec or structured prompt first**, then the code.

## License

See [`LICENSE.txt`](./LICENSE.txt).

# Postman — Indexing pipeline (`/from-project-spec`)

Importable Postman artifacts for Parts 1–3 of the indexing path:

```text
classify → convert → clean → split → embed → write
```

## Files

| Path | Purpose |
|------|---------|
| `Indexing-Pipeline.postman_collection.json` | Collection with happy-path + negative requests and **Tests** scripts |
| `Indexing-Pipeline-Local.postman_environment.json` | Environment (`baseUrl`, `ingestPath`) |
| `fixtures/` | Sample upload files for multipart requests |
| `README.md` | This guide |

### Fixtures

| File | Kind | Expected `data_kind` |
|------|------|----------------------|
| `fixtures/project.txt` | Unstructured | `unstructured` |
| `fixtures/brief.md` | Unstructured | `unstructured` |
| `fixtures/needs.csv` | Structured | `structured` |
| `fixtures/needs.json` | Structured | `structured` |
| `fixtures/empty.txt` | Empty | **400** |
| `fixtures/unsupported.bin` | Unknown | **400** |

## Start the API

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm: [http://localhost:8000/health](http://localhost:8000/health) and [http://localhost:8000/docs](http://localhost:8000/docs).

Default embedder is **mock** (no API key required).

## Import into Postman

1. Open Postman → **Import**.
2. Drag in (or select):
   - `postman/Indexing-Pipeline.postman_collection.json`
   - `postman/Indexing-Pipeline-Local.postman_environment.json`
3. Top-right: select environment **Indexing Pipeline Local**.
4. Optional: confirm `baseUrl` = `http://localhost:8000`.

## Multipart file requests

After import, Postman may not resolve relative `src` paths. For each **file** request:

1. Open the request → **Body** → **form-data**.
2. Row `file` → type **File** → **Select Files**.
3. Choose the matching file under `haystack-fast-api/postman/fixtures/`.

Do **not** set `Content-Type: application/json` on multipart requests. Let Postman set `multipart/form-data` with a boundary.

## Run order (suggested)

| # | Request | Expect |
|---|---------|--------|
| 01 | GET Health | 200 (`ok` or `degraded`) |
| 02 | JSON project_text | 200, `data_kind=unstructured`, `has_embedding=true` |
| 03 | JSON no dates | 200 |
| 04 | multipart `.txt` | 200, unstructured |
| 05 | multipart `.md` | 200, unstructured |
| 06 | multipart `.csv` | 200, **structured** |
| 07 | multipart `.json` | 200, structured |
| 08 | CSV + project_text | 200, often `mixed` |
| 09–14 | Negatives | **400**, `{"error":"bad_request","message":"..."}` |

Use **Collection → Run collection** to execute all Tests tabs.

## Required identity

All requests must include **`user_id`** (JSON or form-data). Optional: **`user_name`**.

Knowledge graph is **mandatory** on successful ingest. Artifacts land under `artifacts/kg/{user_id}/kg_{ingest_id}.json`. Full Ragas transforms only if `KG_APPLY_TRANSFORMS=true` (runs inside `KnowledgeGraphGenerator`). KG failure fails the request.

## Success body checklist

```json
{
  "ingest_id": "ing_…",
  "user_id": "user_demo",
  "user_name": "Demo User",
  "data_kind": "unstructured | structured | mixed",
  "document_count": 1,
  "chunk_count": 1,
  "documents_written": 1,
  "documents": [
    {
      "content_preview": "…",
      "has_embedding": true,
      "meta": { "user_id": "user_demo", "ingest_id": "ing_…" }
    }
  ],
  "kg_built": true,
  "kg_transform_applied": false,
  "warnings": ["Indexing complete …"]
}
```

**Not present** (old recommend API): `recommendation_id`, `results_by_need`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Connection refused | Start uvicorn on port 8000 |
| Multipart 400 / empty file | Re-select fixture file; ensure file type is **File** not Text |
| Wrong Content-Type on file upload | Remove manual `Content-Type` header |
| Tests fail on `has_embedding` | Ensure server is on Part 3 code; restart uvicorn with `--reload` |
| Health `degraded` | OK without Postgres for this endpoint |

## Specs

- **Live HTTP (authoritative):** [`specification/SPEC-indexing-file-type-router.md`](../specification/SPEC-indexing-file-type-router.md)
- Tasks: [`specification/tasks-indexing-file-type-router.md`](../specification/tasks-indexing-file-type-router.md)
- Deferred recommend Postman (reattach only): [`specification/SPEC-recommendation-postman-testing-guide.md`](../specification/SPEC-recommendation-postman-testing-guide.md)
- Pipeline testing (service + live pointers): [`specification/SPEC-recommendation-pipeline-testing-guide.md`](../specification/SPEC-recommendation-pipeline-testing-guide.md)

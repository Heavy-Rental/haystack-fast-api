# Postman Testing Guide: Recommendation API

| Field | Value |
|-------|--------|
| **Document type** | SDD verification guide (Postman-focused) |
| **Status** | **Deferred (2026-08-07)** — describes pre-reroute **recommend** HTTP expectations (`rec_` / `results_by_need`). Live route is **indexing ingest**. |
| **Feature id** | `recommendation-postman-testing` |
| **Spec location** | `specification/SPEC-recommendation-postman-testing-guide.md` |
| **Endpoint** | `POST /api/v1/recommendations/from-project-spec` |
| **Live Postman (use this)** | [`../postman/README.md`](../postman/README.md) — `Indexing-Pipeline.postman_collection.json` |
| **Live API contract** | [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) |
| **Deferred recommend contract** | [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) |
| **Pipeline SDD (service)** | [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) |
| **Audience** | Engineers reattaching recommend HTTP; historical QA notes |

> **Stop:** For current as-built HTTP testing, import **`postman/Indexing-Pipeline.postman_collection.json`** and expect `ingest_id` / `data_kind` / `documents_written`.  
> Sections below remain valid **only after recommend is reattached** to this route (or a new recommend route).

---

## 1. Start the API

Before Postman:

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm:

- Browser: `http://localhost:8000/health` → **200**
- Optional: `http://localhost:8000/docs` (Swagger; same API as Postman)

Default: no auth. `NEED_DECOMPOSER=stub` is fine (no LLM key).

---

## 2. Postman environment

Create an environment (e.g. **Local recommend**):

| Variable | Initial value | Current value |
|----------|---------------|---------------|
| `baseUrl` | `http://localhost:8000` | `http://localhost:8000` |

Select this environment before sending requests.

All recommend URLs use:

```text
{{baseUrl}}/api/v1/recommendations/from-project-spec
```

---

## 3. Suggested collection structure

Create collection: **Recommendation Pipeline MVP**

```text
Recommendation Pipeline MVP
├── 01 GET Health
├── 02 POST Recommend — scissors (JSON happy path)
├── 03 POST Recommend — forklift (multipart file)
├── 04 POST Empty project_text (400)
├── 05 POST Bad dates (400)
├── 06 POST Missing body (400)
└── 07 POST No match — submarine (200, item null)
```

---

## 4. Request: GET Health

| Field | Value |
|-------|--------|
| Method | **GET** |
| URL | `{{baseUrl}}/health` |

### Expected

| Check | Value |
|-------|--------|
| Status | **200** |
| Body | `status` is `ok` or `degraded`; `database` is `up` or `down` |

Health may be `degraded` if Postgres is down; recommend still works with seed fleet.

---

## 5. Request: JSON happy path (scissors)

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `{{baseUrl}}/api/v1/recommendations/from-project-spec` |
| Headers | `Content-Type` = `application/json` |
| Body | **raw** → **JSON** |

### Body

```json
{
  "project_text": "Indoor elevated work ~8m for scissors lift",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "options": {
    "include_pricing": true
  }
}
```

### Expected

| Check | Value |
|-------|--------|
| Status | **200** |
| `recommendation_id` | Starts with `rec_` |
| `start_date` / `end_date` | Echoed |
| `results_by_need` | Array, length ≥ 1 |
| `results_by_need[0].need_id` | Present (e.g. `need_1`) |
| `results_by_need[0].item` | **Object (not null)** |
| `item.equipment_type` | `"Scissors Lift"` |
| `item.asset_id` | Present (e.g. `AST-SL-…`) |
| `item.rank` | `1` |
| `item.rationale` | Non-empty string |
| `item.pricing.currency` | `"SGD"` |
| `item.pricing.deposit_rate` | `0.3` |
| `item.pricing.daily_rate` | Number (scoped to request duration window) |
| `item.pricing.total_price` | Number (estimated total ≈ `daily_rate × duration_days`; not a fabricated weekly rate) |
| `item.pricing.weekly_rate` | **Must not appear** |
| `item.availability` | `"available"` |
| Shape | Key is **`item`**, not `items` |

### Postman Tests tab (optional)

```javascript
pm.test("Status 200", () => pm.response.to.have.status(200));
const j = pm.response.json();
pm.test("Has recommendation_id", () => pm.expect(j.recommendation_id).to.match(/^rec_/));
pm.test("Singular item present", () => {
  const row = j.results_by_need[0];
  pm.expect(row).to.have.property("item");
  pm.expect(row).to.not.have.property("items");
  pm.expect(row.item).to.not.be.null;
  pm.expect(row.item.equipment_type).to.eql("Scissors Lift");
  pm.expect(row.item.rank).to.eql(1);
});
pm.test("Pricing has total_price, not weekly_rate", () => {
  const p = j.results_by_need[0].item.pricing;
  pm.expect(p).to.not.be.null;
  pm.expect(p).to.have.property("daily_rate");
  pm.expect(p).to.have.property("total_price");
  pm.expect(p).to.not.have.property("weekly_rate");
});
```

---

## 6. Request: Multipart file upload

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `{{baseUrl}}/api/v1/recommendations/from-project-spec` |
| Body | **form-data** |

**Do not** set `Content-Type: application/json`. Postman must send `multipart/form-data` with boundary.

### form-data rows

| Key | Type | Value |
|-----|------|--------|
| `file` | **File** | Choose a local `.txt` or `.md` file |
| `start_date` | Text | `2026-09-01` (optional) |
| `end_date` | Text | `2026-09-12` (optional) |
| `project_text` | Text | (optional extra text) |
| `include_pricing` | Text | `true` (optional) |

### Example file content (`project.txt`)

```text
Need one forklift for warehouse loading bay work.
```

### Expected

| Check | Value |
|-------|--------|
| Status | **200** |
| `results_by_need[0].item` | Non-null when text matches catalog keywords |
| `item.equipment_type` | Often `"Fork Lift"` for forklift wording |
| Unsupported type (e.g. PDF) | **400** |

---

## 7. Request: Empty project_text (400)

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `{{baseUrl}}/api/v1/recommendations/from-project-spec` |
| Body raw JSON | `{"project_text": "   "}` |

### Expected

```json
{
  "error": "bad_request",
  "message": "..."
}
```

Status **400**.

---

## 8. Request: Bad dates (400)

```json
{
  "project_text": "Need an excavator",
  "start_date": "2026-09-12",
  "end_date": "2026-09-01"
}
```

### Expected

- Status **400**
- `error`: `"bad_request"`
- `message` mentions date order / validation

---

## 9. Request: Missing body (400)

```json
{}
```

### Expected

- Status **400**
- Shared error shape `error` + `message`

---

## 10. Request: No catalog match (200, item null)

```json
{
  "project_text": "Need a submarine for underwater work",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12"
}
```

### Expected

| Check | Value |
|-------|--------|
| Status | **200** |
| `results_by_need[0].item` | **`null`** |
| `results_by_need[0].warnings` | Non-empty array |

---

## 11. Optional: more free-text samples

| Name | `project_text` (snippet) | Likely type |
|------|--------------------------|-------------|
| Boom | `Facade work needs boom lift aerial access` | Boom Lift |
| Fork | `Warehouse loading needs forklift` | Fork Lift |
| Excavator | `Site trench excavation with excavator` | Excavator |
| Scissors | `Indoor elevated work scissors lift ~8m` | Scissors Lift |

Use the same URL and JSON body shape as §5; only change `project_text`.

---

## 12. Optional: LLM multi-need (Postman + env)

Postman itself does not set server env. Configure the **API process** `.env`:

```bash
NEED_DECOMPOSER=llm
LLM_BASE_URL=https://inference.do-ai.run/v1
LLM_API_KEY=dop_v1_...
LLM_MODEL=router:your-router-name
```

Restart uvicorn, then POST richer project text, e.g.:

```json
{
  "project_text": "Need two scissors lifts for indoor 8m work and one excavator for trenching.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12"
}
```

If the model returns multiple needs / quantities, expect multiple `results_by_need` rows (and possibly `need_*__u1` / `__u2`). Each row still uses singular **`item`**.

Leave `NEED_DECOMPOSER=stub` for default local testing without keys.

---

## 13. Common Postman mistakes

| Mistake | Fix |
|---------|-----|
| Multipart with Header `Content-Type: application/json` | Remove header; use **form-data** only |
| Wrong port / host | Check uvicorn and `baseUrl` |
| Expecting `items[]` array | API returns singular **`item`** |
| Expecting multi-need from long English with stub | Stub = one need from full text; use LLM mode or accept one row |
| 400 with empty string body | Send valid JSON object |
| PDF upload | MVP accepts `.txt` / `.md` only |

---

## 14. Quick checklist

- [ ] Server running on port 8000  
- [ ] Environment `baseUrl` set and selected  
- [ ] Health **200**  
- [ ] Scissors JSON → **200**, non-null `item`, Scissors Lift  
- [ ] Empty text → **400**  
- [ ] Bad dates → **400**  
- [ ] Submarine → **200**, `item` null + warnings  
- [ ] Optional: multipart `.txt` forklift → **200**  

---

## 15. Related specs

| Spec | Role |
|------|------|
| [`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md) | Full guide (pytest + curl + Postman + LLM) |
| [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) | Normative FR-010.1–8 pipeline |
| [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) | API contract |
| [`SPEC-recommendation-intake-and-pipeline-front.md`](./SPEC-recommendation-intake-and-pipeline-front.md) | LLM integration notes |

---

## 16. Change control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-05 | Initial Postman-focused testing guide for recommendation API MVP |
| **1.1.0** | 2026-08-07 | Marked **deferred**; live testing → `postman/README.md` / indexing SPEC |

When the public API path, body shape, or expected status codes change, update **this guide** and the intake/pipeline SPECs in the **same change set**.

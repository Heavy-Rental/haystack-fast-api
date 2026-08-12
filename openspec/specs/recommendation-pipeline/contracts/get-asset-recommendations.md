# Contract: Call 2 Recommend / Quote (`getassetrecommendations`)

| Field | Value |
|-------|--------|
| **Capability** | recommendation-pipeline (+ session from indexing/KG) |
| **Method / path** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Schemas** | `app/schemas/recommend_quote.py` |
| **Service** | `app/services/session_recommend.py` → `RecommendationService` (MVP) |
| **Prerequisite** | Successful Call 1 ingest session `(user_id, ingest_id)` same process |
| **Status** | **as-built MVP** (seed fleet + pricing; not full C/W/D graph yet) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · no invent |

---

## Role

**Call 2 = recommend** for the portal dual-hop after Call 1.  
Spring `POST /api/recommendations/project-spec` → Call 1 → **this Call 2** → React primary body.

Chatbot Q&A is **Call 3**: `POST .../project-knowledge/query`.

---

## Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | yes | Same as Call 1 |
| `ingest_id` | yes | From Call 1 |
| `query` | no | Optional focus / predefined prompt |
| `top_k` | no | Cap on items |

---

## Response `200`

| Field | Notes |
|-------|--------|
| `user_id`, `ingest_id`, `query` | Echo |
| `quoteRef` | Server-minted `QUO-…` (Spring may overwrite for commercial SoT) |
| `confidenceScore` | Deterministic stub score when items present |
| `days` | From session tentative dates when set |
| `estimatedTotal` | Sum of line totals when prices exist |
| `specSummary` | From Call 1 session `user_requirement_summary` |
| `rationale` | Merged item rationales (tool-backed) |
| `items[]` | Ranked equipment; `equipment.id` = catalog `asset_id` only |
| `items[].equipment.baseDailyRate` | From `predict_price` path when available |
| `warnings` | Soft issues / no-match |

### Example

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_…",
  "query": "Need scissors lift",
  "quoteRef": "QUO-A1B2C3D4",
  "confidenceScore": 0.71,
  "days": 12,
  "estimatedTotal": 2220.0,
  "specSummary": "…",
  "rationale": "…",
  "items": [
    {
      "rankOrder": 1,
      "matchScore": 1.0,
      "reason": "…",
      "lineTotal": 2220.0,
      "quantity": 1,
      "needId": "need_1__u1",
      "equipment": {
        "id": "AST-SL-001",
        "name": "Scissors Lift",
        "category": "Scissors Lift",
        "baseDailyRate": 185.0,
        "weekly": null
      }
    }
  ],
  "warnings": [],
  "recommendationId": "rec_…"
}
```

---

## Errors

| Status | When |
|--------|------|
| 404 | Session missing for `(user_id, ingest_id)` |
| 400 | Validation / recommend intake failure |

---

## Safeguards

- Do not invent `equipment.id` or rates — only seed/catalog + pricing path.  
- Empty match → `items: []` + warning.  
- Do not return Q&A `answer` on this route (use Call 3).  

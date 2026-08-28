# Contract: Call 2 Recommend / Quote (`getassetrecommendations`)

| Field | Value |
|-------|--------|
| **Capability** | recommendation-pipeline (+ session from indexing/KG) |
| **Method / path** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Schemas** | `app/schemas/recommend_quote.py` |
| **Service** | `app/services/session_recommend.py` → `RecommendationService` (default MVP) or `run_recommend_graph` when `RECOMMEND_VIA_AGENT_GRAPH=true` (S7.5) |
| **Prerequisite** | Successful Call 1 ingest session `(user_id, ingest_id)` same process |
| **Status** | **as-built** — quote DTO hydrated from `assets` when `FLEET_BACKEND=sql`; graph path optional behind flag (default off) |
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
| `confidenceScore` | Evidence-based: 0.30 need coverage + 0.20 mean matchScore + 0.20 live `assets.id` + 0.15 available + 0.10 priced + 0.05 dates; cap 0.99. `null` when no items |
| `days` | From session tentative dates when set |
| `estimatedTotal` | Sum of line totals when prices exist |
| `specSummary` | From Call 1 session `user_requirement_summary` |
| `rationale` | Joined per-item evidence reasons |
| `items[]` | Ranked equipment (see identity + field tables). Unit-need siblings that share parent `{base}` and `equipment.id` are collapsed (FR-P-013) |
| `items[].quantity` | `1` per unmerged line; after collapse, the number of grouped duplicates (3 copies → `quantity: 3`) |
| `items[].needId` | Unit-need id (`{base}` or `{base}__u{i}`); parent `{base}` when siblings sharing `equipment.id` collapse |
| `items[].matchScore` | 0..1: 0.50 category + 0.20 height cue + 0.15 available + 0.15 priced |
| `items[].reason` | Factual sentence from those signals (not Stub merge) |
| `items[].mlPredictedPrice` | Predicted **daily** rate from `pricing_client` / `predict_price` (required when item is returned) |
| `items[].equipment.baseDailyRate` | Same value as `mlPredictedPrice` (compat) |
| `warnings` | Soft issues / no-match |

### Equipment identity (do not collapse)

Internal fleet tools still use DTO `asset_id` = `assets.name` (UNIQUE). The **quote** remaps for Spring FK `recommendation_items.asset_id`.

| Layer | Field | Live `FLEET_BACKEND=sql` | CI `FLEET_BACKEND=fake` |
|-------|--------|--------------------------|-------------------------|
| Internal fleet DTO / tools | `asset_id` | `assets.name` | Seed catalog id (`AST-*`) |
| Call 2 quote | `equipment.id` | `str(assets.id)` PK | Seed catalog `asset_id` |
| Call 2 quote | `equipment.name` | `assets.name` | `equipment_type` |

Live SQL with a missing `assets` row: **omit the item + warning**. Never emit a seed `AST-*` id on that path. Seed-only picks (fake backend) MAY keep catalog `AST-*`.

### Quote `equipment` fields

| Field | Source | Notes |
|-------|--------|-------|
| `id` | `assets.id` (SQL) or seed `asset_id` | String form of the PK when live |
| `name` | `assets.name` (SQL) or `equipment_type` | |
| `category` | `asset_categories.name` / equipment type | Approved display |
| `baseDailyRate` | `predict_price` daily | Same as `mlPredictedPrice` |
| `weekly` | optional | `null` when unknown |
| `capacity` | `assets.capacity` | Top-level (not extra-only) |
| `purchaseYear` | `assets.purchase_year` | |
| `location` | `assets.location` | Omitted/`null` when the mirror has no column |
| `available` | live-hold booking overlap | `false` when busy; missing dates use today; unreadable bookings → `null` |
| `desc` | `assets.description` | |
| `platformHeight` | `assets.platform_height` | **Only** Scissors Lift / Boom Lift (`category_id` 2 or 3, or name/type containing scissor/boom). Omitted when null or non-aerial |
| `tags` | — | Empty array when unknown |
| `extra` | condition, clamp metadata, … | Optional |

**Not on quote:** `equipment.img` (Haystack does not read `asset_images`). Spring portal DTO MAY drop Haystack-only fields such as `platformHeight`.

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
      "mlPredictedPrice": 185.0,
      "equipment": {
        "id": "12",
        "name": "SL-12m-Yard-A",
        "category": "Scissors Lift",
        "baseDailyRate": 185.0,
        "weekly": null,
        "capacity": 320.0,
        "purchaseYear": 2022,
        "location": "Yard A",
        "available": true,
        "desc": "12m electric scissor",
        "platformHeight": 12.0,
        "tags": []
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
| 400 | Validation / recommend intake failure; graph flag on + `indexing_ok=false` (S7.5 gate refuse) |

---

## Safeguards

- Do not invent `equipment.id` or rates. Live SQL uses `assets.id` only when the row resolves; missing row → drop item + warning. Fake/CI MAY use seed `AST-*`.  
- Empty match → `items: []` + warning.  
- Do not return Q&A `answer` or `tool_traces` on this route (use Call 3 for Q&A; traces stay on graph state).  
- `RECOMMEND_VIA_AGENT_GRAPH` default **false**; same body when true.  
- `PRICING_SCHEMA` remaps fleet/pricing tables only (`primary_snapshot` default / CI; `public` live). It does not change KG-1 or pgvector.  
- FR-P-013: collapse unit-need siblings that share parent need + `equipment.id`. Do not merge across parent needs or distinct equipment ids. Do not put `quantity` on `RecommendationItem`. `estimatedTotal` stays the pre-collapse sum of unit line totals. Collapsed `quantity > 1` sets `equipment.available` false. Quantity-1 availability uses `bookings` + `return_records`.  

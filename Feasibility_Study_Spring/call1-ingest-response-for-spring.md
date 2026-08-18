# Call 1 ingest response — Spring consumer guide

| Field | Value |
|-------|--------|
| **Endpoint** | `POST /internal/v1/recommendations/submitprojectspecification` |
| **Version** | **2.1.0** |
| **Related** | [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md) · [`wire-contract-call1-call2.md`](./wire-contract-call1-call2.md) |

---

## 1. What Call 1 is

| Is | Is not |
|----|--------|
| Project-spec **ingest** + index + KG | Call 2 recommend quote |
| Lean FR-IX-023 summary + `ingest_id` | Call 3 chatbot `answer` |
| **Step 1** of portal submit | Sole body returned to React on submit |

**Portal:** React `POST /api/recommendations/project-spec` → Call 1 → **Call 2 recommend** → React primary body is **Call 2 quote**. Spring must persist Call 1 `user_id` + `ingest_id`.

---

## 2. Lean success body

| Field | Spring action |
|-------|---------------|
| `ingest_id` | **Must persist** — Call 2 / Call 3 |
| `user_id` | **Must persist** |
| `user_requirement_summary` | Display; from **extracted file text first**, then `project_text`. Ignore placeholder caption `"Optional caption alongside file"` |
| `tentative_*` | Optional display / rental window. Extracted when request omits dates (ISO, English months, Q3, month-only, `this/next month`). `8m` is not a date. Never invent |
| `needs_summary[]` | Optional display. Stub / LLM-empty fallback: **one need per approved type** with `equipment_hints` |
| `expected_budget` | Optional extract (`SGD8000`, `budget of 8000`, `$8000` when it looks like money). Not words-only / `$10` / `8m`. Never invent client-side |
| `warnings` | Soft issues |

---

## 3. Saga handoff

```text
React  POST /api/recommendations/project-spec
  → Call 1 200  store user_id, ingest_id
  → Call 2 200  recommend quote → React primary
  → on Call 2 5xx: retry Call 2 only; do NOT re-ingest
  → optional Call 3 chatbot: POST .../project-knowledge/query
```

Idempotency: one `Idempotency-Key` per portal submit on **Call 1 only**.

---

## 4. Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.1.0** | 2026-08-13 | File-before-text + ignore caption; multi-need; expanded date/budget extract |
| **2.0.0** | 2026-08-12 | Call 2 recommend; Call 3 chatbot |
| **1.1.0** | 2026-08-12 | Prior Call 2 as Q&A (superseded) |

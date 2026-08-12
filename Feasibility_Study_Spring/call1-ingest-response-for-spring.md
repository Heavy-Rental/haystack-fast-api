# Call 1 ingest response — Spring consumer guide

| Field | Value |
|-------|--------|
| **Endpoint** | `POST /internal/v1/recommendations/submitprojectspecification` |
| **Version** | **2.0.0** |
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
| `user_requirement_summary` | Display; optional Call 2 focus / Call 3 prompt |
| `tentative_*` | Optional display / rental window |
| `needs_summary[]` | Optional display |
| `expected_budget` | Optional; never invent client-side |
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
| **2.0.0** | 2026-08-12 | Call 2 recommend; Call 3 chatbot |
| **1.1.0** | 2026-08-12 | Prior Call 2 as Q&A (superseded) |

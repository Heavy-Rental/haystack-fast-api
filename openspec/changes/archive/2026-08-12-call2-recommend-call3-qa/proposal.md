# Proposal: Call 2 = recommend; Call 3 = chatbot Q&A

| Field | Value |
|-------|--------|
| **Status** | **Implementing / as-built MVP** |
| **Date** | 2026-08-12 |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD |

## Why

Portal `getassetrecommendations` should return **equipment recommendations + rates**, not free-form Q&A. Product decision: **Call 2 = recommend**; chatbot Q&A moves to **Call 3**.

## Journey

```text
Call 1  POST .../submitprojectspecification     → lean ingest
Call 2  POST .../project-knowledge/getassetrecommendations  → quote / items[]
Call 3  POST .../project-knowledge/query        → chatbot Q&A (answer, hits)
```

## What

| Area | Change |
|------|--------|
| `app/api/recommendations.py` | Call 2 → `SessionRecommendService`; Call 3 → Q&A |
| `app/schemas/recommend_quote.py` | Quote envelope DTO |
| `app/services/session_recommend.py` | Map FR-010 → quote |
| OpenSpec + Feasibility_Study + Spring pack | Converge |

## Safeguards

- No invent of `asset_id` or rates (tool/seed fleet only)
- Call 1 unchanged
- Q&A still dual-source project tools only

## Checklist

- [x] Runtime MVP
- [x] Tests
- [x] OpenSpec + Feasibility_Study + Feasibility_Study_Spring + specification synced

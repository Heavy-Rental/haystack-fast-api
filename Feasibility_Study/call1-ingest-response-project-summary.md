# Feasibility Study: Simplified Call 1 Ingest Response — Project-Spec Summary

| Field | Value |
|-------|--------|
| **Document type** | API / product feasibility study |
| **Status** | Complete (study only — **not implemented**) |
| **Date** | 2026-08-10 |
| **Version** | 1.0.0 |
| **Endpoint** | `POST /api/v1/recommendations/from-project-spec` |
| **Question** | Can the response body be **simplified** to a **summary of needs**, **tentative start/end dates**, and **expected budget** from the uploaded project-spec? |
| **OpenSpec** | FR-IX-023 TARGET · contract `openspec/specs/indexing/contracts/ingest-from-project-spec.md` · proposal `openspec/changes/2026-08-10-call1-project-spec-summary/` |
| **Related** | Dual-plane §2.1 Call 1 · multi-agent synthesis (Call 3) · ml-pricing |

---

## 1. Executive summary

| Question | Result |
|----------|--------|
| Can Call 1 return needs + dates + budget summary? | **GO (TARGET)** |
| As-built today? | **No** — technical ingest + `kg_*` only |
| Replace entire technical body with only three fields? | **CONDITIONAL** — keep **`ingest_id`** (+ status); nest/verbose technical fields |
| Same as Call 3 recommend (assets + rent price)? | **No** |
| `include_pricing` as budget? | **No** (boolean only) |

**Overall:** **GO** to enrich Call 1 with a **client-facing project-spec summary** after successful index + KG. Specs updated as **TARGET** (FR-IX-023); runtime not shipped.

---

## 2. As-built vs target

### As-built

```text
200 IngestFromProjectSpecResponse
  ingest_id, user_*, data_kind, counts, documents[], kg_*
```

- Request may include `start_date` / `end_date` (validated) but they are **not** echoed.
- No needs decomposition on this path.
- No budget extraction.

### Target simplified / enriched body

```text
200
  ingest_id, user_*
  needs_summary[]          ← from project-spec
  tentative_start_date     ← request preferred, else extract
  tentative_end_date
  expected_budget | null   ← extract only; never invent
  warnings[]
  (+ optional indexing/kg detail or verbose)
```

---

## 3. Feasibility of each field

| Field | Source | Feasibility |
|-------|--------|-------------|
| `needs_summary` | NeedDecomposer / LLM on project text; optional KG-1 assist | **GO** |
| `tentative_*` dates | Request body if present; else NER/LLM from text | **GO** |
| `expected_budget` | Currency/amount phrases in text | **CONDITIONAL GO** — often missing → null + warning |
| Keep `ingest_id` | Existing | **Required** for Call 2/3 |

---

## 4. Pipeline placement

```text
[index + KG hard-fail gate]
       │
       ▼
summary extraction (new)
       │
       ▼
response assembly
```

- Extraction **must not** run if index/KG fails.
- Latency: extra LLM → use stub decomposer in CI; optional async later.

---

## 5. Relationship to multi-call journey

| Call | Body focus |
|------|------------|
| **1** | **Needs summary + dates + budget** + `ingest_id` (this study) |
| **2** | Q&A answer over session |
| **3** | Ranked **assets** + **predicted rent** |

Skipping Call 2 after Call 1 remains valid once Call 3 is reattached.

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Breaking clients that parse `documents[]` | Additive fields first; compact default only with versioning |
| Hallucinated budget | Null when uncertain; source marker |
| Confusion with recommend | Spec safeguards FR-IX-023 / FR-I-016 |
| Call 1 latency | Stub path; optional feature flag |

---

## 7. Implementation phasing (later code)

| Phase | Work |
|-------|------|
| S0 | Specs + this study (**done**) |
| S1 | Schema fields + echo request dates |
| S2 | needs_summary via decomposer |
| S3 | Budget extract + warnings |
| S4 | Compact/verbose response policy |
| S5 | Mark OpenSpec as-built when shipped |

---

## 8. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial GO for simplified Call 1 summary; linked OpenSpec FR-IX-023 |

---

## 9. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Simplify Call 1 with needs + dates + budget? | **Yes (TARGET GO)** |
| Drop `ingest_id`? | **No** |
| Invent budget if missing? | **No** |
| Same as Call 3? | **No** |
| Spec status | TARGET until implemented |

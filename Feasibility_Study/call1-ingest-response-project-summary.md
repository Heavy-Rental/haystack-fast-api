# Feasibility Study: Simplified Call 1 Ingest Response — Project-Spec Summary

| Field | Value |
|-------|--------|
| **Document type** | API / product feasibility study |
| **Status** | Complete (study) — lean public body + **FR-IX-023 Call 1 summary as-built** (S1a–S1e); not Call 2 recommend quote |
| **Date** | 2026-08-11 |
| **Version** | 1.3.0 |
| **Endpoint** | `POST /internal/v1/recommendations/submitprojectspecification` |
| **Question** | What should Call 1 return for Spring/portal without over-exposing indexing/KG internals, while enabling Call 2? |
| **OpenSpec** | FR-IX-023 **as-built** (S1a–S1e) · contract `openspec/specs/indexing/contracts/ingest-from-project-spec.md` · proposal `openspec/changes/2026-08-10-call1-project-spec-summary/` |
| **Related** | Dual-plane §2.1 Call 1 · multi-agent synthesis · ml-pricing · C/W/D · [`implementation-plan.md`](./implementation-plan.md) Phase 1 · portal [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) |
| **Portal entry** | React `POST /api/recommendations/project-spec` → Call 1 then **Call 2 recommend quote** → React; Call 3 = chatbot Q&A |

---

## 1. Executive summary

| Question | Result |
|----------|--------|
| Minimal fields for Call 2 handoff? | **`ingest_id` + `user_id`** (client already knows `user_id`) |
| Client-facing requirement text without technical dump? | **GO** — `user_requirement_summary` (string) from `project_text` or extracted file content |
| Full needs + dates + budget (FR-IX-023)? | **GO (as-built)** — S1a–S1e / Phase 1.7 |
| Expose `documents[]` / `kg_*` / counts on public body? | **No** (default) — keep internal; optional verbose later |
| Same as Call 2 recommend (assets + rent price)? | **No** |
| `include_pricing` as budget? | **No** (boolean only) |

**Overall:** Call 1 public response is a **lean client-facing envelope** after successful index + KG (pipeline still runs fully for Call 2 session). Full structured `needs_summary[]` / dates / budget is **FR-IX-023 as-built**.

**Not multi-agent recommend:** Call 1 is HTTP **ingest** enrichment only. It is **not** Call 2 quote/`items[]`, not Coordinator synthesis **[8]**, not fleet/pricing **Workers**.

---

## 2. Shipping lean body + FR-IX-023 as-built

### Lean public body (shipping contract)

Required for Spring saga Call 1 → Call 2 without oversharing:

```text
200 IngestFromProjectSpecResponse (lean + FR-IX-023 as-built)
  ingest_id                      ← required for Call 2
  user_id                        ← echo
  user_requirement_summary       ← string summary of project_text or extracted multipart content
  tentative_start_date / end     ← request preferred; else free-text extract; else null
  needs_summary[]                ← need decomposer (stub default in CI)
  expected_budget | null         ← extract only; never invent
  warnings[]                     ← soft issues (may be empty)
```

**Example:**

```json
{
  "ingest_id": "ing_a1b2c3d4e5f6",
  "user_id": "user_demo",
  "user_requirement_summary": "Need a forklift and a scissors lift for indoor work ~8m. Budget SGD 15000. From 1 Sep 2026 to 30 Sep 2026.",
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-30",
  "needs_summary": [
    {
      "need_id": "need_1",
      "description": "Need a forklift",
      "equipment_hints": ["forklift"],
      "quantity": 1
    },
    {
      "need_id": "need_2",
      "description": "Need a scissors lift for indoor work ~8m",
      "equipment_hints": ["scissor lift"],
      "quantity": 1
    }
  ],
  "expected_budget": {
    "amount": 15000,
    "currency": "SGD",
    "source": "extracted"
  },
  "warnings": []
}
```

| Field | Source | Notes |
|-------|--------|-------|
| `ingest_id` | Generated `ing_` + hex | Handle for Call 2 recommend + Call 3 Q&A |
| `user_id` | Request echo | Client already sent it |
| `user_requirement_summary` | Extracted file text **before** `project_text`; ignore placeholder caption `"Optional caption alongside file"` | Not raw bytes; not LLM invent; truncate + warning if long |
| `tentative_*` | Request dates preferred; else free-text/file extract (S1e) | ISO, English months, Q3, month-only, `this/next month`, … — `8m` is not a date; never invent |
| `needs_summary[]` | Need decomposer after index+KG | Stub / LLM-empty fallback: **one need per approved type** via `equipment_hints`; stub default in CI |
| `expected_budget` | Currency/amount phrases only | `SGD8000`, `SGD 8k`, cue + number, `$8000` when it looks like money. Not words-only / `$10` / `8m`. Never invent |
| `warnings` | Conversion / truncation / missing extract soft issues | Empty when none |

**Internal (not on public body):** DocumentStore write, KG-1 build, session registry, chunk previews, `kg_artifact_path`, counts, `data_kind`, etc. — still **executed** so Call 2 recommend + Call 3 Q&A work.

---

## 3. Feasibility of each field

| Field | Source | Feasibility |
|-------|--------|-------------|
| `ingest_id` | Existing | **Required** for Call 2/3 |
| `user_id` | Request echo | **Required** (lean) |
| `user_requirement_summary` | project_text or extracted docs | **GO (as-built)** |
| `needs_summary[]` | NeedDecomposer / LLM | **GO (as-built S1c)** |
| `tentative_*` dates | Request preferred; else extract | **GO (as-built S1b+S1e)** |
| `expected_budget` | Currency phrases only | **GO (as-built S1d)** — null + warning if uncertain |

---

## 4. Pipeline placement

```text
[index + KG hard-fail gate]     ← still mandatory
       │
       ▼
user_requirement_summary        ← from project_text or extracted content
tentative_* / needs / budget    ← FR-IX-023 as-built (S1b–S1e)
       │
       ▼
lean response assembly          ← no documents[] / kg_* on public body
```

- Summary extraction **must not** run if index/KG fails (no partial “success” without session).
- Prefer **deterministic** summary / extractors for CI; optional LLM decomposer via config.

---

## 5. Relationship to multi-call journey

| Call | Route | Body focus |
|------|-------|------------|
| **1** | `POST /internal/v1/recommendations/submitprojectspecification` | Lean FR-IX-023: **`ingest_id` + `user_id` + summary + dates + needs + budget** |
| **2** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` | Q&A: needs `user_id` + `ingest_id` + `query` |
| **3** | Future multi-agent recommend HTTP | Ranked **assets** + **predicted rent** |

Portal submit uses Call 1 then Call 2 recommend; Call 3 chatbot is optional.

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Clients that parsed technical `documents[]` / `kg_*` | Lean is intentional; Spring should use lean fields only |
| Hallucinated budget or dates | Null when uncertain; source marker; never invent |
| Confusion with recommend | Spec safeguards FR-IX-023 / FR-I-016; path is ingest not Call 2 quote |
| Call 1 latency | Deterministic summary + extractors; stub decomposer default |

---

## 7. Implementation phasing

| Phase | Work | Notes |
|-------|------|--------|
| S0 | Specs + this study | Done |
| **S1a (lean)** | `ingest_id`, `user_id`, `user_requirement_summary`, `warnings` | **Done** |
| **S1b** | Echo request dates as `tentative_*` | **Done** |
| **S1c** | `needs_summary[]` via decomposer | **Done** |
| **S1d** | `expected_budget` extract; never invent | **Done** |
| **S1e** | Free-text / file date extract when request omits dates | **Done** |
| **1.7** | Mark full FR-IX-023 as-built (OpenSpec + Postman) | **Done** |

**FR-IX-023 order:** S1c → S1d → **S1e** → 1.7. Free-text dates are **not** part of S1b.

See [`implementation-plan.md`](./implementation-plan.md) Phase 1 (v3.4.0+).

---

## 8. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial GO for simplified Call 1 summary; linked OpenSpec FR-IX-023 |
| **1.0.1** | 2026-08-11 | Clarify Call 1 ≠ multi-agent recommend synthesis / Workers |
| **1.1.0** | 2026-08-11 | Lean public body: `ingest_id` + `user_id` + `user_requirement_summary`; internal path `/internal/v1/.../submitprojectspecification`; full FR-IX-023 remains TARGET |
| **1.1.1** | 2026-08-11 | FR-IX-023 order: S1c → S1d → **S1e free-text dates** (after S1d) → 1.7 as-built; aligns with implementation-plan v3.4.0 |
| **1.2.0** | 2026-08-11 | **S1e + 1.7 shipped:** free-text date extract; full FR-IX-023 Call 1 summary **as-built** in OpenSpec + Postman |
| **1.3.0** | 2026-08-13 | File-before-text + ignore caption; multi-need hint split; expanded date/budget patterns (not words-only / `$10` / `8m`) |
| **1.2.2** | 2026-08-12 | Cross-link: default pytest isolation (mock embedder dim 384, no optional markers) — [`implementation-plan.md`](./implementation-plan.md) §7.0 |

---

## 9. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Lean public Call 1 body? | **Yes** — `ingest_id`, `user_id`, `user_requirement_summary`, `warnings` |
| Expose indexing/KG technical fields by default? | **No** |
| Full needs + dates + budget? | **Yes (TARGET GO)** later |
| Drop `ingest_id`? | **No** |
| Invent budget if missing? | **No** |
| Same as Call 2 recommend? | **No** |

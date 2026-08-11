# Feasibility Study: Simplified Call 1 Ingest Response — Project-Spec Summary

| Field | Value |
|-------|--------|
| **Document type** | API / product feasibility study |
| **Status** | Complete (study) — **lean public body is the shipping contract**; full FR-IX-023 still TARGET |
| **Date** | 2026-08-11 |
| **Version** | 1.1.0 |
| **Endpoint** | `POST /internal/v1/recommendations/submitprojectspecification` |
| **Question** | What should Call 1 return for Spring/portal without over-exposing indexing/KG internals, while enabling Call 2? |
| **OpenSpec** | FR-IX-023 TARGET (full) · contract `openspec/specs/indexing/contracts/ingest-from-project-spec.md` · proposal `openspec/changes/2026-08-10-call1-project-spec-summary/` |
| **Related** | Dual-plane §2.1 Call 1 · multi-agent synthesis (Call 3) · ml-pricing · C/W/D roles (Call 3 only) · [`implementation-plan.md`](./implementation-plan.md) Phase 1 |

---

## 1. Executive summary

| Question | Result |
|----------|--------|
| Minimal fields for Call 2 handoff? | **`ingest_id` + `user_id`** (client already knows `user_id`) |
| Client-facing requirement text without technical dump? | **GO** — `user_requirement_summary` (string) from `project_text` or extracted file content |
| Full needs + dates + budget (FR-IX-023)? | **GO (TARGET)** — later increment on top of lean body |
| Expose `documents[]` / `kg_*` / counts on public body? | **No** (default) — keep internal; optional verbose later |
| Same as Call 3 recommend (assets + rent price)? | **No** |
| `include_pricing` as budget? | **No** (boolean only) |

**Overall:** Call 1 public response is a **lean client-facing envelope** after successful index + KG (pipeline still runs fully for Call 2 session). Full structured `needs_summary[]` / dates / budget remains **FR-IX-023 TARGET**.

**Not multi-agent recommend:** Call 1 is HTTP **ingest response** enrichment (service path, or Coordinator **[4]** gate when agent-fronted). It is **not** Coordinator synthesis **[8]**, not fleet/pricing **Workers**, and not Call 3 `results_by_need`.

**Not multi-agent recommend:** Call 1 is HTTP **ingest response** enrichment (service path, or Coordinator **[4]** gate when agent-fronted). It is **not** Coordinator synthesis **[8]**, not fleet/pricing **Workers**, and not the same as Call 3 `results_by_need`.

---

## 2. Shipping lean body vs full TARGET

### Lean public body (shipping contract)

Required for Spring saga Call 1 → Call 2 without oversharing:

```text
200 IngestFromProjectSpecResponse (lean)
  ingest_id                      ← required for Call 2
  user_id                        ← echo
  user_requirement_summary       ← string summary of project_text or extracted multipart content
  warnings[]                     ← soft issues (may be empty)
```

**Example:**

```json
{
  "ingest_id": "ing_a1b2c3d4e5f6",
  "user_id": "user_demo",
  "user_requirement_summary": "Indoor elevated work ~8m; need scissors lift on soft clay site for fit-out.",
  "warnings": []
}
```

| Field | Source | Notes |
|-------|--------|-------|
| `ingest_id` | Generated `ing_` + hex | **Only** server-generated handle Call 2 needs |
| `user_id` | Request echo | Client already sent it |
| `user_requirement_summary` | Deterministic summary of `project_text` **or** extracted file text after conversion | Not raw bytes; not LLM invent; truncate + warning if long |
| `warnings` | Conversion / truncation soft issues | Empty when none |

**Internal (not on public body):** DocumentStore write, KG-1 build, session registry, chunk previews, `kg_artifact_path`, counts, `data_kind`, etc. — still **executed** so Call 2 works.

### Full TARGET (FR-IX-023 — later)

```text
200 (future enrichment of lean body)
  ingest_id, user_id
  user_requirement_summary       ← may remain or be superseded by structured needs
  needs_summary[]                ← decomposer / LLM
  tentative_start_date / end     ← request preferred, else extract
  expected_budget | null         ← extract only; never invent
  warnings[]
```

---

## 3. Feasibility of each field

| Field | Source | Feasibility |
|-------|--------|-------------|
| `ingest_id` | Existing | **Required** for Call 2/3 |
| `user_id` | Request echo | **Required** (lean) |
| `user_requirement_summary` | project_text or extracted docs | **GO** (deterministic first) |
| `needs_summary[]` | NeedDecomposer / LLM | **GO (TARGET)** |
| `tentative_*` dates | Request preferred; else extract | **GO (TARGET)** |
| `expected_budget` | Currency phrases only | **CONDITIONAL GO** — null + warning if uncertain |

---

## 4. Pipeline placement

```text
[index + KG hard-fail gate]     ← still mandatory
       │
       ▼
user_requirement_summary        ← from project_text or extracted content
       │
       ▼
lean response assembly          ← no documents[] / kg_* on public body
```

- Summary extraction **must not** run if index/KG fails (no partial “success” without session).
- Prefer **deterministic** summary for CI; optional LLM rewrite later.
- Structured `needs_summary` / budget = later phase after lean ships.

---

## 5. Relationship to multi-call journey

| Call | Route | Body focus |
|------|-------|------------|
| **1** | `POST /internal/v1/recommendations/submitprojectspecification` | Lean: **`ingest_id` + `user_id` + `user_requirement_summary`** |
| **2** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` | Q&A: needs `user_id` + `ingest_id` + `query` |
| **3** | Future multi-agent recommend HTTP | Ranked **assets** + **predicted rent** |

Skipping Call 2 after Call 1 remains valid once Call 3 is reattached.

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Clients that parsed technical `documents[]` / `kg_*` | Lean is intentional; Spring should use lean fields only |
| Hallucinated budget (full TARGET) | Null when uncertain; source marker |
| Confusion with recommend | Spec safeguards FR-IX-023 / FR-I-016; path is ingest not Call 3 |
| Call 1 latency | Deterministic summary; stub decomposer when structured needs land |

---

## 7. Implementation phasing

| Phase | Work |
|-------|------|
| S0 | Specs + this study |
| **S1a (lean)** | Schema + service: `ingest_id`, `user_id`, `user_requirement_summary`, `warnings`; no technical public fields |
| S1b | Echo request dates (optional) |
| S1c | `needs_summary` via decomposer (FR-IX-023) |
| S1d | Budget extract + warnings |
| S1e | Mark full FR-IX-023 as-built when shipped |

See [`implementation-plan.md`](./implementation-plan.md) Phase 1 / Stage S1.

---

## 8. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial GO for simplified Call 1 summary; linked OpenSpec FR-IX-023 |
| **1.0.1** | 2026-08-11 | Clarify Call 1 ≠ multi-agent recommend synthesis / Workers |
| **1.1.0** | 2026-08-11 | Lean public body: `ingest_id` + `user_id` + `user_requirement_summary`; internal path `/internal/v1/.../submitprojectspecification`; full FR-IX-023 remains TARGET |

---

## 9. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Lean public Call 1 body? | **Yes** — `ingest_id`, `user_id`, `user_requirement_summary`, `warnings` |
| Expose indexing/KG technical fields by default? | **No** |
| Full needs + dates + budget? | **Yes (TARGET GO)** later |
| Drop `ingest_id`? | **No** |
| Invent budget if missing? | **No** |
| Same as Call 3? | **No** |

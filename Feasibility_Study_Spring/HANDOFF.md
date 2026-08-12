# Handoff — copy this package into the Spring Boot project

| Field | Value |
|-------|--------|
| **Package** | `Feasibility_Study_Spring/` |
| **Version** | **2.0.0** |
| **Date** | 2026-08-12 |

---

## 1. Copy

```bash
# Example destinations — pick one that matches your Spring repo layout
cp -R Feasibility_Study_Spring /path/to/spring-boot/docs/Feasibility_Study
# or
cp -R Feasibility_Study_Spring /path/to/spring-boot/Feasibility_Study
```

Optional: rename the folder to `Feasibility_Study` inside Spring so engineers have a familiar name. Keep internal relative links (they stay within the package).

---

## 2. Tickets / PRs (S2b)

Use [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) and [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md):

| PR | Content |
|----|---------|
| **S2b-1** | `HaystackRecommenderClient` + properties + timeouts + DTOs + WireMock happy path |
| **S2b-2** | Resilience4j CB + bulkhead + retry-with-same-`Idempotency-Key` (Call 1 only) |
| **S2b-3** | Correlation propagation (may fold into S2b-1) |
| **S2b-4** | Portal `project-spec` saga: **Call 1 → Call 2 recommend quote** → React; optional Call 3 chatbot; no re-ingest on Call 2 fail |
| **S2b-5** | Ops runbook + config docs |

**Minimum combine:** S2b-1 + S2b-2 + headers in one PR; portal dual-hop saga second; docs third.

---

## 3. Preconditions

- [ ] Confirm **S2a** available on target haystack environment before enabling **production** Call 1 retries ([`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md))
- [ ] Agree **max multipart size** across gateway, Spring WebClient codec, and FastAPI/proxy
- [ ] Agree **timeout matrix** (ingest ≫ recommend ≫ Q&A ≫ health) with ops
- [ ] Plan **sticky session / single instance** for Call 1→2 until shared session (Phase 5)

---

## 4. After merge in Spring

- [ ] Link Spring OpenAPI / internal ADR to `wire-contract-call1-call2.md`
- [ ] WireMock suite green (portal dual-hop: Call 1 + Call 2 recommend; React body has quote/items)
- [ ] Optional joint test: Spring + real haystack, same key → one `ingest_id`
- [ ] Portal fallback copy when circuit open (“recommender unavailable”)

---

## 5. Do not

- Implement C/W/D multi-agent roles inside Spring  
- Treat Call 2 as chatbot Q&A (that is Call 3 `.../query`)  
- Expect Call 3 path for portal submit primary body (primary is Call 2 quote)  
- Enable aggressive prod ingest retry without S2a  
- Expand this pack into C2 (202 jobs) without a new plan  

---

## 6. Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.0.0** | 2026-08-12 | Call 2 recommend / Call 3 Q&A handoff checklist |
| **1.1.1** | 2026-08-12 | Dual-hop WireMock checklist; align Feasibility_Study |
| **1.1.0** | 2026-08-12 | Portal dual-hop saga checklist (Call 1 then Call 2) |
| **1.0.0** | 2026-08-12 | Initial Spring export handoff |

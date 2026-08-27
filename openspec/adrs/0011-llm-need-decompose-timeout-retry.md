# LLM need-decompose: retry once on timeout, then keyword fallback

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-20 |
| **Deciders** | haystack-fast-api |
| **Trace** | FR-P-014 |
| **OpenSpec** | [`../specs/recommendation-pipeline/spec.md`](../specs/recommendation-pipeline/spec.md) |
| **Change** | [`../changes/archive/2026-08-20-llm-need-decompose-timeout/`](../changes/archive/2026-08-20-llm-need-decompose-timeout/) |

## Context and Problem Statement

`LlmNeedDecomposer` used a single 60s httpx timeout. DigitalOcean Inference often exceeds that (`ReadTimeout`). The client fell back to keyword split but logged ERROR with a traceback and did not retry. Call 1 stayed 200.

## Considered Options

* Fail ingest on timeout
* Unlimited retries
* Raise default timeout only, no retry
* Split timeout, retry once, then keyword fallback

## Decision Outcome

Chosen option: **recoverable timeouts**.

1. Connect/write/pool 10s; read = `LLM_TIMEOUT_SECONDS` (default 120)
2. Retry **once** on `httpx.TimeoutException`
3. After two timeouts, or any other `HTTPError`, return `split_needs_from_text`
4. Log timeouts at warning without traceback
5. CI keeps `NEED_DECOMPOSER=stub`

### Consequences

* Good: ingest remains available; slow router can finish on the second attempt.
* Bad / accepted: worst-case wait is two read timeouts (~240s); keyword fallback is weaker for multi-need English.

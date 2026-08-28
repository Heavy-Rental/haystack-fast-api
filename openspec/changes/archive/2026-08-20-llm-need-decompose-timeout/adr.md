# ADR: Retry LLM need-decompose timeouts then keyword-fallback

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-20 |
| **Capability** | recommendation-pipeline (FR-010.2) / indexing Call 1 `needs_summary` |
| **Trace** | FR-P-014 |
| **OpenSpec** | [`specs/recommendation-pipeline/spec.md`](../../../specs/recommendation-pipeline/spec.md) |
| **OpenSPDD** | [`design.md`](./design.md) |
| **MADR** | [`../../../adrs/0011-llm-need-decompose-timeout-retry.md`](../../../adrs/0011-llm-need-decompose-timeout-retry.md) |

## Context

`LlmNeedDecomposer` used a single 60s httpx timeout. DigitalOcean Inference
often exceeds that on `/chat/completions` (`ReadTimeout`). The client already
caught `HTTPError` and fell back to `split_needs_from_text`, but logged ERROR
with a full traceback and did not retry. Call 1 ingest stayed 200; needs came
from keywords only.

## Decision

1. Split timeout: connect/write/pool 10s; read = `LLM_TIMEOUT_SECONDS` (default 120).
2. Retry **once** on `httpx.TimeoutException` (read or connect timeout).
3. After two timeouts, or on any other `HTTPError`, return keyword split.
4. Log timeouts at warning without traceback.

## Consequences

### Positive

- Slow router can finish within 120s, or on the second attempt.
- Ingest remains available when the LLM is down or hung.
- Logs no longer look like a crash for an expected timeout.

### Negative / accepted

- Worst-case wait is two read timeouts (~240s) before fallback.
- Keyword fallback is weaker than the LLM for multi-need English.

### Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Fail ingest on timeout | Breaks Call 1 for a slow upstream |
| Unlimited retries | Blocks the ASGI worker / Spring client |
| Raise default only, no retry | One hung request still wastes the only attempt |

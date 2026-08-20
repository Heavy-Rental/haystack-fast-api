# REASONS Canvas: Recoverable LLM need-decompose timeouts

## R — Requirements

See delta [`specs/recommendation-pipeline/spec.md`](./specs/recommendation-pipeline/spec.md)
(**FR-P-014**) and ADR [`adr.md`](./adr.md).

`NEED_DECOMPOSER=llm` MUST treat connect/read timeout as recoverable: one retry,
then keyword fallback. Timeouts MUST NOT fail ingest.

## E — Entities

| Concept | Role |
|---------|------|
| LlmNeedDecomposer | OpenAI-compatible `/chat/completions` client |
| `LLM_TIMEOUT_SECONDS` | Read timeout (default 120) |
| Keyword fallback | `split_needs_from_text` (one need per approved type) |

## A — Approach

`httpx.Timeout(connect=10, read=LLM_TIMEOUT_SECONDS, write=10, pool=10)`.
On `TimeoutException`, warn and retry once. After two timeouts, or on other
`HTTPError`, return `split_needs_from_text` (same empty-parse fallback).

## S — Structure

| Path | Role |
|------|------|
| `app/services/llm_need_decomposer.py` | Split timeout, retry, fallback |
| `app/config.py` / `.env.example` | Default 120s |
| `tests/test_llm_need_decomposer.py` | Retry + fallback |

## O — Operations

```bash
cd haystack-fast-api
uv run pytest tests/test_llm_need_decomposer.py -q
```

Override live read wait with `LLM_TIMEOUT_SECONDS`.

## N — Norms

- RFC 2119 MUST/SHALL in FR-P-014.
- Do not invent needs on fallback (keyword split only).
- Do not log timeout as ERROR + traceback.

## S — Safeguards

- Non-timeout HTTP errors: no extra retry; log exception; fallback.
- CI stays `NEED_DECOMPOSER=stub`.

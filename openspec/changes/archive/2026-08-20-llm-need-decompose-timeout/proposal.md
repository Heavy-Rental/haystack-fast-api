# Proposal: Recoverable LLM need-decompose timeouts

## Why

Call 1 / FR-010.2 with `NEED_DECOMPOSER=llm` POSTs `/chat/completions`. A slow
DigitalOcean Inference read past `LLM_TIMEOUT_SECONDS` raised `httpx.ReadTimeout`,
logged as ERROR with a traceback, then fell back. Ingest did not crash, but the
LLM path looked failed and there was no retry.

## Scope

- Split httpx timeout (short connect, configurable read).
- Retry once on connect/read timeout; then keyword-split fallback.
- Log timeouts as warning (no traceback). Other HTTP errors stay `exception`.
- Default `LLM_TIMEOUT_SECONDS` 60 → 120.
- Record as OpenSpec FR-P-014, OpenSPDD REASONS, and an ADR.

## Out of scope

- Changing provider / model slug.
- Async decomposer or lifespan-warmed client (NFR-008 / open Q #5).
- Spring Call 1 client timeouts.

# Tasks: Recoverable LLM need-decompose timeouts

- [x] Split httpx timeout; retry once on TimeoutException; keyword fallback.
- [x] Log timeouts as warning; keep exception for other HTTP errors.
- [x] Default `LLM_TIMEOUT_SECONDS` 60 → 120 (config + `.env.example`).
- [x] Tests: retry success, persistent timeout fallback, connect error no retry.
- [x] OpenSpec FR-P-014, OpenSPDD REASONS, ADR.

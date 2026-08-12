# Changelog

## Unreleased

### Added (S2a / resilience C1 — 2026-08-12)

- **FR-IX-024** — Optional `Idempotency-Key` on Call 1 ingest (`POST .../submitprojectspecification`). Successful lean **200** bodies are stored process-locally (scoped by `user_id` + key) and replayed on retry with the same `ingest_id`. Failed 4xx/5xx are not cached. Single-flight for concurrent same-key POSTs. TTL via `IDEMPOTENCY_TTL_SECONDS` (default 24h). **Not multi-replica shared.**
- **FR-IX-025** — Optional `X-Correlation-Id` / W3C `traceparent`; server mints correlation id when missing; logs bind id; responses **echo** `X-Correlation-Id`.
- OpenSpec: indexing contract/spec/design + TRACEABILITY; Postman resilience headers; tests in `tests/test_ingest_idempotency.py` and `tests/test_correlation_middleware.py`.

## v1.0.0

### Added or Changed
- Added this changelog :)
- Fixed typos in both templates
- Back to top links
- Added more "Built With" frameworks/libraries
- Changed table of contents to start collapsed
- Added checkboxes for major features on roadmap

### Removed

- Some packages/libraries from acknowledgements I no longer use
## ADDED Requirements

### Requirement: LLM need-decompose timeouts are recoverable (FR-P-014)

When `NEED_DECOMPOSER=llm`, `LlmNeedDecomposer` SHALL call the configured
OpenAI-compatible `/chat/completions` endpoint with a split timeout: connect
10 seconds, read `LLM_TIMEOUT_SECONDS` (default 120). On connect or read
timeout the client SHALL retry **once**. After two timeouts, or on any other
HTTP error, it SHALL return the keyword need split (`split_needs_from_text`)
and MUST NOT raise. Timeout events SHALL be logged at warning without a
traceback. Empty or unparseable model output SHALL use the same keyword
fallback. CI MUST keep `NEED_DECOMPOSER=stub`.

#### Scenario: Read timeout then success

- **GIVEN** `NEED_DECOMPOSER=llm` and the first `/chat/completions` read times out
- **WHEN** the decomposer runs
- **THEN** it retries once
- **AND** a successful second response is parsed into internal needs

#### Scenario: Persistent timeout falls back to keyword split

- **GIVEN** `NEED_DECOMPOSER=llm` and both attempts time out
- **AND** the source text names an approved equipment type
- **WHEN** the decomposer runs
- **THEN** it returns keyword-split needs (no exception)
- **AND** Call 1 ingest can still succeed

#### Scenario: Non-timeout HTTP error does not retry

- **GIVEN** `NEED_DECOMPOSER=llm` and `/chat/completions` raises a connect error
- **WHEN** the decomposer runs
- **THEN** it does not retry
- **AND** it returns the keyword fallback (empty when no types are named)

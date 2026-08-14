# Evaluation docs

Committed **Call 1 / Call 2** offline evaluation artifacts (test data + predictions + scores).

## What’s in this folder

| File / dir | Description |
|------------|-------------|
| [`call1-call2-test-data.md`](./call1-call2-test-data.md) | Index of exported cases (human-readable) |
| [`call1-call2-test-data-and-predictions.json`](./call1-call2-test-data-and-predictions.json) | **Full export**: input + gold + predicted Call 1/2 + metrics |
| [`test-data/`](./test-data/) | Copies of fixtures (`call1_call2_cases.json`, `eval_fleet.json`) |
| [`call1-call2-eval-results.md`](./call1-call2-eval-results.md) | Scoreboard snapshot (tables) |
| [`call1-call2-eval-results.json`](./call1-call2-eval-results.json) | Metrics-only JSON |
| [`../call1-call2-endpoint-process.md`](../call1-call2-endpoint-process.md) §11 | Method, thresholds, HTML report |

**Not committed:** `reports/pytest-report.html` (gitignored).

## Retrieve / refresh test data → `docs/eval`

```bash
cd haystack-fast-api
uv run python scripts/export_eval_test_data.py
```

This re-runs the offline pack (mock embedder, fake fleet) and rewrites:

1. `docs/eval/test-data/*` — fixture copies  
2. `docs/eval/call1-call2-test-data-and-predictions.json` — full I/O  
3. `docs/eval/call1-call2-test-data.md` — case index  
4. `docs/eval/call1-call2-eval-results.json` — metrics refresh  

Also refresh the scoreboard markdown tables in `call1-call2-eval-results.md` if numbers change materially.

## JSON shape (full export)

Each entry in `call1-call2-test-data-and-predictions.json` → `cases[]`:

```json
{
  "case_id": "happy_scissors",
  "kind": "happy",
  "input": { "project_text": "...", "call1_request_dates": {} },
  "expected": { "call1": {}, "call2": {} },
  "predicted": {
    "call1": { "ingest_id": "ing_…", "needs_summary": [], "user_requirement_summary": "…" },
    "call2": { "quoteRef": "QUO-…", "confidenceScore": 0.8, "items": [] }
  },
  "metrics": { "need_f1": 1.0, "hit_at_1_rate": 1.0, "confidence": 0.8 }
}
```

## HTML report (interactive)

```bash
uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q
# open reports/pytest-report.html
```

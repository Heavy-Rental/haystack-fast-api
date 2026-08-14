# Call 1 / Call 2 test data export

| Field | Value |
|-------|--------|
| **Generated at (UTC)** | 2026-08-14T02:31:52Z |
| **Eval seed** | `42` |
| **Full JSON (inputs + gold + predictions)** | [`call1-call2-test-data-and-predictions.json`](./call1-call2-test-data-and-predictions.json) |
| **Metrics-only JSON** | [`call1-call2-eval-results.json`](./call1-call2-eval-results.json) |
| **Fixture copies** | [`test-data/`](./test-data/) |
| **Method** | [`../call1-call2-endpoint-process.md`](../call1-call2-endpoint-process.md) §11 |

This folder holds **retrieved test data** (case inputs, gold labels, fleet) and **predicted** Call 1 / Call 2 outputs from one offline eval run.

## Files

| Path | Contents |
|------|----------|
| `test-data/call1_call2_cases.json` | Seeded case pack (input text + gold) |
| `test-data/eval_fleet.json` | Fake fleet assets/bookings used by Call 2 |
| `call1-call2-test-data-and-predictions.json` | Per case: `input`, `expected`, `predicted.call1`, `predicted.call2`, `metrics` |
| `call1-call2-eval-results.json` / `.md` | Scoreboard snapshot |

## Case index

| case_id | kind | project_text (truncated) | Call 1 gold types | Call 2 gold assets | conf | items |
|---------|------|------------------------|-------------------|--------------------|------|-------|
| `happy_scissors` | happy | Need one scissors lift for indoor elevated work ~8m. From 1 Sep 2026 ... | scissor lift | AST-SL-001, AST-SL-002 | 0.80 | 1 |
| `happy_excavator` | happy | Need an excavator for site prep and trenching. Rental 2026-10-01 to 2... | excavator | AST-EX-001, AST-EX-002 | 0.76 | 1 |
| `happy_forklift` | happy | Warehouse loading bay needs a forklift. From 2026-11-01 to 2026-11-07... | forklift | AST-FL-001 | 0.76 | 1 |
| `happy_boom` | happy | Outdoor facade work requires a boom lift / aerial platform. 2026-08-1... | boom lift | AST-BL-001 | 0.76 | 1 |
| `multi_scissors_excavator` | happy | Need a scissors lift for indoor elevated work ~8m and an excavator fo... | scissor lift, excavator | AST-SL-001, AST-SL-002, AST-EX-001, AST-EX-002 | 0.78 | 2 |
| `no_match_submarine` | no_match | Need a submarine for underwater inspection next month. Budget is tight. | — | — (no-match) | null | 0 |
| `no_dates_scissors` | happy | Need a scissors lift for indoor elevated work around 8 meters. Budget... | scissor lift | AST-SL-001, AST-SL-002 | 0.71 | 1 |
| `no_budget_forklift` | happy | Need a forklift for warehouse loading bay work from 2026-12-01 to 202... | forklift | AST-FL-001 | 0.76 | 1 |
| `excavator_prefers_available` | happy | Need an excavator between 2026-09-05 and 2026-09-12 for trench work. | excavator | AST-EX-001 | 0.76 | 1 |
| `multi_fork_boom` | happy | Site needs a forklift for materials and a boom lift for high exterior... | forklift, boom lift | AST-FL-001, AST-BL-001 | 0.76 | 2 |
| `happy_scissors_short_window` | happy | Scissor lift required for ceiling work ~8m on 2026-09-01 through 2026... | scissor lift | AST-SL-001, AST-SL-002 | 0.80 | 1 |
| `no_match_helicopter` | no_match | Need a helicopter for deep-sea surveying tomorrow. Budget SGD 50000. | — | — (no-match) | null | 0 |

## Example: one case structure (JSON)

Each entry in `call1-call2-test-data-and-predictions.json` → `cases[]` looks like:

```json
{
  "case_id": "happy_scissors",
  "input": {
    "project_text": "...",
    "call1_request_dates": {}
  },
  "expected": {
    "call1": {},
    "call2": {}
  },
  "predicted": {
    "call1": {
      "ingest_id": "ing_\u2026",
      "needs_summary": [],
      "user_requirement_summary": "\u2026"
    },
    "call2": {
      "quoteRef": "QUO-\u2026",
      "confidenceScore": 0.8,
      "items": []
    }
  },
  "metrics": {
    "need_f1": 1.0,
    "hit_at_1_rate": 1.0,
    "confidence": 0.8
  }
}
```

## Regenerate this export

```bash
cd haystack-fast-api
uv run python scripts/export_eval_test_data.py
# or re-run the same export snippet documented in docs/eval/README.md
```


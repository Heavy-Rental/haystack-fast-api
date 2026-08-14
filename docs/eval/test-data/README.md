# Call 1 / Call 2 evaluation fixtures

| Field | Value |
|-------|--------|
| **Seed** | `EVAL_SEED=42` (deterministic pack; not re-randomized each pytest run) |
| **Cases** | [`call1_call2_cases.json`](./call1_call2_cases.json) |
| **Fleet** | [`eval_fleet.json`](./eval_fleet.json) (extends seed with Boom / Fork for pack coverage) |
| **Runner** | `tests/test_call1_call2_eval_pack.py` |
| **Metrics** | `tests/eval/metrics.py` |
| **Docs (full)** | [`docs/call1-call2-endpoint-process.md`](../../../docs/call1-call2-endpoint-process.md) **§11** — metrics, `.env` isolation, case catalog, HTML report |
| **Committed results** | [`docs/eval/call1-call2-eval-results.md`](../../../docs/eval/call1-call2-eval-results.md) · [`.json`](../../../docs/eval/call1-call2-eval-results.json) |

## Case schema

Each case has:

- `project_text` — synthetic brief  
- `call1_expected` — gold needs types, dates, budget (or null + `must_not_invent_budget`)  
- `call2_expected` — gold asset ids / categories, `confidence_min`, `hit_at_1_required`, optional no-match  

## Regenerating

Edit JSON by hand or re-run a local generator with a fixed seed. Commit the file so CI stays reproducible. Do **not** regenerate inside default pytest.

## HTML report

```bash
uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q
# open reports/pytest-report.html
```

See process doc §11.7–11.8 for scoreboard reference numbers and gates.

# Call 1 / Call 2 evaluation results (committed snapshot)

| Field | Value |
|-------|--------|
| **Generated at (UTC)** | 2026-08-14T02:28:12Z |
| **Eval seed** | `42` |
| **Pytest suite** | 28 passed (`test_eval_metrics` + `test_confidence_score` + `test_call1_call2_eval_pack`) |
| **Machine-readable** | [`call1-call2-eval-results.json`](./call1-call2-eval-results.json) |
| **Method / gates** | [`../call1-call2-endpoint-process.md`](../call1-call2-endpoint-process.md) §11 |
| **Fixtures** | [`../../tests/fixtures/eval/`](../../tests/fixtures/eval/) |
| **HTML report** | `reports/pytest-report.html` (gitignored; regenerate with `uv run pytest`) |

This file is a **static snapshot** of predicted-vs-actual metrics so you can review outcomes without re-running pytest.  
Regenerate after changing fixtures or scoring logic (see [Regenerate](#regenerate)).

---

## Configuration used for this snapshot

Same isolation as `tests/conftest.py` (default pytest; host `.env` does not apply):

| Variable | Value |
|----------|--------|
| `INDEXING_EMBEDDER` | `mock` |
| `INDEXING_EMBEDDING_DIM` | `384` |
| `INDEXING_DOCUMENT_STORE` | `memory` |
| `NEED_DECOMPOSER` | `stub` |
| `FLEET_BACKEND` | `fake` |
| `RECOMMEND_VIA_AGENT_GRAPH` | `false` (MVP Call 2) |
| `NEO4J_BACKEND` | `fake` |
| `PRICING_SCHEMA` | `primary_snapshot` |
| `PROJECT_AGENT_MODE` | `stub` |

Pack runtime (code):

| Setting | Value |
|---------|--------|
| Fleet | `tests/fixtures/eval/eval_fleet.json` |
| Cases | `tests/fixtures/eval/call1_call2_cases.json` |
| Call 2 prices | fixed `daily_rate=185.0` |
| Call 2 needs | injected from case gold (`_FixedDecomposer`) |

---

## Macro summary

| Metric | Value |
|--------|--------|
| Cases | **12** |
| mean need F1 | **0.9722** |
| mean Hit@1 | **1.0** |
| mean coverage | **0.8333** |
| mean confidence (scored cases) | **0.765** |
| mean matchScore | **0.85** |
| mean nDCG | **0.9692** |
| mean price MAPE | **0.0** |
| budget invent rate | **0.0** |
| confidence consistency rate | **1.0** |
| confidence bin Hit@1 (`none`) | **1.0** (empty-item no-match) |
| confidence bin Hit@1 (`high`) | **1.0** |
| confidence bin Hit@1 (`low` / `medium`) | n/a (no cases in bin) |

**Note on confidence:** happy-path scores are typically **0.71–0.80**, not 0.99, because fake-fleet ids are `AST-*` (not digit `assets.id`), so the **0.20 live-id** term is zero. Live SQL can raise this when `equipment.id` is numeric.

---

## Per-case scoreboard

| case_id | kind | need F1 | Hit@1 | cov | confidence | conf recompute | nDCG | MAPE | items | conf ≥ min |
|---------|------|---------|-------|-----|------------|----------------|------|------|-------|------------|
| happy_scissors | happy | 1.00 | 1.00 | 1.00 | **0.80** | 0.80 | 1.00 | 0 | 1 | yes (≥0.55) |
| happy_excavator | happy | 1.00 | 1.00 | 1.00 | **0.76** | 0.76 | 1.00 | 0 | 1 | yes |
| happy_forklift | happy | 1.00 | 1.00 | 1.00 | **0.76** | 0.76 | 1.00 | 0 | 1 | yes |
| happy_boom | happy | 0.67 | 1.00 | 1.00 | **0.76** | 0.76 | 1.00 | 0 | 1 | yes |
| multi_scissors_excavator | happy | 1.00 | 1.00 | 1.00 | **0.78** | 0.78 | 0.82 | 0 | 2 | yes |
| multi_fork_boom | happy | 1.00 | 1.00 | 1.00 | **0.76** | 0.76 | 0.82 | 0 | 2 | yes |
| no_dates_scissors | happy | 1.00 | 1.00 | 1.00 | **0.71** | 0.71 | 1.00 | 0 | 1 | yes (≥0.50) |
| no_budget_forklift | happy | 1.00 | 1.00 | 1.00 | **0.76** | 0.76 | 1.00 | 0 | 1 | yes |
| excavator_prefers_available | happy | 1.00 | 1.00 | 1.00 | **0.76** | 0.76 | 1.00 | 0 | 1 | yes |
| happy_scissors_short_window | happy | 1.00 | 1.00 | 1.00 | **0.80** | 0.80 | 1.00 | 0 | 1 | yes |
| no_match_submarine | no_match | 1.00 | empty ok | 0 | **null** | null | empty ok | n/a | 0 | n/a |
| no_match_helicopter | no_match | 1.00 | empty ok | 0 | **null** | null | empty ok | n/a | 0 | n/a |

### Call 1 signals (same run)

All 12 cases: `ingest_ok=1`, `summary_ok=1`.  
Budget invent = 0 on cases with `must_not_invent_budget`.  
Date exact match holds when gold dates are set (request dates preferred on Call 1).

---

## CI gates (all met on this snapshot)

| Gate | Threshold | Snapshot |
|------|-----------|----------|
| Happy need F1 (macro) | ≥ 0.85 | **pass** (~0.97) |
| Happy Hit@1 | ≥ 0.85 | **pass** (1.0) |
| Happy mean confidence | ≥ 0.50 | **pass** (~0.77) |
| Budget invent (forbidden) | 0 | **pass** |
| Confidence consistency | 100% | **pass** |
| Price MAPE | ≤ 0.01 | **pass** (0) |
| No-match empty items | required | **pass** |

---

## How to open interactive HTML

```bash
cd haystack-fast-api
uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q
# browser: reports/pytest-report.html
```

Default pytest config writes a self-contained HTML report via `pytest-html` (`pyproject.toml` `addopts`).

---

## Regenerate

After changing fixtures, metrics, or recommend scoring:

```bash
cd haystack-fast-api

# 1) Confirm suite green + refresh HTML
uv run pytest tests/test_eval_metrics.py tests/test_confidence_score.py tests/test_call1_call2_eval_pack.py -q

# 2) Refresh committed JSON (and then update this .md tables if needed)
uv run python - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
os.environ.update({
    "INDEXING_EMBEDDER": "mock",
    "INDEXING_EMBEDDING_DIM": "384",
    "INDEXING_DOCUMENT_STORE": "memory",
    "NEED_DECOMPOSER": "stub",
    "FLEET_BACKEND": "fake",
    "RECOMMEND_VIA_AGENT_GRAPH": "false",
    "NEO4J_BACKEND": "fake",
    "PROJECT_AGENT_MODE": "stub",
    "PRICING_SCHEMA": "primary_snapshot",
    "KG_ARTIFACT_DIR": "/tmp/kg-eval-report",
})
from app.config import get_settings
get_settings.cache_clear()
from tests.test_call1_call2_eval_pack import _load_pack, _score_case
from tests.eval.metrics import aggregate_report

pack = _load_pack()
results = [_score_case(c) for c in pack["cases"]]
report = aggregate_report(results)
payload = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "eval_seed": pack.get("eval_seed", 42),
    "suite": [
        "tests/test_eval_metrics.py",
        "tests/test_confidence_score.py",
        "tests/test_call1_call2_eval_pack.py",
    ],
    "config_isolation": {
        "INDEXING_EMBEDDER": "mock",
        "INDEXING_EMBEDDING_DIM": "384",
        "INDEXING_DOCUMENT_STORE": "memory",
        "NEED_DECOMPOSER": "stub",
        "FLEET_BACKEND": "fake",
        "RECOMMEND_VIA_AGENT_GRAPH": "false",
        "NEO4J_BACKEND": "fake",
        "PRICING_SCHEMA": "primary_snapshot",
        "PROJECT_AGENT_MODE": "stub",
        "note": "Same isolation as tests/conftest.py autouse for default pytest",
    },
    "fixtures": {
        "cases": "tests/fixtures/eval/call1_call2_cases.json",
        "fleet": "tests/fixtures/eval/eval_fleet.json",
    },
    "pytest_html_report": "reports/pytest-report.html (gitignored; regenerate with uv run pytest)",
    "macro": report,
    "cases": results,
}
Path("docs/eval/call1-call2-eval-results.json").write_text(
    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
)
print("updated docs/eval/call1-call2-eval-results.json")
print("macro:", report)
PY
```

Then refresh the tables in this markdown file if numbers changed.

---

## Related

| Doc | Role |
|-----|------|
| [`../call1-call2-endpoint-process.md`](../call1-call2-endpoint-process.md) §11 | Full evaluation method |
| [`call1-call2-eval-results.json`](./call1-call2-eval-results.json) | Same snapshot as JSON |
| [`../../tests/fixtures/eval/README.md`](../../tests/fixtures/eval/README.md) | Fixture seed / regenerate notes |

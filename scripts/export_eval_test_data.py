#!/usr/bin/env python3
"""Export Call 1 / Call 2 eval fixtures + predicted outputs into docs/eval/.

Usage (from haystack-fast-api project root):

    uv run python scripts/export_eval_test_data.py

Writes:
  docs/eval/test-data/call1_call2_cases.json
  docs/eval/test-data/eval_fleet.json
  docs/eval/call1-call2-test-data-and-predictions.json
  docs/eval/call1-call2-test-data.md
  docs/eval/call1-call2-eval-results.json  (metrics-only refresh)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

# CI-safe isolation (mirrors tests/conftest.py defaults)
os.environ.update(
    {
        "INDEXING_EMBEDDER": "mock",
        "INDEXING_EMBEDDING_DIM": "384",
        "INDEXING_DOCUMENT_STORE": "memory",
        "NEED_DECOMPOSER": "stub",
        "FLEET_BACKEND": "fake",
        "RECOMMEND_VIA_AGENT_GRAPH": "false",
        "NEO4J_BACKEND": "fake",
        "PROJECT_AGENT_MODE": "stub",
        "PRICING_SCHEMA": "primary_snapshot",
        "KG_ARTIFACT_DIR": "/tmp/kg-eval-export",
    }
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from tests.eval.metrics import aggregate_report  # noqa: E402
from tests.test_call1_call2_eval_pack import (  # noqa: E402
    _load_fleet,
    _load_pack,
    _run_call1,
    _run_call2,
    _score_case,
)

DOCS_EVAL = ROOT / "docs" / "eval"
FIXTURES = ROOT / "tests" / "fixtures" / "eval"


def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if hasattr(obj, "model_dump"):
        return _jsonable(obj.model_dump(mode="json"))
    return str(obj)


def main() -> None:
    DOCS_EVAL.mkdir(parents=True, exist_ok=True)
    test_data_dir = DOCS_EVAL / "test-data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for name in ("call1_call2_cases.json", "eval_fleet.json", "README.md"):
        src = FIXTURES / name
        if src.exists():
            shutil.copy2(src, test_data_dir / name)

    pack = _load_pack()
    assets, bookings = _load_fleet()
    detailed: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []

    for case in pack["cases"]:
        ingest = _run_call1(case)
        quote = _run_call2(
            case, user_id=ingest.user_id, ingest_id=ingest.ingest_id
        )
        metrics = _score_case(case)
        scores.append(metrics)
        detailed.append(
            {
                "case_id": case["case_id"],
                "kind": case.get("kind"),
                "input": {
                    "project_text": case.get("project_text"),
                    "call1_request_dates": {
                        "start_date": case.get("call1_expected", {}).get(
                            "start_date"
                        ),
                        "end_date": case.get("call1_expected", {}).get(
                            "end_date"
                        ),
                    },
                },
                "expected": {
                    "call1": case.get("call1_expected"),
                    "call2": case.get("call2_expected"),
                },
                "predicted": {
                    "call1": _jsonable(ingest),
                    "call2": _jsonable(quote),
                },
                "metrics": metrics,
            }
        )

    macro = aggregate_report(scores)
    export = {
        "generated_at": generated_at,
        "eval_seed": pack.get("eval_seed", 42),
        "description": (
            "Full export of eval pack test data (inputs + gold labels) and "
            "predicted Call 1 / Call 2 outputs with metrics."
        ),
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
        },
        "sources": {
            "cases_fixture": "tests/fixtures/eval/call1_call2_cases.json",
            "fleet_fixture": "tests/fixtures/eval/eval_fleet.json",
            "copied_to": "docs/eval/test-data/",
            "runner": "tests/test_call1_call2_eval_pack.py",
        },
        "fleet": {"assets": assets, "bookings": bookings},
        "macro": _jsonable(macro),
        "cases": _jsonable(detailed),
    }

    full_path = DOCS_EVAL / "call1-call2-test-data-and-predictions.json"
    full_path.write_text(json.dumps(export, indent=2) + "\n", encoding="utf-8")

    results_payload = {
        "generated_at": generated_at,
        "eval_seed": pack.get("eval_seed", 42),
        "suite": [
            "tests/test_eval_metrics.py",
            "tests/test_confidence_score.py",
            "tests/test_call1_call2_eval_pack.py",
        ],
        "config_isolation": export["config_isolation"],
        "fixtures": {
            "cases": "tests/fixtures/eval/call1_call2_cases.json",
            "fleet": "tests/fixtures/eval/eval_fleet.json",
            "docs_copy": "docs/eval/test-data/",
            "full_export": "docs/eval/call1-call2-test-data-and-predictions.json",
        },
        "pytest_html_report": (
            "reports/pytest-report.html (gitignored; regenerate with uv run pytest)"
        ),
        "macro": _jsonable(macro),
        "cases": _jsonable(scores),
    }
    (DOCS_EVAL / "call1-call2-eval-results.json").write_text(
        json.dumps(results_payload, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Call 1 / Call 2 test data export",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| **Generated at (UTC)** | {generated_at} |",
        f"| **Eval seed** | `{pack.get('eval_seed', 42)}` |",
        "| **Full JSON (inputs + gold + predictions)** | "
        "[`call1-call2-test-data-and-predictions.json`]"
        "(./call1-call2-test-data-and-predictions.json) |",
        "| **Metrics-only JSON** | "
        "[`call1-call2-eval-results.json`](./call1-call2-eval-results.json) |",
        "| **Fixture copies** | [`test-data/`](./test-data/) |",
        "| **Method** | "
        "[`../call1-call2-endpoint-process.md`]"
        "(../call1-call2-endpoint-process.md) §11 |",
        "",
        "This folder holds **retrieved test data** (case inputs, gold labels, "
        "fleet) and **predicted** Call 1 / Call 2 outputs from one offline eval run.",
        "",
        "## Files",
        "",
        "| Path | Contents |",
        "|------|----------|",
        "| `test-data/call1_call2_cases.json` | Seeded case pack (input text + gold) |",
        "| `test-data/eval_fleet.json` | Fake fleet assets/bookings used by Call 2 |",
        "| `call1-call2-test-data-and-predictions.json` | Per case: `input`, "
        "`expected`, `predicted.call1`, `predicted.call2`, `metrics` |",
        "| `call1-call2-eval-results.json` / `.md` | Scoreboard snapshot |",
        "",
        "## Case index",
        "",
        "| case_id | kind | project_text (truncated) | Call 1 gold types | "
        "Call 2 gold assets | conf | items |",
        "|---------|------|------------------------|-------------------|"
        "--------------------|------|-------|",
    ]
    for row, case in zip(detailed, pack["cases"], strict=True):
        text = (case.get("project_text") or "").replace("|", "/").replace("\n", " ")
        if len(text) > 72:
            text = text[:69] + "..."
        gold_types = (
            ", ".join(case.get("call1_expected", {}).get("equipment_types") or [])
            or "—"
        )
        gold_assets: list[str] = []
        for g in case.get("call2_expected", {}).get("gold_by_need") or []:
            gold_assets.extend(g.get("gold_asset_ids") or [])
        assets_s = ", ".join(gold_assets) if gold_assets else "— (no-match)"
        conf = row["metrics"].get("confidence")
        conf_s = "null" if conf is None else f"{float(conf):.2f}"
        lines.append(
            f"| `{row['case_id']}` | {row['kind']} | {text} | {gold_types} | "
            f"{assets_s} | {conf_s} | {row['metrics'].get('item_count')} |"
        )
    lines.extend(
        [
            "",
            "## Regenerate",
            "",
            "```bash",
            "cd haystack-fast-api",
            "uv run python scripts/export_eval_test_data.py",
            "```",
            "",
        ]
    )
    body = "\n".join(lines) + "\n"
    (DOCS_EVAL / "call1-call2-test-data.md").write_text(body, encoding="utf-8")
    (test_data_dir / "INDEX.md").write_text(body, encoding="utf-8")

    print(f"wrote {full_path} ({full_path.stat().st_size} bytes)")
    print(f"wrote {DOCS_EVAL / 'call1-call2-test-data.md'}")
    print(f"wrote {DOCS_EVAL / 'call1-call2-eval-results.json'}")
    print(f"copied fixtures → {test_data_dir}")
    print(f"cases={len(detailed)} macro={macro}")


if __name__ == "__main__":
    main()

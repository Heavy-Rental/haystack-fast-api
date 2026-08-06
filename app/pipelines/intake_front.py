"""FR-010 steps 1–3: resolve text → decompose → expand quantity (Haystack Pipeline)."""

from __future__ import annotations

from typing import Any

from haystack import Pipeline

from app.pipelines.expand_quantity import ExpandQuantityComponent
from app.pipelines.need_decomposer_component import NeedDecomposerComponent
from app.pipelines.source_text_resolver import SourceTextResolver
from app.services.need_decomposer import NeedDecomposer, StubNeedDecomposer


def build_intake_front_pipeline(
    *,
    decomposer: NeedDecomposer | None = None,
    separator: str = "\n\n",
) -> Pipeline:
    """Build the intake front subgraph (FR-010.1–3 only; 4–8 deferred).

    Graph::

        resolve → decompose → expand
    """
    pipeline = Pipeline()
    pipeline.add_component(
        "resolve",
        SourceTextResolver(separator=separator),
    )
    pipeline.add_component(
        "decompose",
        NeedDecomposerComponent(decomposer=decomposer or StubNeedDecomposer()),
    )
    pipeline.add_component("expand", ExpandQuantityComponent())
    pipeline.connect("resolve.source_text", "decompose.source_text")
    pipeline.connect("decompose.needs", "expand.needs")
    return pipeline


def run_intake_front(
    pipeline: Pipeline,
    *,
    project_text: str | None = None,
    file_text: str | None = None,
) -> list[dict[str, Any]]:
    """Execute the front pipeline; return unit_need dicts from expand."""
    result = pipeline.run(
        {
            "resolve": {
                "project_text": project_text,
                "file_text": file_text,
            }
        }
    )
    expand_out = result.get("expand") or {}
    unit_needs = expand_out.get("unit_needs") or []
    return list(unit_needs)

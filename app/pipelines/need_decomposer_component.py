"""FR-010.2 — Decompose unstructured source text into internal needs."""

from __future__ import annotations

from typing import Any

from haystack import component

from app.schemas.recommendations import DecomposedNeed
from app.services.need_decomposer import NeedDecomposer, StubNeedDecomposer


def _needs_to_dicts(needs: list[DecomposedNeed]) -> list[dict[str, Any]]:
    return [
        {
            "need_id": n.need_id,
            "description": n.description,
            "equipment_hints": list(n.equipment_hints),
            "quantity": n.quantity,
        }
        for n in needs
    ]


@component
class NeedDecomposerComponent:
    """Haystack wrapper around a NeedDecomposer protocol implementation.

    Default: StubNeedDecomposer (one need, quantity=1). Inject a custom
    decomposer for tests or a future LLM implementation (env-gated).
    """

    def __init__(self, decomposer: NeedDecomposer | None = None) -> None:
        self._decomposer: NeedDecomposer = decomposer or StubNeedDecomposer()

    @component.output_types(needs=list)
    def run(self, source_text: str = "") -> dict[str, list]:
        text = (source_text or "").strip()
        if not text:
            return {"needs": []}
        needs = self._decomposer.decompose(text)
        return {"needs": _needs_to_dicts(list(needs or []))}

"""Need decomposition: unstructured project text → internal needs (+ quantity).

Production uses an LLM. Tests and early scaffolding inject StubNeedDecomposer
or a custom NeedDecomposer. When the text names approved types, the stub
splits one need per type (same fallback the LLM uses when it returns []).
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from app.pipelines.catalog import _KEYWORD_TO_MODEL, model_categories_in_text
from app.schemas.recommendations import DecomposedNeed

_QTY_WORDS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(two|2)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(three|3)\b", re.IGNORECASE), 3),
    (re.compile(r"\b(four|4)\b", re.IGNORECASE), 4),
    (re.compile(r"\b(five|5)\b", re.IGNORECASE), 5),
    (re.compile(r"\b(one|1)\b", re.IGNORECASE), 1),
)


def _first_keyword(blob: str, category: str) -> tuple[int, str]:
    best = (-1, "")
    for keyword, cat in _KEYWORD_TO_MODEL:
        if cat != category:
            continue
        idx = blob.find(keyword)
        if idx < 0:
            continue
        if best[0] < 0 or idx < best[0] or (idx == best[0] and len(keyword) > len(best[1])):
            best = (idx, keyword)
    return best


def _snippet_for_category(text: str, category: str) -> str:
    blob = text.lower()
    pos, hit = _first_keyword(blob, category)
    if pos < 0:
        return text.strip()
    start = (
        max(
            text.rfind(".", 0, pos),
            text.rfind("!", 0, pos),
            text.rfind("?", 0, pos),
            text.rfind("\n", 0, pos),
        )
        + 1
    )
    end_at = [
        i
        for i in (
            text.find(".", pos + len(hit)),
            text.find("!", pos + len(hit)),
            text.find("?", pos + len(hit)),
            text.find("\n", pos + len(hit)),
        )
        if i >= 0
    ]
    end = (min(end_at) + 1) if end_at else len(text)
    snippet = text[start:end].strip(" \t-–—")
    return snippet or text.strip()


def _quantity_near(text: str, category: str) -> int:
    blob = text.lower()
    pos, _hit = _first_keyword(blob, category)
    if pos < 0:
        return 1
    window = text[max(0, pos - 40) : pos]
    for pattern, qty in _QTY_WORDS:
        if pattern.search(window):
            return qty
    return 1


def split_needs_from_text(source_text: str) -> list[DecomposedNeed]:
    """One need per approved type mentioned. No types → []. Never invents types."""
    text = (source_text or "").strip()
    if not text:
        return []
    categories = model_categories_in_text(text)
    needs: list[DecomposedNeed] = []
    for index, category in enumerate(categories, start=1):
        needs.append(
            DecomposedNeed(
                need_id=f"need_{index}",
                description=_snippet_for_category(text, category),
                equipment_hints=[category],
                quantity=_quantity_near(text, category),
            )
        )
    return needs


@runtime_checkable
class NeedDecomposer(Protocol):
    """Maps unstructured source text to internal equipment needs."""

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        """Return one or more needs. Empty list is treated as intake failure upstream."""


class StubNeedDecomposer:
    """Deterministic decomposer for tests and when the LLM returns nothing.

    Splits one need per approved equipment type in the text. If no type is
    mentioned, keeps the legacy single-need (full text, no hints).
    """

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        text = source_text.strip()
        if not text:
            return []
        split = split_needs_from_text(text)
        if split:
            return split
        return [
            DecomposedNeed(
                need_id="need_1",
                description=text,
                equipment_hints=[],
                quantity=1,
            )
        ]

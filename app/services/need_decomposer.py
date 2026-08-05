"""Need decomposition: unstructured project text → internal needs (+ quantity).

Production uses an LLM. Tests and early scaffolding inject StubNeedDecomposer
or a custom NeedDecomposer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.recommendations import DecomposedNeed


@runtime_checkable
class NeedDecomposer(Protocol):
    """Maps unstructured source text to internal equipment needs."""

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        """Return one or more needs. Empty list is treated as intake failure upstream."""
        ...


class StubNeedDecomposer:
    """Deterministic decomposer for tests and pre-LLM scaffolding.

    Treats the full source text as a single need with quantity=1.
    """

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        text = source_text.strip()
        if not text:
            return []
        return [
            DecomposedNeed(
                need_id="need_1",
                description=text,
                equipment_hints=[],
                quantity=1,
            )
        ]

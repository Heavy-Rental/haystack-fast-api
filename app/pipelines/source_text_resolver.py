"""FR-010.1 — Resolve free-text and/or file extract into a single source string."""

from __future__ import annotations

from haystack import component


@component
class SourceTextResolver:
    """Merge project_text and file_text (file first, then project_text).

    Empty inputs yield ``source_text=""`` so the service can map to HTTP 400
    (FR-004). Does not raise on empty so the component stays pipeline-safe.
    """

    def __init__(self, separator: str = "\n\n") -> None:
        self._separator = separator

    @component.output_types(source_text=str)
    def run(
        self,
        project_text: str | None = None,
        file_text: str | None = None,
    ) -> dict[str, str]:
        parts: list[str] = []
        if file_text is not None and str(file_text).strip():
            parts.append(str(file_text).strip())
        if project_text is not None and str(project_text).strip():
            parts.append(str(project_text).strip())
        return {"source_text": self._separator.join(parts)}

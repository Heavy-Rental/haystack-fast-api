"""MIME / extension map for project-spec indexing (Part 1).

Normative table: specification/SPEC-indexing-file-type-router.md §3.
"""

from __future__ import annotations

from pathlib import Path

# MIME types registered with Haystack FileTypeRouter.
MIME_TEXT_PLAIN = "text/plain"
MIME_MARKDOWN = "text/markdown"
MIME_PDF = "application/pdf"
MIME_HTML = "text/html"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_CSV = "text/csv"
MIME_JSON = "application/json"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

UNSTRUCTURED_MIME_TYPES: frozenset[str] = frozenset(
    {
        MIME_TEXT_PLAIN,
        MIME_MARKDOWN,
        MIME_PDF,
        MIME_HTML,
        MIME_DOCX,
    }
)

STRUCTURED_MIME_TYPES: frozenset[str] = frozenset(
    {
        MIME_CSV,
        MIME_JSON,
        MIME_XLSX,
    }
)

ALL_ROUTED_MIME_TYPES: list[str] = sorted(UNSTRUCTURED_MIME_TYPES | STRUCTURED_MIME_TYPES)

# Register extensions that stdlib mimetypes often misses (esp. markdown / OOXML).
ADDITIONAL_MIMETYPES: dict[str, str] = {
    MIME_MARKDOWN: ".md",
    MIME_DOCX: ".docx",
    MIME_XLSX: ".xlsx",
}

# Authoritative extension → MIME for packaging ByteStreams from uploads.
EXTENSION_TO_MIME: dict[str, str] = {
    ".txt": MIME_TEXT_PLAIN,
    ".md": MIME_MARKDOWN,
    ".markdown": MIME_MARKDOWN,
    ".pdf": MIME_PDF,
    ".html": MIME_HTML,
    ".htm": MIME_HTML,
    ".docx": MIME_DOCX,
    ".csv": MIME_CSV,
    ".json": MIME_JSON,
    ".xlsx": MIME_XLSX,
}


def guess_mime_from_filename(filename: str | None) -> str | None:
    """Return MIME type from filename extension, or None if unknown."""
    if not filename:
        return None
    ext = Path(filename).suffix.lower()
    return EXTENSION_TO_MIME.get(ext)


def data_kind_for_mime(mime_type: str | None) -> str | None:
    """Map a MIME type to structured / unstructured, or None if unclassified."""
    if not mime_type:
        return None
    if mime_type in STRUCTURED_MIME_TYPES:
        return "structured"
    if mime_type in UNSTRUCTURED_MIME_TYPES:
        return "unstructured"
    return None

"""FileTypeRouter-backed classifier: structured vs unstructured sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from haystack import component
from haystack.components.routers import FileTypeRouter
from haystack.dataclasses import ByteStream

from app.pipelines.indexing.mime_map import (
    ADDITIONAL_MIMETYPES,
    ALL_ROUTED_MIME_TYPES,
    STRUCTURED_MIME_TYPES,
    UNSTRUCTURED_MIME_TYPES,
)


def _source_filename(source: ByteStream | Path | str) -> str:
    if isinstance(source, ByteStream):
        meta = source.meta or {}
        name = meta.get("file_path") or meta.get("filename") or ""
        return str(name) if name else "upload"
    return str(Path(source).name)


def _source_mime(source: ByteStream | Path | str, bucket_key: str | None) -> str | None:
    if isinstance(source, ByteStream) and source.mime_type:
        return source.mime_type
    if bucket_key and bucket_key not in {"unclassified", "failed"}:
        return bucket_key
    return None


@component
class DataKindClassifier:
    """Run Haystack FileTypeRouter and collapse MIME buckets into data kinds.

    Outputs classified source lists for Part 2 converters; embed/write deferred.
    """

    def __init__(self) -> None:
        self._router = FileTypeRouter(
            mime_types=list(ALL_ROUTED_MIME_TYPES),
            additional_mimetypes=dict(ADDITIONAL_MIMETYPES),
        )

    @component.output_types(
        data_kind=str,
        structured_sources=list[ByteStream],
        unstructured_sources=list[ByteStream],
        unclassified_sources=list[ByteStream],
        mime_types_seen=list[str],
        filenames=list[str],
        structured_count=int,
        unstructured_count=int,
        unclassified_count=int,
    )
    def run(self, sources: list[ByteStream | str | Path]) -> dict[str, Any]:
        if not sources:
            return {
                "data_kind": "unclassified",
                "structured_sources": [],
                "unstructured_sources": [],
                "unclassified_sources": [],
                "mime_types_seen": [],
                "filenames": [],
                "structured_count": 0,
                "unstructured_count": 0,
                "unclassified_count": 0,
            }

        routed = self._router.run(sources=list(sources))

        structured: list[ByteStream] = []
        unstructured: list[ByteStream] = []
        unclassified: list[ByteStream] = []
        mime_types_seen: list[str] = []
        filenames: list[str] = []

        for bucket_key, bucket_sources in routed.items():
            if not bucket_sources:
                continue
            if bucket_key in {"unclassified", "failed"}:
                for src in bucket_sources:
                    unclassified.append(self._as_bytestream(src))
                    filenames.append(_source_filename(src))
                continue

            kind = (
                "structured"
                if bucket_key in STRUCTURED_MIME_TYPES
                else "unstructured"
                if bucket_key in UNSTRUCTURED_MIME_TYPES
                else None
            )
            if kind is None:
                for src in bucket_sources:
                    unclassified.append(self._as_bytestream(src))
                    filenames.append(_source_filename(src))
                continue

            if bucket_key not in mime_types_seen:
                mime_types_seen.append(bucket_key)

            target = structured if kind == "structured" else unstructured
            for src in bucket_sources:
                bs = self._as_bytestream(src, default_mime=bucket_key)
                target.append(bs)
                filenames.append(_source_filename(src))
                mime = _source_mime(bs, bucket_key)
                if mime and mime not in mime_types_seen:
                    mime_types_seen.append(mime)

        structured_count = len(structured)
        unstructured_count = len(unstructured)
        unclassified_count = len(unclassified)

        if structured_count and unstructured_count:
            data_kind = "mixed"
        elif structured_count:
            data_kind = "structured"
        elif unstructured_count:
            data_kind = "unstructured"
        else:
            data_kind = "unclassified"

        return {
            "data_kind": data_kind,
            "structured_sources": structured,
            "unstructured_sources": unstructured,
            "unclassified_sources": unclassified,
            "mime_types_seen": mime_types_seen,
            "filenames": filenames,
            "structured_count": structured_count,
            "unstructured_count": unstructured_count,
            "unclassified_count": unclassified_count,
        }

    @staticmethod
    def _as_bytestream(
        source: ByteStream | Path | str,
        *,
        default_mime: str | None = None,
    ) -> ByteStream:
        if isinstance(source, ByteStream):
            if source.mime_type is None and default_mime:
                source.mime_type = default_mime
            return source
        path = Path(source)
        data = path.read_bytes()
        return ByteStream(
            data=data,
            meta={"file_path": str(path.name)},
            mime_type=default_mime,
        )

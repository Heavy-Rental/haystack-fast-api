"""Project-spec intake: indexing + mandatory user-scoped KG (HR-76)."""

from datetime import date

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.core.exceptions import BadRequestError
from app.schemas.indexing import IngestFromProjectSpecResponse
from app.schemas.recommendations import RecommendFromProjectSpecRequest
from app.services.indexing import (
    IndexingIngestService,
    byte_stream_from_upload,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


def _parse_optional_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise BadRequestError(f"invalid date: {value}") from exc


def _require_user_id(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise BadRequestError("user_id is required")
    return text


@router.post(
    "/from-project-spec",
    response_model=IngestFromProjectSpecResponse,
    summary="Ingest project-spec: index chunks and knowledge graph",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "$ref": "#/components/schemas/RecommendFromProjectSpecRequest"
                    }
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["user_id"],
                        "properties": {
                            "user_id": {"type": "string"},
                            "user_name": {"type": "string"},
                            "file": {"type": "string", "format": "binary"},
                            "project_text": {"type": "string"},
                            "start_date": {"type": "string", "format": "date"},
                            "end_date": {"type": "string", "format": "date"},
                            "include_pricing": {"type": "boolean", "default": True},
                        },
                    }
                },
            }
        }
    },
)
async def recommend_from_project_spec(request: Request) -> IngestFromProjectSpecResponse:
    """Index project-spec; always build KG from post-final_doc_joiner chunks.

    Full Ragas transforms run only inside KnowledgeGraphGenerator when
    KG_APPLY_TRANSFORMS is true. KG failure fails the request.
    """
    content_type = request.headers.get("content-type", "")
    service = IndexingIngestService()

    if "application/json" in content_type:
        payload = await request.json()
        try:
            body = RecommendFromProjectSpecRequest.model_validate(payload)
        except ValidationError as exc:
            messages = "; ".join(
                f"{'.'.join(str(loc) for loc in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
                for err in exc.errors()
            )
            raise BadRequestError(messages or "Validation failed") from exc

        return await run_in_threadpool(
            service.ingest_from_project_spec,
            user_id=body.user_id,
            user_name=body.user_name,
            project_text=body.project_text,
            file_sources=None,
        )

    if "multipart/form-data" in content_type:
        form = await request.form()
        user_id = _require_user_id(form.get("user_id"))
        user_name_raw = form.get("user_name")
        user_name = (
            str(user_name_raw).strip()
            if user_name_raw is not None and str(user_name_raw).strip()
            else None
        )
        project_text = form.get("project_text")
        project_text_str = (
            str(project_text).strip()
            if project_text is not None and str(project_text).strip()
            else None
        )
        _ = _parse_optional_date(form.get("start_date"))
        _ = _parse_optional_date(form.get("end_date"))

        file_sources = []
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            raw = await upload.read()
            filename = getattr(upload, "filename", None)
            ctype = getattr(upload, "content_type", None)
            if filename or raw:
                file_sources.append(
                    byte_stream_from_upload(
                        raw=raw if isinstance(raw, (bytes, bytearray)) else bytes(raw),
                        filename=filename,
                        content_type=ctype,
                        user_id=user_id,
                        user_name=user_name,
                    )
                )

        return await run_in_threadpool(
            service.ingest_from_project_spec,
            user_id=user_id,
            user_name=user_name,
            project_text=project_text_str,
            file_sources=file_sources or None,
        )

    raise BadRequestError(
        "Content-Type must be application/json or multipart/form-data"
    )

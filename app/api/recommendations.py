"""Recommendation intake endpoints (thin routers)."""

from datetime import date

from fastapi import APIRouter, Request
from pydantic import ValidationError

from app.core.exceptions import BadRequestError
from app.schemas.recommendations import (
    RecommendFromProjectSpecRequest,
    RecommendFromProjectSpecResponse,
    RecommendOptions,
)
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

_ALLOWED_TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/octet-stream",
}


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


def _decode_upload(filename: str | None, content_type: str | None, raw: bytes) -> str:
    ctype = (content_type or "application/octet-stream").split(";")[0].strip()
    name = (filename or "").lower()
    allowed_by_name = name.endswith((".txt", ".md", ".markdown"))
    if ctype not in _ALLOWED_TEXT_TYPES and not allowed_by_name:
        raise BadRequestError(
            f"unsupported file type '{ctype or 'unknown'}'; "
            "MVP accepts text/plain and text/markdown"
        )
    if not raw:
        raise BadRequestError("uploaded file is empty")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError("file must be valid UTF-8 text") from exc


@router.post(
    "/from-project-spec",
    response_model=RecommendFromProjectSpecResponse,
    summary="Recommend equipment from free-text or project file",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/RecommendFromProjectSpecRequest"}
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
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
async def recommend_from_project_spec(request: Request) -> RecommendFromProjectSpecResponse:
    """Accept unstructured project_text and/or file (+ optional dates).

    LLM (or stub) decomposes text into needs; quantity expands to unit-needs;
    each unit-need returns exactly one ranked item (or null).
    """
    content_type = request.headers.get("content-type", "")

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
        return RecommendationService().recommend_from_project_spec(
            project_text=body.project_text,
            start_date=body.start_date,
            end_date=body.end_date,
            options=body.options,
        )

    if "multipart/form-data" in content_type:
        form = await request.form()
        project_text = form.get("project_text")
        project_text_str = (
            str(project_text).strip() if project_text is not None and str(project_text).strip() else None
        )
        start_date = _parse_optional_date(form.get("start_date"))
        end_date = _parse_optional_date(form.get("end_date"))
        include_raw = form.get("include_pricing", "true")
        include_pricing = str(include_raw).lower() not in {"false", "0", "no"}

        file_text: str | None = None
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            raw = await upload.read()
            filename = getattr(upload, "filename", None)
            ctype = getattr(upload, "content_type", None)
            if filename or raw:
                file_text = _decode_upload(filename, ctype, raw)

        return RecommendationService().recommend_from_project_spec(
            project_text=project_text_str,
            file_text=file_text,
            start_date=start_date,
            end_date=end_date,
            options=RecommendOptions(include_pricing=include_pricing),
        )

    raise BadRequestError(
        "Content-Type must be application/json or multipart/form-data"
    )

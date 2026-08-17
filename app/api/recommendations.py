"""Project-spec intake, Call 2 recommend, Call 3 chatbot Q&A."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.agents.indexing_gate import run_indexing_gate
from app.config import get_settings
from app.core.exceptions import BadRequestError
from app.schemas.indexing import IngestFromProjectSpecResponse
from app.schemas.project_knowledge import (
    ProjectKnowledgeQueryRequest,
    ProjectKnowledgeQueryResponse,
)
from app.schemas.recommend_quote import (
    AssetRecommendRequest,
    AssetRecommendResponse,
)
from app.schemas.recommendations import RecommendFromProjectSpecRequest
from app.services.indexing import (
    IndexingIngestService,
    byte_stream_from_upload,
)
from app.services.ingest_idempotency import (
    get_ingest_idempotency_store,
    normalize_idempotency_key,
    scope_idempotency_key,
)
from app.services.project_knowledge_qa import ProjectKnowledgeQAService
from app.services.session_recommend import SessionRecommendService

router = APIRouter(prefix="/internal/v1/recommendations", tags=["recommendations"])

_CORRELATION_OPENAPI = {
    "parameters": [
        {
            "name": "X-Correlation-Id",
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
            "description": "Optional end-to-end correlation id (logged + echoed).",
        },
        {
            "name": "traceparent",
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
            "description": "Optional W3C trace context (logged when present).",
        },
    ],
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


def _require_user_id(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise BadRequestError("user_id is required")
    return text


async def _run_ingest_with_optional_idempotency(
    *,
    user_id: str,
    idempotency_key: str | None,
    producer,
) -> IngestFromProjectSpecResponse:
    """Run ingest; when key present, return/store successful lean body only."""
    key = normalize_idempotency_key(idempotency_key)
    if key is None:
        return await run_in_threadpool(producer)

    store = get_ingest_idempotency_store()
    scope = scope_idempotency_key(user_id, key)
    return await run_in_threadpool(store.run_once, scope, producer)


@router.post(
    "/submitprojectspecification",
    response_model=IngestFromProjectSpecResponse,
    summary="Submit project specification: index chunks and knowledge graph",
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": False,
                "schema": {"type": "string", "format": "uuid"},
                "description": (
                    "Optional client UUID per logical ingest. When present, a "
                    "successful 200 lean body is replayed for the same "
                    "user_id + key (process-local store). Failed 4xx/5xx are "
                    "not cached. Safe for Spring retries after timeout."
                ),
            },
            {
                "name": "X-Correlation-Id",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
                "description": (
                    "Optional end-to-end correlation id (logged + echoed). "
                    "If omitted, the server mints a UUID."
                ),
            },
            {
                "name": "traceparent",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
                "description": "Optional W3C trace context (logged when present).",
            },
        ],
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
async def recommend_from_project_spec(
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", convert_underscores=False),
    ] = None,
) -> IngestFromProjectSpecResponse:
    """Index project-spec; always build KG from post-final_doc_joiner chunks.

    Full Ragas transforms run only inside KnowledgeGraphGenerator when
    KG_APPLY_TRANSFORMS is true. KG failure fails the request.

    Optional ``Idempotency-Key`` (S2a): successful 200 responses are cached
    process-locally under ``user_id`` + key so Spring retries return the same
    ``ingest_id`` without double-indexing.
    """
    content_type = request.headers.get("content-type", "")
    service = IndexingIngestService()
    via_gate = bool(get_settings().indexing_via_agent_gate)

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

        def _produce_json() -> IngestFromProjectSpecResponse:
            if via_gate:
                # Coordinator gate [4]: forced non-LLM START→index_gate→END
                gate = run_indexing_gate(
                    user_id=body.user_id,
                    user_name=body.user_name,
                    project_text=body.project_text,
                    file_sources=None,
                    start_date=body.start_date,
                    end_date=body.end_date,
                    service=service,
                )
                assert gate.response is not None
                return gate.response
            return service.ingest_from_project_spec(
                user_id=body.user_id,
                user_name=body.user_name,
                project_text=body.project_text,
                file_sources=None,
                start_date=body.start_date,
                end_date=body.end_date,
            )

        return await _run_ingest_with_optional_idempotency(
            user_id=body.user_id,
            idempotency_key=idempotency_key,
            producer=_produce_json,
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
        start_date = _parse_optional_date(form.get("start_date"))
        end_date = _parse_optional_date(form.get("end_date"))
        if start_date is not None and end_date is not None and end_date < start_date:
            raise BadRequestError("end_date must be on or after start_date")

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

        def _produce_multipart() -> IngestFromProjectSpecResponse:
            if via_gate:
                gate = run_indexing_gate(
                    user_id=user_id,
                    user_name=user_name,
                    project_text=project_text_str,
                    file_sources=file_sources or None,
                    start_date=start_date,
                    end_date=end_date,
                    service=service,
                )
                assert gate.response is not None
                return gate.response
            return service.ingest_from_project_spec(
                user_id=user_id,
                user_name=user_name,
                project_text=project_text_str,
                file_sources=file_sources or None,
                start_date=start_date,
                end_date=end_date,
            )

        return await _run_ingest_with_optional_idempotency(
            user_id=user_id,
            idempotency_key=idempotency_key,
            producer=_produce_multipart,
        )

    raise BadRequestError(
        "Content-Type must be application/json or multipart/form-data"
    )


@router.post(
    "/project-knowledge/getassetrecommendations",
    response_model=AssetRecommendResponse,
    summary="Call 2: recommend / quote equipment for a Call 1 session",
    openapi_extra=_CORRELATION_OPENAPI,
)
async def get_asset_recommendations(
    body: AssetRecommendRequest,
) -> AssetRecommendResponse:
    """Fleet + pricing recommend for a prior ingest (portal dual-hop Call 2).

    Requires successful ``/submitprojectspecification`` for the same
    ``user_id`` + ``ingest_id``. Returns a quote envelope (``quoteRef``,
    ``items[].equipment``, rates). Does **not** invent asset ids or rates.

    Default: ``RecommendationService`` MVP. When
    ``RECOMMEND_VIA_AGENT_GRAPH=true`` (S7.5), the C/W/D graph runs and
    maps ``results_by_need`` onto this same DTO. Gate refuse → 400.

    Stage-1 project-knowledge **chatbot Q&A** is Call 3:
    ``POST .../project-knowledge/query``.
    """
    service = SessionRecommendService()
    return await run_in_threadpool(
        service.recommend,
        user_id=body.user_id,
        ingest_id=body.ingest_id,
        query=body.query,
        top_k=body.top_k,
    )


@router.post(
    "/project-knowledge/query",
    response_model=ProjectKnowledgeQueryResponse,
    summary="Call 3: chatbot Q&A over project DocumentStore + KG-1",
    openapi_extra=_CORRELATION_OPENAPI,
)
async def query_project_knowledge(
    body: ProjectKnowledgeQueryRequest,
) -> ProjectKnowledgeQueryResponse:
    """LangGraph research → graph → synthesis over Stage-1 project sources only.

    Requires a prior successful ``/submitprojectspecification`` ingest for the
    same ``user_id`` + ``ingest_id`` (process-local session). Optional
    ``kg_artifact_path`` can reload KG-1 after restart; vector store is empty
    until re-ingest.

    Chatbot / free-form Q&A path (Call 3). Asset recommend is Call 2
    ``getassetrecommendations``.
    """
    service = ProjectKnowledgeQAService()
    return await run_in_threadpool(
        service.ask,
        user_id=body.user_id,
        ingest_id=body.ingest_id,
        query=body.query,
        top_k=body.top_k,
        kg_artifact_path=body.kg_artifact_path,
    )

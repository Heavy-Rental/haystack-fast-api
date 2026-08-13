"""Call 2: recommend / quote from a Call 1 project-knowledge session.

Default: FR-010 ``RecommendationService`` (seed fleet + pricing).
S7.5: ``RECOMMEND_VIA_AGENT_GRAPH=true`` runs the C/W/D graph and maps
``results_by_need`` onto the **same** quote DTO. Does **not** invent
asset_id or rates. ``tool_traces`` stay on graph state (not the HTTP body).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from app.agents.recommend_graph import run_recommend_graph
from app.agents.recommend_state import indexing_ok as state_indexing_ok
from app.agents.tool_factory import RecommendToolCatalog
from app.config import Settings, get_settings
from app.core.exceptions import BadRequestError
from app.schemas.recommend_quote import (
    AssetRecommendResponse,
    EquipmentQuote,
    RecommendQuoteItem,
)
from app.schemas.recommendations import (
    NeedResult,
    RecommendFromProjectSpecResponse,
    RecommendOptions,
)
from app.services.need_decomposer import NeedDecomposer
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
)
from app.services.recommendations import RecommendationService

logger = logging.getLogger(__name__)


def _parse_iso_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def project_text_from_session(session: ProjectKnowledgeSession) -> str:
    """Build grounding text from session meta + document store (no invent)."""
    meta = session.meta or {}
    parts: list[str] = []
    summary = meta.get("user_requirement_summary")
    if summary:
        parts.append(str(summary))
    for need in meta.get("needs_summary") or []:
        if isinstance(need, dict) and need.get("description"):
            parts.append(str(need["description"]))
    try:
        docs = session.document_store.filter_documents()
        for doc in docs[:30]:
            content = getattr(doc, "content", None) or ""
            if str(content).strip():
                parts.append(str(content).strip())
    except Exception as exc:  # noqa: BLE001
        logger.debug("document_store filter failed: %s", exc)
    text = "\n".join(parts).strip()
    return text or "equipment rental project"


def map_recommend_to_quote(
    *,
    user_id: str,
    ingest_id: str,
    query: str | None,
    recommend: RecommendFromProjectSpecResponse,
    session: ProjectKnowledgeSession,
    top_k: int | None = None,
) -> AssetRecommendResponse:
    """Map FR-010 results_by_need → portal quote envelope."""
    meta = session.meta or {}
    start = recommend.start_date
    end = recommend.end_date
    days: int | None = None
    if start is not None and end is not None:
        days = max(1, (end - start).days + 1)

    items: list[RecommendQuoteItem] = []
    estimated = 0.0
    has_price = False
    rationales: list[str] = []
    warnings: list[str] = list(meta.get("warnings") or []) if isinstance(meta.get("warnings"), list) else []

    rank = 0
    for need_result in recommend.results_by_need:
        item = need_result.item
        if need_result.warnings:
            warnings.extend(need_result.warnings)
        if item is None or not item.asset_id:
            continue
        rank += 1
        if top_k is not None and rank > top_k:
            break
        daily = item.pricing.daily_rate if item.pricing else None
        total = item.pricing.total_price if item.pricing else None
        if total is None and daily is not None and days is not None:
            total = float(daily) * float(days)
        if total is not None:
            estimated += float(total)
            has_price = True
        if item.rationale:
            rationales.append(str(item.rationale))
        score = 1.0 / float(rank) if rank else None
        if item.rank is not None and item.rank > 0:
            score = 1.0 / float(item.rank)
        items.append(
            RecommendQuoteItem(
                rankOrder=rank,
                matchScore=score,
                reason=item.rationale,
                lineTotal=total,
                quantity=1,
                needId=need_result.need_id,
                equipment=EquipmentQuote(
                    id=item.asset_id,
                    name=item.equipment_type,
                    category=item.equipment_type,
                    baseDailyRate=daily,
                    weekly=None,
                    extra={
                        k: v
                        for k, v in {
                            "availability": item.availability,
                            "currency": (
                                item.pricing.currency if item.pricing else None
                            ),
                            "model_version": (
                                item.pricing.model_version if item.pricing else None
                            ),
                        }.items()
                        if v is not None
                    },
                ),
            )
        )

    if not items:
        warnings.append("No equipment matched for this project-spec session")

    conf = None
    if items:
        conf = round(min(0.99, 0.55 + 0.08 * len(items)), 2)

    quote_ref = f"QUO-{uuid.uuid4().hex[:8].upper()}"
    summary = meta.get("user_requirement_summary")
    if isinstance(summary, str):
        spec_summary = summary
    else:
        spec_summary = None

    rationale = " ".join(rationales).strip() or None
    if not rationale and items:
        rationale = (
            f"Selected {len(items)} catalog-backed asset(s) for the project needs."
        )

    return AssetRecommendResponse(
        user_id=user_id,
        ingest_id=ingest_id,
        query=query,
        quoteRef=quote_ref,
        confidenceScore=conf,
        days=days,
        estimatedTotal=estimated if has_price else None,
        specSummary=spec_summary,
        rationale=rationale,
        items=items,
        warnings=warnings,
        recommendationId=recommend.recommendation_id,
    )


def results_to_recommend_response(
    state: dict[str, Any],
    *,
    start_date: date | None,
    end_date: date | None,
) -> RecommendFromProjectSpecResponse:
    """Map graph ``recommendation.results_by_need`` to the FR-010 envelope."""
    rec = state.get("recommendation") or {}
    rows = rec.get("results_by_need") or []
    return RecommendFromProjectSpecResponse(
        recommendation_id=f"rec_{uuid.uuid4().hex}",
        start_date=start_date,
        end_date=end_date,
        results_by_need=[NeedResult.model_validate(row) for row in rows],
    )


def _session_indexing_ok(session: ProjectKnowledgeSession) -> bool:
    """Session existence implies gate success unless meta overrides."""
    meta = session.meta or {}
    if "indexing_ok" in meta:
        return bool(meta["indexing_ok"])
    return True


class SessionRecommendService:
    """Recommend quote for an existing Call 1 session."""

    def __init__(
        self,
        recommendation_service: RecommendationService | None = None,
        *,
        catalog: RecommendToolCatalog | None = None,
        decomposer: NeedDecomposer | None = None,
        price_fn: Callable[..., dict[str, Any]] | None = None,
        fanout_cap: int | None = None,
        via_agent_graph: bool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._recommend = recommendation_service or RecommendationService()
        self._catalog = catalog
        self._decomposer = decomposer
        self._price_fn = price_fn
        self._fanout_cap = fanout_cap
        self._via_agent_graph = via_agent_graph
        self._settings = settings

    def _use_agent_graph(self) -> bool:
        if self._via_agent_graph is not None:
            return bool(self._via_agent_graph)
        cfg = self._settings or get_settings()
        return bool(cfg.recommend_via_agent_graph)

    def recommend(
        self,
        *,
        user_id: str,
        ingest_id: str,
        query: str | None = None,
        top_k: int | None = None,
        include_pricing: bool = True,
    ) -> AssetRecommendResponse:
        session = get_project_knowledge_registry().get(user_id, ingest_id)
        meta = session.meta or {}
        project_text = project_text_from_session(session)
        if query and str(query).strip():
            project_text = f"{project_text}\n\nFocus: {str(query).strip()}"

        start = _parse_iso_date(meta.get("tentative_start_date"))
        end = _parse_iso_date(meta.get("tentative_end_date"))

        if self._use_agent_graph():
            recommend = self._recommend_via_graph(
                session=session,
                user_id=user_id,
                ingest_id=ingest_id,
                project_text=project_text,
                start=start,
                end=end,
                include_pricing=include_pricing,
            )
        else:
            recommend = self._recommend.recommend_from_project_spec(
                project_text=project_text,
                file_text=None,
                start_date=start,
                end_date=end,
                options=RecommendOptions(include_pricing=include_pricing),
            )
        return map_recommend_to_quote(
            user_id=user_id,
            ingest_id=ingest_id,
            query=query,
            recommend=recommend,
            session=session,
            top_k=top_k,
        )

    def _recommend_via_graph(
        self,
        *,
        session: ProjectKnowledgeSession,
        user_id: str,
        ingest_id: str,
        project_text: str,
        start: date | None,
        end: date | None,
        include_pricing: bool,
    ) -> RecommendFromProjectSpecResponse:
        gate_ok = _session_indexing_ok(session)
        state = run_recommend_graph(
            user_id=user_id,
            ingest_id=ingest_id,
            indexing_ok=gate_ok,
            source_text=project_text,
            start_date=start.isoformat() if start is not None else None,
            end_date=end.isoformat() if end is not None else None,
            include_pricing=include_pricing,
            catalog=self._catalog,
            decomposer=self._decomposer,
            fanout_cap=self._fanout_cap,
            price_fn=self._price_fn,
            settings=self._settings,
            project_session=session,
        )
        if not state_indexing_ok(state):
            raise BadRequestError(
                "indexing gate refused: indexing_ok=false; no recommend"
            )
        return results_to_recommend_response(
            state, start_date=start, end_date=end
        )

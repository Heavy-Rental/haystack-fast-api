"""Call 2: recommend / quote from a Call 1 project-knowledge session.

Uses FR-010 ``RecommendationService`` (seed fleet + pricing) grounded on session
text/meta. Does **not** invent asset_id or rates.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from app.schemas.recommend_quote import (
    AssetRecommendResponse,
    EquipmentQuote,
    RecommendQuoteItem,
)
from app.schemas.recommendations import (
    RecommendFromProjectSpecResponse,
    RecommendOptions,
)
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


class SessionRecommendService:
    """Recommend quote for an existing Call 1 session."""

    def __init__(self, recommendation_service: RecommendationService | None = None) -> None:
        self._recommend = recommendation_service or RecommendationService()

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

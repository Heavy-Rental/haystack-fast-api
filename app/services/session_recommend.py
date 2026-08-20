"""Call 2: recommend / quote from a Call 1 project-knowledge session.

Default: FR-010 ``RecommendationService`` (seed fleet + pricing).
S7.5: ``RECOMMEND_VIA_AGENT_GRAPH=true`` runs the C/W/D graph and maps
``results_by_need`` onto the **same** quote DTO. Does **not** invent
asset_id or rates. ``tool_traces`` stay on graph state (not the HTTP body).
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.agents.recommend_graph import run_recommend_graph
from app.agents.recommend_state import indexing_ok as state_indexing_ok
from app.agents.tool_factory import RecommendToolCatalog
from app.config import Settings, get_settings, is_sql_fleet_backend
from app.core.exceptions import BadRequestError
from app.repositories.fleet_repository import FleetRepository
from app.schemas.recommend_quote import (
    AssetRecommendResponse,
    EquipmentQuote,
    RecommendQuoteItem,
)
from app.schemas.recommendations import (
    NeedResult,
    RecommendationItem,
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

# Quantity expansion ids: ``{base}__u{i}`` (see expand_needs_to_unit_dicts).
_UNIT_NEED_RE = re.compile(r"^(.+)__u\d+$")


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


def compute_confidence_score(
    *,
    items: list[RecommendQuoteItem],
    need_count: int,
    has_dates: bool,
) -> float | None:
    """Evidence-based quote confidence (not an LLM stub).

    Weighted sum of observable signals, capped at 0.99:

    * 0.30 need coverage (items / needs)
    * 0.20 mean item matchScore
    * 0.20 live ``assets.id`` (digit ``equipment.id``)
    * 0.15 ``equipment.available is True``
    * 0.10 ``mlPredictedPrice > 0``
    * 0.05 both rental dates known
    """
    if not items:
        return None
    n = float(len(items))
    needs = max(1, int(need_count or 0))
    coverage = min(1.0, n / needs)
    scores = [
        float(item.matchScore)
        for item in items
        if item.matchScore is not None
    ]
    mean_match = (sum(scores) / len(scores)) if scores else 0.0
    live = (
        sum(1 for item in items if str(item.equipment.id or "").isdigit()) / n
    )
    available = (
        sum(1 for item in items if item.equipment.available is True) / n
    )
    priced_hits = 0
    for item in items:
        raw = item.mlPredictedPrice
        if raw is None:
            continue
        try:
            if float(raw) > 0:
                priced_hits += 1
        except (TypeError, ValueError):
            continue
    priced = priced_hits / n
    total = (
        0.30 * coverage
        + 0.20 * mean_match
        + 0.20 * live
        + 0.15 * available
        + 0.10 * priced
        + (0.05 if has_dates else 0.0)
    )
    return round(min(0.99, max(0.0, total)), 2)


def _parent_unit_need_id(need_id: str | None) -> str | None:
    """Return ``{base}`` for ``{base}__u{i}`` unit-need ids; otherwise None."""
    if not need_id:
        return None
    match = _UNIT_NEED_RE.fullmatch(need_id)
    return match.group(1) if match else None


def collapse_duplicate_equipment_quotes(
    items: list[RecommendQuoteItem],
) -> list[RecommendQuoteItem]:
    """Merge unit-need quote lines that share parent need + equipment.id.

    Quantity expansion emits ``need_1__u1`` / ``need_1__u2`` as separate items
    with ``quantity=1``. When they resolve to the same catalog asset, collapse
    to one line whose ``quantity`` is the number of grouped duplicates
    (3 copies → ``quantity=3``), parent ``needId``, and summed ``lineTotal``.
    Distinct equipment under the same parent, and the same equipment on
    different parent needs, stay separate. Rank is re-numbered 1..n.
    Merged ``quantity > 1`` sets ``equipment.available`` false: one physical
    machine cannot fulfill N concurrent units.
    """
    grouped: dict[tuple[str, str] | int, list[RecommendQuoteItem]] = {}
    order: list[tuple[str, str] | int] = []
    for idx, item in enumerate(items):
        parent = _parent_unit_need_id(item.needId)
        eq_id = str(item.equipment.id or "").strip()
        key: tuple[str, str] | int
        if parent and eq_id:
            key = (parent, eq_id)
        else:
            key = idx
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(item)

    collapsed: list[RecommendQuoteItem] = []
    for rank, key in enumerate(order, start=1):
        group = grouped[key]
        if len(group) == 1:
            collapsed.append(group[0].model_copy(update={"rankOrder": rank}))
            continue
        first = group[0]
        parent_id = key[0] if isinstance(key, tuple) else first.needId
        totals = [row.lineTotal for row in group if row.lineTotal is not None]
        # Each grouped line is one duplicate (Call 2 emits quantity=1).
        # Three duplicates → quantity 3.
        quantity = sum(max(1, int(row.quantity or 1)) for row in group)
        equipment = first.equipment.model_copy(update={"available": False})
        collapsed.append(
            first.model_copy(
                update={
                    "rankOrder": rank,
                    "needId": parent_id,
                    "quantity": quantity,
                    "lineTotal": sum(totals) if totals else None,
                    "equipment": equipment,
                }
            )
        )
    return collapsed


def _warn_unfulfillable_quantity(
    items: list[RecommendQuoteItem],
    warnings: list[str],
) -> None:
    """One physical ``assets.id`` cannot fulfill quantity > 1 in one window."""
    for item in items:
        if item.quantity <= 1:
            continue
        eq_id = item.equipment.id or "?"
        warnings.append(
            f"cannot fulfill quantity={item.quantity} of assets.id={eq_id}; "
            "one physical machine"
        )


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


def _lookup_asset_row(
    *,
    item: RecommendationItem,
    session: Any | None,
) -> dict[str, Any] | None:
    """Resolve the selected item against the assets table (id or name)."""
    if session is None:
        return None
    keys: list[str] = []
    if item.fleet_id is not None:
        keys.append(str(item.fleet_id))
    if item.asset_id:
        keys.append(str(item.asset_id))
    if item.name and str(item.name) not in keys:
        keys.append(str(item.name))
    repo = FleetRepository()
    for key in keys:
        try:
            row = repo.get_asset(session, key)
        except Exception:
            logger.debug("assets-table lookup failed for key=%s", key, exc_info=True)
            return None
        if row is not None:
            return row
    return None


_AERIAL_CATEGORY_IDS = frozenset({2, 3})


def _is_aerial_asset(*parts: Any) -> bool:
    """Scissor / boom: category_id 2 or 3, or name/type contains scissor/boom."""
    for part in parts:
        if isinstance(part, dict):
            try:
                if int(part.get("category_id")) in _AERIAL_CATEGORY_IDS:
                    return True
            except (TypeError, ValueError):
                # category_id may be missing/non-numeric; fall back to text heuristics below.
                # This preserves existing behavior without failing recommendation flow.
                pass
            blob = " ".join(
                str(part.get(k) or "")
                for k in ("equipment_type", "category", "name")
            )
        else:
            blob = str(part or "")
        lowered = blob.lower()
        if "scissor" in lowered or "boom" in lowered:
            return True
    return False


def _platform_height_for_quote(
    row: dict[str, Any] | None,
    item: RecommendationItem,
) -> float | None:
    raw = None
    if row:
        raw = row.get("platform_height")
    if raw is None:
        raw = item.platform_height
    try:
        height = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        height = None
    if height is None:
        return None
    if _is_aerial_asset(row or {}, item.equipment_type, item.name, item.asset_id):
        return height
    return None


def _pipeline_available(item: RecommendationItem) -> bool | None:
    status = str(item.availability or "").strip().lower()
    if status == "available":
        return True
    if status == "unavailable":
        return False
    return None


def _hydrate_available(
    *,
    row: dict[str, Any],
    session: Any,
    start: date | None,
    end: date | None,
    warnings: list[str],
) -> bool | None:
    """Live-hold availability from bookings + return_records. Failure → null."""
    repo = FleetRepository()
    pk = row.get("id")
    try:
        pk_int = int(pk) if pk is not None else None
    except (TypeError, ValueError):
        pk_int = None
    try:
        available = repo.is_asset_available(
            session, pk_int, start_date=start, end_date=end
        )
    except Exception:
        logger.debug("availability lookup failed for id=%s", pk, exc_info=True)
        warnings.append(
            f"availability unread for assets.id={pk}; left null (no invent)"
        )
        return None
    if available is None:
        warnings.append(
            f"availability unread for assets.id={pk}; left null (no invent)"
        )
    return available


def _equipment_quote(
    item: RecommendationItem,
    *,
    daily: float | None,
    extra: dict[str, Any],
    session: Any | None = None,
    require_table_row: bool = False,
    start: date | None = None,
    end: date | None = None,
    warnings: list[str] | None = None,
) -> EquipmentQuote | None:
    """Build quote equipment from the assets table when a row resolves.

    ``equipment.id`` is ``assets.id`` (PK) when known so Spring can FK
    ``recommendation_items.asset_id``. Seed-only picks keep the catalog
    ``asset_id`` and never invent a PK. On the live SQL path
    (``require_table_row``) a missing row is dropped instead of emitting
    a seed ``AST-*`` id.
    """
    notes = warnings if warnings is not None else []
    row = _lookup_asset_row(item=item, session=session)
    if row is not None and row.get("id") is not None:
        for key, value in {
            "capacity": row.get("capacity"),
            "condition": row.get("condition"),
            "platform_height": row.get("platform_height"),
        }.items():
            if value is not None and key not in extra:
                extra[key] = value
        available = _pipeline_available(item)
        if session is not None:
            available = _hydrate_available(
                row=row,
                session=session,
                start=start,
                end=end,
                warnings=notes,
            )
        return EquipmentQuote(
            id=str(row["id"]),
            name=row.get("name") or item.name or item.equipment_type,
            category=row.get("equipment_type") or item.equipment_type,
            baseDailyRate=daily,
            weekly=None,
            capacity=row.get("capacity"),
            purchaseYear=row.get("purchase_year"),
            location=row.get("location"),
            available=available,
            desc=row.get("description"),
            platformHeight=_platform_height_for_quote(row, item),
            tags=[],
            extra=extra,
        )
    if item.fleet_id is not None:
        return EquipmentQuote(
            id=str(item.fleet_id),
            name=item.name or item.equipment_type,
            category=item.equipment_type,
            baseDailyRate=daily,
            weekly=None,
            available=_pipeline_available(item),
            platformHeight=_platform_height_for_quote(None, item),
            tags=[],
            extra=extra,
        )
    if require_table_row:
        return None
    return EquipmentQuote(
        id=item.asset_id,
        name=item.name or item.equipment_type,
        category=item.equipment_type,
        baseDailyRate=daily,
        weekly=None,
        available=_pipeline_available(item),
        platformHeight=_platform_height_for_quote(None, item),
        tags=[],
        extra=extra,
    )


def map_recommend_to_quote(
    *,
    user_id: str,
    ingest_id: str,
    query: str | None,
    recommend: RecommendFromProjectSpecResponse,
    session: ProjectKnowledgeSession,
    top_k: int | None = None,
    db: Session | None = None,
    require_table_row: bool = False,
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
        if top_k is not None and len(items) >= top_k:
            break
        daily = item.pricing.daily_rate if item.pricing else None
        total = item.pricing.total_price if item.pricing else None
        if total is None and daily is not None and days is not None:
            total = float(daily) * float(days)
        extra = {
            k: v
            for k, v in {
                "availability": item.availability,
                "currency": (item.pricing.currency if item.pricing else None),
                "model_version": (
                    item.pricing.model_version if item.pricing else None
                ),
                "was_clamped": (
                    item.pricing.was_clamped
                    if item.pricing and item.pricing.was_clamped is not None
                    else None
                ),
                "explanation": (
                    item.pricing.explanation if item.pricing else None
                ),
            }.items()
            if v is not None
        }
        equipment = _equipment_quote(
            item,
            daily=daily,
            extra=extra,
            session=db,
            require_table_row=require_table_row,
            start=start,
            end=end,
            warnings=warnings,
        )
        if equipment is None:
            warnings.append(
                f"assets table has no row for need_id={need_result.need_id!r} "
                f"asset_id={item.asset_id!r}; omitted (live fleet, no seed id)"
            )
            continue
        rank += 1
        if daily is not None:
            has_price = True
        if total is not None:
            estimated += float(total)
        if item.rationale:
            rationales.append(str(item.rationale))
        score = item.match_score
        if score is None:
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
                mlPredictedPrice=daily,
                equipment=equipment,
            )
        )

    if not items:
        warnings.append("No equipment matched for this project-spec session")

    items = collapse_duplicate_equipment_quotes(items)
    _warn_unfulfillable_quantity(items, warnings)

    needs_meta = meta.get("needs_summary") if isinstance(meta.get("needs_summary"), list) else []
    need_count = len(needs_meta) if needs_meta else len(recommend.results_by_need)
    conf = compute_confidence_score(
        items=items,
        need_count=need_count,
        has_dates=start is not None and end is not None,
    )

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
        self._recommend = recommendation_service
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

        cfg = self._settings or get_settings()
        live_sql = is_sql_fleet_backend(getattr(cfg, "fleet_backend", None))
        db: Session | None = None
        owned_db = False
        if live_sql:
            from app.core.db import SessionLocal

            db = SessionLocal()
            owned_db = True
        try:
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
                svc = self._recommend
                if svc is None:
                    svc = RecommendationService(db=db, settings=cfg)
                recommend = svc.recommend_from_project_spec(
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
                db=db,
                require_table_row=live_sql,
            )
        finally:
            if owned_db and db is not None:
                db.close()

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

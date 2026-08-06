"""FR-010.5 — Filter candidates by booking date-window overlap (seed MVP)."""

from __future__ import annotations

from datetime import date
from typing import Any

from haystack import component

from app.pipelines.seed_fleet import get_seed_bookings


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _ranges_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


@component
class BookingAvailabilityFilter:
    """Remove candidates with overlapping seed bookings for the rental window.

    If start_date or end_date is missing, all candidates pass as available (FR-013
    only applies when dates are provided).
    """

    def __init__(self, bookings: list[dict[str, Any]] | None = None) -> None:
        self._bookings = bookings

    @component.output_types(available_candidates=list)
    def run(
        self,
        candidates: list | None = None,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> dict[str, list]:
        pool = list(candidates or [])
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        if start is None or end is None or not pool:
            return {"available_candidates": [dict(c) for c in pool]}

        bookings = self._bookings if self._bookings is not None else get_seed_bookings()
        busy: set[str] = set()
        for booking in bookings:
            b_start = _parse_date(booking.get("start_date"))
            b_end = _parse_date(booking.get("end_date"))
            asset_id = str(booking.get("asset_id") or "")
            if not asset_id or b_start is None or b_end is None:
                continue
            if _ranges_overlap(start, end, b_start, b_end):
                busy.add(asset_id)

        available = [
            dict(c)
            for c in pool
            if str(c.get("asset_id") or "") not in busy
        ]
        for c in available:
            c["availability"] = "available"
        return {"available_candidates": available}

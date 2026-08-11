"""Resolve Call 1 rental dates: request preferred, else free-text extract (S1e).

Never invent dates. Request values always override extract when present.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")

# Range patterns (non-greedy between dates)
_FROM_TO_ISO = re.compile(
    r"(?i)\b(?:from|start(?:ing)?(?:\s+date)?|begin(?:ning)?)\s*[:=]?\s*"
    r"(\d{4}-\d{2}-\d{2})\s*"
    r"(?:to|until|through|-|–|—)\s*"
    r"(\d{4}-\d{2}-\d{2})\b"
)
_BETWEEN_ISO = re.compile(
    r"(?i)\bbetween\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})\b"
)
_FROM_TO_DMY = re.compile(
    r"(?i)\b(?:from|start(?:ing)?(?:\s+date)?|begin(?:ning)?)\s*[:=]?\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*"
    r"(?:to|until|through|-|–|—)\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b"
)
_START_ONLY_ISO = re.compile(
    r"(?i)\b(?:start(?:ing)?(?:\s+date)?|from|begin(?:ning)?)\s*[:=]?\s*"
    r"(\d{4}-\d{2}-\d{2})\b"
)
_END_ONLY_ISO = re.compile(
    r"(?i)\b(?:end(?:ing)?(?:\s+date)?|until|to|through)\s*[:=]?\s*"
    r"(\d{4}-\d{2}-\d{2})\b"
)


def _parse_iso(y: str, m: str, d: str) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _parse_dmy(token: str) -> date | None:
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", token.strip())
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Prefer DMY (common in SG/AU); reject impossible months
    if month > 12 and day <= 12:
        day, month = month, day
    if month > 12 or day > 31:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_iso_token(token: str) -> date | None:
    m = _ISO.fullmatch(token.strip()) if hasattr(_ISO, "fullmatch") else None
    if m is None:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", token.strip())
    if not m:
        return None
    return _parse_iso(m.group(1), m.group(2), m.group(3))


def _extract_pair_from_text(text: str) -> tuple[date | None, date | None]:
    """Best-effort pair or single-bound extract; never invent."""
    source = text or ""

    for rx in (_FROM_TO_ISO, _BETWEEN_ISO):
        m = rx.search(source)
        if m:
            a = _parse_iso_token(m.group(1))
            b = _parse_iso_token(m.group(2))
            if a and b:
                return (a, b) if a <= b else (b, a)

    m = _FROM_TO_DMY.search(source)
    if m:
        a = _parse_dmy(m.group(1))
        b = _parse_dmy(m.group(2))
        if a and b:
            return (a, b) if a <= b else (b, a)

    # Two bare ISO dates in order → treat as window if chronological
    isos = list(_ISO.finditer(source))
    if len(isos) >= 2:
        a = _parse_iso(isos[0].group(1), isos[0].group(2), isos[0].group(3))
        b = _parse_iso(isos[1].group(1), isos[1].group(2), isos[1].group(3))
        if a and b and a <= b:
            return a, b

    start_m = _START_ONLY_ISO.search(source)
    end_m = _END_ONLY_ISO.search(source)
    start_only = (
        _parse_iso_token(start_m.group(1)) if start_m else None
    )
    end_only = _parse_iso_token(end_m.group(1)) if end_m else None
    if start_only or end_only:
        if start_only and end_only and start_only > end_only:
            return None, None
        return start_only, end_only

    # Single ISO date with rental-window cue
    if len(isos) == 1:
        window = source[max(0, isos[0].start() - 30) : isos[0].end() + 30]
        if re.search(r"(?i)\b(start|from|begin|end|until|rental|hire|mobilis)", window):
            d = _parse_iso(isos[0].group(1), isos[0].group(2), isos[0].group(3))
            if d and re.search(r"(?i)\b(end|until|through)\b", window):
                return None, d
            if d:
                return d, None

    return None, None


def resolve_rental_dates(
    *,
    request_start: date | None,
    request_end: date | None,
    text: str,
) -> tuple[date | None, date | None, list[str]]:
    """Merge request echo (preferred) with free-text extract.

    Returns (start, end, warnings).
    """
    warnings: list[str] = []

    # Request both set: pure echo (S1b); already validated end>=start at API layer
    if request_start is not None and request_end is not None:
        return request_start, request_end, warnings

    ext_start, ext_end = _extract_pair_from_text(text)

    start = request_start if request_start is not None else ext_start
    end = request_end if request_end is not None else ext_end

    if start is not None and end is not None and end < start:
        warnings.append("rental dates invalid or inconsistent; not inventing")
        # Prefer request sides if any valid alone
        if request_start is not None and request_end is None:
            return request_start, None, warnings
        if request_end is not None and request_start is None:
            return None, request_end, warnings
        return None, None, warnings

    if start is None and end is None:
        if not (request_start or request_end):
            warnings.append("rental dates not found")
        return None, None, warnings

    if request_start is None and ext_start is not None:
        # extracted start used
        pass
    if request_end is None and ext_end is not None:
        pass

    return start, end, warnings

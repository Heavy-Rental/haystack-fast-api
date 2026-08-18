"""Resolve Call 1 rental dates: request preferred, else free-text extract (S1e).

Never invent dates. Request values always override extract when present.
"""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")
_YMD_SEP = re.compile(r"\b(\d{4})[/.](\d{1,2})[/.](\d{1,2})\b")
_DMY = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")

_MONTH_ALT = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
)
_MONTH_DOT = rf"(?:{_MONTH_ALT})\.?"
_ORD = r"(?:st|nd|rd|th)?"
_YEAR = r"(?:\d{4}|\d{2})"
_MONTH_NUM: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
# 1 Sep 2026 | 1st of September 2026 | 1-Sep-26 | Sep. 1, 2026
_NAMED_DATE = (
    rf"(?:\d{{1,2}}{_ORD}(?:\s+of)?[\s\-]+{_MONTH_DOT}[\s\-]+{_YEAR}"
    rf"|{_MONTH_DOT}[\s\-]+\d{{1,2}}{_ORD},?[\s\-]+{_YEAR})"
)
_NUMERIC_DATE = (
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?"
    r"|20\d{6}"
    r"|\d{4}[/.]\d{1,2}[/.]\d{1,2}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
)
_ANY_DATE = rf"(?:{_NAMED_DATE}|{_NUMERIC_DATE})"
_ANY_DATE_RX = re.compile(rf"\b({_ANY_DATE})\b", re.IGNORECASE)
_RANGE_LEAD = r"(?:from|on|start(?:ing)?(?:\s+date)?|begin(?:ning)?)"
_RANGE_MID = r"(?:to|until|through|till|-|–|—)"

_FROM_TO_ANY = re.compile(
    rf"(?i)\b{_RANGE_LEAD}\s*[:=]?\s*({_ANY_DATE})\s*{_RANGE_MID}\s*({_ANY_DATE})\b"
)
_BETWEEN_ANY = re.compile(rf"(?i)\bbetween\s+({_ANY_DATE})\s+and\s+({_ANY_DATE})\b")
_START_ONLY_ANY = re.compile(
    rf"(?i)\b(?:start(?:ing)?(?:\s+date)?|from|on|begin(?:ning)?)\s*[:=]?\s*"
    rf"({_ANY_DATE})\b"
)
_END_ONLY_ANY = re.compile(
    rf"(?i)\b(?:end(?:ing)?(?:\s+date)?|until|to|through|till)\s*[:=]?\s*"
    rf"({_ANY_DATE})\b"
)
_QUARTER = re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE)
_MONTH_YEAR = re.compile(rf"\b({_MONTH_DOT})\s+(\d{{4}})\b", re.IGNORECASE)
_END_OF_MONTH = re.compile(
    rf"\b(?:end|ending|close)\s+of\s+({_MONTH_DOT})(?:\s+(\d{{4}}))?\b", re.IGNORECASE
)
_START_OF_MONTH = re.compile(
    rf"\b(?:start|starting|beginning|begin)\s+of\s+({_MONTH_DOT})(?:\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
_NEXT_MONTH = re.compile(r"\bnext\s+month\b", re.IGNORECASE)
_THIS_MONTH = re.compile(r"\bthis\s+month\b", re.IGNORECASE)
_QUARTER_MONTHS: dict[int, tuple[int, int]] = {
    1: (1, 3),
    2: (4, 6),
    3: (7, 9),
    4: (10, 12),
}


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _month_from_token(token: str) -> int | None:
    return _MONTH_NUM.get(token.strip(".").strip().lower())


def _year_for_month(month: int, year_token: str | None, *, today: date) -> int:
    if year_token:
        return _expand_year(int(year_token))
    if _month_end(today.year, month) >= today:
        return today.year
    return today.year + 1


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _extract_phrase_window(text: str, *, today: date) -> tuple[date | None, date | None]:
    """Quarter / month / relative phrases. Not used for heights like ``8m``."""
    source = text or ""

    q = _QUARTER.search(source)
    if q:
        first, last = _QUARTER_MONTHS[int(q.group(1))]
        year = int(q.group(2))
        return date(year, first, 1), _month_end(year, last)

    end_of = _END_OF_MONTH.search(source)
    if end_of:
        month = _month_from_token(end_of.group(1))
        if month:
            year = _year_for_month(month, end_of.group(2), today=today)
            return None, _month_end(year, month)

    start_of = _START_OF_MONTH.search(source)
    if start_of:
        month = _month_from_token(start_of.group(1))
        if month:
            year = _year_for_month(month, start_of.group(2), today=today)
            return date(year, month, 1), None

    my = _MONTH_YEAR.search(source)
    if my:
        month = _month_from_token(my.group(1))
        if month:
            year = int(my.group(2))
            return date(year, month, 1), _month_end(year, month)

    if _NEXT_MONTH.search(source):
        year, month = _shift_month(today.year, today.month, 1)
        return date(year, month, 1), _month_end(year, month)

    if _THIS_MONTH.search(source):
        return date(today.year, today.month, 1), _month_end(today.year, today.month)

    return None, None


def _parse_iso(y: str | int, m: str | int, d: str | int) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _expand_year(year: int) -> int:
    """Map 00–99 to 2000–2099 (rental windows are current-century)."""
    if 0 <= year < 100:
        return 2000 + year
    return year


def _parse_dmy(token: str) -> date | None:
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", token.strip())
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), _expand_year(int(m.group(3)))
    # Prefer DMY (common in SG/AU); reject impossible months
    if month > 12 and day <= 12:
        day, month = month, day
    if month > 12 or day > 31:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_named_token(token: str) -> date | None:
    text = re.sub(r"\s+", " ", (token or "").strip().strip(".,"))
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bof\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    dmy = re.fullmatch(
        rf"(\d{{1,2}})[\s\-]+({_MONTH_DOT})[\s\-]+(\d{{2,4}})", text, flags=re.IGNORECASE
    )
    if dmy:
        return _parse_named_parts(int(dmy.group(1)), dmy.group(2), _expand_year(int(dmy.group(3))))
    mdy = re.fullmatch(
        rf"({_MONTH_DOT})[\s\-]+(\d{{1,2}}),?[\s\-]+(\d{{2,4}})", text, flags=re.IGNORECASE
    )
    if mdy:
        return _parse_named_parts(int(mdy.group(2)), mdy.group(1), _expand_year(int(mdy.group(3))))
    return None


def _parse_named_parts(day: int, month_token: str, year: int) -> date | None:
    key = month_token.strip(".").strip().lower()
    month = _MONTH_NUM.get(key)
    if month is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_iso_token(token: str) -> date | None:
    text = token.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not m:
        return None
    return _parse_iso(m.group(1), m.group(2), m.group(3))


def _parse_any_token(token: str) -> date | None:
    """Parse one captured date token (named or numeric). Never invent."""
    text = (token or "").strip()
    if not text:
        return None
    parsed = _parse_named_token(text)
    if parsed:
        return parsed
    parsed = _parse_iso_token(text)
    if parsed:
        return parsed
    compact = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})", text)
    if compact:
        return _parse_iso(compact.group(1), compact.group(2), compact.group(3))
    ymd = re.fullmatch(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", text)
    if ymd:
        return _parse_iso(ymd.group(1), ymd.group(2), ymd.group(3))
    return _parse_dmy(text)


def _extract_pair_from_text(
    text: str, *, today: date | None = None
) -> tuple[date | None, date | None]:
    """Best-effort pair or single-bound extract; never invent."""
    source = text or ""
    today = today or datetime.now(UTC).date()

    for rx in (_FROM_TO_ANY, _BETWEEN_ANY):
        m = rx.search(source)
        if m:
            a = _parse_any_token(m.group(1))
            b = _parse_any_token(m.group(2))
            if a and b:
                return (a, b) if a <= b else (b, a)

    found: list[date] = []
    for match in _ANY_DATE_RX.finditer(source):
        parsed = _parse_any_token(match.group(1))
        if parsed is not None:
            found.append(parsed)
    if len(found) >= 2 and found[0] <= found[1]:
        return found[0], found[1]

    start_m = _START_ONLY_ANY.search(source)
    end_m = _END_ONLY_ANY.search(source)
    start_only = _parse_any_token(start_m.group(1)) if start_m else None
    end_only = _parse_any_token(end_m.group(1)) if end_m else None
    if start_only or end_only:
        if start_only and end_only and start_only > end_only:
            return None, None
        return start_only, end_only

    if len(found) == 1:
        # Re-find span for the rental-cue window.
        only = next(_ANY_DATE_RX.finditer(source), None)
        if only is not None:
            window = source[max(0, only.start() - 30) : only.end() + 30]
            if re.search(
                r"(?i)\b(start|from|on|begin|end|until|rental|hire|mobilis)\b",
                window,
            ):
                d = found[0]
                if re.search(r"(?i)\b(end|until|through|till)\b", window):
                    return None, d
                return d, None

    return _extract_phrase_window(source, today=today)


def resolve_rental_dates(
    *,
    request_start: date | None,
    request_end: date | None,
    text: str,
    today: date | None = None,
) -> tuple[date | None, date | None, list[str]]:
    """Merge request echo (preferred) with free-text extract.

    Returns (start, end, warnings).
    """
    warnings: list[str] = []
    today = today or datetime.now(UTC).date()

    # Request both set: pure echo (S1b); already validated end>=start at API layer
    if request_start is not None and request_end is not None:
        return request_start, request_end, warnings

    ext_start, ext_end = _extract_pair_from_text(text, today=today)

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

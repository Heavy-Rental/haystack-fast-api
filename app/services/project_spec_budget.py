"""Deterministic expected_budget extract from project-spec text (FR-IX-023 / S1d).

Never invents a budget. Returns null when no confident currency+amount pattern
is found. Does not use options.include_pricing (boolean only).
"""

from __future__ import annotations

import re
from typing import Any

_CURRENCY_CODES = r"SGD|USD|EUR|GBP|AUD|MYR|IDR|THB|JPY|CNY|RM"
_AMOUNT = (
    r"(?P<amount>\d{1,3}(?:[ ,]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"(?P<scale>[kKmM])?"
)
_CUE = (
    r"budget|cost|capex|estimate|estimated|approx\.?|approximately|"
    r"not\s+to\s+exceed|nte|allocation|spend|quote|priced|pricing|"
    r"fees?(?!t)|limit|ceiling|capped|cap(?:\s+of)?"
)
_BUDGET_CUE = re.compile(rf"(?i)\b(?:{_CUE})\b")
_HEIGHT_OR_SIZE = re.compile(r"(?i)\b\d+(?:\.\d+)?\s*(?:m|metre|meter|ton|tonne|ft|feet)\b")

_CODE_BEFORE = re.compile(
    rf"(?i)\b(?:{_CUE})?\s*[:\-]?\s*"
    rf"(?P<currency>{_CURRENCY_CODES})\s*"
    rf"{_AMOUNT}\b"
)
_CODE_AFTER = re.compile(rf"(?i)\b{_AMOUNT}\s*(?P<currency>{_CURRENCY_CODES})\b")
_SYMBOL_BEFORE = re.compile(
    rf"(?i)(?:{_CUE})?\s*[:\-]?\s*"
    r"(?P<symbol>S\$|\$|€|£|¥|￥)\s*"
    rf"{_AMOUNT}\b"
)
_SPOKEN = re.compile(
    rf"(?i)\b{_AMOUNT}\s+"
    r"(?P<spoken>singapore\s+dollars?|us\s+dollars?|dollars?|euros?|pounds?)\b"
)
_CUE_NUMBER = re.compile(rf"(?i)\b(?:{_CUE})\s*(?:of|is|at|:|-)?\s*{_AMOUNT}\b")

_SYMBOL_TO_CURRENCY = {
    "S$": "SGD",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "￥": "JPY",
}
_SPOKEN_TO_CURRENCY = {
    "singapore dollar": "SGD",
    "singapore dollars": "SGD",
    "us dollar": "USD",
    "us dollars": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "euro": "EUR",
    "euros": "EUR",
    "pound": "GBP",
    "pounds": "GBP",
}
_WINDOW_CURRENCY = re.compile(rf"(?i)\b(?P<code>{_CURRENCY_CODES})\b|S\$|singapore|\bRM\b")


def _parse_amount(raw: str, scale: str | None) -> float | None:
    try:
        value = float(raw.replace(",", "").replace(" ", ""))
    except ValueError:
        return None
    if value <= 0:
        return None
    if scale:
        letter = scale.lower()
        if letter == "k":
            value *= 1_000
        elif letter == "m":
            value *= 1_000_000
    return value


def _looks_like_height(source: str, start: int, end: int) -> bool:
    after = source[end : min(len(source), end + 16)]
    if re.search(rf"(?i)\b(?:{_CURRENCY_CODES}|dollars?|euros?|pounds?)\b", after):
        return False
    if re.search(r"S\$|\$|€|£", after):
        return False
    window = source[max(0, start - 2) : min(len(source), end + 8)]
    return _HEIGHT_OR_SIZE.search(window) is not None


def _currency_nearby(source: str, start: int, end: int) -> str | None:
    window = source[max(0, start - 40) : min(len(source), end + 40)]
    if re.search(r"S\$", window) or re.search(r"(?i)singapore", window):
        return "SGD"
    m = _WINDOW_CURRENCY.search(window)
    if not m:
        return None
    code = (m.groupdict().get("code") or "").upper()
    if code == "RM":
        return "MYR"
    if code:
        return code
    return None


def _add(
    candidates: list[tuple[int, dict[str, Any]]],
    start: int,
    amount: float,
    currency: str | None,
) -> None:
    candidates.append(
        (
            start,
            {"amount": amount, "currency": currency, "source": "extracted"},
        )
    )


def extract_expected_budget(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (budget_dict | None, warnings).

    budget_dict keys: amount (float), currency (str | None), source (\"extracted\").
    """
    warnings: list[str] = []
    source = (text or "").strip()
    if not source:
        warnings.append("expected_budget not found")
        return None, warnings

    candidates: list[tuple[int, dict[str, Any]]] = []

    for m in _CODE_BEFORE.finditer(source):
        if _looks_like_height(source, m.start("amount"), m.end()):
            continue
        amount = _parse_amount(m.group("amount"), m.group("scale"))
        if amount is None:
            continue
        code = m.group("currency").upper()
        _add(candidates, m.start(), amount, "MYR" if code == "RM" else code)

    for m in _CODE_AFTER.finditer(source):
        if _looks_like_height(source, m.start("amount"), m.end()):
            continue
        amount = _parse_amount(m.group("amount"), m.group("scale"))
        if amount is None:
            continue
        code = m.group("currency").upper()
        _add(candidates, m.start(), amount, "MYR" if code == "RM" else code)

    for m in _SYMBOL_BEFORE.finditer(source):
        if _looks_like_height(source, m.start("amount"), m.end()):
            continue
        amount = _parse_amount(m.group("amount"), m.group("scale"))
        if amount is None:
            continue
        symbol = m.group("symbol")
        currency = _SYMBOL_TO_CURRENCY.get(symbol)
        if symbol == "$":
            left = max(0, m.start() - 40)
            right = min(len(source), m.end() + 16)
            while right < len(source) and source[right].isalpha():
                right += 1
            window = source[left:right]
            has_cue = _BUDGET_CUE.search(window) is not None
            looks_money = "," in m.group("amount") or amount >= 100
            if not has_cue and not looks_money:
                continue
        _add(candidates, m.start(), amount, currency)

    for m in _SPOKEN.finditer(source):
        if _looks_like_height(source, m.start("amount"), m.end()):
            continue
        amount = _parse_amount(m.group("amount"), m.group("scale"))
        if amount is None:
            continue
        spoken = re.sub(r"\s+", " ", m.group("spoken").strip().lower())
        _add(candidates, m.start(), amount, _SPOKEN_TO_CURRENCY.get(spoken))

    for m in _CUE_NUMBER.finditer(source):
        if _looks_like_height(source, m.start("amount"), m.end()):
            continue
        amount = _parse_amount(m.group("amount"), m.group("scale"))
        if amount is None:
            continue
        currency = _currency_nearby(source, m.start(), m.end())
        _add(candidates, m.start(), amount, currency)

    if not candidates:
        warnings.append("expected_budget not found")
        return None, warnings

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1], warnings

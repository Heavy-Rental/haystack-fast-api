"""Deterministic expected_budget extract from project-spec text (FR-IX-023 / S1d).

Never invents a budget. Returns null when no confident currency+amount pattern is found.
Does not use options.include_pricing (boolean only).
"""

from __future__ import annotations

import re
from typing import Any

# Currency code before or after amount, or common symbols.
_CODE_BEFORE = re.compile(
    r"(?i)\b(?:budget|cost|capex|estimate|estimated|approx\.?|approximately|"
    r"not\s+to\s+exceed|nte|allocation)?\s*[:\-]?\s*"
    r"(?P<currency>SGD|USD|EUR|GBP|AUD|MYR|IDR|THB|JPY|CNY)\s*"
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\b"
)
_CODE_AFTER = re.compile(
    r"(?i)\b(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*"
    r"(?P<currency>SGD|USD|EUR|GBP|AUD|MYR|IDR|THB|JPY|CNY)\b"
)
_SYMBOL_BEFORE = re.compile(
    r"(?i)(?:budget|cost|capex|estimate|estimated|approx\.?|approximately|"
    r"not\s+to\s+exceed|nte|allocation)?\s*[:\-]?\s*"
    r"(?P<symbol>S\$|\$|€|£)\s*"
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\b"
)

_SYMBOL_TO_CURRENCY = {
    "S$": "SGD",
    "$": "USD",  # ambiguous; only accept with budget-like cue in pattern
    "€": "EUR",
    "£": "GBP",
}

# Prefer matches that look like budget language for bare $
_BUDGET_CUE = re.compile(
    r"(?i)\b(budget|cost|capex|estimate|estimated|approx|approximately|"
    r"not\s+to\s+exceed|nte|allocation|spend)\b"
)


def _parse_amount(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


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
        amount = _parse_amount(m.group("amount"))
        if amount is None or amount <= 0:
            continue
        candidates.append(
            (
                m.start(),
                {
                    "amount": amount,
                    "currency": m.group("currency").upper(),
                    "source": "extracted",
                },
            )
        )

    for m in _CODE_AFTER.finditer(source):
        amount = _parse_amount(m.group("amount"))
        if amount is None or amount <= 0:
            continue
        candidates.append(
            (
                m.start(),
                {
                    "amount": amount,
                    "currency": m.group("currency").upper(),
                    "source": "extracted",
                },
            )
        )

    for m in _SYMBOL_BEFORE.finditer(source):
        amount = _parse_amount(m.group("amount"))
        if amount is None or amount <= 0:
            continue
        symbol = m.group("symbol")
        currency = _SYMBOL_TO_CURRENCY.get(symbol)
        # Bare $ is ambiguous: require a budget cue in nearby context
        if symbol == "$":
            window = source[max(0, m.start() - 40) : m.end() + 10]
            if not _BUDGET_CUE.search(window):
                continue
        candidates.append(
            (
                m.start(),
                {
                    "amount": amount,
                    "currency": currency,
                    "source": "extracted",
                },
            )
        )

    if not candidates:
        warnings.append("expected_budget not found")
        return None, warnings

    # First confident match in document order
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1], warnings

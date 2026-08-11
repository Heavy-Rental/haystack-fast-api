"""Unit tests for deterministic Call 1 user_requirement_summary helper."""

from app.services.indexing import (
    USER_REQUIREMENT_SUMMARY_MAX_CHARS,
    _build_user_requirement_summary,
    _normalize_requirement_text,
)


def test_normalize_collapses_whitespace() -> None:
    raw = "  Need   scissors\n\n  lift  "
    assert _normalize_requirement_text(raw) == "Need scissors\nlift"


def test_summary_short_text_unchanged() -> None:
    text = "Indoor elevated work for scissors lift"
    summary, warnings = _build_user_requirement_summary(text)
    assert summary == text
    assert warnings == []


def test_summary_truncates_long_text() -> None:
    text = "x" * (USER_REQUIREMENT_SUMMARY_MAX_CHARS + 50)
    summary, warnings = _build_user_requirement_summary(text)
    assert len(summary) == USER_REQUIREMENT_SUMMARY_MAX_CHARS
    assert summary.endswith("…")
    assert "truncated" in warnings[0]


def test_summary_empty() -> None:
    summary, warnings = _build_user_requirement_summary("   \n  ")
    assert summary == ""
    assert warnings

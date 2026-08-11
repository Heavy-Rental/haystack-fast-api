"""Unit tests for S1e rental date resolution (request preferred, free-text extract)."""

from datetime import date

from app.services.project_spec_dates import resolve_rental_dates


def test_request_dates_override_text() -> None:
    start, end, warnings = resolve_rental_dates(
        request_start=date(2026, 10, 1),
        request_end=date(2026, 10, 15),
        text="Rental from 2026-09-01 to 2026-09-12",
    )
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 15)
    assert warnings == []


def test_extract_from_to_iso_when_request_omits() -> None:
    start, end, warnings = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Please hire from 2026-09-01 to 2026-09-12 for the fit-out.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 12)
    assert warnings == []


def test_extract_between_iso() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Works between 2026-11-01 and 2026-11-30.",
    )
    assert start == date(2026, 11, 1)
    assert end == date(2026, 11, 30)


def test_no_dates_returns_null_with_warning() -> None:
    start, end, warnings = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Indoor elevated work for scissors lift on soft clay.",
    )
    assert start is None
    assert end is None
    assert any("not found" in w for w in warnings)


def test_request_start_only_keeps_extract_end() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=date(2026, 9, 1),
        request_end=None,
        text="Until 2026-09-30 for demobilisation.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_never_invent_from_random_numbers() -> None:
    start, end, warnings = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="We need 20 ton excavators and 8m boom reach.",
    )
    assert start is None
    assert end is None
    assert any("not found" in w for w in warnings)

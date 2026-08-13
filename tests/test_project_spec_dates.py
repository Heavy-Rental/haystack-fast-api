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


def test_extract_from_to_named_month() -> None:
    start, end, warnings = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Warehouse fit-out on 1 Sep 2026 to 30 Sep 2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)
    assert warnings == []


def test_extract_between_named_month() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Works between 1 September 2026 and 30 September 2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_mdy_named_pair() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Hire Sep 1, 2026 to Sep 30, 2026 for the fit-out.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_two_bare_named_dates() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Mobilise 1 Sep 2026. Demobilise 30 Sep 2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_named_start_only_with_cue() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Rental starting 1 Sep 2026 for the warehouse fit-out.",
    )
    assert start == date(2026, 9, 1)
    assert end is None


def test_extract_ordinal_and_of() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="From the 1st of September 2026 to the 30th of September 2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_hyphenated_named() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Hire 1-Sep-2026 to 30-Sep-2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_two_digit_year() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Rental from 1 Sep 26 to 30 Sep 26.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_dotted_dmy_and_ymd_slash() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="From 01.09.2026 to 30.09.2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Window 2026/09/01 to 2026/09/30.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_iso_datetime() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Start 2026-09-01T08:00:00 until 2026-09-30T18:00:00.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_compact_yyyymmdd() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Period 20260901 to 20260930.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_quarter() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Need scissors lifts for Q3 2026 warehouse work.",
    )
    assert start == date(2026, 7, 1)
    assert end == date(2026, 9, 30)


def test_extract_month_only_year() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Hire a forklift in Sep 2026.",
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_end_of_month_with_year() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Available until end of September 2026.",
    )
    assert start is None
    assert end == date(2026, 9, 30)


def test_extract_end_of_month_infers_year() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Need boom lift until end of September.",
        today=date(2026, 8, 13),
    )
    assert start is None
    assert end == date(2026, 9, 30)


def test_extract_next_month() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Need a scissor lift next month.",
        today=date(2026, 8, 13),
    )
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 30)


def test_extract_this_month() -> None:
    start, end, _ = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="Mobilise this month for indoor work.",
        today=date(2026, 8, 13),
    )
    assert start == date(2026, 8, 1)
    assert end == date(2026, 8, 31)


def test_never_invent_from_random_numbers() -> None:
    start, end, warnings = resolve_rental_dates(
        request_start=None,
        request_end=None,
        text="We need 20 ton excavators and 8m boom reach.",
    )
    assert start is None
    assert end is None
    assert any("not found" in w for w in warnings)

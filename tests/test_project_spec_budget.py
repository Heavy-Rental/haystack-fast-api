"""Unit tests for S1d expected_budget extract (never invent)."""

from app.services.project_spec_budget import extract_expected_budget


def test_extract_sgd_code_before_amount() -> None:
    budget, warnings = extract_expected_budget(
        "Project budget SGD 15,000 for scissors lifts on site."
    )
    assert budget is not None
    assert budget["amount"] == 15000.0
    assert budget["currency"] == "SGD"
    assert budget["source"] == "extracted"
    assert warnings == []


def test_extract_amount_then_currency() -> None:
    budget, warnings = extract_expected_budget("Total estimate 25000 USD for earthworks.")
    assert budget is not None
    assert budget["amount"] == 25000.0
    assert budget["currency"] == "USD"
    assert warnings == []


def test_extract_budget_cue_with_dollar() -> None:
    budget, _ = extract_expected_budget("Estimated budget: $12,500 for access equipment.")
    assert budget is not None
    assert budget["amount"] == 12500.0
    assert budget["currency"] == "USD"


def test_extract_code_no_space_and_k_suffix() -> None:
    budget, _ = extract_expected_budget("Cap SGD8000 for the fleet hire.")
    assert budget is not None
    assert budget["amount"] == 8000.0
    assert budget["currency"] == "SGD"
    budget, _ = extract_expected_budget("Need scissors. Budget SGD 8k.")
    assert budget is not None
    assert budget["amount"] == 8000.0


def test_extract_millions_with_currency() -> None:
    budget, _ = extract_expected_budget("Project estimate 1.5m SGD for the fit-out.")
    assert budget is not None
    assert budget["amount"] == 1_500_000.0
    assert budget["currency"] == "SGD"


def test_extract_spoken_and_rm() -> None:
    budget, _ = extract_expected_budget("Allow 8000 Singapore dollars for rental.")
    assert budget is not None
    assert budget["amount"] == 8000.0
    assert budget["currency"] == "SGD"
    budget, _ = extract_expected_budget("Budget RM 8000 for the excavator.")
    assert budget is not None
    assert budget["amount"] == 8000.0
    assert budget["currency"] == "MYR"


def test_extract_cue_bare_number_and_spaced_thousands() -> None:
    budget, _ = extract_expected_budget("Max budget of 8000 for indoor work.")
    assert budget is not None
    assert budget["amount"] == 8000.0
    budget, _ = extract_expected_budget("budget: 8 000 on this package.")
    assert budget is not None
    assert budget["amount"] == 8000.0


def test_extract_dollar_without_cue_when_looks_like_money() -> None:
    budget, _ = extract_expected_budget("Package is $8000 including delivery.")
    assert budget is not None
    assert budget["amount"] == 8000.0
    assert budget["currency"] == "USD"
    budget, _ = extract_expected_budget("Line total $12,500 this week.")
    assert budget is not None
    assert budget["amount"] == 12500.0


def test_no_budget_returns_null() -> None:
    budget, warnings = extract_expected_budget(
        "Indoor elevated work ~8m for scissors lift on soft clay."
    )
    assert budget is None
    assert any("not found" in w for w in warnings)


def test_bare_dollar_without_budget_cue_not_invented() -> None:
    # Ambiguous $ amount without budget language should not invent a budget.
    budget, warnings = extract_expected_budget(
        "Room size is about $10 by 20 feet near the loading bay."
    )
    assert budget is None
    assert any("not found" in w for w in warnings)


def test_words_only_and_height_not_budget() -> None:
    budget, warnings = extract_expected_budget("Tight budget and low cost site work.")
    assert budget is None
    assert any("not found" in w for w in warnings)
    budget, warnings = extract_expected_budget("Indoor elevated work ~8m for scissors lift.")
    assert budget is None
    assert any("not found" in w for w in warnings)
    budget, warnings = extract_expected_budget("Need 20 ton excavators on site.")
    assert budget is None

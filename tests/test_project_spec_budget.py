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

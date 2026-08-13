"""Multi-need split + ingest source merge (caption vs file brief)."""

from __future__ import annotations

from app.services.indexing import is_placeholder_project_text, merge_ingest_source
from app.services.need_decomposer import StubNeedDecomposer, split_needs_from_text

_POSTMAN_BRIEF = (
    "Need one forklift for loading bay and indoor elevated work about 8m "
    "for scissors lift."
)


def test_placeholder_caption_is_ignored() -> None:
    assert is_placeholder_project_text("Optional caption alongside file")
    assert is_placeholder_project_text("  optional caption alongside file  ")
    assert is_placeholder_project_text("  ")
    assert not is_placeholder_project_text("Need a forklift")


def test_merge_file_first_skips_caption() -> None:
    merged = merge_ingest_source(
        "Optional caption alongside file",
        _POSTMAN_BRIEF,
    )
    assert "forklift" in merged.lower()
    assert "scissors" in merged.lower()
    assert "optional caption" not in merged.lower()


def test_merge_keeps_real_project_text_after_file() -> None:
    merged = merge_ingest_source("Also need boom lift", "Need excavator")
    assert merged == "Need excavator\n\nAlso need boom lift"


def test_split_postman_brief_two_needs() -> None:
    needs = split_needs_from_text(_POSTMAN_BRIEF)
    assert [n.equipment_hints for n in needs] == [["forklift"], ["scissor lift"]]
    assert needs[0].need_id == "need_1"
    assert needs[1].need_id == "need_2"
    assert needs[0].quantity == 1
    assert needs[1].quantity == 1
    assert "forklift" in needs[0].description.lower()
    assert "scissor" in needs[1].description.lower()


def test_split_two_scissors_sets_quantity() -> None:
    needs = split_needs_from_text("Need two scissors lifts for indoor work")
    assert len(needs) == 1
    assert needs[0].equipment_hints == ["scissor lift"]
    assert needs[0].quantity == 2


def test_split_no_type_returns_empty() -> None:
    assert split_needs_from_text("Optional caption alongside file") == []


def test_stub_falls_back_to_single_need_when_no_type() -> None:
    needs = StubNeedDecomposer().decompose("Indoor work ~8m")
    assert len(needs) == 1
    assert needs[0].description == "Indoor work ~8m"
    assert needs[0].equipment_hints == []


def test_stub_splits_forklift_and_scissors() -> None:
    needs = StubNeedDecomposer().decompose(_POSTMAN_BRIEF)
    assert len(needs) == 2
    assert needs[0].equipment_hints == ["forklift"]
    assert needs[1].equipment_hints == ["scissor lift"]

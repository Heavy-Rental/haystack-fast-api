"""Traceable need-match score and evidence rationale."""

from __future__ import annotations

from app.pipelines.rank_rationale_generator import (
    build_evidence_rationale,
    score_need_match,
)


def test_category_hint_beats_wrong_type() -> None:
    need = {
        "description": "Need one forklift for loading bay and scissors lift ~8m",
        "equipment_hints": ["forklift"],
    }
    fork = {
        "category": "forklift",
        "equipment_type": "Fork Lift",
        "name": "Hyster",
        "availability": "available",
        "pricing": {"daily_rate": 175.0},
    }
    scissor = {
        "category": "scissor lift",
        "equipment_type": "Scissors Lift",
        "name": "Genie",
        "availability": "available",
        "platform_height": 10.0,
        "pricing": {"daily_rate": 150.0},
    }
    assert score_need_match(need, fork) > score_need_match(need, scissor)


def test_height_cue_prefers_taller_platform() -> None:
    need = {"description": "indoor elevated work ~8m", "equipment_hints": ["scissor lift"]}
    short = {
        "category": "scissor lift",
        "platform_height": 6.0,
        "availability": "available",
        "pricing": {"daily_rate": 120.0},
    }
    tall = {
        "category": "scissor lift",
        "platform_height": 10.0,
        "availability": "available",
        "pricing": {"daily_rate": 150.0},
    }
    assert score_need_match(need, tall) == 1.0
    assert score_need_match(need, short) == 0.80


def test_evidence_reason_has_no_stub_merge() -> None:
    text = build_evidence_rationale(
        {"equipment_hints": ["forklift"], "description": "loading bay"},
        {
            "name": "Hyster H4.2FT Forklift",
            "category": "forklift",
            "available": False,
            "pricing": {"daily_rate": 175.0},
            "match_score": 0.8,
        },
    )
    assert "Stub merge" not in text
    assert text.startswith("Matched forklift to Hyster H4.2FT Forklift")
    assert "available=false" in text
    assert "daily_rate=175.0" in text

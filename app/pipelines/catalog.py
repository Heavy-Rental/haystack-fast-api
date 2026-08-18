"""Approved equipment catalog and keyword → category mapping (FR-011)."""

from __future__ import annotations

# Display names used in API responses
APPROVED_EQUIPMENT_TYPES: tuple[str, ...] = (
    "Boom Lift",
    "Scissors Lift",
    "Fork Lift",
    "Excavator",
)

# ml-experiments feature_schema categories
MODEL_CATEGORIES: tuple[str, ...] = (
    "boom lift",
    "scissor lift",
    "forklift",
    "excavator",
)

DISPLAY_TO_MODEL: dict[str, str] = {
    "Boom Lift": "boom lift",
    "Scissors Lift": "scissor lift",
    "Fork Lift": "forklift",
    "Excavator": "excavator",
}

MODEL_TO_DISPLAY: dict[str, str] = {v: k for k, v in DISPLAY_TO_MODEL.items()}

# Keywords (lowercase) → model category
_KEYWORD_TO_MODEL: list[tuple[str, str]] = [
    ("boom lift", "boom lift"),
    ("boom", "boom lift"),
    ("scissors lift", "scissor lift"),
    ("scissor lift", "scissor lift"),
    ("scissors", "scissor lift"),
    ("scissor", "scissor lift"),
    ("fork lift", "forklift"),
    ("forklift", "forklift"),
    ("fork", "forklift"),
    ("excavator", "excavator"),
    ("excavate", "excavator"),
    ("trench", "excavator"),
    ("elevated", "scissor lift"),
    ("platform", "scissor lift"),
    ("aerial", "boom lift"),
    ("warehouse", "forklift"),
    ("loading", "forklift"),
]


def model_categories_in_text(text: str) -> list[str]:
    """Approved model categories, ordered by first mention in ``text``."""
    blob = str(text or "").lower()
    first_at: dict[str, int] = {}
    for keyword, category in _KEYWORD_TO_MODEL:
        idx = blob.find(keyword)
        if idx < 0:
            continue
        prev = first_at.get(category)
        if prev is None or idx < prev:
            first_at[category] = idx
    return [cat for cat, _ in sorted(first_at.items(), key=lambda kv: kv[1])]


def infer_model_categories(unit_need: dict) -> list[str]:
    """Infer ml model categories from hints + description (approved only)."""
    hints = unit_need.get("equipment_hints") or []
    description = str(unit_need.get("description") or "")
    blob = " ".join([str(h) for h in hints] + [description]).lower()

    found: list[str] = []
    for keyword, category in _KEYWORD_TO_MODEL:
        if keyword in blob and category not in found:
            found.append(category)
    return found


def is_approved_display_type(equipment_type: str) -> bool:
    return equipment_type in APPROVED_EQUIPMENT_TYPES

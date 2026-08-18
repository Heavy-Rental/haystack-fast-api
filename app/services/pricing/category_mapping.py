"""DB category name <-> feature_schema.CATEGORIES mapping (Phase 2a, 2026-08-11).

Fixes a real bug found while auditing Phase 2 prep against the live DB:
``AssetCategory.name`` (Spring-Boot canonical business names -- ``Excavator``,
``Scissors Lift``, ``Boom Lift``, ``Fork Lift``) never matched
``feature_schema.CATEGORIES`` (the ML naming convention baked into the
trained model's one-hot columns -- ``excavator``, ``scissor lift``,
``boom lift``, ``forklift``), not even case-insensitively. Confirmed live
against ``heavy_rental``: ``compute_period_utilization()``'s
``AssetCategory.name == category`` join always returned zero rows when given
a ``feature_schema``-style name, silently falling back to a static
per-category constant with no error and no degraded flag -- or raised
``ValueError`` from ``spec_band()`` when given a DB-style name instead.

Direction matters: the DB name is the source of truth (Spring-Boot-owned
business data); the ML slug is the derived form baked into already-trained
model artifacts. Fix the mapping here, never rename ``AssetCategory.name``
values to match the model.

See openspec/specs/dynamic-pricing/design.md "Category name mapping" for the
full incident writeup.
"""

from __future__ import annotations

DB_NAME_TO_FEATURE_NAME: dict[str, str] = {
    "Excavator": "excavator",
    "Scissors Lift": "scissor lift",
    "Boom Lift": "boom lift",
    "Fork Lift": "forklift",
}

FEATURE_NAME_TO_DB_NAME: dict[str, str] = {
    feature_name: db_name for db_name, feature_name in DB_NAME_TO_FEATURE_NAME.items()
}


def to_feature_name(db_category_name: str) -> str:
    """Convert a real ``AssetCategory.name`` value to feature_schema convention.

    Raises ``KeyError`` on an unrecognized DB name -- fail loud rather than
    silently mis-band or mis-predict for a category this mapping doesn't
    know about yet.
    """
    return DB_NAME_TO_FEATURE_NAME[db_category_name]


def to_db_name(feature_category_name: str) -> str:
    """Convert a feature_schema-convention category back to the real DB name.

    Used where a query must filter ``AssetCategory.name`` (DB convention)
    but the caller only has a ``feature_schema``-style category string.
    Raises ``KeyError`` on an unrecognized feature name.
    """
    return FEATURE_NAME_TO_DB_NAME[feature_category_name]

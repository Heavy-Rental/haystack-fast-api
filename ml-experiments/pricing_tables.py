"""Numeric constant tables for synthetic equipment-rental pricing data.

Every table here backs a specific pricing dynamic in ``generate_synthetic_data.py``.
See that module's module-level docstring for the full source citations
(Pollisum / Ben's Rental rate cards, NEA monsoon calendar, BCA construction-demand
data, fleet-KPI utilization benchmarks). Figures below are defensible illustrative
approximations derived from those sources, not verbatim quotes.

Units are fixed, not a per-row/per-category field, matching the real entity
(no unit column on Asset): ``capacity`` is always kg, ``platform_height`` is
always m.

``AERIAL_CATEGORIES`` and the other category-keyed tables here are code-side
groupings derived from ``category`` (which maps to the real ``AssetCategory.name``
field) -- not new schema concepts, so nothing here needs a corresponding
ERD/class-diagram change.
"""

CATEGORIES = ["forklift", "scissor lift", "boom lift", "excavator"]

AERIAL_CATEGORIES = {"scissor lift", "boom lift"}

# Load/operating capacity in kg, present for every category. For forklift and
# excavator this is the primary size dimension that drives base price. For
# scissor/boom lift it is platform load capacity -- a secondary feature;
# platform_height (below) drives their base price instead, matching how
# aerial-lift rate cards actually scale (a 43m boom lift costs far more than a
# 12m one; load capacity varies much less across a given lift's size range).
CATEGORY_CAPACITY_KG = {
    "forklift": {"min": 1000, "max": 5000, "step": 250},
    "excavator": {"min": 1000, "max": 30000, "step": 500},  # ~1-30 metric tons
    "scissor lift": {"min": 230, "max": 450, "step": 10},
    "boom lift": {"min": 200, "max": 450, "step": 10},
}

# Platform working height in m -- aerial-only. Not applicable to
# forklift/excavator (left null for those rows in the generated data).
CATEGORY_PLATFORM_HEIGHT_M = {
    "scissor lift": {"min": 6, "max": 14, "step": 1},
    "boom lift": {"min": 12, "max": 43, "step": 1},
}

# Which field is each category's primary base-rate size driver.
CATEGORY_PRICE_DRIVER = {
    "forklift": "capacity",
    "excavator": "capacity",
    "scissor lift": "platform_height",
    "boom lift": "platform_height",
}

# Illustrative SGD/day base-rate anchors at each category's price-driver
# min/max (capacity for forklift/excavator, platform_height for aerial lifts).
# Ordering (forklift cheapest -> excavator most expensive) follows Pollisum /
# Ben's Rental published rate-card ranges and general industry rate guides.
CATEGORY_BASE_RATE = {
    "forklift": {"rate_at_min": 90, "rate_at_max": 220},
    "excavator": {"rate_at_min": 180, "rate_at_max": 750},
    "scissor lift": {"rate_at_min": 140, "rate_at_max": 260},
    "boom lift": {"rate_at_min": 220, "rate_at_max": 480},
}

# Concave elasticity exponent: price scales with the price-driver dimension but
# with diminishing returns (doubling size does not double price).
CAPACITY_ELASTICITY_EXPONENT = 0.6

# Secondary effect of platform load capacity on price for aerial categories only
# (forklift/excavator have no secondary driver -- capacity is already primary).
# Centered at the category's capacity midpoint so it doesn't shift the mean rate
# already tuned via CATEGORY_BASE_RATE; deliberately small (+/-5% swing) so it
# doesn't compete with platform_height as the dominant aerial price signal.
SECONDARY_CAPACITY_SLOPE = 0.10

# Per-row guardrail jitter ranges. Wide enough that the non-linear duration
# discount (down to ~0.35x at long durations) is not clipped away for most rows.
GUARDRAIL_MIN_RATIO_RANGE = (0.28, 0.35)
GUARDRAIL_MAX_RATIO_RANGE = (1.15, 1.30)

# Non-linear duration discount: m(d) = DISCOUNT_FLOOR + (1 - DISCOUNT_FLOOR) * exp(-DISCOUNT_RATE * (d - 1))
# m(1) = 1.0 exactly; m(7) ~= 0.487 -> weekly total ~= 3.4x daily (target 3-4x);
# m(30) ~= 0.350 -> monthly total ~= 10.5x daily (target 10-12x); floors at long durations.
DISCOUNT_FLOOR = 0.35
DISCOUNT_RATE = 0.26

# Seasonality: NEA Northeast Monsoon (~Dec-Mar, wettest Dec-Jan) suppresses
# outdoor/earthmoving demand most; aerial lifts (facade/exterior work) are
# moderately sensitive; scissor lifts (mostly indoor fit-out) and forklifts
# (warehouse/logistics) are barely sensitive. BCA quarterly construction-demand
# data shows Q4 (Oct-Dec) contract-award spikes from public housing/institutional
# pipelines, lifting construction-linked categories more than forklift.
SEASONALITY = {
    "excavator": {
        1: 0.88, 2: 0.92, 3: 0.96, 4: 1.00, 5: 1.00, 6: 1.00,
        7: 1.00, 8: 1.00, 9: 1.02, 10: 1.06, 11: 1.08, 12: 0.95,
    },
    "boom lift": {
        1: 0.94, 2: 0.96, 3: 0.98, 4: 1.00, 5: 1.00, 6: 1.00,
        7: 1.00, 8: 1.00, 9: 1.01, 10: 1.04, 11: 1.05, 12: 0.98,
    },
    "scissor lift": {
        1: 0.98, 2: 0.99, 3: 1.00, 4: 1.00, 5: 1.00, 6: 1.00,
        7: 1.00, 8: 1.00, 9: 1.00, 10: 1.02, 11: 1.03, 12: 1.00,
    },
    "forklift": {
        1: 1.00, 2: 1.00, 3: 1.00, 4: 1.00, 5: 1.00, 6: 1.00,
        7: 1.00, 8: 1.00, 9: 1.00, 10: 1.01, 11: 1.02, 12: 1.01,
    },
}

# Condition is ordinal (NEEDS_REPAIR < FAIR < GOOD < EXCELLENT). Worse condition
# pulls price down; ~26% spread between the extremes keeps the signal recoverable
# by SHAP in the Phase 1b review.
CONDITIONS = ["NEEDS_REPAIR", "FAIR", "GOOD", "EXCELLENT"]
CONDITION_MULTIPLIER = {
    "NEEDS_REPAIR": 0.80,
    "FAIR": 0.90,
    "GOOD": 1.00,
    "EXCELLENT": 1.08,
}

# Fleet-KPI utilization benchmarks by category bucket. Generators (80%+ band in
# the source benchmarks) are not one of our 4 categories -- reference point only,
# not used anywhere in the generator.
CATEGORY_UTILIZATION = {
    "scissor lift": 0.76,   # aerial bucket, 72-80% band, midpoint
    "boom lift": 0.76,      # aerial bucket, 72-80% band, midpoint
    "forklift": 0.685,      # blended/general bucket, 65-72% band, midpoint
    "excavator": 0.585,     # earthmoving bucket, 55-62% band, midpoint
}

SHORT_DURATION_PREMIUM = {1: 1.15, 2: 1.10, 3: 1.05} # default 1.0 for duration_days > 3

# firmness = 1 + FIRMNESS_SLOPE * (utilization - FIRMNESS_PIVOT)
# Higher utilization -> firmer (higher) prices, modest effect (<= ~2%).
FIRMNESS_SLOPE = 0.15
FIRMNESS_PIVOT = 0.65

# noise_std_frac = NOISE_SCALE * (NOISE_PIVOT - utilization)
# Lower utilization -> more scatter (softer, more negotiable pricing).
NOISE_SCALE = 0.10
NOISE_PIVOT = 1.30

# Delivery distance (km) from the equipment yard (Tuas, postal 629462) to the
# job site. Phase 1: sampled directly from a realistic distribution, same
# approach as duration_days -- NOT computed from two coordinates or real
# postal codes. Real geocoding (OneMap or otherwise) is explicitly deferred to
# a later phase (see docs/dynamic-pricing-masterplan.md). Right-skewed:
# most jobs stay within the western half of Singapore (closer to the Tuas
# yard), with a longer tail reaching Changi/Woodlands-distance sites across
# the island. Mean ~19km, clipped to [1, 50].
DISTANCE_KM_GAMMA_SHAPE = 2.0
DISTANCE_KM_GAMMA_SCALE = 9.0
DISTANCE_KM_MIN = 1
DISTANCE_KM_MAX = 50

# distance_mult = 1 + DISTANCE_PRICE_SLOPE * (distance_km - DISTANCE_PIVOT_KM)
# Modest, monotonic delivery-distance premium -- farther jobs cost more to
# service. Deliberately small relative to duration/category/condition
# (~-4% at the near end to ~+10% at the far end of the sampled range) so it's
# a learnable secondary signal, not a dominant one.
DISTANCE_PRICE_SLOPE = 0.003
DISTANCE_PIVOT_KM = 15

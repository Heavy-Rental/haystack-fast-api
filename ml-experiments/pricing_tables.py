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
    "forklift": {"rate_at_min": 80, "rate_at_max": 220},
    "excavator": {"rate_at_min": 230, "rate_at_max": 985},
    "scissor lift": {"rate_at_min": 85, "rate_at_max": 205},
    "boom lift": {"rate_at_min": 120, "rate_at_max": 500},
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

# Phase 2d-ii: fitted to the real asset base/min/max relationship. Kept close
# enough to the duration floor that multi-day signal survives target clamping.
GUARDRAIL_MIN_RATIO_RANGE = (0.74, 0.88)
GUARDRAIL_MAX_RATIO_RANGE = (1.12, 1.33)

# Non-linear duration discount: m(d) = DISCOUNT_FLOOR + (1 - DISCOUNT_FLOOR) * exp(-DISCOUNT_RATE * (d - 1))
# Phase 2d-ii duration calibration: m(1)=1, m(7)≈0.894, m(14)≈0.855,
# m(30)≈0.841. The curve stays mostly inside duration-agnostic asset bounds.
DISCOUNT_FLOOR = 0.84
DISCOUNT_RATE = 0.18

# Seasonality: NEA Northeast Monsoon (~Dec-Mar, wettest Dec-Jan) suppresses
# outdoor/earthmoving demand most; aerial lifts (facade/exterior work) are
# moderately sensitive; scissor lifts (mostly indoor fit-out) and forklifts
# (warehouse/logistics) are barely sensitive. BCA quarterly construction-demand
# data shows Q4 (Oct-Dec) contract-award spikes from public housing/institutional
# pipelines, lifting construction-linked categories more than forklift.
SEASONALITY = {
    "excavator": {
        1: 0.88,
        2: 0.92,
        3: 0.96,
        4: 1.00,
        5: 1.00,
        6: 1.00,
        7: 1.00,
        8: 1.00,
        9: 1.02,
        10: 1.06,
        11: 1.08,
        12: 0.95,
    },
    "boom lift": {
        1: 0.94,
        2: 0.96,
        3: 0.98,
        4: 1.00,
        5: 1.00,
        6: 1.00,
        7: 1.00,
        8: 1.00,
        9: 1.01,
        10: 1.04,
        11: 1.05,
        12: 0.98,
    },
    "scissor lift": {
        1: 0.98,
        2: 0.99,
        3: 1.00,
        4: 1.00,
        5: 1.00,
        6: 1.00,
        7: 1.00,
        8: 1.00,
        9: 1.00,
        10: 1.02,
        11: 1.03,
        12: 1.00,
    },
    "forklift": {
        1: 1.00,
        2: 1.00,
        3: 1.00,
        4: 1.00,
        5: 1.00,
        6: 1.00,
        7: 1.00,
        8: 1.00,
        9: 1.00,
        10: 1.01,
        11: 1.02,
        12: 1.01,
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
#
# Used two ways: (1) as CATEGORY_UTILIZATION below, the static category-level
# baseline that noise_std_frac() and (as of Phase 1d) sample_period_utilization()
# perturb per-row -- a fleet-wide long-run average, not a live signal; (2) as the
# production fallback in predict_price.py/pricing_client.py when a live
# period_utilization value isn't available (e.g. no DB session).
CATEGORY_UTILIZATION = {
    "scissor lift": 0.76,  # aerial bucket, 72-80% band, midpoint
    "boom lift": 0.76,  # aerial bucket, 72-80% band, midpoint
    "forklift": 0.685,  # blended/general bucket, 65-72% band, midpoint
    "excavator": 0.585,  # earthmoving bucket, 55-62% band, midpoint
}

# Spec-band boundaries for period_utilization grouping (Phase 1d). Excavator/
# forklift bucket on capacity (kg, matching CATEGORY_CAPACITY_KG's units);
# scissor lift/boom lift bucket on platform_height (m, matching
# CATEGORY_PLATFORM_HEIGHT_M's units). Grouping by raw category alone would be
# misleading for period_utilization -- a fully-booked small-excavator fleet
# shouldn't make a large excavator look scarce (see
# docs/dynamic-pricing-masterplan.md). Fixed constants, not derived from the
# current fleet's distribution -- see generate_synthetic_data.py's References
# for the real-world load-class/aerial-height-tier conventions these are
# grounded in. (lo, hi) tuples, half-open (lo, hi] except the open-ended last
# bucket (lo, None) which matches anything above lo. Consumed by
# feature_schema.spec_band(), the single source of truth for both
# training-time bucketing here and the live production query (Phase 1e) --
# never a new persisted column.
CAPACITY_BINS = {
    # Mini/compact/standard/large excavator weight classes -- a standard
    # rental-industry categorization (roughly: mini <3t, compact/midi 3-7t,
    # standard 7-15t, large 15t+). Our fleet's capacity range (1-30t, see
    # CATEGORY_CAPACITY_KG) spans all four.
    "excavator": [(0, 3000), (3000, 7000), (7000, 15000), (15000, None)],
    # Counterbalance forklift capacity classes. Our fleet only spans 1-5t
    # (see CATEGORY_CAPACITY_KG), narrower than the full industry range (up
    # to 10-16t+ for heavy forklifts) -- three bands, not four, since a
    # fourth would be near-empty against this fleet's actual range.
    "forklift": [(0, 2000), (2000, 3500), (3500, None)],
}
HEIGHT_BINS = {
    # Scissor lift rental catalog tiers, commonly grouped around ~19/26/32/40ft
    # platform heights -- converted to meters (~5.8/7.9/9.8/12.2m) and rounded
    # to whole meters to match CATEGORY_PLATFORM_HEIGHT_M's 6-14m fleet range.
    "scissor lift": [(0, 8), (8, 10), (10, 12), (12, None)],
    # Boom lift rental catalog tiers, commonly grouped around ~40/60/80/100ft+
    # platform heights -- converted to meters (~12.2/18.3/24.4/30.5m) and
    # rounded to whole meters; open-ended top bucket covers this fleet's
    # largest units up to 43m (~141ft), within the range of large specialty
    # boom lifts.
    "boom lift": [(0, 18), (18, 24), (24, 31), (31, None)],
}

SHORT_DURATION_PREMIUM = {1: 1.15, 2: 1.10, 3: 1.05}  # default 1.0 for duration_days > 3

# firmness = 1 + FIRMNESS_SLOPE * (utilization - FIRMNESS_PIVOT)
# Higher utilization -> firmer (higher) prices. Bumped 1.4x (Phase 1d, from
# 0.15) after the Phase 1d SHAP review showed period_utilization/
# lead_time_days importance too low relative to duration/condition/capacity
# -- still deliberately kept well below those dominant features (a rental
# price driven more by when you book than what you're renting would be a red
# flag, not an improvement).
FIRMNESS_SLOPE = 0.21
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

# lead_time_days: days between "today" (request time) and the booking's
# startDate (Phase 1d). Right-skewed, same sampling approach as
# distance_km/duration_days -- most requests are made with fairly short
# notice, a long tail of far-ahead planning. Mean ~18 days.
LEAD_TIME_GAMMA_SHAPE = 1.8
LEAD_TIME_GAMMA_SCALE = 10.0
LEAD_TIME_MIN_DAYS = 0
LEAD_TIME_MAX_DAYS = 120

# period_utilization (Phase 1d): live per-row signal replacing the static
# CATEGORY_UTILIZATION as firmness_premium()'s input (CATEGORY_UTILIZATION
# itself is unchanged -- still used by noise_std_frac(), a separate use).
# Modeled as the category baseline adjusted by lead_time_days: a longer lead
# time means the requested window is further in the future, so fewer
# bookings have accumulated against it yet -- lower utilization. This is the
# generator-side mechanism behind "booking early into an unclaimed window
# gets a lower price" (intentional scarcity pricing, locked in
# SPEC-dynamic-pricing.md/masterplan -- not an early-bird bug), since lower
# utilization feeds a lower firmness_premium. Pivot set near the lead-time
# distribution's mean so roughly half of rows sit above/below the category
# baseline.
LEAD_TIME_UTILIZATION_SLOPE = 0.003
LEAD_TIME_UTILIZATION_PIVOT_DAYS = 18
PERIOD_UTILIZATION_NOISE_STD = 0.08

# lead_time_urgency_multiplier = 1 - LEAD_TIME_URGENCY_SLOPE * (lead_time_days - LEAD_TIME_URGENCY_PIVOT_DAYS)
# Small, independent last-minute-urgency premium on lead_time_days --
# separate from (and still smaller than) the period_utilization-mediated
# effect above, so the two correlated features (see feature_schema.py) each
# retain some standalone price signal for the Phase 1d SHAP review to
# compare, rather than lead_time_days acting purely through
# period_utilization with nothing left over once utilization is held fixed.
# Bumped 1.4x (Phase 1d, from 0.0015) alongside FIRMNESS_SLOPE, same
# reasoning -- see that constant's comment.
LEAD_TIME_URGENCY_SLOPE = 0.0021
LEAD_TIME_URGENCY_PIVOT_DAYS = 18

"""In-memory seed fleet + bookings for prototype (Day-1 subset until real SQL)."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

# Seed assets: 4 approved types, multiple units for multi-quantity demos
SEED_ASSETS: list[dict[str, Any]] = [
    {
        "asset_id": "AST-BL-001",
        "equipment_type": "Boom Lift",
        "category": "boom lift",
        "condition": "GOOD",
        "capacity": 250.0,
        "platform_height": 18.0,
        "min_daily_rate": 200.0,
        "max_daily_rate": 450.0,
    },
    {
        "asset_id": "AST-BL-002",
        "equipment_type": "Boom Lift",
        "category": "boom lift",
        "condition": "EXCELLENT",
        "capacity": 300.0,
        "platform_height": 22.0,
        "min_daily_rate": 220.0,
        "max_daily_rate": 500.0,
    },
    {
        "asset_id": "AST-SL-001",
        "equipment_type": "Scissors Lift",
        "category": "scissor lift",
        "condition": "GOOD",
        "capacity": 300.0,
        "platform_height": 10.0,
        "min_daily_rate": 120.0,
        "max_daily_rate": 280.0,
    },
    {
        "asset_id": "AST-SL-002",
        "equipment_type": "Scissors Lift",
        "category": "scissor lift",
        "condition": "EXCELLENT",
        "capacity": 350.0,
        "platform_height": 12.0,
        "min_daily_rate": 140.0,
        "max_daily_rate": 320.0,
    },
    {
        "asset_id": "AST-SL-003",
        "equipment_type": "Scissors Lift",
        "category": "scissor lift",
        "condition": "FAIR",
        "capacity": 250.0,
        "platform_height": 8.0,
        "min_daily_rate": 100.0,
        "max_daily_rate": 240.0,
    },
    {
        "asset_id": "AST-FL-001",
        "equipment_type": "Fork Lift",
        "category": "forklift",
        "condition": "GOOD",
        "capacity": 2500.0,
        "platform_height": None,
        "min_daily_rate": 80.0,
        "max_daily_rate": 200.0,
    },
    {
        "asset_id": "AST-FL-002",
        "equipment_type": "Fork Lift",
        "category": "forklift",
        "condition": "EXCELLENT",
        "capacity": 3500.0,
        "platform_height": None,
        "min_daily_rate": 100.0,
        "max_daily_rate": 240.0,
    },
    {
        "asset_id": "AST-EX-001",
        "equipment_type": "Excavator",
        "category": "excavator",
        "condition": "GOOD",
        "capacity": 5000.0,
        "platform_height": None,
        "min_daily_rate": 250.0,
        "max_daily_rate": 600.0,
    },
    {
        "asset_id": "AST-EX-002",
        "equipment_type": "Excavator",
        "category": "excavator",
        "condition": "FAIR",
        "capacity": 4000.0,
        "platform_height": None,
        "min_daily_rate": 200.0,
        "max_daily_rate": 500.0,
    },
]

# Overlapping bookings for Scenario C demos (asset fully booked in window)
SEED_BOOKINGS: list[dict[str, Any]] = [
    {
        "booking_id": "BKG-001",
        "asset_id": "AST-EX-002",
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 30),
    },
]


def get_seed_assets() -> list[dict[str, Any]]:
    return deepcopy(SEED_ASSETS)


def get_seed_bookings() -> list[dict[str, Any]]:
    return deepcopy(SEED_BOOKINGS)

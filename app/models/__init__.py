"""SQLAlchemy ORM models / domain persistence types.

Feature SDDs introduce concrete models. Import Base from app.core.db for new models.
"""

from app.core.db import Base
from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.models.return_record import ReturnRecord

__all__ = [
    "Asset",
    "AssetCategory",
    "Base",
    "Booking",
    "BookingItem",
    "ReturnRecord",
]

"""SQLAlchemy ORM models / domain persistence types.

Feature SDDs introduce concrete models. Import Base from app.core.db for new models.
"""

from app.core.db import Base

__all__ = ["Base"]

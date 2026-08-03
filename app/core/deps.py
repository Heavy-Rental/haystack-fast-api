"""Shared FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.db import get_db


def get_app_settings() -> Settings:
    """Inject application settings."""
    return get_settings()


# Re-export for convenience in routers/services
__all__ = ["get_app_settings", "get_db", "Session", "Generator"]

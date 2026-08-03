"""Health check orchestration."""

import logging

from sqlalchemy.orm import Session

from app.core.db import check_database_connection
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)


class HealthService:
    """Reports application and database readiness."""

    def check(self, db: Session) -> HealthResponse:
        try:
            check_database_connection(db)
            return HealthResponse(status="ok", database="up")
        except Exception:
            logger.exception("Database health check failed")
            return HealthResponse(status="degraded", database="down")

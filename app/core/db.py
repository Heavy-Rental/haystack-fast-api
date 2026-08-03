"""SQLAlchemy engine and session helpers for PostgreSQL."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def create_db_engine(settings: Settings | None = None):
    """Create a SQLAlchemy engine for the configured Postgres URL."""
    cfg = settings or get_settings()
    return create_engine(
        cfg.database_url,
        pool_pre_ping=True,
    )


_settings = get_settings()
engine = create_db_engine(_settings)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(session: Session | None = None) -> bool:
    """Return True if a simple SELECT 1 against Postgres succeeds."""
    if session is not None:
        session.execute(text("SELECT 1"))
        return True
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return True

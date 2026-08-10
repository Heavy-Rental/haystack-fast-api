"""Settings / configuration tests."""

from app.config import Settings


def test_default_database_url() -> None:
    settings = Settings(
        postgres_hostname="postgres-haystack",
        postgres_port=5432,
        postgres_db="heavy_rental",
        postgres_user="postgres",
        postgres_password="postgres",
        database_url_override=None,
    )
    assert (
        settings.database_url
        == "postgresql+psycopg://postgres:postgres@postgres-haystack:5432/heavy_rental"
    )


def test_database_url_override() -> None:
    settings = Settings(
        database_url_override="postgresql+psycopg://user:pass@other:5432/mydb",
    )
    assert settings.database_url == "postgresql+psycopg://user:pass@other:5432/mydb"


def test_database_url_override_normalizes_bare_postgresql_scheme() -> None:
    """Bare postgresql:// must use psycopg v3, not the psycopg2 default dialect."""
    settings = Settings(
        database_url_override="postgresql://user:pass@other:5432/mydb",
    )
    assert settings.database_url == "postgresql+psycopg://user:pass@other:5432/mydb"


def test_database_url_override_normalizes_postgres_scheme() -> None:
    settings = Settings(
        database_url_override="postgres://user:pass@other:5432/mydb",
    )
    assert settings.database_url == "postgresql+psycopg://user:pass@other:5432/mydb"


def test_database_url_override_preserves_explicit_asyncpg() -> None:
    settings = Settings(
        database_url_override="postgresql+asyncpg://user:pass@other:5432/mydb",
    )
    assert settings.database_url == "postgresql+asyncpg://user:pass@other:5432/mydb"

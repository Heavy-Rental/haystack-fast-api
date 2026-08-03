"""Settings / configuration tests."""

from app.config import Settings


def test_default_database_url() -> None:
    settings = Settings(
        postgres_hostname="db",
        postgres_port=5432,
        postgres_db="postgres",
        postgres_user="postgres",
        postgres_password="postgres",
        database_url_override=None,
    )
    assert (
        settings.database_url
        == "postgresql+psycopg://postgres:postgres@db:5432/postgres"
    )


def test_database_url_override() -> None:
    settings = Settings(
        database_url_override="postgresql+psycopg://user:pass@other:5432/mydb",
    )
    assert settings.database_url == "postgresql+psycopg://user:pass@other:5432/mydb"

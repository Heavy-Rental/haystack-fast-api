"""Settings / configuration tests."""

from app.config import Settings, is_sql_fleet_backend, normalize_fleet_backend


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


def test_indexing_document_store_defaults_to_memory() -> None:
    """Phase 5 / I0–I1: INDEXING_DOCUMENT_STORE defaults to memory (CI-safe)."""
    settings = Settings()
    assert settings.indexing_document_store == "memory"
    assert settings.indexing_chunk_ttl_seconds == 0.0


def test_recommend_fanout_cap_defaults_to_four() -> None:
    """Phase 7 / S7.3: RECOMMEND_FANOUT_CAP defaults to 4 (min 1)."""
    settings = Settings()
    assert settings.recommend_fanout_cap == 4


def test_recommend_via_agent_graph_defaults_to_false() -> None:
    """Phase 7 / S7.5: RECOMMEND_VIA_AGENT_GRAPH defaults off (MVP Call 2)."""
    settings = Settings()
    assert settings.recommend_via_agent_graph is False


def test_pricing_schema_defaults_to_primary_snapshot() -> None:
    settings = Settings()
    assert settings.pricing_schema == "primary_snapshot"


def test_pricing_schema_accepts_public() -> None:
    settings = Settings(PRICING_SCHEMA="public")
    assert settings.pricing_schema == "public"


def test_fleet_backend_defaults_to_fake() -> None:
    """Phase 4 / S4: FLEET_BACKEND defaults to fake (CI-safe seed)."""
    settings = Settings()
    assert settings.fleet_backend == "fake"


def test_fleet_backend_normalizes_dotenv_double_equals() -> None:
    """FLEET_BACKEND==sql in .env is parsed as value '=sql'; still means sql."""
    assert normalize_fleet_backend("=sql") == "sql"
    assert normalize_fleet_backend("SQL") == "sql"
    assert normalize_fleet_backend("  =SQL  ") == "sql"
    assert is_sql_fleet_backend("=sql") is True
    assert is_sql_fleet_backend("fake") is False
    settings = Settings(fleet_backend="=sql")
    assert settings.fleet_backend == "sql"


def test_neo4j_backend_defaults_to_fake() -> None:
    """Phase 8 / S8.3: NEO4J_BACKEND defaults to fake (CI-safe)."""
    settings = Settings()
    assert settings.neo4j_backend == "fake"
    assert settings.neo4j_uri == "bolt://neo4j:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_populate_url == "http://neo4j-populate:8089/v1/populate"
    assert settings.neo4j_populate_timeout_seconds == 2.0

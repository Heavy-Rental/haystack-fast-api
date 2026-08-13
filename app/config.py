"""Env-backed application settings (pydantic-settings)."""

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="haystack-fast-api", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_hostname: str = Field(default="postgres-haystack", alias="POSTGRES_HOSTNAME")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="heavy_rental", alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")

    # Optional full override; when set, wins over discrete POSTGRES_* fields.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    # Need decomposer: stub (default, CI-safe) | llm (OpenAI-compatible, e.g. DigitalOcean)
    need_decomposer: str = Field(default="stub", alias="NEED_DECOMPOSER")
    # OpenAI-compatible base URL. DigitalOcean Inference: https://inference.do-ai.run/v1
    llm_base_url: str = Field(
        default="https://inference.do-ai.run/v1",
        alias="LLM_BASE_URL",
    )
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    # Model id or Inference Router: router:<router-name>
    llm_model: str = Field(default="router:default", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")

    # Indexing pipeline: Packt Ch.4 dual-branch → embed → write
    # embedder: mock (CI-safe) | openai | sentence-transformers
    indexing_embedder: str = Field(default="mock", alias="INDEXING_EMBEDDER")
    indexing_embedding_dim: int = Field(default=384, alias="INDEXING_EMBEDDING_DIM")
    indexing_split_length: int = Field(default=200, alias="INDEXING_SPLIT_LENGTH")
    indexing_split_overlap: int = Field(default=20, alias="INDEXING_SPLIT_OVERLAP")
    indexing_openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="INDEXING_OPENAI_EMBEDDING_MODEL",
    )
    indexing_st_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="INDEXING_ST_MODEL",
    )
    # DocumentStore backend (Phase 5 / I0 factory + I1 pipeline wire):
    # memory (default, CI) | pgvector (shared table; tenant meta filters required)
    indexing_document_store: str = Field(
        default="memory",
        alias="INDEXING_DOCUMENT_STORE",
    )
    # Optional TTL for project chunks (seconds). 0 / negative = no expires_at stamp.
    # Used with purge_expired_chunks / discard helpers (Phase 5.5).
    indexing_chunk_ttl_seconds: float = Field(
        default=0.0,
        alias="INDEXING_CHUNK_TTL_SECONDS",
    )

    # Knowledge graph (HR-76): mandatory after final_doc_joiner; transforms on generator only
    kg_artifact_dir: str = Field(default="artifacts/kg", alias="KG_ARTIFACT_DIR")
    kg_apply_transforms: bool = Field(default=False, alias="KG_APPLY_TRANSFORMS")

    # Stage-1 multi-agent project-knowledge Q&A (LangGraph + Haystack tools)
    # stub = deterministic synthesis from tool hits (CI-safe); llm = OpenAI-compatible
    project_agent_mode: str = Field(default="stub", alias="PROJECT_AGENT_MODE")
    project_agent_top_k: int = Field(default=5, alias="PROJECT_AGENT_TOP_K")

    # Call 1 ingest idempotency (S2a / C1) — process-local memory store
    # TTL in seconds for cached successful lean responses (0 or negative = no expiry)
    idempotency_ttl_seconds: float = Field(
        default=86400.0,
        alias="IDEMPOTENCY_TTL_SECONDS",
    )

    # Phase 3 / S3: route Call 1 ingest through Coordinator gate [4]
    # (forced non-LLM LangGraph edge → run_indexing_from_request tool).
    # Default false keeps as-built direct IndexingIngestService path.
    indexing_via_agent_gate: bool = Field(
        default=False,
        alias="INDEXING_VIA_AGENT_GATE",
    )

    # Phase 7 / S7.3: max needs processed in one fleet (then price) batch.
    # 1 = serialize each need pipeline (fleet→price); >=2 batches fleets first.
    recommend_fanout_cap: int = Field(default=4, alias="RECOMMEND_FANOUT_CAP", ge=1)

    # Phase 7 / S7.5: Call 2 getassetrecommendations via recommend LangGraph.
    # false (default) = SessionRecommendService → RecommendationService MVP
    # true  = run_recommend_graph → same quote DTO (no invent)
    recommend_via_agent_graph: bool = Field(
        default=False,
        alias="RECOMMEND_VIA_AGENT_GRAPH",
    )

    # S4 / Phase 4: fleet tool data source for recommend catalog.
    # fake (default, CI) = seed / injected DTOs
    # sql = LiveSqlFleetBackend against Postgres-Haystack (allowlisted ORM)
    fleet_backend: str = Field(default="fake", alias="FLEET_BACKEND")

    # S8.3 / Phase 8: KG-2 Neo4j tools.
    # fake (default, CI) = FakeNeo4jBackend (empty unless injected)
    # bolt = live driver against fleet labels only (never :Document)
    neo4j_backend: str = Field(default="fake", alias="NEO4J_BACKEND")
    neo4j_uri: str = Field(default="bolt://neo4j:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="neo4j", alias="NEO4J_PASSWORD")
    neo4j_populate_url: str = Field(
        default="http://neo4j-populate:8089/v1/populate",
        alias="NEO4J_POPULATE_URL",
    )
    neo4j_populate_timeout_seconds: float = Field(
        default=2.0,
        alias="NEO4J_POPULATE_TIMEOUT_SECONDS",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self._normalize_database_url(self.database_url_override)
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_hostname}:{self.postgres_port}/{self.postgres_db}"
        )

    @staticmethod
    def _normalize_database_url(url: str) -> str:
        """Ensure bare postgresql:// URLs use the installed psycopg (v3) driver.

        SQLAlchemy maps scheme ``postgresql://`` to the legacy ``psycopg2``
        dialect. This project depends on ``psycopg`` v3, so a bare URL from
        env (common in containers) would fail at engine creation with
        ``ModuleNotFoundError: No module named 'psycopg2'``. Explicit dialects
        (``+psycopg``, ``+asyncpg``, ``+psycopg2``, …) are left unchanged.
        """
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url.removeprefix("postgresql://")
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url.removeprefix("postgres://")
        return url


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

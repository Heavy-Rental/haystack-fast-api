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

    postgres_hostname: str = Field(default="db", alias="POSTGRES_HOSTNAME")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="postgres", alias="POSTGRES_DB")
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_hostname}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

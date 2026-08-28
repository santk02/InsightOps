"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://insightops:insightops@localhost:5432/insightops"
    database_ro_url: str = "postgresql://analytics_ro:analytics_ro_pass@localhost:5432/insightops"
    database_rw_url: str = "postgresql://analytics_rw:analytics_rw_pass@localhost:5432/insightops"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    litellm_model_complex: str = "claude-sonnet-4-20250514"
    litellm_model_simple: str = "claude-3-5-haiku-20241022"
    routing_enabled: bool = True

    mem0_api_key: str = ""
    mem0_user_id: str = "default"

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    app_env: str = "development"
    charts_dir: str = "charts"
    approvals_enabled: bool = True

    max_iterations: int = 8
    max_revisions: int = 2
    critic_threshold: float = 0.7


@lru_cache
def get_settings() -> Settings:
    return Settings()

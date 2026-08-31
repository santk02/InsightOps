"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central, typed configuration loaded from environment variables / .env."""

    # Read from .env (UTF-8), silently ignore any extra/unknown keys instead of raising
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Full-privilege connection string, used only for audit logging (runs/tool_calls/dead_letters)
    database_url: str = "postgresql://insightops:insightops@localhost:5432/insightops"
    # Read-only role connection — the only credential the `read_db` tool is allowed to use
    database_ro_url: str = "postgresql://analytics_ro:analytics_ro_pass@localhost:5432/insightops"
    # Read-write role connection — used exclusively by the approval-gated `write_db` tool
    database_rw_url: str = "postgresql://analytics_rw:analytics_rw_pass@localhost:5432/insightops"
    # Redis connection for the event queue / dead-letter worker
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic credential for LiteLLM-routed model calls
    anthropic_api_key: str = ""
    # "Complex" tier model used for planning/summarizing harder steps
    litellm_model_complex: str = "claude-sonnet-4-20250514"
    # "Simple" tier model used for cheap/easy steps to cut token spend
    litellm_model_simple: str = "claude-3-5-haiku-20241022"
    # Master switch for cost-aware routing; when False everything uses the complex tier
    routing_enabled: bool = True

    # Mem0 credentials (falls back to the local file-backed MemoryStore when unset)
    mem0_api_key: str = ""
    mem0_user_id: str = "default"

    # Langfuse tracing toggle + credentials; tracing is a no-op when disabled
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # Deployment environment label, surfaced on /health
    app_env: str = "development"
    # Directory where generated chart PNGs are written
    charts_dir: str = "charts"
    # Master switch for the human-approval gate on risky tools
    approvals_enabled: bool = True

    # Hard cap on supervisor loop iterations — the runaway-agent guard
    max_iterations: int = 8
    # Hard cap on critic-triggered revision passes
    max_revisions: int = 2
    # Minimum critic score required to ship a draft without another revision
    critic_threshold: float = 0.7


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance (env is read once)."""
    return Settings()

"""Configuration management using pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SECONDBRAIN_",
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # Vault settings
    vault_path: Path | None = None

    # Data storage
    data_path: Path = _PROJECT_ROOT / "data"

    # Embedding settings
    embedding_provider: str = "local"  # "local" or "openai"
    embedding_model: str = "BAAI/bge-base-en-v1.5"  # local sentence-transformers model
    openai_embedding_model: str = "text-embedding-3-small"  # OpenAI embedding model
    openai_embedding_dimensions: int | None = None  # None = use model default

    # LLM settings
    rerank_model: str = "claude-haiku-4-5"
    answer_model: str = "claude-haiku-4-5"
    inbox_model: str = "claude-sonnet-4-5"
    inbox_provider: str = "anthropic"

    # Ollama settings (local LLM)
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = "gemma4"

    # API keys (loaded from env or .env file)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Gradio UI settings
    gradio_port: int = 7860

    # Metadata extraction settings
    metadata_db_name: str = "metadata.db"

    # Cost alerting
    cost_alert_threshold: float = 1.00

    # Tracing
    tracing_enabled: bool = False

    # Langfuse (trace viewer UI) — self-hosted at localhost:3000
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # Data retention
    usage_retention_days: int = 90

    # Contextual retrieval
    context_generation_enabled: bool = True

    # Feed (FEED-1 attention router) — off by default so repo cloners aren't affected
    feed_enabled: bool = False
    feed_config_path: str = "_config/feed.md"  # vault-relative sources/interests note
    feed_db_name: str = "feed.db"
    feed_retention_days: int = 30
    feed_summary_model: str = "claude-haiku-4-5"
    feed_top_n: int = 10  # items sent to the one summary call
    feed_min_per_type: int = 3  # guaranteed slots per type so one domain can't crowd out the other
    feed_page_limit: int = 50  # rows returned by GET /feed
    feed_digest_window_hours: int = 20  # digest counts only refreshes this recent
    feed_min_interval_hours: int = 20  # skip a refresh this soon after the last one


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()

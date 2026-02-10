"""Configuration management using pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SECONDBRAIN_",
        env_file=".env",
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
    data_path: Path = Path("data")

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
    ollama_model: str = "gpt-oss:20b"

    # API keys (loaded from env or .env file)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Gradio UI settings
    gradio_port: int = 7860

    # Metadata extraction settings
    metadata_db_name: str = "metadata.db"


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()

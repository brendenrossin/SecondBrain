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

    # Model settings
    embedding_model: str = "all-MiniLM-L6-v2"
    rerank_model: str = "gpt-4o-mini"
    answer_model: str = "gpt-4o-mini"

    # API keys (loaded from env or .env file)
    openai_api_key: str | None = None

    # Gradio UI settings
    gradio_port: int = 7860


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()

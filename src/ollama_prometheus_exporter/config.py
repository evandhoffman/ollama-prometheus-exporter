"""Configuration for the exporter."""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ollama_base_url: AnyHttpUrl = Field(default="http://localhost:11434")
    exporter_host: str = Field(default="0.0.0.0")
    exporter_port: int = Field(default=9497)
    ollama_timeout_seconds: float = Field(default=5.0, gt=0)
    ollama_verify_tls: bool = Field(default=True)
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""

    return Settings()

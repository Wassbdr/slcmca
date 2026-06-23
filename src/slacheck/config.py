"""Settings loaded from environment / .env (pydantic-settings). Secrets never hardcoded."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Datadog credentials + defaults. Copy .env.example -> .env (gitignored)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DD_", extra="ignore")

    api_key: str | None = None
    app_key: str | None = None
    site: str = "datadoghq.eu"
    env: str = "prod"

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.app_key)

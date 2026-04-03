from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    direct_url: str | None = None          # Supabase direct (non-pooled) URL for migrations
    redis_url: str
    redis_token: str
    secret_key: str                    # for itsdangerous cookie signing
    encryption_key: str                # Fernet key
    hmac_secret: str                   # for token HMAC
    supabase_url: str                  # e.g. https://xxx.supabase.co
    supabase_service_key: str          # service_role key
    sentry_dsn: str = ""               # optional in dev
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

settings = Settings()

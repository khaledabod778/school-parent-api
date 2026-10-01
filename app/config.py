from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 30

    # CORS
    cors_origins: str = "*"

    # FCM
    fcm_enabled: bool = False
    fcm_credentials_path: str | None = None

    # App
    app_name: str = "School Parent API"
    app_version: str = "1.0.0"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings shared by the API and future worker."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SUPPORTPILOT_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = (
        "postgresql+asyncpg://supportpilot_app:local_app_password@localhost:5432/supportpilot"
    )
    migration_database_url: str = (
        "postgresql+psycopg://supportpilot_migrator:local_migrator_password"
        "@localhost:5432/supportpilot"
    )
    jwt_secret: str = Field(
        default="local-development-secret-change-before-deployment",
        repr=False,
    )
    jwt_issuer: str = "supportpilot"
    jwt_audience: str = "supportpilot-api"
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    allowed_origins: list[str] = ["http://localhost:5173"]
    secure_cookies: bool = False
    refresh_cookie_name: str = "supportpilot_refresh"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret.startswith("local-") or len(self.jwt_secret) < 32:
                raise ValueError("production requires a strong SUPPORTPILOT_JWT_SECRET")
            if not self.secure_cookies:
                raise ValueError("production requires secure cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

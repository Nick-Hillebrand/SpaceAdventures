from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    database_url_sync: str = "sqlite:///./data/app.db"

    # NASA
    nasa_api_key: str = "DEMO_KEY"
    nasa_base_url: str = "https://api.nasa.gov"

    # N2YO
    n2yo_api_key: str = ""
    n2yo_base_url: str = "https://api.n2yo.com/rest/v1/satellite"
    n2yo_hourly_cap: int = 900

    # Launch Library 2
    ll2_base_url: str = "https://ll.thespacedevs.com/2.3.0"
    ll2_api_key: str = ""
    ll2_sync_interval_minutes: int = 30

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1_209_600

    # Unsubscribe & admin
    unsubscribe_secret_key: str = ""
    admin_api_key: str = ""

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # CORS
    frontend_origin: str = "http://localhost:5173"

    # HTTP client
    http_timeout_seconds: float = 10.0

    # Feature flags for tests (allow bypass of secret requirements in dev/test)
    require_secrets: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        if not self.require_secrets:
            return self
        missing = [
            name
            for name, value in (
                ("JWT_SECRET_KEY", self.jwt_secret_key),
                ("UNSUBSCRIBE_SECRET_KEY", self.unsubscribe_secret_key),
                ("ADMIN_API_KEY", self.admin_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        return self


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

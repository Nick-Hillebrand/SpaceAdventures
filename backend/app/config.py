from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    database_url_sync: str = "sqlite:///./data/app.db"
    # Pool settings only apply when database_url is postgresql+asyncpg://… (P2.1).
    db_pool_size: int = 10
    db_max_overflow: int = 20

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

    # JPL Horizons (22-ephemeris-and-mission-replay.md — Foundation). Free,
    # no key. Courtesy rules are hard requirements: batch queries, cache for
    # days, never proxy a user request to JPL — all traffic originates from
    # the ephemeris_sync worker job.
    horizons_base_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"

    # Open-Meteo Geocoding (20-location-and-sky-alerts.md — Foundation).
    # Free, no key. The frontend never calls this directly — every request
    # goes through GET /api/v1/location/search so the response is
    # size-capped/schema-validated server-side first (25-security-testing.md §2.5).
    geocode_base_url: str = "https://geocoding-api.open-meteo.com"

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

    # Web Push / VAPID (19-notification-channels-v2.md B1.2)
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = ""

    # Outbox hardening (19-…md B1.1) — per-user monthly SMS cap; over cap
    # converts that notification to email instead (financial self-protection).
    sms_monthly_cap: int = 30

    # CORS
    frontend_origin: str = "http://localhost:5173"

    # SEO launch pages + sitemap (23-seo-widgets-and-growth.md B2) — directory
    # containing the built frontend (`npm run build` output, index.html +
    # static assets incl. public/missions/*.json). Default is relative to a
    # bare `uvicorn` invocation from `backend/`; prod compose overrides this
    # to the shared read-only bind mount (`/srv/dist`).
    frontend_dist_path: str = "../frontend/dist"

    # HTTP client
    http_timeout_seconds: float = 10.0

    # Cookies (P1.4) — Secure attribute on the refresh-token cookie; True in
    # prod, disabled only for plain-HTTP local dev.
    cookie_secure: bool = Field(default=True)

    # Rate limiting (P1.6) — only trust X-Forwarded-For when behind a proxy
    # we control (Caddy in prod); never in dev, to prevent IP spoofing.
    trust_proxy_headers: bool = Field(default=False)

    # DeepL (P1.7)
    deepl_api_key: str = ""
    deepl_base_url: str = "https://api-free.deepl.com"

    # API docs (25-security-testing.md §5) — disabled by default, only
    # enabled explicitly in non-prod deploys.
    expose_docs: bool = Field(default=False)

    # Worker & scheduling (17-worker-and-scheduling.md P3)
    # Dev-only convenience: run the scheduler inside the web process instead
    # of the dedicated worker container (single-container SQLite dev compose).
    # Prod compose never sets this.
    scheduler_in_app: bool = Field(default=False)

    # Observability (P3.6) — empty DSN disables Sentry entirely.
    sentry_dsn: str = ""

    # Feature flags for tests (allow bypass of secret requirements in dev/test)
    require_secrets: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        if not self.require_secrets:
            return self
        secret_fields = (
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("UNSUBSCRIBE_SECRET_KEY", self.unsubscribe_secret_key),
            ("ADMIN_API_KEY", self.admin_api_key),
        )
        missing = [name for name, value in secret_fields if not value]
        if missing:
            raise ValueError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        too_short = [
            name for name, value in secret_fields if len(value) < _MIN_SECRET_LENGTH
        ]
        if too_short:
            raise ValueError(
                f"Environment variables must be at least {_MIN_SECRET_LENGTH} "
                "characters long: " + ", ".join(too_short)
            )
        return self


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

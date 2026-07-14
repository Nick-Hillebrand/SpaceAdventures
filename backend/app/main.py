import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability
from app.config import Settings
from app.database import dispose_engine, get_db, init_engine
from app.jobs import JOB_STALENESS_SECONDS, register_jobs
from app.models.job_status import JobStatus
from app.models.n2yo_quota import N2yoQuota
from app.models.notification_log import PendingNotification
from app.routers import apod as apod_router
from app.routers import iss as iss_router
from app.routers import mars as mars_router
from app.routers import neo as neo_router
from app.routers import space_weather as space_weather_router
from app.routers import auth as auth_router
from app.routers import launches as launches_router
from app.routers import push as push_router
from app.routers import subscriptions as subscriptions_router
from app.routers import settings as settings_router
from app.services import translation_service
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient, NasaClientError

_health_bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    init_engine(settings)
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.state.translator = translation_service.translate_fields

    # The web tier never schedules background work (CLAUDE.md rule 7) — ALL
    # recurring jobs run in the dedicated `app/worker.py` process. The one
    # exception is dev convenience: SCHEDULER_IN_APP=1 lets a single-container
    # SQLite dev compose run the same job registry in-process. Prod compose
    # never sets this (17-worker-and-scheduling.md P3.1).
    scheduler: AsyncIOScheduler | None = None
    if settings.scheduler_in_app:
        clients = SimpleNamespace(
            ll2_client=app.state.ll2_client,
            translator=app.state.translator,
        )
        scheduler = AsyncIOScheduler()
        register_jobs(scheduler, settings, clients)
        scheduler.start()

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()
        await app.state.ll2_client.close()
        await app.state.mars_raw_images_client.close()
        await dispose_engine()


def _default_settings() -> Settings:
    # Tests and local runs without a .env should not blow up on missing secrets.
    require_secrets = os.getenv("APP_REQUIRE_SECRETS", "0") == "1"
    return Settings(require_secrets=require_secrets)  # type: ignore[call-arg]


def _is_admin_health_request(
    settings: Settings, credentials: HTTPAuthorizationCredentials | None
) -> bool:
    if not settings.admin_api_key or credentials is None:
        return False
    # Constant-time comparison — a plain != leaks key prefixes via timing.
    return secrets.compare_digest(credentials.credentials.encode(), settings.admin_api_key.encode())


def _smtp_status(settings: Settings) -> str:
    return "ok" if settings.smtp_host else "unconfigured"


def _quota_status(settings: Settings, quota_row: N2yoQuota | None) -> str:
    if not settings.n2yo_api_key:
        return "unconfigured"
    if quota_row is None:
        return "ok"
    if quota_row.used >= settings.n2yo_hourly_cap:
        return "exhausted"
    if quota_row.used >= settings.n2yo_hourly_cap * 0.9:
        return "warning"
    return "ok"


async def _health_snapshot(
    session: AsyncSession,
) -> tuple[str, list[JobStatus], N2yoQuota | None, int]:
    """Read of everything the health endpoint needs, on the request's own
    session (so tests exercising `get_db` overrides see real data).

    Never raises — a DB outage must degrade the health check, not crash it.
    """
    try:
        await session.execute(text("SELECT 1"))
        job_rows = list((await session.execute(select(JobStatus))).scalars().all())
        quota_row = await session.get(N2yoQuota, 1)
        dead_letter_count = await session.scalar(
            select(func.count()).select_from(PendingNotification).where(
                PendingNotification.dead.is_(True)
            )
        )
        return "ok", job_rows, quota_row, dead_letter_count or 0
    except Exception:  # noqa: BLE001 — health check must never propagate a raw DB error
        return "error", [], None, 0


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or _default_settings()

    observability.configure_logging()
    observability.init_sentry(settings, component="web")

    app = FastAPI(title="Space Adventures API", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(NasaClientError)
    async def _nasa_error_handler(request: Request, exc: NasaClientError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/api/v1/health")
    async def health(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(_health_bearer),
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        db_status, job_rows, quota_row, dead_letter_count = await _health_snapshot(session)
        now = datetime.now(timezone.utc)

        job_staleness: dict[str, str] = {}
        for name, budget_seconds in JOB_STALENESS_SECONDS.items():
            row = next((r for r in job_rows if r.job_name == name), None)
            if row is None or row.last_success_at is None:
                job_staleness[name] = "stale"
            else:
                age = (now - row.last_success_at).total_seconds()
                job_staleness[name] = "ok" if age <= budget_seconds else "stale"

        heartbeat_fresh = job_staleness.get("worker_heartbeat") == "ok"
        public_status = "ok" if db_status == "ok" and heartbeat_fresh else "degraded"

        if not _is_admin_health_request(request.app.state.settings, credentials):
            return {"status": public_status}

        return {
            "status": public_status,
            "db": db_status,
            "smtp": _smtp_status(request.app.state.settings),
            "n2yo_quota": {"status": _quota_status(request.app.state.settings, quota_row)},
            "jobs": job_staleness,
            "notifications": {"dead_letter_count": dead_letter_count},
        }

    app.include_router(apod_router.router)
    app.include_router(neo_router.router)
    app.include_router(space_weather_router.router)
    app.include_router(mars_router.router)
    app.include_router(iss_router.router)
    app.include_router(launches_router.router)
    app.include_router(auth_router.router)
    app.include_router(subscriptions_router.router)
    app.include_router(push_router.router)
    app.include_router(settings_router.router)

    return app


app = create_app()

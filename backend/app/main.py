import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.database import AsyncSessionLocal
from app.routers import apod as apod_router
from app.routers import iss as iss_router
from app.routers import mars as mars_router
from app.routers import neo as neo_router
from app.routers import space_weather as space_weather_router
from app.routers import auth as auth_router
from app.routers import launches as launches_router
from app.routers import subscriptions as subscriptions_router
from app.routers import settings as settings_router
from app.services import launches_service
from app.services import translation_service
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient, NasaClientError


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.state.translator = translation_service.translate_fields

    scheduler = AsyncIOScheduler()

    async def _sync_job() -> None:
        async with AsyncSessionLocal() as session:
            await launches_service.sync_launches(
                session, app.state.ll2_client, settings,
                translator=app.state.translator,
            )

    scheduler.add_job(
        _sync_job,
        trigger="interval",
        minutes=settings.ll2_sync_interval_minutes,
    )
    scheduler.start()

    # Startup: immediate sync if table is empty
    async with AsyncSessionLocal() as session:
        if await launches_service.is_launches_table_empty(session):
            await launches_service.sync_launches(
                session, app.state.ll2_client, settings,
                translator=app.state.translator,
            )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()
        await app.state.ll2_client.close()
        await app.state.mars_raw_images_client.close()


def _default_settings() -> Settings:
    # Tests and local runs without a .env should not blow up on missing secrets.
    require_secrets = os.getenv("APP_REQUIRE_SECRETS", "0") == "1"
    return Settings(require_secrets=require_secrets)  # type: ignore[call-arg]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or _default_settings()

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
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(apod_router.router)
    app.include_router(neo_router.router)
    app.include_router(space_weather_router.router)
    app.include_router(mars_router.router)
    app.include_router(iss_router.router)
    app.include_router(launches_router.router)
    app.include_router(auth_router.router)
    app.include_router(subscriptions_router.router)
    app.include_router(settings_router.router)

    return app


app = create_app()

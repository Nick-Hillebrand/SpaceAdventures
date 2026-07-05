import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.routers import apod as apod_router
from app.routers import iss as iss_router
from app.routers import mars as mars_router
from app.routers import neo as neo_router
from app.routers import space_weather as space_weather_router
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient, NasaClientError


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    try:
        yield
    finally:
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()


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
        allow_methods=["*"],
        allow_headers=["*"],
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

    return app


app = create_app()

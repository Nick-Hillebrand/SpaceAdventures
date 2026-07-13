"""Dedicated background-job process (17-worker-and-scheduling.md P3.1).

Run as `python -m app.worker` in its own container (same image as the web
backend). All recurring jobs live here — the web tier never schedules
anything (dev exception: `SCHEDULER_IN_APP=1`, see `main.py`).
"""
from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import observability
from app.config import Settings
from app.database import dispose_engine, init_engine
from app.jobs import register_jobs
from app.services import translation_service
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient

logger = logging.getLogger(__name__)


@dataclass
class Clients:
    nasa_client: NasaClient
    n2yo_client: N2YOClient
    ll2_client: LL2Client
    mars_raw_images_client: MarsRawImagesClient
    translator: Any


def build_clients(settings: Settings) -> Clients:
    return Clients(
        nasa_client=NasaClient(settings),
        n2yo_client=N2YOClient(settings),
        ll2_client=LL2Client(settings),
        mars_raw_images_client=MarsRawImagesClient(settings),
        translator=translation_service.translate_fields,
    )


async def close_clients(clients: Clients) -> None:
    await clients.nasa_client.close()
    await clients.n2yo_client.close()
    await clients.ll2_client.close()
    await clients.mars_raw_images_client.close()


async def main() -> None:
    observability.configure_logging()
    settings = Settings()  # type: ignore[call-arg] — APP_REQUIRE_SECRETS honored via env
    observability.init_sentry(settings, component="worker")

    init_engine(settings)
    clients = build_clients(settings)

    scheduler = AsyncIOScheduler()
    register_jobs(scheduler, settings, clients)
    scheduler.start()
    logger.info("worker started")

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        await shutdown_event.wait()
    finally:
        logger.info("worker shutting down")
        scheduler.shutdown(wait=True)
        await close_clients(clients)
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())

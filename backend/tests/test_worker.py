"""Tests for the dedicated worker entrypoint (17-worker-and-scheduling.md P3.1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app import worker
from app.config import Settings


def test_build_clients_populates_all_fields():
    settings = Settings(require_secrets=False)  # type: ignore[call-arg]
    clients = worker.build_clients(settings)

    assert clients.nasa_client is not None
    assert clients.n2yo_client is not None
    assert clients.ll2_client is not None
    assert clients.mars_raw_images_client is not None
    assert clients.horizons_client is not None
    assert clients.translator is not None


async def test_close_clients_closes_every_client():
    clients = worker.Clients(
        nasa_client=AsyncMock(),
        n2yo_client=AsyncMock(),
        ll2_client=AsyncMock(),
        mars_raw_images_client=AsyncMock(),
        horizons_client=AsyncMock(),
        translator=MagicMock(),
    )

    await worker.close_clients(clients)

    clients.nasa_client.close.assert_awaited_once()
    clients.n2yo_client.close.assert_awaited_once()
    clients.ll2_client.close.assert_awaited_once()
    clients.mars_raw_images_client.close.assert_awaited_once()
    clients.horizons_client.close.assert_awaited_once()


async def test_main_starts_scheduler_registers_jobs_and_shuts_down_cleanly():
    fake_event = MagicMock()
    fake_event.wait = AsyncMock(return_value=None)

    fake_loop = MagicMock()
    fake_scheduler = MagicMock()

    settings = Settings(require_secrets=False)  # type: ignore[call-arg]

    with patch("app.worker.Settings", return_value=settings), \
         patch("app.worker.observability.configure_logging"), \
         patch("app.worker.observability.init_sentry"), \
         patch("app.worker.init_engine") as mock_init_engine, \
         patch("app.worker.dispose_engine", new=AsyncMock()) as mock_dispose, \
         patch("app.worker.build_clients", return_value=worker.Clients(
             nasa_client=AsyncMock(), n2yo_client=AsyncMock(),
             ll2_client=AsyncMock(), mars_raw_images_client=AsyncMock(),
             horizons_client=AsyncMock(),
             translator=MagicMock(),
         )), \
         patch("app.worker.AsyncIOScheduler", return_value=fake_scheduler), \
         patch("app.worker.register_jobs") as mock_register, \
         patch("app.worker.asyncio.Event", return_value=fake_event), \
         patch("app.worker.asyncio.get_running_loop", return_value=fake_loop):
        await worker.main()

    mock_init_engine.assert_called_once_with(settings)
    mock_register.assert_called_once()
    fake_scheduler.start.assert_called_once()
    fake_event.wait.assert_awaited_once()
    fake_scheduler.shutdown.assert_called_once_with(wait=True)
    mock_dispose.assert_awaited_once()
    assert fake_loop.add_signal_handler.call_count == 2

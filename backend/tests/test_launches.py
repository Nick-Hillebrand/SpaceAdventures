"""Tests for the Launches feature (Step 9)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import respx
from httpx import Response
from sqlalchemy import select

from app.config import Settings
from app.models.launches import Launch
from app.models.notification_log import PendingNotification
from app.models.subscription import Subscription
from app.models.user import User
from app.services import launches_service
from app.services.ll2_client import LL2Client, LL2ClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LL2_BASE = "https://ll.thespacedevs.example"


def _make_raw_launch(
    ll2_id: str = "launch-001",
    name: str = "Falcon 9 Block 5 | Starlink",
    net: str = "2025-07-10T12:00:00Z",
    status_abbrev: str = "Go",
    status_name: str = "Go for Launch",
    agency_name: str = "SpaceX",
    agency_type: str | None = "Commercial",
    rocket_name: str = "Falcon 9 Block 5",
    rocket_family: str | None = "Falcon",
    mission_name: str | None = "Starlink Mission",
    mission_description: str | None = "A batch of Starlink satellites.",
    mission_type: str | None = "Communications",
    pad_name: str = "SLC-40",
    pad_location: str = "Cape Canaveral, FL, USA",
    image_url: str | None = "https://example.com/img.jpg",
    vidURLs: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "id": ll2_id,
        "name": name,
        "net": net,
        "status": {"abbrev": status_abbrev, "name": status_name},
        "launch_service_provider": {"name": agency_name, "type": agency_type},
        "rocket": {
            "configuration": {"name": rocket_name, "family": rocket_family}
        },
        "mission": {
            "name": mission_name,
            "description": mission_description,
            "type": mission_type,
        },
        "pad": {
            "name": pad_name,
            "location": {"name": pad_location},
        },
        "image": image_url,
        "vidURLs": vidURLs or [],
    }


def _ll2_page(launches: list[dict], next_url: str | None = None) -> dict:
    return {"count": len(launches), "next": next_url, "previous": None, "results": launches}


@pytest_asyncio.fixture
async def user(db_session):
    u = User(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password_hash="x",
    )
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def launch_subscription(db_session, user):
    sub = Subscription(
        user_id=user.id,
        type="launch",
        ll2_id="launch-001",
        notify_email=True,
    )
    db_session.add(sub)
    await db_session.flush()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def agency_subscription(db_session, user):
    sub = Subscription(
        user_id=user.id,
        type="agency",
        agency_name="SpaceX",
        notify_email=True,
    )
    db_session.add(sub)
    await db_session.flush()
    await db_session.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


class TestUpsertNewLaunch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_upsert_new_launch(self, db_session, settings):
        """Syncing with a new launch stores it with correct fields."""
        raw = _make_raw_launch()
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        result = await db_session.get(Launch, "launch-001")
        assert result is not None
        assert result.name == "Falcon 9 Block 5 | Starlink"
        assert result.status_abbrev == "Go"
        assert result.agency_name == "SpaceX"
        assert result.rocket_name == "Falcon 9 Block 5"
        assert result.pad_name == "SLC-40"
        assert result.pad_location == "Cape Canaveral, FL, USA"
        assert result.mission_description == "A batch of Starlink satellites."
        assert result.image_url == "https://example.com/img.jpg"
        assert result.fetched_at is not None
        await client.close()


class TestUpsertExistingLaunch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_upsert_existing_launch(self, db_session, settings):
        """Syncing same launch twice updates fetched_at without creating duplicate."""
        raw = _make_raw_launch()
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)
        first_fetched_at = (await db_session.get(Launch, "launch-001")).fetched_at

        # Second sync — same data
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )
        await launches_service.sync_launches(db_session, client)

        result = await db_session.execute(
            select(Launch).where(Launch.ll2_id == "launch-001")
        )
        launches = result.scalars().all()
        assert len(launches) == 1
        # fetched_at should be updated (or at least not older)
        assert launches[0].fetched_at >= first_fetched_at
        await client.close()


class TestNetSlipDetection:
    @respx.mock
    @pytest.mark.asyncio
    async def test_net_slip_detection(self, db_session, settings, launch_subscription):
        """NET change > 5 min creates NET_SLIP pending notification."""
        raw = _make_raw_launch(net="2025-07-10T12:00:00Z")
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        # Now sync with net shifted by > 5 minutes
        raw2 = _make_raw_launch(net="2025-07-10T12:10:00Z")  # +10 minutes
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw2]))
        )
        await launches_service.sync_launches(db_session, client)

        result = await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.ll2_id == "launch-001",
                PendingNotification.change_type == "NET_SLIP",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) >= 1
        assert notifications[0].subscription_id == launch_subscription.id
        await client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_net_slip_below_threshold(self, db_session, settings, launch_subscription):
        """NET change < 5 min does NOT create pending notification."""
        raw = _make_raw_launch(net="2025-07-10T12:00:00Z")
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        # Shift by < 5 minutes
        raw2 = _make_raw_launch(net="2025-07-10T12:04:00Z")  # +4 minutes
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw2]))
        )
        await launches_service.sync_launches(db_session, client)

        result = await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.ll2_id == "launch-001",
                PendingNotification.change_type == "NET_SLIP",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) == 0
        await client.close()


class TestStatusChangeDetection:
    @respx.mock
    @pytest.mark.asyncio
    async def test_status_change_detection(self, db_session, settings, launch_subscription):
        """Status change creates STATUS_CHANGE pending notification."""
        raw = _make_raw_launch(status_abbrev="Go", status_name="Go for Launch")
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        # Status changes to TBD
        raw2 = _make_raw_launch(status_abbrev="TBD", status_name="To Be Determined")
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw2]))
        )
        await launches_service.sync_launches(db_session, client)

        result = await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.ll2_id == "launch-001",
                PendingNotification.change_type == "STATUS_CHANGE",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) >= 1
        assert notifications[0].old_value == "Go"
        assert notifications[0].new_value == "TBD"
        await client.close()


class TestGoneMarking:
    @respx.mock
    @pytest.mark.asyncio
    async def test_gone_marking(self, db_session, settings):
        """Launch in DB but not returned in next sync is marked Gone."""
        raw = _make_raw_launch()
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        # Second sync returns empty list
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([]))
        )
        await launches_service.sync_launches(db_session, client)

        result = await db_session.get(Launch, "launch-001")
        assert result is not None
        assert result.status_abbrev == "Gone"
        await client.close()


class TestGetUpcomingLaunches:
    @pytest.mark.asyncio
    async def test_get_upcoming_launches_empty(self, db_session):
        """Empty DB returns ([], None)."""
        launches, last_synced_at = await launches_service.get_upcoming_launches(db_session)
        assert launches == []
        assert last_synced_at is None

    @pytest.mark.asyncio
    async def test_get_upcoming_launches_filters_past(self, db_session):
        """Launches with net < now-24h are excluded."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old_launch = Launch(
            ll2_id="old-001",
            name="Old Launch",
            net=now - timedelta(hours=25),
            status_abbrev="Success",
            status_name="Launch Successful",
            agency_name="SpaceX",
            rocket_name="Falcon 9",
            pad_name="SLC-40",
            pad_location="Cape Canaveral",
            livestream_urls=[],
            fetched_at=now,
        )
        future_launch = Launch(
            ll2_id="future-001",
            name="Future Launch",
            net=now + timedelta(hours=5),
            status_abbrev="Go",
            status_name="Go for Launch",
            agency_name="SpaceX",
            rocket_name="Falcon 9",
            pad_name="SLC-40",
            pad_location="Cape Canaveral",
            livestream_urls=[],
            fetched_at=now,
        )
        db_session.add(old_launch)
        db_session.add(future_launch)
        await db_session.commit()

        launches, _ = await launches_service.get_upcoming_launches(db_session)
        assert len(launches) == 1
        assert launches[0].ll2_id == "future-001"


class TestSyncHandlesLL2Error:
    @pytest.mark.asyncio
    async def test_sync_handles_ll2_error(self, db_session, settings):
        """When fetch_upcoming raises LL2ClientError, service logs and returns."""
        mock_client = AsyncMock(spec=LL2Client)
        mock_client.fetch_upcoming.side_effect = LL2ClientError(
            "LL2_UNAVAILABLE", "Connection refused"
        )

        # Should not raise
        await launches_service.sync_launches(db_session, mock_client)

        # DB still empty
        launches, _ = await launches_service.get_upcoming_launches(db_session)
        assert launches == []


class TestFieldTruncation:
    @respx.mock
    @pytest.mark.asyncio
    async def test_field_truncation(self, db_session, settings):
        """Overly long fields are truncated to spec limits."""
        long_name = "X" * 300
        long_desc = "Y" * 2500
        long_pad = "Z" * 600

        raw = _make_raw_launch(
            name=long_name,
            mission_description=long_desc,
            pad_name=long_pad,
        )
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        result = await db_session.get(Launch, "launch-001")
        assert result is not None
        assert len(result.name) == 200
        assert len(result.mission_description) == 2000
        assert len(result.pad_name) == 500
        await client.close()


class TestDefensiveFieldAccess:
    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_vid_urls(self, db_session, settings):
        """Launch with missing vidURLs field doesn't crash."""
        raw = _make_raw_launch()
        del raw["vidURLs"]
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        result = await db_session.get(Launch, "launch-001")
        assert result is not None
        assert result.livestream_urls == []
        await client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_null_mission(self, db_session, settings):
        """Launch with null mission doesn't crash."""
        raw = _make_raw_launch()
        raw["mission"] = None
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        result = await db_session.get(Launch, "launch-001")
        assert result is not None
        assert result.mission_name is None
        assert result.mission_description is None
        await client.close()


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------


class TestUpcomingRoute:
    @pytest.mark.asyncio
    async def test_upcoming_route(self, client, db_session):
        """GET /api/v1/launches/upcoming returns 200 with correct envelope."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        launch = Launch(
            ll2_id="route-001",
            name="Test Launch",
            net=now + timedelta(hours=2),
            status_abbrev="Go",
            status_name="Go for Launch",
            agency_name="SpaceX",
            rocket_name="Falcon 9",
            pad_name="SLC-40",
            pad_location="Cape Canaveral",
            image_url=None,
            livestream_urls=[],
            fetched_at=now,
        )
        db_session.add(launch)
        await db_session.commit()

        response = await client.get("/api/v1/launches/upcoming")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "last_synced_at" in body
        assert "cached" in body
        assert len(body["data"]) == 1
        assert body["data"][0]["ll2_id"] == "route-001"
        assert body["data"][0]["name"] == "Test Launch"

    @pytest.mark.asyncio
    async def test_upcoming_route_empty(self, client):
        """GET /api/v1/launches/upcoming returns empty list when no launches."""
        response = await client.get("/api/v1/launches/upcoming")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["last_synced_at"] is None


@pytest_asyncio.fixture
async def admin_client(db_engine):
    """HTTP client with admin_api_key configured."""
    from httpx import ASGITransport, AsyncClient as httpxAsyncClient
    from app.main import create_app
    from app.services.nasa_client import NasaClient
    from app.services.n2yo_client import N2YOClient
    from app.services.ll2_client import LL2Client
    from app.database import get_db
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    admin_settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key="test-admin-secret",
        ll2_base_url="https://ll.thespacedevs.example",
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with factory() as session:
            yield session

    admin_app = create_app(settings=admin_settings)
    admin_app.state.nasa_client = NasaClient(admin_settings)
    admin_app.state.n2yo_client = N2YOClient(admin_settings)
    admin_app.state.ll2_client = LL2Client(admin_settings)
    admin_app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=admin_app)
    try:
        async with httpxAsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await admin_app.state.nasa_client.close()
        await admin_app.state.n2yo_client.close()
        await admin_app.state.ll2_client.close()


class TestSyncRoute:
    @pytest.mark.asyncio
    async def test_sync_route_requires_admin(self, admin_client):
        """POST /api/v1/launches/sync without auth returns 401."""
        response = await admin_client.post("/api/v1/launches/sync")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_route_wrong_key(self, admin_client):
        """POST /api/v1/launches/sync with wrong key returns 401."""
        response = await admin_client.post(
            "/api/v1/launches/sync",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_route_no_admin_key_configured(self, client):
        """POST /api/v1/launches/sync when admin_api_key is empty returns 503.

        The `client` fixture uses settings with require_secrets=False and
        empty admin_api_key by default, so this test uses it directly.
        """
        response = await client.post(
            "/api/v1/launches/sync",
            headers={"Authorization": "Bearer somekey"},
        )
        assert response.status_code == 503

    @respx.mock
    @pytest.mark.asyncio
    async def test_sync_route_admin_triggers_sync(self, admin_client):
        """POST /api/v1/launches/sync with correct admin key calls sync."""
        raw = _make_raw_launch()
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        response = await admin_client.post(
            "/api/v1/launches/sync",
            headers={"Authorization": "Bearer test-admin-secret"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"


class TestNewLaunchNotification:
    @respx.mock
    @pytest.mark.asyncio
    async def test_new_launch_creates_notification_for_agency_sub(
        self, db_session, settings, agency_subscription
    ):
        """Brand new launch creates NEW_LAUNCH notification for agency subscribers."""
        raw = _make_raw_launch()
        respx.get(f"{_LL2_BASE}/launches/upcoming/").mock(
            return_value=Response(200, json=_ll2_page([raw]))
        )

        client = LL2Client(settings)
        await launches_service.sync_launches(db_session, client)

        result = await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.ll2_id == "launch-001",
                PendingNotification.change_type == "NEW_LAUNCH",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) == 1
        assert notifications[0].subscription_id == agency_subscription.id
        await client.close()


class TestPagination:
    @respx.mock
    @pytest.mark.asyncio
    async def test_pagination_follows_next(self, db_session, settings):
        """Pagination follows next URL until None."""
        raw1 = _make_raw_launch(ll2_id="p-001", name="Launch 1")
        raw2 = _make_raw_launch(ll2_id="p-002", name="Launch 2")

        page1_url = f"{_LL2_BASE}/launches/upcoming/?mode=detailed&limit=100&ordering=net"
        page2_url = f"{_LL2_BASE}/launches/upcoming/?mode=detailed&limit=100&ordering=net&offset=100"

        respx.get(page1_url).mock(
            return_value=Response(
                200, json=_ll2_page([raw1], next_url=page2_url)
            )
        )
        respx.get(page2_url).mock(
            return_value=Response(200, json=_ll2_page([raw2]))
        )

        client = LL2Client(settings)
        results = await client.fetch_upcoming()
        assert len(results) == 2
        assert results[0]["id"] == "p-001"
        assert results[1]["id"] == "p-002"
        await client.close()


# ---------------------------------------------------------------------------
# LL2Client error branch coverage
# ---------------------------------------------------------------------------


class TestLL2ClientErrors:
    """Cover ll2_client.py error branches directly."""

    @pytest.mark.asyncio
    async def test_api_key_sets_auth_header(self, settings):
        """When ll2_api_key is set, Authorization header is included on the httpx client."""
        settings_with_key = Settings(  # type: ignore[call-arg]
            require_secrets=False,
            ll2_base_url=_LL2_BASE,
            ll2_api_key="mytoken123",
        )
        client = LL2Client(settings_with_key)
        # The header is set on the underlying httpx.AsyncClient at construction time
        assert client._client.headers.get("authorization") == "Token mytoken123"
        await client.close()

    @pytest.mark.asyncio
    async def test_connect_error_raises_ll2_client_error(self, settings):
        """ConnectError → LL2ClientError with LL2_UNAVAILABLE code."""
        import httpx as _httpx
        import pytest

        async def _transport(request):
            raise _httpx.ConnectError("refused")

        mock_client = _httpx.AsyncClient(transport=_httpx.MockTransport(_transport))
        client = LL2Client(settings, client=mock_client)
        with pytest.raises(LL2ClientError) as exc_info:
            await client.fetch_upcoming()
        assert exc_info.value.code == "LL2_UNAVAILABLE"
        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_raises_ll2_client_error(self, settings):
        """TimeoutException → LL2ClientError with LL2_TIMEOUT code."""
        import httpx as _httpx
        import pytest

        async def _transport(request):
            raise _httpx.TimeoutException("timed out")

        mock_client = _httpx.AsyncClient(transport=_httpx.MockTransport(_transport))
        client = LL2Client(settings, client=mock_client)
        with pytest.raises(LL2ClientError) as exc_info:
            await client.fetch_upcoming()
        assert exc_info.value.code == "LL2_TIMEOUT"
        await client.close()

    @pytest.mark.asyncio
    async def test_http_error_raises_ll2_client_error(self, settings):
        """Generic HTTPError → LL2ClientError with LL2_HTTP_ERROR code."""
        import httpx as _httpx
        import pytest

        async def _transport(request):
            raise _httpx.HTTPError("network error")

        mock_client = _httpx.AsyncClient(transport=_httpx.MockTransport(_transport))
        client = LL2Client(settings, client=mock_client)
        with pytest.raises(LL2ClientError) as exc_info:
            await client.fetch_upcoming()
        assert exc_info.value.code == "LL2_HTTP_ERROR"
        await client.close()

    @pytest.mark.asyncio
    async def test_large_response_raises_ll2_client_error(self, settings):
        """Response > 5 MB → LL2ClientError with LL2_RESPONSE_TOO_LARGE."""
        import httpx as _httpx
        import pytest

        async def _transport(request):
            big_body = b"x" * (5 * 1024 * 1024 + 1)
            return _httpx.Response(200, content=big_body)

        mock_client = _httpx.AsyncClient(transport=_httpx.MockTransport(_transport))
        client = LL2Client(settings, client=mock_client)
        with pytest.raises(LL2ClientError) as exc_info:
            await client.fetch_upcoming()
        assert exc_info.value.code == "LL2_RESPONSE_TOO_LARGE"
        await client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_200_raises_ll2_client_error(self, settings):
        """Non-200 response → LL2ClientError with LL2_ERROR code."""
        import pytest

        url = f"{_LL2_BASE}/launches/upcoming/?mode=detailed&limit=100&ordering=net"
        respx.get(url).mock(return_value=Response(503, text="Service Unavailable"))

        client = LL2Client(settings)
        with pytest.raises(LL2ClientError) as exc_info:
            await client.fetch_upcoming()
        assert exc_info.value.code == "LL2_ERROR"
        await client.close()

    @pytest.mark.asyncio
    async def test_invalid_json_raises_ll2_client_error(self, settings):
        """Invalid JSON body → LL2ClientError with LL2_INVALID_JSON code."""
        import httpx as _httpx
        import pytest

        async def _transport(request):
            return _httpx.Response(200, content=b"not-json{{{")

        mock_client = _httpx.AsyncClient(transport=_httpx.MockTransport(_transport))
        client = LL2Client(settings, client=mock_client)
        with pytest.raises(LL2ClientError) as exc_info:
            await client.fetch_upcoming()
        assert exc_info.value.code == "LL2_INVALID_JSON"
        await client.close()

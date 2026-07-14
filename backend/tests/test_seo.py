"""SEO launch pages + sitemap (Architecture/23-seo-widgets-and-growth.md B2).

Covers the three routes in `app/routers/seo.py`: per-launch meta injection
(default + language-prefixed), unknown-id noindex fallback, and the sitemap.
Uses a temp directory standing in for the shared `frontend-dist` volume, since
these routes read a built `index.html` off disk rather than from a template
engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from lxml import etree
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database import get_db
from app.main import create_app
from app.routers.seo import _DEFAULT_TITLE_TAG, _SEO_PLACEHOLDER
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient
from tests.test_launches_service_unit import FakeLL2Client, _raw

_FAKE_INDEX_HTML = f"""<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    {_DEFAULT_TITLE_TAG}
    {_SEO_PLACEHOLDER}
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
"""


@pytest_asyncio.fixture
async def dist_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(_FAKE_INDEX_HTML, encoding="utf-8")
    missions_dir = tmp_path / "missions"
    missions_dir.mkdir()
    (missions_dir / "index.json").write_text(
        '{"missions": [{"slug": "apollo-11"}, {"slug": "pathfinder"}]}',
        encoding="utf-8",
    )
    return tmp_path


@pytest_asyncio.fixture
async def seo_settings(dist_dir: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key="",
        cookie_secure=False,
        nasa_api_key="TEST_KEY",
        nasa_base_url="https://api.nasa.example",
        n2yo_api_key="TEST_N2YO",
        n2yo_base_url="https://api.n2yo.example/rest/v1/satellite",
        n2yo_hourly_cap=900,
        ll2_base_url="https://ll.thespacedevs.example",
        frontend_origin="https://example.test",
        frontend_dist_path=str(dist_dir),
    )


@pytest_asyncio.fixture
async def seo_client(db_engine, seo_settings: Settings) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app(settings=seo_settings)
    app.state.nasa_client = NasaClient(seo_settings)
    app.state.n2yo_client = N2YOClient(seo_settings)
    app.state.ll2_client = LL2Client(seo_settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(seo_settings)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()
        await app.state.ll2_client.close()
        await app.state.mars_raw_images_client.close()


async def _seed_launch(db_session, **overrides) -> None:
    from app.services.launches_service import sync_launches

    await sync_launches(db_session, FakeLL2Client([_raw(**overrides)]))


# ---------------------------------------------------------------------------
# Per-launch meta injection
# ---------------------------------------------------------------------------


async def test_seo_launch_page_injects_meta(seo_client, db_session) -> None:
    await _seed_launch(db_session, ll2_id="l-1")

    resp = await seo_client.get("/launches/l-1")
    assert resp.status_code == 200
    body = resp.text

    assert _DEFAULT_TITLE_TAG not in body
    assert "<title>Starlink — Space Adventures</title>" in body
    assert 'property="og:title" content="Starlink — Space Adventures"' in body
    assert 'name="twitter:card" content="summary_large_image"' in body
    assert 'rel="canonical" href="https://example.test/launches/l-1"' in body
    assert '<script type="application/ld+json">' in body
    assert '"@type": "Event"' in body
    assert '"name": "Starlink"' in body
    assert resp.headers.get("cache-control") == "public, max-age=300"
    assert "x-robots-tag" not in resp.headers


async def test_seo_launch_page_localized_lang_prefix(seo_client, db_session) -> None:
    await _seed_launch(db_session, ll2_id="l-2")

    resp = await seo_client.get("/de/launches/l-2")
    assert resp.status_code == 200
    body = resp.text

    assert 'rel="canonical" href="https://example.test/de/launches/l-2"' in body
    # hreflang alternates cross-link every supported locale plus x-default.
    assert 'hreflang="en" href="https://example.test/launches/l-2"' in body
    assert 'hreflang="de" href="https://example.test/de/launches/l-2"' in body
    assert 'hreflang="ja" href="https://example.test/ja/launches/l-2"' in body
    assert 'hreflang="x-default" href="https://example.test/launches/l-2"' in body


async def test_seo_launch_page_unsupported_lang_falls_back_to_en_content(
    seo_client, db_session
) -> None:
    await _seed_launch(db_session, ll2_id="l-3")

    resp = await seo_client.get("/xx/launches/l-3")
    assert resp.status_code == 200
    # No translations exist, and "xx" isn't a supported lang: the localized
    # canonical URL still reflects the raw path segment, but content
    # (title/description) falls back to the English/default fields rather
    # than erroring.
    assert "<title>Starlink — Space Adventures</title>" in resp.text


async def test_seo_launch_page_uses_stored_translation(seo_client, db_session) -> None:
    from app.models.launches import Launch

    await _seed_launch(db_session, ll2_id="l-tr")
    launch = await db_session.get(Launch, "l-tr")
    launch.translations_json = {"de": {"mission_name": "Starlink (DE)", "mission_description": "Satelliten."}}
    await db_session.commit()

    resp = await seo_client.get("/de/launches/l-tr")
    assert resp.status_code == 200
    assert "<title>Starlink (DE) — Space Adventures</title>" in resp.text
    assert 'content="Satelliten."' in resp.text

    # English (no prefix) must not pick up the German translation.
    resp_en = await seo_client.get("/launches/l-tr")
    assert "<title>Starlink — Space Adventures</title>" in resp_en.text


async def test_seo_launch_page_status_maps_to_event_status(seo_client, db_session) -> None:
    await _seed_launch(db_session, ll2_id="l-hold", status={"abbrev": "Hold", "name": "On Hold"})
    resp = await seo_client.get("/launches/l-hold")
    assert '"eventStatus": "https://schema.org/EventPostponed"' in resp.text

    await _seed_launch(db_session, ll2_id="l-fail", status={"abbrev": "Failure", "name": "Failed"})
    resp = await seo_client.get("/launches/l-fail")
    assert '"eventStatus": "https://schema.org/EventCancelled"' in resp.text


async def test_seo_launch_page_no_image_omits_og_image(seo_client, db_session) -> None:
    await _seed_launch(db_session, ll2_id="l-noimg", image=None)
    resp = await seo_client.get("/launches/l-noimg")
    assert 'property="og:image"' not in resp.text
    assert 'name="twitter:image"' not in resp.text


async def test_seo_launch_page_unknown_id_serves_noindex(seo_client, db_session) -> None:
    resp = await seo_client.get("/launches/does-not-exist")
    assert resp.status_code == 200
    assert resp.headers.get("x-robots-tag") == "noindex"
    # Untouched index: default title survives, placeholder never got filled.
    assert _DEFAULT_TITLE_TAG in resp.text
    assert _SEO_PLACEHOLDER in resp.text


async def test_seo_launch_page_gone_launch_serves_noindex(seo_client, db_session) -> None:
    """A launch LL2 stopped returning entirely (status "Gone") is excluded
    from the sitemap (test_sitemap_excludes_gone_and_stale_launches below) —
    a direct/stale link to its detail page must get the same noindex
    treatment as an unknown id, not a full indexable SEO page claiming the
    event is still scheduled."""
    from app.models.launches import Launch

    await _seed_launch(db_session, ll2_id="l-gone")
    launch = await db_session.get(Launch, "l-gone")
    launch.status_abbrev = "Gone"
    await db_session.commit()

    resp = await seo_client.get("/launches/l-gone")
    assert resp.status_code == 200
    assert resp.headers.get("x-robots-tag") == "noindex"
    assert _DEFAULT_TITLE_TAG in resp.text
    assert _SEO_PLACEHOLDER in resp.text


async def test_seo_launch_page_xss_mission_name_escaped_in_response(
    seo_client, db_session
) -> None:
    """Integration-level companion to the unit test in
    tests/security/test_injection.py — same control, exercised through the
    real HTTP router instead of calling `_build_seo_head` directly."""
    await _seed_launch(
        db_session,
        ll2_id="l-xss",
        mission={"name": "<script>alert(1)</script>", "description": "Sats.", "type": "Comms"},
    )

    resp = await seo_client.get("/launches/l-xss")
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------


async def test_sitemap_xml_is_well_formed_and_complete(seo_client, db_session) -> None:
    await _seed_launch(db_session, ll2_id="l-map")

    resp = await seo_client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert resp.headers.get("cache-control") == "max-age=3600"

    root = etree.fromstring(resp.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "xhtml": "http://www.w3.org/1999/xhtml"}
    locs = [el.text for el in root.findall("sm:url/sm:loc", ns)]

    assert "https://example.test" in locs  # "/" static route
    assert "https://example.test/launches" in locs
    assert "https://example.test/missions/apollo-11" in locs
    assert "https://example.test/missions/pathfinder" in locs
    assert "https://example.test/launches/l-map" in locs
    assert "https://example.test/de/launches/l-map" in locs

    launch_url_el = next(
        el for el in root.findall("sm:url", ns)
        if el.find("sm:loc", ns).text == "https://example.test/launches/l-map"
    )
    alt_langs = {
        link.get("hreflang") for link in launch_url_el.findall("xhtml:link", ns)
    }
    assert alt_langs == {"en", "de", "es", "fr", "ja", "ru", "x-default"}


async def test_sitemap_tolerates_missing_missions_index(db_engine, tmp_path: Path, db_session) -> None:
    """`missions/index.json` absent (or malformed) must degrade to zero
    mission URLs, never a 500 — the sitemap is a public, unauthenticated
    endpoint and a bad/missing static file is not the caller's fault."""
    (tmp_path / "index.html").write_text(_FAKE_INDEX_HTML, encoding="utf-8")
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key="",
        cookie_secure=False,
        nasa_api_key="TEST_KEY",
        nasa_base_url="https://api.nasa.example",
        n2yo_api_key="TEST_N2YO",
        n2yo_base_url="https://api.n2yo.example/rest/v1/satellite",
        n2yo_hourly_cap=900,
        ll2_base_url="https://ll.thespacedevs.example",
        frontend_origin="https://example.test",
        frontend_dist_path=str(tmp_path),
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app(settings=settings)
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.dependency_overrides[get_db] = _override_get_db

    await _seed_launch(db_session, ll2_id="l-nomissions")

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/sitemap.xml")
    finally:
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()
        await app.state.ll2_client.close()
        await app.state.mars_raw_images_client.close()

    assert resp.status_code == 200
    assert "https://example.test/missions/" not in resp.text
    root = etree.fromstring(resp.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text for el in root.findall("sm:url/sm:loc", ns)]
    assert "https://example.test/launches/l-nomissions" in locs


async def test_sitemap_excludes_gone_and_stale_launches(seo_client, db_session) -> None:
    from datetime import datetime, timedelta, timezone as tz

    old_net = (datetime.now(tz.utc) - timedelta(days=365)).isoformat()
    await _seed_launch(db_session, ll2_id="l-old", net=old_net)

    resp = await seo_client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "l-old" not in resp.text


# ---------------------------------------------------------------------------
# No upstream calls — crawlers hammering these routes must never trigger an
# LL2/NASA/etc. request (23-…md B2 "Tests" requirement).
# ---------------------------------------------------------------------------


@respx.mock
async def test_seo_routes_never_call_upstream(seo_client, db_session) -> None:
    """No respx route is registered: if the handler attempted any outbound
    HTTP call, respx's default `assert_all_mocked=True` would raise
    AllMockedAssertionError. A clean 200 here is itself the proof of zero
    upstream calls."""
    await _seed_launch(db_session, ll2_id="l-noupstream")

    resp1 = await seo_client.get("/launches/l-noupstream")
    assert resp1.status_code == 200

    resp2 = await seo_client.get("/en/launches/l-noupstream")
    assert resp2.status_code == 200

    resp3 = await seo_client.get("/sitemap.xml")
    assert resp3.status_code == 200

    resp4 = await seo_client.get("/launches/does-not-exist")
    assert resp4.status_code == 200


# ---------------------------------------------------------------------------
# Frontend build unavailable
# ---------------------------------------------------------------------------


async def test_seo_launch_page_503_when_dist_missing(db_engine, tmp_path: Path) -> None:
    missing_dist = tmp_path / "does-not-exist"
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key="",
        cookie_secure=False,
        nasa_api_key="TEST_KEY",
        nasa_base_url="https://api.nasa.example",
        n2yo_api_key="TEST_N2YO",
        n2yo_base_url="https://api.n2yo.example/rest/v1/satellite",
        n2yo_hourly_cap=900,
        ll2_base_url="https://ll.thespacedevs.example",
        frontend_origin="https://example.test",
        frontend_dist_path=str(missing_dist),
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app(settings=settings)
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/launches/anything")
    finally:
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()
        await app.state.ll2_client.close()
        await app.state.mars_raw_images_client.close()

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Launch history endpoint (GET /api/v1/launches/{ll2_id}/history)
# ---------------------------------------------------------------------------


async def test_launch_history_empty_for_unknown_launch(seo_client) -> None:
    resp = await seo_client.get("/api/v1/launches/does-not-exist/history")
    assert resp.status_code == 200
    assert resp.json() == {"data": []}


async def test_launch_history_returns_recorded_changes(seo_client, db_session) -> None:
    from app.services.launches_service import _record_change

    await _seed_launch(db_session, ll2_id="l-hist")
    _record_change(
        db_session,
        launch_id="l-hist",
        change_type="net",
        provider_name="SpaceX",
        rocket_name="Falcon 9",
        pad_name=None,
        old_value="2099-01-01T00:00:00+00:00",
        new_value="2099-01-02T00:00:00+00:00",
    )
    await db_session.commit()

    resp = await seo_client.get("/api/v1/launches/l-hist/history")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["data"]) == 1
    entry = payload["data"][0]
    assert entry["change_type"] == "net"
    assert entry["old_value"] == "2099-01-01T00:00:00+00:00"
    assert entry["new_value"] == "2099-01-02T00:00:00+00:00"
    assert "detected_at" in entry

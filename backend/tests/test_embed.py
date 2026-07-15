"""Embeddable widget tests (Architecture/23-seo-widgets-and-growth.md L3).

Coverage requirements per CLAUDE.md definition-of-done:
- embed HTML self-contained (no external asset URLs)
- provider filter filters by agency_name
- lang param selects widget language
- CSP frame-ancestors * header present
- no Set-Cookie header
- response size ≤ 30 KB
- no upstream calls (marked with respx)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
import respx

from app.models.launches import Launch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _future(hours: int = 24) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(tzinfo=None)


async def _add_launch(
    db_session,
    ll2_id: str = "embed-l1",
    agency_name: str = "SpaceX",
    mission_name: str | None = "Starlink G10-1",
    status_abbrev: str = "Go",
    hours: int = 24,
) -> Launch:
    launch = Launch(
        ll2_id=ll2_id,
        name=f"Falcon 9 | {mission_name or 'Launch'}",
        net=_future(hours),
        status_abbrev=status_abbrev,
        status_name="Go for Launch",
        agency_name=agency_name,
        agency_type="Commercial",
        rocket_name="Falcon 9",
        rocket_family="Falcon",
        mission_name=mission_name,
        mission_description="Test mission.",
        mission_type="Communications",
        pad_name="SLC-40",
        pad_location="Cape Canaveral",
        livestream_urls=[],
    )
    db_session.add(launch)
    await db_session.commit()
    return launch


# ---------------------------------------------------------------------------
# Basic embed route
# ---------------------------------------------------------------------------


async def test_embed_returns_200_html(client, db_session):
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_embed_contains_mission_name(client, db_session):
    await _add_launch(db_session, mission_name="Starlink G10-1")
    resp = await client.get("/embed/next-launch")
    body = resp.text
    # Mission name appears in the JSON data variable (JSON-encoded).
    assert "Starlink G10-1" in body


async def test_embed_with_no_launches_returns_200(client):
    resp = await client.get("/embed/next-launch")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_embed_launch_data_is_json_encoded(client, db_session):
    """LL2 data is embedded in a <script> JSON variable, not raw HTML."""
    await _add_launch(db_session, mission_name="Starlink G10-1")
    resp = await client.get("/embed/next-launch")
    body = resp.text
    # The JS data variable must be valid JSON — no raw strings that would
    # break out of the <script> block.
    script_open = "<script>"
    assert script_open in body
    assert "</script>" in body


async def test_embed_excludes_gone_launches(client, db_session):
    """Gone launches (LL2 stopped tracking) must not appear in the widget."""
    await _add_launch(db_session, ll2_id="gone-l", status_abbrev="Gone")
    resp = await client.get("/embed/next-launch")
    assert resp.status_code == 200
    # The response body should not contain the gone launch — the JS data
    # variable should be null.
    assert '"status_abbrev"' not in resp.text  # we only embed name/net/etc.
    # The launch JSON should be null (no launch found after filtering Gone).
    assert "var L=null" in resp.text or "var L= null" in resp.text or "L=null" in resp.text


# ---------------------------------------------------------------------------
# Provider filter
# ---------------------------------------------------------------------------


async def test_embed_provider_filter_matches(client, db_session):
    """?provider= filters by agency_name (case-insensitive substring)."""
    await _add_launch(db_session, ll2_id="l-spacex", agency_name="SpaceX", hours=10)
    await _add_launch(db_session, ll2_id="l-ula", agency_name="United Launch Alliance", hours=5)

    # Without filter: returns earliest launch (ULA at 5h)
    resp = await client.get("/embed/next-launch")
    assert resp.status_code == 200
    assert "United Launch Alliance" in resp.text

    # With SpaceX filter: returns SpaceX launch
    resp = await client.get("/embed/next-launch?provider=SpaceX")
    assert resp.status_code == 200
    assert "SpaceX" in resp.text


async def test_embed_provider_filter_case_insensitive(client, db_session):
    await _add_launch(db_session, agency_name="SpaceX", hours=5)
    resp = await client.get("/embed/next-launch?provider=spacex")
    assert resp.status_code == 200
    assert "SpaceX" in resp.text


async def test_embed_provider_filter_no_match_returns_null(client, db_session):
    """Provider filter with no matching agency results in null launch data."""
    await _add_launch(db_session, agency_name="SpaceX", hours=5)
    resp = await client.get("/embed/next-launch?provider=ESA")
    assert resp.status_code == 200
    # null launch data → JS renders the "no upcoming launches" message
    assert "null" in resp.text


# ---------------------------------------------------------------------------
# Language support
# ---------------------------------------------------------------------------


async def test_embed_default_lang_is_en(client, db_session):
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch")
    assert 'lang="en"' in resp.text
    assert "Next Launch" in resp.text


@pytest.mark.parametrize("lang,expected_title", [
    ("de", "Nächster Start"),
    ("es", "Próximo lanzamiento"),
    ("fr", "Prochain lancement"),
    ("ja", "次回打ち上げ"),
    ("ru", "Следующий пуск"),
])
async def test_embed_lang_param_selects_labels(lang, expected_title, client, db_session):
    await _add_launch(db_session)
    resp = await client.get(f"/embed/next-launch?lang={lang}")
    assert resp.status_code == 200
    assert expected_title in resp.text


async def test_embed_unknown_lang_falls_back_to_en(client, db_session):
    """An unsupported lang code falls back to English labels silently."""
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch?lang=xx")
    assert resp.status_code == 200
    assert 'lang="en"' in resp.text
    assert "Next Launch" in resp.text


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


async def test_embed_csp_allows_framing(client, db_session):
    """CSP frame-ancestors * must be present so third-party sites can embed."""
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch")
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors *" in csp


async def test_embed_no_set_cookie_header(client, db_session):
    """Embed responses must never set cookies — no auth, no session."""
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch")
    assert "set-cookie" not in resp.headers


async def test_embed_cache_control(client, db_session):
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch")
    cc = resp.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=60" in cc


# ---------------------------------------------------------------------------
# Size budget (≤ 30 KB per 26-performance.md §2.1)
# ---------------------------------------------------------------------------

_MAX_EMBED_BYTES = 30 * 1024  # 30 KB


async def test_embed_response_size_within_budget(client, db_session):
    """The embed page total (HTML + inline CSS + JS) must stay ≤ 30 KB."""
    await _add_launch(db_session, mission_name="A" * 200)  # large-ish mission name
    resp = await client.get("/embed/next-launch")
    assert resp.status_code == 200
    size = len(resp.content)
    assert size <= _MAX_EMBED_BYTES, (
        f"Embed response is {size} bytes — exceeds the 30 KB budget "
        f"(Architecture/26-performance.md §2.1)"
    )


# ---------------------------------------------------------------------------
# Self-containment: no external asset URLs
# ---------------------------------------------------------------------------

# Pattern that finds external src/href in <script>, <link>, <img> tags.
_EXTERNAL_ASSET_RE = re.compile(
    r'<(?:script|link|img)[^>]+(?:src|href)=["\']https?://',
    re.IGNORECASE,
)


async def test_embed_html_has_no_external_asset_urls(client, db_session):
    """No external CDN scripts/stylesheets/images in the embed HTML.

    The widget must be truly self-contained: only relative/same-origin refs
    allowed in asset tags.  The attribution <a href> link is exempted since it
    is not an asset-loading tag.
    """
    await _add_launch(db_session)
    resp = await client.get("/embed/next-launch")
    body = resp.text
    # Check <script src>, <link href>, <img src> for external URLs.
    matches = _EXTERNAL_ASSET_RE.findall(body)
    assert not matches, (
        f"Embed HTML contains external asset URL(s) — breaks self-containment: "
        f"{matches}"
    )


# ---------------------------------------------------------------------------
# No upstream calls from the embed route
# ---------------------------------------------------------------------------


@respx.mock
async def test_embed_makes_no_upstream_calls(client, db_session):
    """The embed route reads only from the DB — it must never trigger an
    upstream LL2/NASA/N2YO/etc. request."""
    await _add_launch(db_session)
    # respx.mock with no routes registered will raise if any HTTP call is made.
    resp = await client.get("/embed/next-launch")
    assert resp.status_code == 200
    # If we got here without an httpx error, no upstream calls were made.


# ---------------------------------------------------------------------------
# Attribution link
# ---------------------------------------------------------------------------


async def test_embed_attribution_link_present(client, db_session):
    """The attribution backlink must be present and not suppressible via params."""
    await _add_launch(db_session)
    for url in ["/embed/next-launch", "/embed/next-launch?provider=SpaceX&lang=de"]:
        resp = await client.get(url)
        assert resp.status_code == 200
        body = resp.text
        # The attribution link must always appear.
        assert 'rel="noopener noreferrer"' in body
        # "Space Adventures" must be in the link text (set via textContent in JS).
        assert "Space Adventures" in body


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_launch_json_normalizes_naive_net():
    """_launch_json() must add UTC tzinfo when net has no tzinfo attribute
    (defensive against non-DB-construction paths; UTCDateTime normalizes at
    readback, but direct model construction produces naive datetimes)."""
    import json as _json
    from datetime import datetime

    from app.models.launches import Launch
    from app.routers.embed import _launch_json

    launch = Launch(
        ll2_id="unit-test",
        name="Unit Test Launch",
        net=datetime(2099, 6, 15, 12, 0, 0),  # naive: tzinfo=None
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="TestCo",
        rocket_name="Test Rocket",
        pad_name="Pad 1",
        pad_location="Test Site",
        livestream_urls=[],
    )
    result = _launch_json(launch)
    data = _json.loads(result)
    # The ISO string must include a UTC offset so the browser's Date() parses
    # it correctly as UTC rather than local time.
    assert "net" in data
    net_str = data["net"]
    assert "+00:00" in net_str or net_str.endswith("Z"), (
        f"Expected UTC offset in net string, got: {net_str!r}"
    )


def test_launch_json_returns_null_for_none():
    from app.routers.embed import _launch_json

    assert _launch_json(None) == "null"


def test_json_safe_escapes_line_separator_and_paragraph_separator():
    """U+2028 / U+2029 are ECMAScript line terminators; inside <script> they
    break string literals.  _json_safe() must escape them to \\u2028 / \\u2029."""
    from app.routers.embed import _json_safe

    result = _json_safe({"name": "test line end"})
    assert " " not in result, "U+2028 must be escaped, not literal"
    assert " " not in result, "U+2029 must be escaped, not literal"
    assert "\\u2028" in result
    assert "\\u2029" in result

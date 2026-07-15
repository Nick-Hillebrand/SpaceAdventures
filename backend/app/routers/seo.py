"""Per-launch SEO pages + sitemap (Architecture/23-seo-widgets-and-growth.md B2).

Server-rendered meta + client-rendered content: these routes read the
already-built frontend `index.html` from a shared read-only volume and
inject `<title>`/OG/Twitter/canonical/hreflang/JSON-LD tags into a
`<!--seo-head-->` placeholder, then hand the (otherwise unmodified) SPA
bundle back to the browser. They read only from the DB + the static dist
directory — never from an upstream client — so a crawler hammering these
routes can never trigger an LL2/NASA/etc. request.

Mission names and descriptions come from LL2, untrusted input
(25-security-testing.md §2.3): every value interpolated into the HTML meta
tags is `html.escape()`d, and the JSON-LD block is neutralised against
`</script>` breakout separately (see `_json_ld_safe`).
"""
from __future__ import annotations

import html
import json
import logging
import xml.etree.ElementTree as ET
from datetime import timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.launches import Launch
from app.services import launches_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["seo"])

SUPPORTED_LANGS: tuple[str, ...] = ("en", "de", "es", "fr", "ja", "ru")

_SEO_PLACEHOLDER = "<!--seo-head-->"
# The static default title baked into the built index.html — swapped out
# in place rather than left in the document alongside the injected one,
# since a page with two <title> elements is invalid HTML and most parsers
# resolve document.title to whichever one they saw first.
_DEFAULT_TITLE_TAG = "<title>Space Adventures</title>"

# Top-level SPA routes with no dynamic id — one <url> entry each in the
# sitemap, no hreflang (i18n is client-side only, not URL-prefixed).
_STATIC_ROUTES: tuple[str, ...] = (
    "/",
    "/apod",
    "/iss",
    "/launches",
    "/mars",
    "/neo",
    "/space-weather",
    "/solar-system",
    "/missions",
    "/widgets",
)

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_XHTML_NS = "http://www.w3.org/1999/xhtml"


# ---------------------------------------------------------------------------
# Shared dist-volume readers
# ---------------------------------------------------------------------------


def _dist_path(settings: Any, *parts: str) -> Path:
    return Path(settings.frontend_dist_path).joinpath(*parts)


def _read_index_html(settings: Any) -> str | None:
    path = _dist_path(settings, "index.html")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("SEO: frontend dist index.html not found at %s", path)
        return None


def _read_mission_slugs(settings: Any) -> list[str]:
    """Mission slugs for the sitemap — read from the same built dist
    directory (Vite copies `public/*` verbatim, so `missions/index.json`
    lands next to `index.html`)."""
    path = _dist_path(settings, "missions", "index.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    missions = data.get("missions") if isinstance(data, dict) else None
    if not isinstance(missions, list):
        return []
    return [m["slug"] for m in missions if isinstance(m, dict) and m.get("slug")]


# ---------------------------------------------------------------------------
# URL / meta helpers
# ---------------------------------------------------------------------------


def _base_url(settings: Any) -> str:
    return str(settings.frontend_origin).rstrip("/")


def _canonical_url(base: str, lang: str, ll2_id: str) -> str:
    prefix = "" if lang == "en" else f"/{lang}"
    return f"{base}{prefix}/launches/{ll2_id}"


def _resolved_lang(lang: str) -> str:
    return lang if lang in SUPPORTED_LANGS else "en"


def _localized_field(launch: Launch, lang: str, field: str) -> str | None:
    if lang == "en" or not launch.translations_json:
        return None
    return (launch.translations_json.get(lang) or {}).get(field) or None


def _display_name(launch: Launch, lang: str) -> str:
    return _localized_field(launch, lang, "mission_name") or launch.mission_name or launch.name


def _display_description(launch: Launch, lang: str) -> str:
    return _localized_field(launch, lang, "mission_description") or launch.mission_description or ""


def _event_status(status_abbrev: str, status_name: str) -> str:
    name = status_name.lower()
    if status_abbrev == "Hold":
        return "https://schema.org/EventPostponed"
    if status_abbrev == "Failure" or "cancel" in name:
        return "https://schema.org/EventCancelled"
    return "https://schema.org/EventScheduled"


def _json_ld_safe(data: dict) -> str:
    """`json.dumps()`, then neutralise `<` so the blob can never break out of
    the `<script type="application/ld+json">` tag it's embedded in — the
    JSON-LD equivalent of `html.escape()` for the meta tags below."""
    return json.dumps(data).replace("<", "\\u003c")


def _build_seo_head(launch: Launch, lang: str, settings: Any) -> tuple[str, str]:
    """Returns (title_tag, rest_of_head) — kept separate because the title
    tag replaces the static default in index.html in place, while the rest
    of the tags fill the `<!--seo-head-->` placeholder (see
    `_inject_and_respond`)."""
    base = _base_url(settings)
    name = _display_name(launch, lang)
    description = (_display_description(launch, lang) or (
        f"{launch.agency_name} {launch.rocket_name} launching from {launch.pad_name}."
    ))[:300]
    canonical = _canonical_url(base, lang, launch.ll2_id)
    title = f"{name} — Space Adventures"

    esc_title = html.escape(title)
    esc_description = html.escape(description)
    esc_canonical = html.escape(canonical, quote=True)

    title_tag = f"<title>{esc_title}</title>"
    tags = [
        f'<meta name="description" content="{esc_description}">',
        f'<link rel="canonical" href="{esc_canonical}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{esc_title}">',
        f'<meta property="og:description" content="{esc_description}">',
        f'<meta property="og:url" content="{esc_canonical}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc_title}">',
        f'<meta name="twitter:description" content="{esc_description}">',
    ]

    if launch.image_url:
        esc_image = html.escape(launch.image_url, quote=True)
        tags.append(f'<meta property="og:image" content="{esc_image}">')
        tags.append(f'<meta name="twitter:image" content="{esc_image}">')

    for alt_lang in SUPPORTED_LANGS:
        href = html.escape(_canonical_url(base, alt_lang, launch.ll2_id), quote=True)
        tags.append(f'<link rel="alternate" hreflang="{alt_lang}" href="{href}">')
    default_href = html.escape(_canonical_url(base, "en", launch.ll2_id), quote=True)
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{default_href}">')

    net = launch.net if launch.net.tzinfo is not None else launch.net.replace(tzinfo=timezone.utc)
    start_date = net.isoformat()
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": name,
        "startDate": start_date,
        "eventStatus": _event_status(launch.status_abbrev, launch.status_name),
        "location": {"@type": "Place", "name": launch.pad_name},
    }
    tags.append(f'<script type="application/ld+json">{_json_ld_safe(json_ld)}</script>')

    return title_tag, "\n".join(tags)


def _inject_and_respond(
    index_html: str, head: tuple[str, str] | None, *, noindex: bool, cache_seconds: int
) -> Response:
    body = index_html
    if head is not None:
        title_tag, rest = head
        body = body.replace(_DEFAULT_TITLE_TAG, title_tag).replace(_SEO_PLACEHOLDER, rest)
    headers = {"Cache-Control": f"public, max-age={cache_seconds}"}
    if noindex:
        headers["X-Robots-Tag"] = "noindex"
    return Response(content=body, media_type="text/html", headers=headers)


async def _serve_launch_page(
    ll2_id: str, lang: str, request: Request, session: AsyncSession
) -> Response:
    settings = request.app.state.settings
    index_html = _read_index_html(settings)
    if index_html is None:
        raise HTTPException(status_code=503, detail="Frontend build not available")

    launch = await launches_service.get_launch_by_id(session, ll2_id)
    if launch is None or launch.status_abbrev == "Gone":
        # Unknown id, or a launch LL2 stopped returning entirely (excluded
        # from the sitemap for the same reason, see get_sitemap_launches):
        # serve the untouched index — the SPA shows its own 404 — tagged
        # noindex so crawlers don't keep this URL around.
        return _inject_and_respond(index_html, None, noindex=True, cache_seconds=300)

    head = _build_seo_head(launch, _resolved_lang(lang), settings)
    return _inject_and_respond(index_html, head, noindex=False, cache_seconds=300)


@router.get("/launches/{ll2_id}")
async def seo_launch_page(
    ll2_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    return await _serve_launch_page(ll2_id, "en", request, session)


@router.get("/{lang}/launches/{ll2_id}")
async def seo_launch_page_localized(
    lang: str,
    ll2_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    return await _serve_launch_page(ll2_id, lang, request, session)


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------


def _sitemap_xml(settings: Any, launches: list[Launch], mission_slugs: list[str]) -> str:
    ET.register_namespace("", _SITEMAP_NS)
    ET.register_namespace("xhtml", _XHTML_NS)
    urlset = ET.Element(f"{{{_SITEMAP_NS}}}urlset")
    base = _base_url(settings)

    def _add_simple_url(loc: str) -> None:
        url_el = ET.SubElement(urlset, f"{{{_SITEMAP_NS}}}url")
        ET.SubElement(url_el, f"{{{_SITEMAP_NS}}}loc").text = loc

    for route in _STATIC_ROUTES:
        _add_simple_url(f"{base}{route}" if route != "/" else base)

    for slug in mission_slugs:
        _add_simple_url(f"{base}/missions/{slug}")

    for launch in launches:
        for lang in SUPPORTED_LANGS:
            url_el = ET.SubElement(urlset, f"{{{_SITEMAP_NS}}}url")
            ET.SubElement(url_el, f"{{{_SITEMAP_NS}}}loc").text = _canonical_url(
                base, lang, launch.ll2_id
            )
            for alt_lang in (*SUPPORTED_LANGS, "x-default"):
                href_lang = "en" if alt_lang == "x-default" else alt_lang
                ET.SubElement(
                    url_el,
                    f"{{{_XHTML_NS}}}link",
                    {
                        "rel": "alternate",
                        "hreflang": alt_lang,
                        "href": _canonical_url(base, href_lang, launch.ll2_id),
                    },
                )

    xml_bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


@router.get("/sitemap.xml")
async def sitemap(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    settings = request.app.state.settings
    launches = await launches_service.get_sitemap_launches(session)
    mission_slugs = _read_mission_slugs(settings)
    xml_content = _sitemap_xml(settings, launches, mission_slugs)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "max-age=3600"},
    )

"""Route-authorization matrix (Architecture/25-security-testing.md §2.1).

A single parametrized test over a declared table of every route the app
registers. This is the highest-value security test in the suite: it fails
structurally the moment a new route is added without an explicit auth-level
decision, catching "forgot to protect the new endpoint" at review time
instead of in production.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database import get_db
from app.main import create_app
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient

# (method, path, auth_level) for every route FastAPI registers.
# auth_level:
#   public      — no credential required.
#   user        — requires `Authorization: Bearer <access_token>`.
#   admin       — requires `Authorization: Bearer <admin_api_key>`.
#   capability  — a bearer secret proves the right to act (refresh-token
#                 cookie, unsubscribe JWT); there is no notion of "user tier"
#                 to check, only "did you present the one valid secret".
ROUTE_TABLE: list[tuple[str, str, str]] = [
    ("GET", "/api/v1/health", "public"),
    ("GET", "/api/v1/apod", "public"),
    ("GET", "/api/v1/neo/feed", "public"),
    ("GET", "/api/v1/space-weather/flares", "public"),
    ("GET", "/api/v1/space-weather/storms", "public"),
    ("GET", "/api/v1/space-weather/cmes", "public"),
    ("GET", "/api/v1/space-weather/sep", "public"),
    ("GET", "/api/v1/space-weather/rbe", "public"),
    ("GET", "/api/v1/mars/rovers", "public"),
    ("GET", "/api/v1/mars/photos", "public"),
    ("GET", "/api/v1/iss/positions", "public"),
    ("GET", "/api/v1/iss/tle", "public"),
    ("GET", "/api/v1/iss/passes/visual", "public"),
    ("GET", "/api/v1/iss/passes/radio", "public"),
    ("GET", "/api/v1/iss/quota", "public"),
    ("GET", "/api/v1/launches/upcoming", "public"),
    ("POST", "/api/v1/launches/sync", "admin"),
    ("POST", "/api/v1/auth/register", "public"),
    ("POST", "/api/v1/auth/verify/email", "user"),
    ("POST", "/api/v1/auth/verify/phone", "user"),
    ("POST", "/api/v1/auth/verify/resend", "user"),
    ("POST", "/api/v1/auth/login", "public"),
    ("POST", "/api/v1/auth/refresh", "capability"),
    ("POST", "/api/v1/auth/logout", "capability"),
    ("GET", "/api/v1/auth/me", "user"),
    ("POST", "/api/v1/auth/consent", "user"),
    ("DELETE", "/api/v1/auth/me", "user"),
    ("GET", "/api/v1/auth/me/export", "user"),
    ("GET", "/api/v1/subscriptions", "user"),
    ("POST", "/api/v1/subscriptions/unsubscribe", "capability"),
    ("POST", "/api/v1/subscriptions", "user"),
    ("DELETE", "/api/v1/subscriptions/{subscription_id}", "user"),
    ("GET", "/api/v1/push/vapid-public-key", "public"),
    ("POST", "/api/v1/push/subscribe", "user"),
    ("DELETE", "/api/v1/push/subscribe", "user"),
    ("GET", "/api/v1/settings", "public"),
    # FastAPI's auto-generated interactive docs — read-only schema/UI, no
    # data access. Declared explicitly so the completeness check stays green;
    # revisit before a public launch if the OpenAPI surface should be hidden.
    ("GET", "/docs", "public"),
    ("GET", "/docs/oauth2-redirect", "public"),
    ("GET", "/redoc", "public"),
    ("GET", "/openapi.json", "public"),
]

VALID_AUTH_LEVELS = {"public", "user", "admin", "capability"}

# Path params in the table above need a concrete value to build a real URL.
_PATH_PARAM_FILLS = {"subscription_id": "route-matrix-test-id"}


def _concrete_path(path: str) -> str:
    for name, value in _PATH_PARAM_FILLS.items():
        path = path.replace(f"{{{name}}}", value)
    return path


def _iter_routes(routes):
    """Yield every leaf route, recursing into `include_router()` wrappers.

    FastAPI >= 0.139 no longer flattens included routers into `app.routes` —
    each `include_router()` call is instead represented by a lazy
    `_IncludedRouter` wrapper whose actual routes live on
    `original_router.routes`. Recursing here keeps this test working across
    that internal change instead of silently seeing an near-empty route list.
    """
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_routes(original_router.routes)
            continue
        yield route


def _actual_routes(app) -> set[tuple[str, str]]:
    actual: set[tuple[str, str]] = set()
    for route in _iter_routes(app.routes):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or path is None:
            continue
        for method in methods:
            if method == "HEAD":
                continue  # implied by GET, not separately declared
            actual.add((method, path))
    return actual


def test_every_declared_auth_level_is_valid():
    for method, path, auth_level in ROUTE_TABLE:
        assert auth_level in VALID_AUTH_LEVELS, f"{method} {path}: unknown auth_level {auth_level!r}"


def test_every_registered_route_is_declared(settings):
    """The structural check: a route missing from the table fails CI.

    This is what catches "added an endpoint, forgot to think about auth" —
    Architecture/25-security-testing.md §2.1 calls this the single
    highest-value security test.
    """
    app = create_app(settings=settings)
    declared = {(method, path) for method, path, _ in ROUTE_TABLE}
    undeclared = _actual_routes(app) - declared
    assert not undeclared, (
        "Route(s) registered but missing from ROUTE_TABLE in "
        "tests/security/test_route_matrix.py — every new route must land in "
        f"the route-authorization matrix before merge: {sorted(undeclared)}"
    )


def test_every_declared_route_is_registered(settings):
    """Catch stale entries left behind after a route is renamed/removed."""
    app = create_app(settings=settings)
    declared = {(method, path) for method, path, _ in ROUTE_TABLE}
    stale = declared - _actual_routes(app)
    assert not stale, f"ROUTE_TABLE declares route(s) that no longer exist: {sorted(stale)}"


# ---------------------------------------------------------------------------
# Credential-rejection checks — every non-public route must refuse an
# anonymous/invalid caller. Uses an admin-key-configured settings so the
# admin route actually reaches its auth check instead of short-circuiting on
# "admin key not configured".
# ---------------------------------------------------------------------------

ADMIN_API_KEY = "route-matrix-test-admin-key"


@pytest_asyncio.fixture
async def matrix_client(db_engine):
    admin_settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key=ADMIN_API_KEY,
        cookie_secure=False,
        nasa_api_key="TEST_KEY",
        nasa_base_url="https://api.nasa.example",
        n2yo_api_key="TEST_N2YO",
        n2yo_base_url="https://api.n2yo.example/rest/v1/satellite",
        n2yo_hourly_cap=900,
        ll2_base_url="https://ll.thespacedevs.example",
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app = create_app(settings=admin_settings)
    app.state.nasa_client = NasaClient(admin_settings)
    app.state.n2yo_client = N2YOClient(admin_settings)
    app.state.ll2_client = LL2Client(admin_settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(admin_settings)
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


# Bodies for routes whose auth dependency is evaluated ahead of body
# validation (an HTTPException raised in a FastAPI dependency propagates
# immediately, before pydantic validates the request body), so an empty body
# is enough to exercise the auth check — except the capability routes, whose
# handlers read the body themselves and need a plausible-shaped payload.
_CAPABILITY_BODIES = {
    "/api/v1/subscriptions/unsubscribe": {"token": "not-a-valid-jwt"},
}

NON_PUBLIC_ROUTES = [
    (method, path, auth_level) for method, path, auth_level in ROUTE_TABLE if auth_level != "public"
]


@pytest.mark.parametrize("method,path,auth_level", NON_PUBLIC_ROUTES)
async def test_non_public_route_rejects_anonymous_caller(matrix_client, method, path, auth_level):
    """No credential presented at all -> never 200, never a 5xx."""
    url = _concrete_path(path)
    json_body = _CAPABILITY_BODIES.get(path) if method in ("POST", "PUT", "PATCH") else None
    response = await matrix_client.request(method, url, json=json_body)

    assert response.status_code < 500, (
        f"{method} {path} ({auth_level}) 5xx'd on an anonymous call instead of "
        f"cleanly rejecting it: {response.status_code} {response.text}"
    )
    assert response.status_code != 200, (
        f"{method} {path} is declared auth_level={auth_level!r} but an anonymous "
        f"caller got 200 — the route is not actually enforcing auth."
    )
    if auth_level in ("user", "admin"):
        assert response.status_code == 401, (
            f"{method} {path} ({auth_level}): expected 401 for a missing credential, "
            f"got {response.status_code}"
        )
    else:  # capability — the handler reports an invalid/missing token itself
        assert response.status_code in (400, 401, 404), (
            f"{method} {path} (capability): expected a 400/401/404 invalid-token "
            f"response, got {response.status_code}"
        )


@pytest.mark.parametrize(
    "method,path,auth_level",
    [(m, p, a) for m, p, a in NON_PUBLIC_ROUTES if a in ("user", "admin")],
)
async def test_route_rejects_wrong_bearer_token(matrix_client, method, path, auth_level):
    """A well-formed but wrong bearer token must also be rejected with 401 —
    never a distinguishable error from the "no token" case, and never 200."""
    url = _concrete_path(path)
    json_body = None
    response = await matrix_client.request(
        method, url, json=json_body, headers={"Authorization": "Bearer definitely-wrong-token"}
    )
    assert response.status_code == 401, (
        f"{method} {path} ({auth_level}): expected 401 for a wrong bearer token, "
        f"got {response.status_code} {response.text}"
    )

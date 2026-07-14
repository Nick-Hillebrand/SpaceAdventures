"""Query-count / N+1 guard (Architecture/26-performance.md §1.2).

A `before_cursor_execute` listener counts SQL statements issued while a
request is served. Budget: <= 5 statements per request, and the count must
be *identical* whether the table holds 10 or 100 rows — that equality is
what actually catches an N+1 (a per-row lazy load scales with row count; a
batched/eager query does not).

Every new list endpoint registers itself in this module's table, the same
pattern as the security route matrix (`25-security-testing.md` §2.1).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

from app.models.launches import Launch
from app.models.subscription import Subscription
from app.models.user import User

MAX_STATEMENTS = 5


@contextmanager
def count_queries(db_engine):
    """Count SQL statements executed on *db_engine* for the life of the block."""
    count = 0

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal count
        count += 1

    sync_engine = db_engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _on_execute)
    try:
        yield lambda: count
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_execute)


async def _seed_launches(db_session, n: int, offset: int = 0) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(offset, offset + n):
        db_session.add(
            Launch(
                ll2_id=f"perf-launch-{i}",
                name=f"Launch {i}",
                net=now + timedelta(hours=i + 1),
                status_abbrev="Go",
                status_name="Go for Launch",
                agency_name="Perf Agency",
                rocket_name="Perf Rocket",
                pad_name="Pad 1",
                pad_location="Perf Site",
            )
        )
    await db_session.commit()


async def _seed_subscriptions(db_session, user_id: int, n: int, offset: int = 0) -> None:
    for i in range(offset, offset + n):
        db_session.add(
            Subscription(
                user_id=user_id,
                type="launch",
                ll2_id=f"perf-sub-{i}",
                notify_email=True,
                notify_sms=False,
            )
        )
    await db_session.commit()


async def _register_and_login(client) -> dict:
    await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Perf",
            "last_name": "Tester",
            "email": "perf-tester@example.com",
            "password": "securepassword",
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": "perf-tester@example.com", "password": "securepassword"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# GET /api/v1/launches/upcoming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row_count", [10, 100])
async def test_upcoming_launches_query_count_within_budget(client, db_engine, db_session, row_count):
    await _seed_launches(db_session, row_count)
    with count_queries(db_engine) as get_count:
        response = await client.get("/api/v1/launches/upcoming")
    assert response.status_code == 200
    assert len(response.json()["data"]) == row_count
    assert get_count() <= MAX_STATEMENTS


async def test_upcoming_launches_query_count_is_row_count_independent(client, db_engine, db_session):
    await _seed_launches(db_session, 10)
    with count_queries(db_engine) as get_count:
        r = await client.get("/api/v1/launches/upcoming")
    assert r.status_code == 200
    count_at_10 = get_count()

    await _seed_launches(db_session, 90, offset=10)  # bring the total to 100
    with count_queries(db_engine) as get_count:
        r = await client.get("/api/v1/launches/upcoming")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 100
    count_at_100 = get_count()

    assert count_at_10 == count_at_100, (
        f"query count grew with row count ({count_at_10} at 10 rows vs "
        f"{count_at_100} at 100 rows) — this is the N+1 signature"
    )
    assert count_at_100 <= MAX_STATEMENTS


# ---------------------------------------------------------------------------
# GET /sitemap.xml
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row_count", [10, 100])
async def test_sitemap_query_count_within_budget(client, db_engine, db_session, row_count):
    await _seed_launches(db_session, row_count)
    with count_queries(db_engine) as get_count:
        response = await client.get("/sitemap.xml")
    assert response.status_code == 200
    assert get_count() <= MAX_STATEMENTS


async def test_sitemap_query_count_is_row_count_independent(client, db_engine, db_session):
    await _seed_launches(db_session, 10)
    with count_queries(db_engine) as get_count:
        r = await client.get("/sitemap.xml")
    assert r.status_code == 200
    count_at_10 = get_count()

    await _seed_launches(db_session, 90, offset=10)  # bring the total to 100
    with count_queries(db_engine) as get_count:
        r = await client.get("/sitemap.xml")
    assert r.status_code == 200
    count_at_100 = get_count()

    assert count_at_10 == count_at_100, (
        f"query count grew with row count ({count_at_10} at 10 rows vs "
        f"{count_at_100} at 100 rows) — this is the N+1 signature"
    )
    assert count_at_100 <= MAX_STATEMENTS


# ---------------------------------------------------------------------------
# GET /api/v1/subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row_count", [10, 100])
async def test_list_subscriptions_query_count_within_budget(client, db_engine, db_session, row_count):
    headers = await _register_and_login(client)
    user_id = (
        await db_session.execute(select(User.id).where(User.email == "perf-tester@example.com"))
    ).scalar_one()
    await _seed_subscriptions(db_session, user_id, row_count)

    with count_queries(db_engine) as get_count:
        response = await client.get("/api/v1/subscriptions", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == row_count
    assert get_count() <= MAX_STATEMENTS


async def test_list_subscriptions_query_count_is_row_count_independent(client, db_engine, db_session):
    headers = await _register_and_login(client)
    user_id = (
        await db_session.execute(select(User.id).where(User.email == "perf-tester@example.com"))
    ).scalar_one()

    await _seed_subscriptions(db_session, user_id, 10)
    with count_queries(db_engine) as get_count:
        r = await client.get("/api/v1/subscriptions", headers=headers)
    assert r.status_code == 200
    count_at_10 = get_count()

    await _seed_subscriptions(db_session, user_id, 90, offset=10)
    with count_queries(db_engine) as get_count:
        r = await client.get("/api/v1/subscriptions", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 100
    count_at_100 = get_count()

    assert count_at_10 == count_at_100, (
        f"query count grew with row count ({count_at_10} at 10 rows vs "
        f"{count_at_100} at 100 rows) — this is the N+1 signature"
    )
    assert count_at_100 <= MAX_STATEMENTS

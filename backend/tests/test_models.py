from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Apod,
    IssPassSet,
    IssPositionBatch,
    IssTle,
    Launch,
    LoginAttempt,
    MarsPhoto,
    N2yoQuota,
    Neo,
    NotificationLog,
    Otp,
    PendingNotification,
    RefreshToken,
    SpaceWeatherEvent,
    Subscription,
    User,
)


async def test_apod_insert_and_query(db_session):
    row = Apod(
        date="2026-07-04",
        title="Great APOD",
        explanation="Nice",
        url="https://example.com/img.jpg",
        media_type="image",
    )
    db_session.add(row)
    await db_session.commit()

    result = await db_session.execute(select(Apod).where(Apod.date == "2026-07-04"))
    fetched = result.scalar_one()
    assert fetched.title == "Great APOD"
    assert fetched.hdurl is None
    assert fetched.fetched_at is not None


async def test_neo_insert(db_session):
    row = Neo(
        id="9999",
        name="Test NEO",
        close_approach_date="2026-07-04",
        is_potentially_hazardous=True,
    )
    db_session.add(row)
    await db_session.commit()

    fetched = (await db_session.execute(select(Neo))).scalar_one()
    assert fetched.is_potentially_hazardous is True


async def test_space_weather_event_check_constraint(db_session):
    good = SpaceWeatherEvent(
        id="SW-1",
        event_type="FLR",
        start_date="2026-07-04",
        raw_json="{}",
    )
    db_session.add(good)
    await db_session.commit()

    bad = SpaceWeatherEvent(
        id="SW-2",
        event_type="INVALID",
        start_date="2026-07-04",
        raw_json="{}",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_mars_photo_unique(db_session):
    photo1 = MarsPhoto(
        id=1,
        sol=1000,
        earth_date="2026-07-04",
        rover_name="curiosity",
        camera_name="MAST",
        img_src="https://example.com/mars1.jpg",
    )
    db_session.add(photo1)
    await db_session.commit()

    # A different id works
    photo2 = MarsPhoto(
        id=2,
        sol=1000,
        earth_date="2026-07-04",
        rover_name="curiosity",
        camera_name="MAST",
        img_src="https://example.com/mars2.jpg",
    )
    db_session.add(photo2)
    await db_session.commit()

    rows = (await db_session.execute(select(MarsPhoto))).scalars().all()
    assert len(rows) == 2


async def test_iss_tables_insert(db_session):
    batch = IssPositionBatch(id=1, positions="[]")
    tle = IssTle(id=1, tle_line0="ISS", tle_line1="1", tle_line2="2")
    passes = IssPassSet(
        pass_type="visual",
        observer_lat=48.0,
        observer_lng=11.0,
        observer_alt=0.0,
        passes_json="[]",
    )
    db_session.add_all([batch, tle, passes])
    await db_session.commit()

    assert (await db_session.execute(select(IssPositionBatch))).scalar_one().id == 1
    assert (await db_session.execute(select(IssTle))).scalar_one().tle_line0 == "ISS"
    assert (await db_session.execute(select(IssPassSet))).scalar_one().pass_type == "visual"


async def test_iss_pass_bad_type_rejected(db_session):
    bad = IssPassSet(
        pass_type="bogus",
        observer_lat=0.0,
        observer_lng=0.0,
        observer_alt=0.0,
        passes_json="[]",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_n2yo_quota_insert(db_session):
    q = N2yoQuota(id=1, window_start=datetime.utcnow(), used=0)
    db_session.add(q)
    await db_session.commit()
    row = (await db_session.execute(select(N2yoQuota))).scalar_one()
    assert row.used == 0


async def test_launch_insert(db_session):
    launch = Launch(
        ll2_id="ll2-uuid-1",
        name="Test launch",
        net=datetime(2026, 8, 1, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for launch",
        agency_name="SpaceX",
        agency_type="Commercial",
        rocket_name="Falcon 9",
        pad_name="LC-39A",
        pad_location="Kennedy Space Center",
        livestream_urls="[]",
    )
    db_session.add(launch)
    await db_session.commit()
    row = (await db_session.execute(select(Launch))).scalar_one()
    assert row.status_abbrev == "Go"


async def test_user_email_or_phone_check(db_session):
    good = User(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        password_hash="hash",
    )
    db_session.add(good)
    await db_session.commit()

    bad = User(first_name="Nobody", last_name="Nowhere", password_hash="x")
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_user_unique_email(db_session):
    a = User(
        first_name="A", last_name="B", email="dup@example.com", password_hash="h"
    )
    b = User(
        first_name="C", last_name="D", email="dup@example.com", password_hash="h"
    )
    db_session.add(a)
    await db_session.commit()
    db_session.add(b)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_otp_channel_check_and_fk(db_session):
    user = User(
        first_name="Grace", last_name="Hopper", email="grace@example.com", password_hash="h"
    )
    db_session.add(user)
    await db_session.commit()

    otp = Otp(
        user_id=user.id,
        channel="email",
        code_hash="abc",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db_session.add(otp)
    await db_session.commit()

    # bad channel
    bad = Otp(
        user_id=user.id,
        channel="invalid",
        code_hash="abc",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_fk_enforcement_on_otp(db_session):
    # FK to non-existent user should fail (P25)
    otp = Otp(
        user_id=99999,
        channel="email",
        code_hash="abc",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db_session.add(otp)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_refresh_token_insert(db_session):
    user = User(
        first_name="Ada",
        last_name="L",
        email="rt@example.com",
        password_hash="h",
    )
    db_session.add(user)
    await db_session.commit()

    token = RefreshToken(
        user_id=user.id,
        token_hash="hash",
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db_session.add(token)
    await db_session.commit()
    row = (await db_session.execute(select(RefreshToken))).scalar_one()
    assert row.revoked is False


async def test_login_attempt_insert(db_session):
    att = LoginAttempt(identifier="sha256-hash", ip_address="127.0.0.1")
    db_session.add(att)
    await db_session.commit()
    row = (await db_session.execute(select(LoginAttempt))).scalar_one()
    assert row.ip_address == "127.0.0.1"


async def test_subscription_check_and_unique(db_session):
    user = User(
        first_name="Sub", last_name="Test", email="sub@example.com", password_hash="h"
    )
    db_session.add(user)
    await db_session.commit()
    user_id = user.id

    sub = Subscription(
        id="sub-1",
        user_id=user_id,
        type="launch",
        ll2_id="ll2-1",
        notify_email=True,
    )
    db_session.add(sub)
    await db_session.commit()

    dup = Subscription(
        id="sub-2",
        user_id=user_id,
        type="launch",
        ll2_id="ll2-1",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    bad_type = Subscription(id="sub-3", user_id=user_id, type="invalid")
    db_session.add(bad_type)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_notification_log_check(db_session):
    user = User(first_name="N", last_name="L", email="nl@example.com", password_hash="h")
    db_session.add(user)
    await db_session.commit()
    user_id = user.id

    good = NotificationLog(
        user_id=user_id,
        ll2_id="ll2-x",
        change_type="NET_SLIP",
        channel="email",
        delivery_status="sent",
    )
    db_session.add(good)
    await db_session.commit()

    bad_chan = NotificationLog(
        user_id=user_id,
        ll2_id="ll2-x",
        change_type="NET_SLIP",
        channel="fax",
        delivery_status="sent",
    )
    db_session.add(bad_chan)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    bad_status = NotificationLog(
        user_id=user_id,
        ll2_id="ll2-x",
        change_type="NET_SLIP",
        channel="email",
        delivery_status="unknown",
    )
    db_session.add(bad_status)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_pending_notification_check(db_session):
    user = User(first_name="P", last_name="N", email="pn@example.com", password_hash="h")
    db_session.add(user)
    await db_session.commit()

    sub = Subscription(id="pn-sub-1", user_id=user.id, type="launch", ll2_id="ll2-x")
    db_session.add(sub)
    await db_session.commit()

    good = PendingNotification(
        subscription_id="pn-sub-1",
        ll2_id="ll2-x",
        change_type="NET_SLIP",
        old_value="2026-08-01",
        new_value="2026-08-05",
    )
    db_session.add(good)
    await db_session.commit()

    bad = PendingNotification(
        subscription_id="pn-sub-1",
        ll2_id="ll2-x",
        change_type="OTHER",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_cascade_delete_of_user_removes_related(db_session):
    user = User(first_name="Del", last_name="Ete", email="del@example.com", password_hash="h")
    db_session.add(user)
    await db_session.commit()

    otp = Otp(
        user_id=user.id,
        channel="email",
        code_hash="c",
        expires_at=datetime.utcnow() + timedelta(minutes=1),
    )
    rt = RefreshToken(
        user_id=user.id,
        token_hash="t",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    sub = Subscription(id="cascade-1", user_id=user.id, type="agency", agency_name="NASA")
    db_session.add_all([otp, rt, sub])
    await db_session.commit()

    await db_session.delete(user)
    await db_session.commit()

    assert (await db_session.execute(select(Otp))).scalars().all() == []
    assert (await db_session.execute(select(RefreshToken))).scalars().all() == []
    assert (await db_session.execute(select(Subscription))).scalars().all() == []

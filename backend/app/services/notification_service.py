"""Notification delivery service — drains the pending_notifications queue."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import unicodedata  # noqa: F401
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosmtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import jwt as _jwt
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import observability
from app.config import Settings
from app.models.iss_pass_alert import IssPassAlert
from app.models.launches import Launch
from app.models.notification_log import NotificationLog, PendingNotification
from app.models.push_subscription import PushSubscription
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)
# Structured events (`notification.sent|failed`) feed the delivery-rate KPI —
# distinct from `logger` above, which stays plain-text for local dev reading
# (17-worker-and-scheduling.md P3.6).
struct_logger = structlog.get_logger(__name__)

_BASE_URL = "https://spaceadventures.app"  # used in unsubscribe links

# B1.1 (19-notification-channels-v2.md) — drain batch size and retry backoff.
_DRAIN_BATCH_LIMIT = 100
# Indexed by (attempt_count - 1): 1 min, 5 min, 30 min, 2 h, 12 h.
_BACKOFF_SCHEDULE_SECONDS = [60, 300, 1800, 7200, 43200]
_MAX_ATTEMPTS = len(_BACKOFF_SCHEDULE_SECONDS)


# ---------------------------------------------------------------------------
# Sanitisation helpers
# ---------------------------------------------------------------------------


def sanitise(text: str) -> str:
    """Strip control characters that could enable header injection or rendering issues."""
    text = re.sub(r"[\r\n\0\x01-\x1f\x7f]", " ", text)
    return text.strip()


def ical_escape(value: str) -> str:
    """RFC 5545 §3.3.11 TEXT escaping for iCal property values.

    Backslash must be escaped first (to avoid double-escaping the escapes
    added for the other characters). Newlines are normalised to \\n — RFC
    5545 allows \\N or \\n; we always emit lowercase.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;")
    value = value.replace(",", "\\,")
    # Normalise all newline variants to the RFC 5545 \\n sequence.
    value = value.replace("\r\n", "\\n")
    value = value.replace("\r", "\\n")
    value = value.replace("\n", "\\n")
    return value


def scrub_error(exc: Exception) -> str:
    """Remove secrets from exception message before logging to DB."""
    detail = f"{type(exc).__name__}: {exc}"
    detail = re.sub(
        r"(?i)(password|token|auth|key|secret)[^\s]*",
        "[REDACTED]",
        detail,
    )
    return detail[:500]


# ---------------------------------------------------------------------------
# Unsubscribe token
# ---------------------------------------------------------------------------


def create_unsubscribe_token(
    subscription_id: str, user_id: int, settings: Settings
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "subscription_id": subscription_id,
        "user_id": user_id,
        "exp": now + timedelta(days=30),
    }
    return _jwt.encode(payload, settings.unsubscribe_secret_key, algorithm="HS256")


# ---------------------------------------------------------------------------
# Notification content
# ---------------------------------------------------------------------------


def _change_label(change_type: str, old_value: str | None, new_value: str | None) -> str:
    if change_type == "NET_SLIP":
        return f"NET slipped from {old_value} to {new_value}"
    if change_type == "STATUS_CHANGE":
        return f"Status changed from {old_value} to {new_value}"
    if change_type == "NEW_LAUNCH":
        return "New launch announced"
    return change_type


def _build_email_content(
    launch: Launch,
    change_type: str,
    old_value: str | None,
    new_value: str | None,
    unsubscribe_url: str,
) -> tuple[str, str, str]:
    """Return (subject, body_text, body_html)."""
    name = sanitise(launch.name)
    agency = sanitise(launch.agency_name)
    rocket = sanitise(launch.rocket_name)
    net_str = sanitise(launch.net.isoformat() + "Z")

    subject = f"Space Adventures — Launch Update: {name}"

    change_detail = _change_label(change_type, old_value, new_value)

    body_text = (
        f"Launch Update\n\n"
        f"Launch: {name}\n"
        f"Agency: {agency}\n"
        f"Rocket: {rocket}\n"
        f"NET: {net_str}\n\n"
        f"{change_detail}\n\n"
        f"Unsubscribe: {unsubscribe_url}\n"
    )

    # Launch fields come from the untrusted LL2 feed — escape for the HTML
    # context on top of the control-character strip in sanitise().
    body_html = f"""<html><body>
<h2>Launch Update</h2>
<p><strong>Launch:</strong> {html.escape(name)}</p>
<p><strong>Agency:</strong> {html.escape(agency)}</p>
<p><strong>Rocket:</strong> {html.escape(rocket)}</p>
<p><strong>NET:</strong> {html.escape(net_str)}</p>
<p>{html.escape(change_detail)}</p>
<hr>
<p style="font-size:small"><a href="{html.escape(unsubscribe_url, quote=True)}">Unsubscribe</a></p>
</body></html>"""

    return subject, body_text, body_html


def _build_sms_body(
    launch: Launch,
    change_type: str,
    old_value: str | None,
    new_value: str | None,
) -> str:
    name = sanitise(launch.name)
    net_str = sanitise(launch.net.isoformat() + "Z")
    change_label = _change_label(change_type, old_value, new_value)

    # Truncate name to 40 chars for SMS brevity
    name_40 = name[:40]
    body = f"SpaceAdv: {name_40} — {change_label}. NET: {net_str}. Reply STOP to opt out."

    # Hard truncate to 160 chars
    return body[:160]


def _build_push_payload(
    launch: Launch,
    change_type: str,
    old_value: str | None,
    new_value: str | None,
) -> str:
    """Return the JSON string sent as the Web Push `data` payload.

    Shape matches what `frontend/src/sw.ts` expects: `{title, body, url}` —
    the service worker calls `showNotification(title, {body, data: {url}})`.
    """
    name = sanitise(launch.name)
    title = f"Space Adventures — {name}"
    body = sanitise(_change_label(change_type, old_value, new_value))
    return json.dumps({"title": title, "body": body, "url": f"{_BASE_URL}/launches"})


# ---------------------------------------------------------------------------
# ISS pass alerts (20-location-and-sky-alerts.md L1) — a different content
# shape (IssPassAlert, not Launch) and a different channel policy (push
# preferred, email fallback, see _process_iss_pass_pending below).
# ---------------------------------------------------------------------------

_COMPASS_POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _compass_direction(azimuth_degrees: float) -> str:
    index = round((azimuth_degrees % 360) / 45) % 8
    return _COMPASS_POINTS[index]


def _resolve_location_tz(location_tz: str | None) -> ZoneInfo | timezone:
    """CLAUDE.md rule 4's one documented exception: notification templates
    format with the user's stored `location_tz`; `dateTime.ts` is frontend-only."""
    if not location_tz:
        return timezone.utc
    try:
        return ZoneInfo(location_tz)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def _build_iss_pass_content(alert: IssPassAlert, user: User) -> tuple[str, str]:
    """Return (title, body) shared by the push payload and the email fallback."""
    tz = _resolve_location_tz(user.location_tz)
    local_start = alert.start_utc.astimezone(tz)
    time_str = local_start.strftime("%H:%M")
    direction = _compass_direction(alert.start_az)
    duration_seconds = max(0, int((alert.end_utc - alert.start_utc).total_seconds()))
    minutes, seconds = divmod(duration_seconds, 60)
    duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    title = "ISS pass visible tonight"
    body = (
        f"Visible at {time_str} from the {direction}, reaching "
        f"{alert.max_el:.0f}° elevation, for about {duration_str}."
    )
    return title, body


# ---------------------------------------------------------------------------
# SMS monthly cap (B1.1 — financial self-protection against SMS-pump abuse)
# ---------------------------------------------------------------------------


def _current_month_str(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def _sms_cap_allows(user: User, settings: Settings) -> bool:
    """Roll the user's counter over to the current month if stale, then
    report whether they're still under `settings.sms_monthly_cap`. Does not
    itself increment the counter — call `_record_sms_sent` after a
    confirmed-successful send."""
    month = _current_month_str()
    if user.sms_month != month:
        user.sms_month = month
        user.sms_sent_month = 0
    return user.sms_sent_month < settings.sms_monthly_cap


def _record_sms_sent(user: User) -> None:
    user.sms_sent_month += 1


# ---------------------------------------------------------------------------
# Email and SMS sending
# ---------------------------------------------------------------------------


async def _send_email(
    settings: Settings,
    to: str,
    subject: str,
    body_text: str,
    body_html: str,
    list_unsubscribe: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["List-Unsubscribe"] = f"<{list_unsubscribe}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    send_kwargs: dict = dict(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
    )
    if settings.smtp_port == 465:
        send_kwargs["use_tls"] = True
    else:
        send_kwargs["start_tls"] = True

    await aiosmtplib.send(msg, **send_kwargs)


async def _send_sms(settings: Settings, to: str, body: str) -> None:
    from twilio.rest import Client  # noqa: PLC0415

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    await asyncio.to_thread(
        client.messages.create,
        to=to,
        from_=settings.twilio_from_number,
        body=body,
    )


class PushSubscriptionGone(Exception):
    """Raised when the push service reports the endpoint as revoked
    (HTTP 404/410) — the caller should delete the subscription row."""


def _webpush_sync(settings: Settings, subscription_info: dict, payload: str) -> None:
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
        )
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            raise PushSubscriptionGone(str(exc)) from exc
        raise


async def _send_push(settings: Settings, subscription: PushSubscription, payload: str) -> None:
    """pywebpush is sync (P32 rule, same as Twilio) — wrap in asyncio.to_thread."""
    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    await asyncio.to_thread(_webpush_sync, settings, subscription_info, payload)


# ---------------------------------------------------------------------------
# Main drain function
# ---------------------------------------------------------------------------


def _merge_error(existing: str | None, new: str) -> str:
    if existing is None:
        return new
    return (existing + " | " + new)[:500]


async def _send_push_to_user(
    session: AsyncSession,
    settings: Settings,
    user: User,
    payload: str,
) -> tuple[bool, str | None]:
    """Send to every device the user has registered. Returns (any_success,
    error_detail). A 404/410 from one device prunes that device silently and
    is never treated as a failure of the notification as a whole."""
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.user_id == user.id)
    )
    devices = list(result.scalars().all())

    any_success = False
    error_detail: str | None = None
    for device in devices:
        try:
            await _send_push(settings, device, payload)
            any_success = True
        except PushSubscriptionGone:
            await session.delete(device)
        except Exception as exc:  # noqa: BLE001
            error_detail = _merge_error(error_detail, scrub_error(exc))
    return any_success, error_detail


async def drain_queue(session: AsyncSession, settings: Settings) -> None:
    """Select a due batch from pending_notifications and attempt delivery.

    B1.1 (19-notification-channels-v2.md): `FOR UPDATE SKIP LOCKED` so a
    concurrent drain (a second worker, or an overlapping run of this same
    job) picks a different due batch instead of blocking on rows this call
    already holds — the whole batch commits as one transaction specifically
    so those locks stay held for the batch's full duration, not just the
    first row. Failed rows are rescheduled with exponential backoff instead
    of retried immediately; a row dead-letters after 5 attempts rather than
    being deleted, so it stays visible in the admin health payload.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(PendingNotification)
        .where(PendingNotification.dead.is_(False), PendingNotification.next_attempt_at <= now)
        .order_by(PendingNotification.created_at)
        .limit(_DRAIN_BATCH_LIMIT)
        .with_for_update(skip_locked=True)
        .options(
            selectinload(PendingNotification.subscription).selectinload(Subscription.user)
        )
    )
    result = await session.execute(stmt)
    pending_list = list(result.scalars().all())

    for pending in pending_list:
        try:
            await _process_pending(session, settings, pending)
        except Exception as exc:  # noqa: BLE001 — one row's unexpected failure
            # must not roll back every already-processed row in this batch
            # (the whole batch shares one transaction/commit, see docstring).
            logger.warning("Unexpected error processing pending %d: %s", pending.id, exc)
            _reschedule_or_dead_letter(pending, scrub_error(exc))

    await session.commit()


def _reschedule_or_dead_letter(pending: PendingNotification, error_detail: str) -> None:
    pending.attempt_count += 1
    if pending.attempt_count >= _MAX_ATTEMPTS:
        pending.dead = True
        observability.capture_message(
            f"notification dead-lettered after {pending.attempt_count} attempts: {error_detail}"
        )
    else:
        backoff = _BACKOFF_SCHEDULE_SECONDS[pending.attempt_count - 1]
        pending.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)


async def _send_email_and_log(
    session: AsyncSession,
    settings: Settings,
    pending: PendingNotification,
    user: User,
    subject: str,
    body_text: str,
    body_html: str,
    unsubscribe_url: str,
) -> None:
    """Send the update email and record it — shared by the normal email
    channel and the SMS-monthly-cap conversion path so the two never drift."""
    await _send_email(
        settings,
        to=user.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        list_unsubscribe=unsubscribe_url,
    )
    session.add(
        NotificationLog(
            user_id=user.id,
            ll2_id=pending.ll2_id,
            change_type=pending.change_type,
            channel="email",
            delivery_status="sent",
        )
    )


async def _process_iss_pass_pending(
    session: AsyncSession,
    settings: Settings,
    pending: PendingNotification,
    subscription: Subscription,
    user: User,
) -> None:
    """ISS_PASS notifications are push-preferred with an email fallback
    (20-location-and-sky-alerts.md L1) — unlike the launch path below, which
    sends every channel the user opted into independently, here email is
    only attempted if push didn't succeed."""
    alert: IssPassAlert | None = await session.get(IssPassAlert, pending.iss_pass_alert_id)
    if alert is None:
        # Precomputed row cleaned up (or never existed) since pass_notify
        # enqueued this — nothing left to send.
        await session.delete(pending)
        return

    title, body = _build_iss_pass_content(alert, user)

    success = False
    error_detail: str | None = None
    channel_attempted: str | None = None

    if subscription.notify_push:
        channel_attempted = "push"
        push_payload = json.dumps({"title": title, "body": body, "url": f"{_BASE_URL}/iss"})
        push_success, push_error = await _send_push_to_user(session, settings, user, push_payload)
        if push_success:
            session.add(
                NotificationLog(
                    user_id=user.id,
                    iss_pass_alert_id=alert.id,
                    change_type="ISS_PASS",
                    channel="push",
                    delivery_status="sent",
                )
            )
            success = True
            struct_logger.info("notification.sent", channel="push", iss_pass_alert_id=alert.id)
        elif push_error is not None:
            error_detail = _merge_error(error_detail, push_error)
            struct_logger.warning(
                "notification.failed", channel="push", reason=push_error, iss_pass_alert_id=alert.id
            )

    if not success and subscription.notify_email and user.email_verified and user.email:
        channel_attempted = "email"
        try:
            unsubscribe_token = create_unsubscribe_token(subscription.id, user.id, settings)
            unsubscribe_url = f"{_BASE_URL}/confirm-unsubscribe?token={unsubscribe_token}"
            subject = f"Space Adventures — {title}"
            body_text = f"{body}\n\nUnsubscribe: {unsubscribe_url}\n"
            body_html = (
                f"<html><body><h2>{html.escape(title)}</h2>"
                f"<p>{html.escape(body)}</p>"
                f'<hr><p style="font-size:small">'
                f'<a href="{html.escape(unsubscribe_url, quote=True)}">Unsubscribe</a></p>'
                f"</body></html>"
            )
            await _send_email(
                settings,
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                list_unsubscribe=unsubscribe_url,
            )
            session.add(
                NotificationLog(
                    user_id=user.id,
                    iss_pass_alert_id=alert.id,
                    change_type="ISS_PASS",
                    channel="email",
                    delivery_status="sent",
                )
            )
            success = True
            struct_logger.info("notification.sent", channel="email", iss_pass_alert_id=alert.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email delivery failed for pending %d: %s", pending.id, exc)
            error_detail = _merge_error(error_detail, scrub_error(exc))
            struct_logger.warning(
                "notification.failed", channel="email", reason=error_detail, iss_pass_alert_id=alert.id
            )

    any_channel_requested = subscription.notify_push or subscription.notify_email
    if success or not any_channel_requested:
        await session.delete(pending)
    elif error_detail is not None:
        was_dead = pending.attempt_count + 1 >= _MAX_ATTEMPTS
        _reschedule_or_dead_letter(pending, error_detail)
        if was_dead:
            session.add(
                NotificationLog(
                    user_id=user.id,
                    iss_pass_alert_id=alert.id,
                    change_type="ISS_PASS",
                    channel=channel_attempted or "push",
                    delivery_status="failed",
                    error_detail=error_detail,
                )
            )
    else:
        await session.delete(pending)


async def _process_pending(
    session: AsyncSession, settings: Settings, pending: PendingNotification
) -> None:
    subscription = pending.subscription
    user = subscription.user

    if pending.change_type == "ISS_PASS":
        await _process_iss_pass_pending(session, settings, pending, subscription, user)
        return

    launch: Launch | None = await session.get(Launch, pending.ll2_id)
    if launch is None:
        # Launch no longer in DB — drop the notification
        await session.delete(pending)
        return

    unsubscribe_token = create_unsubscribe_token(subscription.id, user.id, settings)
    unsubscribe_url = f"{_BASE_URL}/confirm-unsubscribe?token={unsubscribe_token}"

    subject, body_text, body_html = _build_email_content(
        launch,
        pending.change_type,
        pending.old_value,
        pending.new_value,
        unsubscribe_url,
    )
    sms_body = _build_sms_body(
        launch,
        pending.change_type,
        pending.old_value,
        pending.new_value,
    )

    success = False
    error_detail: str | None = None
    email_sent = False

    # --- Email ---
    if subscription.notify_email and user.email_verified and user.email:
        try:
            await _send_email_and_log(
                session, settings, pending, user, subject, body_text, body_html, unsubscribe_url
            )
            success = True
            email_sent = True
            struct_logger.info("notification.sent", channel="email", ll2_id=pending.ll2_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email delivery failed for pending %d: %s", pending.id, exc)
            error_detail = _merge_error(error_detail, scrub_error(exc))
            struct_logger.warning(
                "notification.failed", channel="email", reason=error_detail, ll2_id=pending.ll2_id
            )

    # --- SMS (per-user monthly cap; over cap converts to email) ---
    if subscription.notify_sms and user.phone_verified and user.phone:
        if _sms_cap_allows(user, settings):
            try:
                await _send_sms(settings, to=user.phone, body=sms_body)
                _record_sms_sent(user)
                session.add(
                    NotificationLog(
                        user_id=user.id,
                        ll2_id=pending.ll2_id,
                        change_type=pending.change_type,
                        channel="sms",
                        delivery_status="sent",
                    )
                )
                success = True
                struct_logger.info("notification.sent", channel="sms", ll2_id=pending.ll2_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("SMS delivery failed for pending %d: %s", pending.id, exc)
                error_detail = _merge_error(error_detail, scrub_error(exc))
                struct_logger.warning(
                    "notification.failed", channel="sms", reason=error_detail, ll2_id=pending.ll2_id
                )
        else:
            struct_logger.warning(
                "notification.sms_capped", user_id=user.id, ll2_id=pending.ll2_id
            )
            if not email_sent and user.email_verified and user.email:
                try:
                    await _send_email_and_log(
                        session, settings, pending, user, subject, body_text, body_html, unsubscribe_url
                    )
                    success = True
                    email_sent = True
                    struct_logger.info(
                        "notification.sent", channel="email", ll2_id=pending.ll2_id, sms_cap_conversion=True
                    )
                except Exception as exc:  # noqa: BLE001
                    error_detail = _merge_error(error_detail, scrub_error(exc))

    # --- Push ---
    if subscription.notify_push:
        payload = _build_push_payload(
            launch, pending.change_type, pending.old_value, pending.new_value
        )
        push_success, push_error = await _send_push_to_user(session, settings, user, payload)
        if push_success:
            session.add(
                NotificationLog(
                    user_id=user.id,
                    ll2_id=pending.ll2_id,
                    change_type=pending.change_type,
                    channel="push",
                    delivery_status="sent",
                )
            )
            success = True
            struct_logger.info("notification.sent", channel="push", ll2_id=pending.ll2_id)
        elif push_error is not None:
            error_detail = _merge_error(error_detail, push_error)
            struct_logger.warning(
                "notification.failed", channel="push", reason=push_error, ll2_id=pending.ll2_id
            )

    # --- Post-delivery logic ---
    any_channel_requested = (
        subscription.notify_email or subscription.notify_sms or subscription.notify_push
    )
    if success or not any_channel_requested:
        await session.delete(pending)
    elif error_detail is not None:
        was_dead = pending.attempt_count + 1 >= _MAX_ATTEMPTS
        _reschedule_or_dead_letter(pending, error_detail)
        if was_dead:
            session.add(
                NotificationLog(
                    user_id=user.id,
                    ll2_id=pending.ll2_id,
                    change_type=pending.change_type,
                    channel="email" if subscription.notify_email else "sms",
                    delivery_status="failed",
                    error_detail=error_detail,
                )
            )
    else:
        await session.delete(pending)

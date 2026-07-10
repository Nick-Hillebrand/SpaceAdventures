"""Notification delivery service — drains the pending_notifications queue."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import unicodedata  # noqa: F401
from datetime import datetime, timedelta, timezone

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jose import jwt as _jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models.launches import Launch
from app.models.notification_log import NotificationLog, PendingNotification
from app.models.subscription import Subscription

logger = logging.getLogger(__name__)

_BASE_URL = "https://spaceadventures.app"  # used in unsubscribe links


# ---------------------------------------------------------------------------
# Sanitisation helpers
# ---------------------------------------------------------------------------


def sanitise(text: str) -> str:
    """Strip control characters that could enable header injection or rendering issues."""
    text = re.sub(r"[\r\n\0\x01-\x1f\x7f]", " ", text)
    return text.strip()


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


# ---------------------------------------------------------------------------
# Main drain function
# ---------------------------------------------------------------------------


async def drain_queue(session: AsyncSession, settings: Settings) -> None:
    """Load all pending_notification rows and attempt delivery."""
    stmt = select(PendingNotification).options(
        selectinload(PendingNotification.subscription).selectinload(Subscription.user)
    )
    result = await session.execute(stmt)
    pending_list = list(result.scalars().all())

    for pending in pending_list:
        subscription = pending.subscription
        user = subscription.user

        # Fetch the launch data for content building
        launch: Launch | None = await session.get(Launch, pending.ll2_id)
        if launch is None:
            # Launch no longer in DB — drop the notification
            await session.delete(pending)
            await session.commit()
            continue

        unsubscribe_token = create_unsubscribe_token(subscription.id, user.id, settings)
        unsubscribe_url = (
            f"{_BASE_URL}/confirm-unsubscribe?token={unsubscribe_token}"
        )

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

        # --- Email ---
        if subscription.notify_email and user.email_verified and user.email:
            try:
                await _send_email(
                    settings,
                    to=user.email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    list_unsubscribe=unsubscribe_url,
                )
                log = NotificationLog(
                    user_id=user.id,
                    ll2_id=pending.ll2_id,
                    change_type=pending.change_type,
                    channel="email",
                    delivery_status="sent",
                )
                session.add(log)
                success = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Email delivery failed for pending %d: %s", pending.id, exc)
                error_detail = scrub_error(exc)

        # --- SMS ---
        if subscription.notify_sms and user.phone_verified and user.phone:
            try:
                await _send_sms(settings, to=user.phone, body=sms_body)
                log = NotificationLog(
                    user_id=user.id,
                    ll2_id=pending.ll2_id,
                    change_type=pending.change_type,
                    channel="sms",
                    delivery_status="sent",
                )
                session.add(log)
                success = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("SMS delivery failed for pending %d: %s", pending.id, exc)
                if error_detail is None:
                    error_detail = scrub_error(exc)
                else:
                    error_detail = (error_detail + " | " + scrub_error(exc))[:500]

        # --- Post-delivery logic ---
        if success or (not subscription.notify_email and not subscription.notify_sms):
            # Delivered successfully (or nothing to send) — remove the pending row
            await session.delete(pending)
        elif error_detail is not None:
            # At least one delivery was attempted and failed
            pending.attempt_count += 1
            if pending.attempt_count >= 3:
                # Max retries reached — log failure and delete
                fail_log = NotificationLog(
                    user_id=user.id,
                    ll2_id=pending.ll2_id,
                    change_type=pending.change_type,
                    channel="email" if subscription.notify_email else "sms",
                    delivery_status="failed",
                    error_detail=error_detail,
                )
                session.add(fail_log)
                await session.delete(pending)
        else:
            # No channels active — remove the pending row
            await session.delete(pending)

        await session.commit()

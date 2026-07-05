# Subscriptions & Notifications

---

## Subscription Types

| Type | Trigger |
|---|---|
| `launch` | Subscribed to a specific launch by `ll2_id` — notified on NET slip, status change |
| `agency` | Subscribed to all launches from an `agency_name` — notified on any change OR new launch |

---

## DB Tables

See `01-database-schemas.md` for: `subscriptions`, `pending_notifications`, `notification_log`.

Key points:
- `subscriptions.id` is a UUID (opaque) — prevents ID enumeration
- `notify_email` and `notify_sms` both default `FALSE` — must be explicitly set by the user in `<SubscribeModal>`
- `notification_log.error_detail` is scrubbed before storage: only exception type + message; all password/token/auth substrings replaced with `[REDACTED]`

---

## Change Detection (inside `launches_service.py`)

Before upserting each launch during sync:

| Condition | `change_type` inserted |
|---|---|
| `net` changed by > 5 minutes | `NET_SLIP` |
| `status_abbrev` changed | `STATUS_CHANGE` |
| Row is brand new | `NEW_LAUNCH` |

For each detected change, find all matching subscriptions (launch-type for that `ll2_id`, agency-type for that `agency_name`) and insert a row into `pending_notifications`.

---

## Notification Delivery (`notification_service.py`)

Called after every LL2 sync to drain `pending_notifications`:

1. Load pending rows with eager-loaded `subscription → user` (use `selectinload` — do NOT access relationships after session closes).
2. If `notify_email = TRUE` and `user.email_verified = TRUE` → send email via aiosmtplib.
3. If `notify_sms = TRUE` and `user.phone_verified = TRUE` → send SMS via Twilio.
4. Write to `notification_log` with delivery status.
5. Delete the `pending_notifications` row on success.
6. On failure: increment `attempt_count`. After 3 failures, delete the row and write a final ERROR log.

**Twilio is synchronous** — wrap every call in `asyncio.to_thread()`:
```python
await asyncio.to_thread(twilio_client.messages.create, to=phone, from_=TWILIO_FROM, body=body)
```

**aiosmtplib port selection:**
- Port 587 (STARTTLS): `aiosmtplib.SMTP(hostname=..., port=587, start_tls=True)`
- Port 465 (SMTPS): `aiosmtplib.SMTP(hostname=..., port=465, use_tls=True)`

---

## Notification Content

### Sanitisation (MANDATORY before embedding any LL2 data in a message)

All fields from LL2 are external untrusted data:
- Strip `\r`, `\n`, null bytes, and control characters from any field used in email subjects, SMS bodies, or email headers. Replace with space.
- HTML email body: use Jinja2 with auto-escaping enabled — **never use `| safe`**.
- SMS: validate final body is GSM-7; strip non-GSM characters.

### Email

Subject: `"Space Adventures — Launch Update: <sanitised launch name>"`

Body (plain text + HTML via Jinja2):
- Change type heading: "NET Slip" / "Status Change" / "New Launch from \<agency\>"
- Launch name, rocket, agency
- Old value → New value
- New NET: `"New NET: 2026-07-04 19:30 UTC"` — UTC only; email cannot know the recipient's timezone
- Unsubscribe link: `https://<APP_DOMAIN>/confirm-unsubscribe?token=<signed_token>` (frontend confirmation page — NOT a direct API call)
- Include `List-Unsubscribe` header (RFC 8058)

### SMS

Max 160 characters, strictly enforced:
```
SpaceAdv: <name ≤ 40 chars> — <change type>. NET: <YYYY-MM-DD HH:MMz>. Reply STOP to opt out.
```
Truncate name at 40 chars with `…`. Change type one of: "NET slip", "Status: Go", "Status: Hold", "New launch".

---

## Unsubscribe Flow

1. Email contains link: `https://<APP_DOMAIN>/confirm-unsubscribe?token=<signed_token>`
2. Frontend page (`/confirm-unsubscribe`) shows subscription details and a "Confirm Unsubscribe" button.
3. Button click fires: `POST /api/v1/subscriptions/unsubscribe` with `{ token }` in the request body.
4. Backend verifies token signature (using `UNSUBSCRIBE_SECRET_KEY` — separate from `JWT_SECRET_KEY`).
5. Token claims must contain both `subscription_id` AND `user_id`.
6. Backend queries: `WHERE id = subscription_id AND user_id = user_id`. If mismatch → 404.
7. Delete subscription.

**No GET variant exists** — a GET endpoint would allow browser prefetch (from `<img src=...>` in a malicious email) to silently delete subscriptions.

Unsubscribe token: signed JWT with `UNSUBSCRIBE_SECRET_KEY`, claims `{ subscription_id, user_id, exp: now+30d }`. Rotating `JWT_SECRET_KEY` does NOT invalidate unsubscribe tokens.

---

## API Routes

```
GET    /api/v1/subscriptions                 # current user's only (server filters by user_id)
POST   /api/v1/subscriptions                 # auth required; body: { type, ll2_id?, agency_name?, notify_email, notify_sms }
DELETE /api/v1/subscriptions/{id}            # 404 if not found OR belongs to another user (same response prevents enumeration)
POST   /api/v1/subscriptions/unsubscribe     # { token } in body; no auth required
```

---

## `/confirm-unsubscribe` Frontend Page

- Reads `?token=` from URL
- Calls backend to preview subscription details (optional — can decode token client-side for display)
- Shows: "You are about to unsubscribe from: \<launch name or agency\>"
- Single "Confirm Unsubscribe" button → fires `POST /api/v1/subscriptions/unsubscribe`
- On success: show confirmation message

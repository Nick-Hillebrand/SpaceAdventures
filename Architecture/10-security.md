# Security Requirements

Read this file before implementing auth, subscriptions, notifications, or any endpoint that handles user data.

---

## Authentication & Tokens

- **bcrypt** — cost factor ≥ 12. `CryptContext` defined once at module level; never inside a function.
- **JWT** — always pass `options={"verify_exp": True}` to `jwt.decode()`. Never rely on the default.
- **Access tokens** — 15-minute expiry; sent as `Authorization: Bearer` header; stored in `localStorage` (XSS risk documented in `src/lib/api.ts`; mitigated by CSP header).
- **Refresh tokens** — 30-day expiry; stored SHA-256 hashed in DB; rotated on every use (`SELECT … FOR UPDATE`); invalidated on logout.
- **JWT secret rotation** — `JWT_SECRET_KEY` can be rotated without breaking unsubscribe links (they use `UNSUBSCRIBE_SECRET_KEY`).

## OTPs

- 6-digit codes, bcrypt-hashed before storage.
- Expire after 10 minutes.
- Single-use: `used` column set atomically in same transaction.
- Brute-force: delete OTP row after 5 wrong attempts (`failed_attempts` column).
- Send-rate: max 5 sends per (user_id, channel) per hour.
- Re-verification: `email_verified = TRUE` makes the verify endpoint a no-op.

## Login Rate Limiting

- Max 5 failed attempts per `(SHA256(email_or_phone), ip_address)` per 15 minutes.
- 5th failure → 429 with `Retry-After` + security-alert email to the user.
- Always respond in constant time (prevents timing attacks distinguishing wrong email vs wrong password).
- Identifier hashed with SHA-256 before storage in `login_attempts` — never store plaintext.

## Account Enumeration Prevention

- Registration: duplicate email/phone returns the same generic error as invalid format: `{ "code": "REGISTRATION_FAILED", "message": "Please check your details and try again" }`. Never reveal whether an address is registered.
- Future password reset (v2): same success message whether the email exists or not.

## IDOR Prevention

- `DELETE /api/v1/subscriptions/{id}`: verify `subscriptions.user_id == current_user.id`. Return 404 for both "not found" and "belongs to another user" (identical response prevents enumeration).
- `GET /api/v1/subscriptions`: always filter by `user_id = current_user.id`.
- `GET /api/v1/auth/me`: never include `password_hash` or internal fields.
- Subscription IDs are UUIDs — not sequential integers.

## Unsubscribe Token

- Signed with `UNSUBSCRIBE_SECRET_KEY` (not `JWT_SECRET_KEY`).
- Claims: `{ subscription_id, user_id, exp: now+30d }`.
- Endpoint is `POST` (not GET) — prevents browser prefetch silently triggering unsubscribe.
- Backend verifies signature AND confirms `subscriptions.id = subscription_id AND subscriptions.user_id = user_id`. Mismatch → 404.

## Admin Endpoint

- `POST /api/v1/launches/sync` — requires `Authorization: Bearer <ADMIN_API_KEY>`.
- Never use a custom header (`X-Admin-Key`) — Caddy logs request headers by default and would expose the key.
- Caddy log config strips `Authorization` and any sensitive headers (see `12-deployment.md` Caddyfile).

## Notification Content Sanitisation

All LL2 data is external untrusted data. Before embedding in any notification:
- Strip `\r`, `\n`, null bytes, control characters from all fields. Replace with space.
- HTML email: Jinja2 auto-escaping — never `| safe`.
- SMS: validate GSM-7; name truncated to 40 chars.
- `error_detail` in `notification_log`: scrub before storage — keep only exception type + message; replace password/token/auth substrings with `[REDACTED]`.

## API Key Security

- NASA and N2YO keys stored in-process only. Never in the DB, never in any response.
- `GET /api/v1/settings` returns only `{ nasa_key_set: bool, n2yo_key_set: bool }`.
- Frontend never calls NASA or N2YO directly.

## Input Validation

- ISS pass parameters: `lat ∈ [-90, 90]`, `lng ∈ [-180, 180]`, `alt ∈ [0, 10000]` — return 400 if invalid.
- LL2 response size: reject if `Content-Length > 5 MB`; truncate individual fields (name ≤ 200, description ≤ 2000, others ≤ 500 chars); process max 100 launches per sync.

## Open Redirect Prevention

`?return=` parameter on login/register must be validated before redirect:
```ts
function safeReturnUrl(): string {
  const raw = decodeURIComponent(new URLSearchParams(location.search).get('return') ?? '/');
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('://')) return '/';
  return raw;
}
```

## Health Endpoint Tiers

- Unauthenticated: `{ "status": "ok" | "degraded" }` only — no internal details.
- Admin (`Authorization: Bearer <ADMIN_API_KEY>`): `{ db, smtp, n2yo_quota: { status } }` — status strings only, no raw numbers or error messages.

## Startup Validation

`config.py` must use a Pydantic `model_validator` to assert all required env vars are present and non-empty: `JWT_SECRET_KEY`, `UNSUBSCRIBE_SECRET_KEY`, `ADMIN_API_KEY`. App must refuse to start with a clear error message if any are missing.

## Source Maps

`vite.config.ts` must set `build.sourcemap: false` — source maps expose the full TypeScript source to anyone who can access `.map` files.

## General

- Passwords: bcrypt cost ≥ 12; never in logs, responses, or DB in plaintext.
- All images must have `alt` text (WCAG AA).
- HSTS: do NOT submit domain to the preload list during initial deployment. Wait one stable month. See `12-deployment.md`.

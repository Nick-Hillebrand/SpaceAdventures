# User Accounts & Authentication

---

## Registration Requirements

| Field | Required | Notes |
|---|---|---|
| First name | Yes | |
| Last name | Yes | |
| Email | One of email/phone | Used for login and email notifications |
| Phone | One of email/phone | E.164 format e.g. `+14155552671` |
| Password | Yes | Min 8 chars; bcrypt cost ≥ 12; never stored in plaintext |

At least one of email or phone is required — validated in the router, not just the DB.

---

## DB Tables

See `01-database-schemas.md` for: `users`, `otps`, `refresh_tokens`, `login_attempts`.

---

## Authentication Flow

- **JWT**: access token (15 min expiry) + refresh token (30 days, hashed in `refresh_tokens`)
- Access token: `Authorization: Bearer <token>` header
- Frontend stores both tokens in `localStorage` — XSS risk documented in `src/lib/api.ts` comments; mitigated by CSP header in Caddyfile (`script-src 'self'`)
- Log WARN if the same access token is seen from two different IPs within 15-minute validity window

### OTP Verification

After registration, send 6-digit OTP to each provided channel (email and/or phone). OTPs:
- Hashed with bcrypt before storage — never stored in plaintext
- Expire after 10 minutes
- Single-use: the `used` column is set atomically in the same transaction that reads it
- Brute-force protected: `failed_attempts` column; OTP row deleted after 5 wrong submissions
- Send-rate limited: max 5 OTP rows per `(user_id, channel)` per hour

`email_verified` and `phone_verified` set to TRUE only after successful OTP verification. Once TRUE, the verify endpoint is a no-op (not an error). Notifications only dispatched to verified channels.

### Login Rate Limiting

Before processing any login: count `login_attempts` rows for `(SHA256(identifier), ip_address)` in the last 15 minutes.
- ≥ 5 failures → 429 Too Many Requests with `Retry-After` header
- After successful login → delete all rows for that identifier
- Always respond in **constant time** — no timing leak between "wrong email" vs "wrong password"
- Send security-alert email to the user on the 5th failed attempt

### Refresh Token Rotation

On each `/auth/refresh`:
1. Acquire `SELECT … FOR UPDATE` (PostgreSQL) or asyncio.Lock (SQLite) on the refresh_tokens row.
2. Verify `revoked = FALSE`.
3. Issue a new access token + new refresh token.
4. Set old token `revoked = TRUE`.
5. Return both new tokens.

Concurrent refresh attempts with the same token: only one succeeds; the other gets 401.

---

## API Routes

```
POST /api/v1/auth/register
  Body: { first_name, last_name, email?, phone?, password }
  On duplicate email/phone: return same generic error as invalid format
  Error body: { "code": "REGISTRATION_FAILED", "message": "Please check your details and try again" }

POST /api/v1/auth/verify/email    { otp } → 200 (no-op if already verified)
POST /api/v1/auth/verify/phone    { otp } → 200 (no-op if already verified)
POST /api/v1/auth/verify/resend   { channel: "email"|"phone" } → 429 if > 5/hr

POST /api/v1/auth/login
  Body: { email_or_phone, password }
  Rate-limited: 5 failures per (identifier, IP) per 15 min
  Returns: { access_token, refresh_token }

POST /api/v1/auth/refresh         { refresh_token } → { access_token, refresh_token }
POST /api/v1/auth/logout          { refresh_token } → revokes token
GET  /api/v1/auth/me              → { id, first_name, last_name, email, phone, email_verified, phone_verified, created_at }
                                     NEVER include password_hash
```

---

## Frontend Pages

### `RegisterPage.tsx`

- Fields: first_name, last_name, email (optional), phone (optional), password, confirm_password
- Inline validation
- On success: show inline OTP input(s) for each provided channel
- Link to `/login`

### `LoginPage.tsx`

- Fields: email_or_phone, password
- On success: store tokens in localStorage; redirect to `safeReturnUrl()`:
```ts
function safeReturnUrl(): string {
  const raw = decodeURIComponent(new URLSearchParams(location.search).get('return') ?? '/');
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('://')) return '/';
  return raw;
}
```
- "Forgot password?" → placeholder for v2 (not implemented)

### `AccountPage.tsx`

Requires authentication (redirect to `/login` if not logged in). Two tabs:

**Profile tab:** first_name, last_name, email + verified badge, phone + verified badge, resend OTP buttons (only if not verified)

**My Subscriptions tab:**
- List of current user's subscriptions only (filtered server-side by `user_id = current_user.id`)
- Per-subscription: type, target (launch name or agency), notification channels, delete button
- Notification history: `sent_at`, `change_type`, `channel`, `delivery_status` — no body content
- "Subscribe to agency" input

### Navbar User Widget

Top-right corner of `Navbar.tsx`:
- Not logged in → "Log In" button → `/login`
- Logged in → initials avatar circle → dropdown: "My Account" → `/account`, "Log Out"

---

## Implementation Notes

- `CryptContext(schemes=["bcrypt"])` — define once at module level in `auth_service.py`, never inside a function
- `jwt.decode()` — always pass `options={"verify_exp": True}` explicitly
- OTP rate-limit check must be atomic — use asyncio.Lock (SQLite) or `SELECT … FOR UPDATE` (PostgreSQL) to prevent concurrent insert race

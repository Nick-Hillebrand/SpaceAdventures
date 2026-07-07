# Production Hardening (v2 Step P1)

Fixes that MUST land before any public user touches the app. Read together with
`10-security.md` (still fully in force) and `25-security-testing.md`.

---

## P1.1 — Settings endpoints: remove the unauthenticated key mutation

**Current defect:** `POST /api/v1/settings/nasa-api-key` and
`POST /api/v1/settings/n2yo-api-key` (`routers/settings.py`) are unauthenticated
and mutate server-wide keys on `app.state.settings`. Any anonymous visitor can
break every feature.

**Required change:**

- **Delete both POST endpoints and the frontend key-entry forms** on
  `SettingsPage.tsx`. Production runs exclusively on server-side keys from env
  vars. The "bring your own key" model is dead — do not admin-gate it, remove it.
- `GET /api/v1/settings` remains public and returns only
  `{ nasa_key_set: bool, n2yo_key_set: bool }` (unchanged).
- `SettingsPage.tsx` keeps the language switcher; replace the key forms with a
  read-only status row per key (`t("settings.keyConfigured")` /
  `t("settings.keyMissing")`).
- Remove the corresponding i18n keys only if unused elsewhere; add the new ones
  to all six locale files.

**Tests:** route tests assert POST to the removed paths returns 404 (routes gone,
not 401 — do not leave dead auth-gated routes); settings page test asserts no
input fields render.

## P1.2 — Secrets enforcement

- `docker-compose.prod.yml` sets `APP_REQUIRE_SECRETS=1` unconditionally.
- `config.py` model validator (already present) must additionally reject secrets
  shorter than 32 characters (`JWT_SECRET_KEY`, `UNSUBSCRIBE_SECRET_KEY`,
  `ADMIN_API_KEY`) — a short secret is as bad as a missing one.
- `.env.prod` stays gitignored. Verify `backend/.env` has never carried real
  secrets in git history (`git log --all -p -- backend/.env`); rotate anything
  that ever appeared.

## P1.3 — JWT library migration: python-jose → PyJWT

python-jose is in maintenance limbo. Replace with `PyJWT`:

- `pip install PyJWT` (pure-Python HS256 needs no extras); remove
  `python-jose[cryptography]` from `requirements.txt`.
- `auth_service.py`: `jwt.encode(payload, key, algorithm="HS256")` /
  `jwt.decode(token, key, algorithms=["HS256"], options={"require": ["exp", "sub"]})`.
  PyJWT verifies `exp` by default, but pass `options={"require": ["exp", "sub"]}`
  explicitly — a token *without* an `exp` claim must be rejected, not accepted.
- PyJWT raises `jwt.PyJWTError` subclasses (`ExpiredSignatureError`,
  `InvalidTokenError`) — update all `except JWTError` sites and the unsubscribe
  token verification.
- PyJWT requires `sub` to be a string — cast `user_id` with `str()` on encode,
  `int()` on decode.

**Tests:** all existing auth tests must pass unchanged in behavior; add: token
with no `exp` → 401; token signed with wrong key → 401; token with `alg: none`
→ 401 (PyJWT rejects it when `algorithms=["HS256"]` is pinned — assert anyway).

## P1.4 — Refresh token: localStorage → httpOnly cookie

Supersedes the localStorage line in `10-security.md`.

**Backend:**

- `POST /api/v1/auth/login`, `/verify-otp`, `/refresh` no longer return
  `refresh_token` in the JSON body. Instead set:
  `Set-Cookie: sa_refresh=<raw>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=1209600`.
  (`Secure` is skipped only when `settings.cookie_secure` is False — dev default
  True in prod, False in dev; add the setting.)
- `POST /api/v1/auth/refresh` and `/logout` read the token from the cookie —
  not the body. Keep accepting a body token for **one release** (mobile-browser
  sessions mid-migration), then remove.
- Logout clears the cookie (`Max-Age=0`).
- CSRF: `SameSite=Strict` + the cookie being scoped to `Path=/api/v1/auth` +
  refresh being a POST that returns a *new access token in the body* (useless to
  a cross-site attacker who cannot read responses) is sufficient. No CSRF token
  needed. Document this reasoning in a comment in the auth router.

**Frontend (`src/lib/api.ts`):**

- Access token: **memory only** (module-level variable). Remove all
  `localStorage` usage for both tokens, including the migration cleanup:
  on app boot, `localStorage.removeItem()` both legacy keys.
- On boot and on 401, attempt `POST /auth/refresh` (cookie rides along;
  `credentials: 'include'` on every request) to restore the session. If it
  fails, treat as logged out.
- CORS: this makes `allow_credentials=True` load-bearing. Origin list must be
  exact (`settings.frontend_origin`) — never `*`.

**Tests:** cookie is set with `HttpOnly`, `SameSite=Strict`, correct `Path`;
refresh with valid cookie succeeds; refresh with no cookie → 401; logout clears
cookie AND revokes the DB row; rotated cookie invalidates the previous value;
frontend test asserts nothing auth-related is written to `localStorage`.

## P1.5 — CORS tightening

In `main.py`, replace the wildcard configuration:

```python
allow_methods=["GET", "POST", "DELETE"],
allow_headers=["Authorization", "Content-Type"],
```

`allow_origins` stays `[settings.frontend_origin]` exactly.

## P1.6 — IP rate limiting

Account-level limits exist (`login_attempts`); add IP-level limits. Implement as
a small dependency (`app/rate_limit.py`) backed by a DB table (works across
multiple web workers — an in-process dict does NOT; see `17-worker-and-scheduling.md`):

```
rate_limit_events
  id          INTEGER PK AUTOINCREMENT
  bucket      TEXT      -- e.g. "auth", "otp_send"
  ip_hash     TEXT      -- SHA256(client_ip)  — never store raw IPs here
  created_at  DATETIME  server_default CURRENT_TIMESTAMP
  INDEX (bucket, ip_hash, created_at)
```

Limits (per IP, sliding window; count rows, insert, then check):

| Bucket | Routes | Limit |
|---|---|---|
| `auth` | `/auth/login`, `/auth/register`, `/auth/refresh` | 30 / 15 min |
| `otp_send` | `/auth/resend-otp`, registration OTP issue | 10 / hour |

- Exceeded → 429 with `Retry-After`. Response body identical for all callers
  (no enumeration).
- Client IP: read `request.client.host`; behind Caddy trust `X-Forwarded-For`
  **first value** only when `settings.trust_proxy_headers` is True (True in
  prod compose, False otherwise).
- The worker purges rows older than 24 h daily.
- **OTP SMS is a financial attack surface** (each SMS costs money) — the
  `otp_send` bucket is mandatory, not optional.

**Tests:** 31st auth call within window → 429; different IPs don't interfere;
window slides (row expiry frees the bucket); `X-Forwarded-For` honored only
when the setting is on.

## P1.7 — Translation service: replace deep-translator with DeepL

`translation_service.py` currently scrapes Google Translate (unofficial — TOS
violation for a commercial product; will be IP-blocked at volume).

- Add settings: `deepl_api_key: str = ""`, `deepl_base_url: str = "https://api-free.deepl.com"`.
- Reimplement `translate_fields()` against the DeepL REST API via the shared
  lifespan `httpx.AsyncClient` pattern (P6): **one request per target language**
  batching all field texts (DeepL accepts multiple `text` params, returns them
  in order) — not per-field requests.
- Language mapping: `ja → JA`, `ru → RU`, `de → DE`, `fr → FR`, `es → ES`.
- Missing key or any DeepL error → fall back to English text per field (same
  contract as today, preserved: callers never see an exception). Log a warning
  once per sync run, not per field.
- Remove `deep-translator` from `requirements.txt`.
- Public interface (`translate_fields(fields) -> {lang: {field: text}}`) is
  unchanged — `main.py` wiring and all call sites untouched.

**Tests (respx):** batching (one HTTP call per language, N texts in);
per-language failure falls back to English while other languages succeed;
missing key short-circuits without HTTP calls; quota-exceeded (456) response
falls back gracefully.

## P1.8 — Email deliverability

Notifications are the product; spam-foldered email is a broken product.

- Keep `aiosmtplib` — point it at a transactional provider's SMTP relay
  (Postmark or SES; config only, no code change).
- Add `List-Unsubscribe: <https://{domain}/confirm-unsubscribe?token=…>` and
  `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers to every
  notification email (`notification_service._send_email`). Gmail/Yahoo require
  this at volume. The one-click POST target is the existing unsubscribe
  endpoint — no new route.
- SPF, DKIM, DMARC records are a deploy-runbook item — add a checklist section
  to `12-deployment.md`'s runbook: provider DKIM keys installed, SPF includes
  provider, DMARC `p=quarantine` after one clean week.

**Tests:** email construction includes both headers with a valid signed token.

## P1.9 — Consent recording (CASL/PIPEDA/GDPR)

Alerting to email/SMS requires provable express consent (CASL applies — the
operator is Canadian).

- Add to `users`: `consent_notifications_at DATETIME NULLABLE`,
  `consent_source TEXT NULLABLE` (e.g. `"register-form-v1"`).
- Registration UI adds an unticked-by-default checkbox
  (`t("auth.consentNotifications")`); registering without it still creates the
  account but no notification subscriptions can be created until consent is
  given (subscription POST → 403 `{"code": "CONSENT_REQUIRED"}`; frontend
  surfaces a consent prompt in `<SubscribeModal>`).
- Consent timestamp + source recorded at grant; cleared on withdrawal
  (AccountPage toggle).

**Tests:** subscribe without consent → 403; grant → subscribe succeeds;
withdrawal keeps account intact but blocks new subscriptions.

## P1.10 — Account deletion & data export (GDPR/PIPEDA)

- `DELETE /api/v1/auth/me` (authenticated, requires current password in body):
  hard-deletes the user row; FK cascades remove otps, refresh_tokens,
  subscriptions, pending notifications; `notification_log` rows are anonymized
  (user_id set NULL, recipient scrubbed) not deleted — they are billing/audit
  records. Session cookie cleared.
- `GET /api/v1/auth/me/export` (authenticated): JSON of user profile,
  subscriptions, notification history. No password hash, no token hashes.
- Frontend: "Delete account" (destructive-confirm dialog, type-email-to-confirm)
  and "Download my data" on `AccountPage.tsx`.

**Tests:** deletion cascades verified table-by-table; export contains no
sensitive fields; wrong password → 403 and no deletion; deleted user's
refresh cookie can no longer mint access tokens.

---

## Definition of done for Step P1

All of the above implemented; every module ≥ 80 % branch coverage (per-module
gate — see `11-testing.md` amendment in CLAUDE.md); security tests from
`25-security-testing.md` §Auth pass; `pip-audit` and `npm audit` clean of
highs/criticals.

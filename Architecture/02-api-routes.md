# API Routes

All routes prefixed `/api/v1/`. Backend is FastAPI + Uvicorn.

---

## Standard Response Envelope

All data endpoints return:
```json
{ "data": "...", "cached": true, "fetched_at": "2026-07-04T19:30:00Z", "is_today": false }
```

- `cached: true` — served from DB, no upstream API call
- `stale: true` — served from DB because upstream API failed (degraded mode)
- `is_today: true` — data for today's UTC date; will be re-fetched on next request
- ISS responses additionally include `quota_exhausted: bool`
- `/api/v1/launches/upcoming` additionally includes `last_synced_at: ISO8601` (MAX fetched_at across returned rows)

---

## NASA Routes

```
GET  /api/v1/apod?date=YYYY-MM-DD
GET  /api/v1/apod/range?start=YYYY-MM-DD&end=YYYY-MM-DD

GET  /api/v1/neo/feed?start=YYYY-MM-DD&end=YYYY-MM-DD

GET  /api/v1/space-weather/flares?start=YYYY-MM-DD&end=YYYY-MM-DD
GET  /api/v1/space-weather/storms?start=YYYY-MM-DD&end=YYYY-MM-DD
GET  /api/v1/space-weather/cmes?start=YYYY-MM-DD&end=YYYY-MM-DD
GET  /api/v1/space-weather/sep?start=YYYY-MM-DD&end=YYYY-MM-DD
GET  /api/v1/space-weather/rbe?start=YYYY-MM-DD&end=YYYY-MM-DD

GET  /api/v1/mars/photos?rover=curiosity&sol=1000&camera=FHAZ&page=1
GET  /api/v1/mars/rovers
```

---

## ISS / N2YO Routes

```
GET  /api/v1/iss/positions
GET  /api/v1/iss/tle
GET  /api/v1/iss/passes/visual?lat=0&lng=0&alt=0   # lat∈[-90,90], lng∈[-180,180], alt∈[0,10000] — 400 if invalid
GET  /api/v1/iss/passes/radio?lat=0&lng=0&alt=0    # same validation
GET  /api/v1/iss/passes                             # auth required — passes over the caller's saved location; 400 LOCATION_REQUIRED if none set (20-location-and-sky-alerts.md L1). NOT Pro-gated — any authenticated user with a saved location can view passes; the "iss_pass" subscription type (below) is the Pro-gated alerting feature.
GET  /api/v1/iss/quota                              # { used, cap, window_start, resets_at }
```

---

## Location Routes (20-location-and-sky-alerts.md L1)

All three routes require auth — a saved location is PII and the geocode
search is proxied server-side so Open-Meteo's response never reaches the
browser unvalidated (`25-security-testing.md` §2.5).

```
GET    /api/v1/location/search?q=       # rate-limited 20/hr per user — { candidates: [{ name, country?, admin1?, latitude, longitude, timezone }] }
POST   /api/v1/location                 # { name, latitude, longitude, timezone } → { location_name, location_lat, location_lng, location_tz }
DELETE /api/v1/location                 # 204 — clears the four location_* columns
```

---

## Launch Routes

```
GET  /api/v1/launches/upcoming    # net > now-24h, ordered by net asc; includes last_synced_at
POST /api/v1/launches/sync        # admin only — Authorization: Bearer <ADMIN_API_KEY>
```

---

## Auth Routes

```
POST /api/v1/auth/register        # generic error on duplicate email/phone (prevents enumeration)
POST /api/v1/auth/verify/email    # { otp } — no-op if already verified
POST /api/v1/auth/verify/phone    # { otp } — no-op if already verified
POST /api/v1/auth/verify/resend   # { channel } — rate-limited 5/hr
POST /api/v1/auth/login           # rate-limited 5 failures per (identifier, IP) per 15 min
POST /api/v1/auth/refresh         # token rotation — returns new access + refresh token
POST /api/v1/auth/logout          # { refresh_token } — revokes token
GET  /api/v1/auth/me              # returns: id, first_name, last_name, email, phone, email_verified, phone_verified, created_at, consent_notifications_at, is_pro, location_name, location_lat, location_lng, location_tz — NEVER password_hash
POST /api/v1/admin/users/{user_id}/pro  # admin only — Authorization: Bearer <ADMIN_API_KEY> — { is_pro } → UserResponse; grant/revoke Pro (20-location-and-sky-alerts.md L1; no billing integration yet, operator action only)
```

---

## Subscription Routes

```
GET    /api/v1/subscriptions                  # current user's only (filtered server-side)
POST   /api/v1/subscriptions                  # auth required — type: "launch" | "agency" | "iss_pass". "iss_pass" (20-location-and-sky-alerts.md L1) takes no ll2_id/agency_name; 403 PRO_REQUIRED if !is_pro, 403 CONSENT_REQUIRED if consent not recorded, 409 ALREADY_SUBSCRIBED if one already exists for the user
DELETE /api/v1/subscriptions/{id}             # 404 if not found OR belongs to another user
POST   /api/v1/subscriptions/unsubscribe      # { token } in body — no auth required; token contains subscription_id + user_id
```

---

## Push Routes (19-notification-channels-v2.md B1.2)

```
GET    /api/v1/push/vapid-public-key          # public — { public_key } (empty string if VAPID not configured)
POST   /api/v1/push/subscribe                 # auth required — { endpoint, keys: { p256dh, auth } }; upserts on endpoint; 422 if endpoint isn't a safe https URL (SSRF guard, 25-security-testing.md §2.5)
DELETE /api/v1/push/subscribe                 # auth required — { endpoint }; 404 if not found or belongs to another user
```

---

## iCal Feed Routes (19-notification-channels-v2.md L2)

```
GET  /api/v1/ical/{token}.ics   # capability-URL auth — no Bearer header; Pro-gated; returns RFC 5545 ICS; 404 if token unknown (no oracle), 403 PRO_REQUIRED if user is not Pro; Cache-Control: private, max-age=900
POST /api/v1/ical/rotate        # auth required — rotates (or creates) users.ical_token; returns { ical_token }; old URL is immediately invalid
```

- `GET /api/v1/auth/me` now includes `ical_token: str | null` (null until first rotate).
- The token is a 32-byte URL-safe secret (`secrets.token_urlsafe(32)`); rotating invalidates the previous URL.
- SEQUENCE field = count of `launch_net_changes` rows with `change_type = 'net'` for that launch.
- `status_abbrev == "Gone"` launches get `STATUS:CANCELLED` in the VEVENT.

---

## Embeddable Widget Routes (23-seo-widgets-and-growth.md L3)

```
GET  /embed/next-launch?provider=&lang=
```

Returns a self-contained HTML page (≤ 30 KB, inline CSS + JS, no external
assets) showing a live countdown to the next upcoming launch.  Consumers
embed via `<iframe src="https://{domain}/embed/next-launch">`.

- `?provider=` — optional, case-insensitive substring match on `agency_name`
  (e.g. `?provider=SpaceX`); omit for the globally next launch.
- `?lang=` — optional, one of `en|de|es|fr|ja|ru`; widget UI labels are
  rendered in that language using inline translations (no locale-file fetch).
  Date/time is formatted client-side via `Intl.DateTimeFormat`.
- No cookies, no auth, no personal data.
- `Cache-Control: public, max-age=60`.
- `Content-Security-Policy: frame-ancestors *` — overrides the main-app
  `frame-ancestors 'self'` so third-party sites can embed the widget.
- The attribution backlink ("Powered by Space Adventures") is always present
  and cannot be removed via query params (white-label is a later B2B feature).

The SPA docs page at `/widgets` provides a copy-paste snippet generator
(iframe code, provider filter, language dropdown, live preview).

---

## Settings Routes

```
GET  /api/v1/settings                         # { nasa_key_set: bool, n2yo_key_set: bool } — never returns key values
POST /api/v1/settings/nasa-api-key            # { api_key } — stored in-process; never reflected back
POST /api/v1/settings/n2yo-api-key            # { api_key } — stored in-process; never reflected back
```

---

## Health Route

```
GET  /api/v1/health
```

Response (unauthenticated):
```json
{ "status": "ok" }
```

Response (with `Authorization: Bearer <ADMIN_API_KEY>`):
```json
{ "db": "ok", "smtp": "ok", "n2yo_quota": { "status": "ok" } }
```

Values are exactly: `"ok"`, `"error"`, `"unconfigured"`, `"warning"`, `"exhausted"` — never error messages or hostnames.

---

## Error Response Format

All errors:
```json
{ "error": { "code": "NASA_UNAVAILABLE", "message": "..." } }
```

| Scenario | HTTP | code |
|---|---|---|
| No internet | 502 | `NO_INTERNET` |
| NASA unreachable, internet up | 502 | `NASA_UNAVAILABLE` |
| NASA non-2xx response | 502 | `NASA_ERROR` |
| NASA key invalid | 502 | `NASA_AUTH_ERROR` |
| N2YO quota exhausted, no cache | 429 | `N2YO_QUOTA_EXHAUSTED` |
| Internal error | 500 | `INTERNAL_ERROR` |

Stale/quota responses return 200 with flags (`stale: true`, `quota_exhausted: true`) — not error codes.

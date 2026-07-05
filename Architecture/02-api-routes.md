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
GET  /api/v1/iss/quota                              # { used, cap, window_start, resets_at }
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
GET  /api/v1/auth/me              # returns: id, first_name, last_name, email, phone, email_verified, phone_verified, created_at — NEVER password_hash
```

---

## Subscription Routes

```
GET    /api/v1/subscriptions                  # current user's only (filtered server-side)
POST   /api/v1/subscriptions                  # auth required
DELETE /api/v1/subscriptions/{id}             # 404 if not found OR belongs to another user
POST   /api/v1/subscriptions/unsubscribe      # { token } in body — no auth required; token contains subscription_id + user_id
```

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

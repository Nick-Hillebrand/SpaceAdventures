# Space Adventures — Implementation Plan

This document is the authoritative specification for Claude Code to implement the **Space Adventures** web application. Follow it top-to-bottom; every section contains decisions already made — do not re-ask the user about them.

---

## 1. Project Overview

**Space Adventures** is a multilingual, data-rich web application that fetches, caches, and visualises data from the free NASA APIs and the N2YO satellite-tracking API. The frontend is React; the backend is Python (FastAPI). All external data is persisted in a local database to minimise API calls, stay well within rate limits, and allow multiple concurrent users to be served from the same cached records.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, React Router v6, i18next |
| UI Components | shadcn/ui + Tailwind CSS |
| State / Data fetching | TanStack Query (React Query) v5 |
| Backend | Python 3.12, FastAPI, Uvicorn |
| ORM | SQLAlchemy 2 (async) |
| Database | SQLite (dev) — swap to PostgreSQL via env var for prod |
| Migrations | Alembic |
| HTTP client (backend) | httpx (async) |
| Caching layer | Database-backed permanent cache (see §6) |
| 3D Globe | Globe.gl (MIT licence, Three.js-based) |
| Calendar | FullCalendar React v6 (`@fullcalendar/react` + `@fullcalendar/daygrid`). **Licence note**: both packages are MIT in v6 when used without premium plugins. Do not add any `@fullcalendar/premium` or scheduler plugins. Set `editable: false` to disable drag-and-drop (calendar is read-only). |
| Auth (backend) | python-jose[cryptography] (JWT) + passlib[bcrypt] (password hashing) |
| Email (backend) | aiosmtplib — async SMTP, works with any provider (Gmail, SendGrid, etc.) |
| SMS (backend) | Twilio Python SDK |
| Backend testing | pytest + pytest-asyncio + pytest-cov + httpx (AsyncClient for route tests) + respx (httpx mock) |
| Frontend testing | Vitest + React Testing Library + @testing-library/user-event + MSW v2 (mock service worker) |
| Coverage enforcement | pytest-cov (backend, branch mode); @vitest/coverage-v8 (frontend, branch mode) |
| Reverse proxy / TLS | Caddy v2 (automatic Let's Encrypt, HTTP→HTTPS redirect, static file serving) |
| Containerisation | Docker + docker-compose (dev) / docker-compose.prod.yml (production) |
| Linting / formatting | Ruff (Python), ESLint + Prettier (TS) |

---

## 3. Repository Structure

```
space-adventures/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, router registration
│   │   ├── config.py                # Settings via pydantic-settings (reads .env)
│   │   ├── database.py              # Async SQLAlchemy engine + session factory
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── apod.py
│   │   │   ├── neo.py
│   │   │   ├── space_weather.py
│   │   │   ├── mars.py
│   │   │   ├── iss.py
│   │   │   ├── launches.py
│   │   │   ├── user.py
│   │   │   ├── subscription.py
│   │   │   ├── notification_log.py
│   │   │   └── n2yo_quota.py        # Rolling transaction counter
│   │   ├── routers/                 # FastAPI routers (one per tab)
│   │   │   ├── apod.py
│   │   │   ├── neo.py
│   │   │   ├── space_weather.py
│   │   │   ├── mars.py
│   │   │   ├── iss.py
│   │   │   ├── launches.py
│   │   │   ├── auth.py
│   │   │   └── subscriptions.py
│   │   ├── services/                # Business logic: fetch → cache → return
│   │   │   ├── nasa_client.py       # Shared async httpx client + connectivity probe
│   │   │   ├── n2yo_client.py       # N2YO client with transaction-quota guard
│   │   │   ├── ll2_client.py        # Launch Library 2 client
│   │   │   ├── apod_service.py
│   │   │   ├── neo_service.py
│   │   │   ├── space_weather_service.py
│   │   │   ├── mars_service.py
│   │   │   ├── iss_service.py
│   │   │   ├── launches_service.py  # includes change-detection + notification dispatch
│   │   │   ├── auth_service.py
│   │   │   ├── subscription_service.py
│   │   │   └── notification_service.py  # email + SMS dispatch
│   │   └── schemas/                 # Pydantic response schemas (mirrors frontend types)
│   │       ├── apod.py
│   │       ├── neo.py
│   │       ├── space_weather.py
│   │       ├── mars.py
│   │       ├── iss.py
│   │       ├── launches.py
│   │       ├── auth.py
│   │       └── subscriptions.py
│   ├── alembic/
│   ├── tests/
│   │   ├── conftest.py              # shared fixtures: async DB session, test client, mock httpx
│   │   ├── test_apod.py
│   │   ├── test_neo.py
│   │   ├── test_space_weather.py
│   │   ├── test_mars.py
│   │   ├── test_iss.py
│   │   ├── test_n2yo_quota.py
│   │   ├── test_launches.py         # sync logic, change detection, upsert behaviour
│   │   ├── test_auth.py             # register, login, JWT, OTP, refresh, logout
│   │   ├── test_subscriptions.py    # CRUD, unsubscribe token
│   │   └── test_notifications.py    # pending queue drain, email/SMS dispatch, retry
│   ├── pytest.ini                   # testpaths, asyncio_mode = auto, branch coverage config
│   ├── requirements.txt
│   └── Dockerfile                   # production image (installs libffi-dev/gcc for bcrypt C ext)
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/                  # One file per page/tab
│   │   │   ├── ApodPage.tsx
│   │   │   ├── NeoPage.tsx
│   │   │   ├── SpaceWeatherPage.tsx
│   │   │   ├── MarsPage.tsx
│   │   │   ├── IssPage.tsx
│   │   │   ├── LaunchesPage.tsx
│   │   │   ├── LoginPage.tsx
│   │   │   ├── RegisterPage.tsx
│   │   │   ├── AccountPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   ├── components/              # Shared UI components
│   │   │   ├── Navbar.tsx           # includes user avatar / login button top-right
│   │   │   ├── LanguageSwitcher.tsx
│   │   │   ├── SubscribeModal.tsx
│   │   │   └── …
│   │   ├── hooks/                   # Custom React Query hooks
│   │   ├── lib/
│   │   │   ├── api.ts               # Axios/fetch wrapper pointing at backend
│   │   │   └── i18n.ts              # i18next initialisation
│   │   ├── locales/                 # Translation JSON files
│   │   │   ├── en.json
│   │   │   ├── de.json
│   │   │   ├── fr.json
│   │   │   ├── ja.json
│   │   │   ├── ru.json
│   │   │   └── es.json
│   │   └── types/                   # TypeScript interfaces mirroring backend schemas
│   ├── __tests__/               # mirrors src/routes and src/components structure
│   │   ├── routes/
│   │   │   ├── ApodPage.test.tsx
│   │   │   ├── NeoPage.test.tsx
│   │   │   ├── SpaceWeatherPage.test.tsx
│   │   │   ├── MarsPage.test.tsx
│   │   │   ├── IssPage.test.tsx
│   │   │   ├── LaunchesPage.test.tsx
│   │   │   ├── LoginPage.test.tsx
│   │   │   ├── RegisterPage.test.tsx
│   │   │   └── AccountPage.test.tsx
│   │   ├── components/
│   │   │   ├── ErrorBanner.test.tsx
│   │   │   ├── LaunchCard.test.tsx
│   │   │   ├── SubscribeModal.test.tsx
│   │   │   └── Navbar.test.tsx
│   │   └── hooks/               # test each custom TanStack Query hook in isolation
│   ├── src/msw/                 # MSW request handlers (mock backend API)
│   │   └── handlers.ts
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── Dockerfile              # production multi-stage build
│   └── Dockerfile.dev          # dev: runs Vite dev server
├── docker-compose.yml          # development only (HTTP, hot reload, bind mounts)
├── docker-compose.prod.yml     # production (HTTPS via Caddy, built assets)
├── Caddyfile                   # Caddy reverse-proxy + TLS config
├── .env.example                # development env template
├── .env.prod.example           # production env template
└── Architecture/
    ├── shell.md
    └── plan.md                      # ← this file
```

---

## 4. Navigation & Pages

The app uses a persistent top navigation bar with the following tabs:

| Route | Page | Description |
|---|---|---|
| `/` | Astronomy Picture of the Day | Hero image/video, title, explanation, date picker to browse past APODs |
| `/neo` | Near-Earth Objects | Filterable, sortable table of NEOs for a selectable date range; detail drawer with full NASA data |
| `/space-weather` | Space Weather | Solar flares, geomagnetic storms, radiation belt enhancements, solar energetic particles from NASA DONKI API |
| `/mars` | Mars Explorer | Rover selector (Curiosity, Opportunity, Spirit, Perseverance), sol/Earth-date picker, camera selector, photo gallery grid |
| `/iss` | ISS Tracker | Live 3D globe showing the ISS position, ground track, visibility footprint, altitude, velocity, and upcoming visual passes |
| `/launches` | Rocket Launches | Card grid of upcoming launches — company, rocket, countdown, mission summary, and livestream link per launch; toggle to calendar view |
| `/settings` | Settings | Language selector, API key entry |
| `/login` | Login | Not in nav; accessible via user icon in Navbar top-right |
| `/register` | Register | Not in nav; linked from Login page |
| `/account` | My Account | Not in nav; accessible via user icon dropdown when logged in — manage subscriptions |
| `/confirm-unsubscribe?token=…` | Confirm Unsubscribe | Not in nav; linked from notification emails — shows subscription details and requires explicit button click to POST unsubscribe |

---

## 5. NASA APIs Used

### 5.1 APOD — Astronomy Picture of the Day
- Endpoint: `GET https://api.nasa.gov/planetary/apod`
- Key params: `date`, `start_date`, `end_date`, `count`, `thumbs`
- Fields stored: `date`, `title`, `explanation`, `url`, `hdurl`, `media_type`, `copyright`, `thumbnail_url`

### 5.2 NeoWs — Near-Earth Object Web Service
- Endpoint: `GET https://api.nasa.gov/neo/rest/v1/feed`
- Key params: `start_date`, `end_date` (max 7-day window)
- Fields stored: `id`, `name`, `absolute_magnitude_h`, `estimated_diameter_min_km`, `estimated_diameter_max_km`, `is_potentially_hazardous`, `close_approach_date`, `relative_velocity_kph`, `miss_distance_km`, `orbiting_body`, `nasa_jpl_url`

### 5.3 DONKI — Space Weather
- Endpoints (all GET under `https://api.nasa.gov/DONKI/`):
  - `FLR` — Solar Flares
  - `GST` — Geomagnetic Storms
  - `RBE` — Radiation Belt Enhancements
  - `SEP` — Solar Energetic Particles
  - `CME` — Coronal Mass Ejections
- Key params: `startDate`, `endDate`
- Store full JSON response per event type per day; expose raw fields plus parsed summary.

### 5.4 Mars Rover Photos
- Endpoint: `GET https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/photos`
- Rovers: `curiosity`, `opportunity`, `spirit`, `perseverance`
- Key params: `sol` or `earth_date`, `camera`, `page`
- Fields stored: `id`, `sol`, `earth_date`, `rover_name`, `camera_name`, `img_src`

---

## 5b. N2YO API — ISS Tracking

**Base URL:** `https://api.n2yo.com/rest/v1/satellite/`
**Authentication:** `&apiKey=<N2YO_API_KEY>` query parameter on every request
**ISS NORAD ID:** `25544`
**Free tier limit:** 1 000 transactions / hour (see §6b for quota enforcement)

### Endpoints used

| Endpoint | Purpose | Cache behaviour |
|---|---|---|
| `positions/25544/{lat}/{lng}/{alt}/300` | Returns 300 seconds (5 min) of second-by-second ISS positions | Cached for 5 minutes; serves all users from the same batch |
| `tle/25544` | Raw Two-Line Element set — used to derive orbit path | Cached for 6 hours |
| `visualpasses/25544/{lat}/{lng}/{alt}/7/10` | Upcoming visible passes for a location over 7 days, min 10° elevation | Cached for 1 hour |
| `radiopasses/25544/{lat}/{lng}/{alt}/7/10` | Upcoming amateur-radio passes | Cached for 1 hour |

### Fields stored per position record
`timestamp`, `satlatitude`, `satlongitude`, `sataltitude` (km), `azimuth`, `elevation`, `ra`, `dec`, `eclipsed` (bool)

### Fields stored for TLE
`tle_line0` (name), `tle_line1`, `tle_line2`, `fetched_at`

### Fields stored per visual/radio pass
`startAz`, `startAzCompass`, `startEl`, `startUTC`, `maxAz`, `maxAzCompass`, `maxEl`, `maxUTC`, `endAz`, `endAzCompass`, `endEl`, `endUTC`, `mag` (visual only), `duration`

---

## 5c. Launch Library 2 — Upcoming Rocket Launches

**Base URL:** `https://ll.thespacedevs.com/2.3.0/`
**Authentication:** none required for the free tier; optionally supply a token via `Authorization: Token <LL2_API_KEY>` header to raise the rate limit
**Free tier rate limit:** 15 requests / hour (unauthenticated). Because launches are cached in the DB and refreshed on a schedule (see §6c), the app consumes at most 2–4 requests/hour regardless of user count.

### Endpoint used

```
GET https://ll.thespacedevs.com/2.3.0/launches/upcoming/?mode=detailed&limit=50&ordering=net
```

`mode=detailed` returns the full nested object including rocket configuration, agency, mission description, pad, and video URLs in a single request — no per-launch follow-up calls needed.

### Fields stored per launch (`launches` table)

| Column | Source field | Notes |
|---|---|---|
| `ll2_id` | `id` | UUID, primary key from LL2 |
| `name` | `name` | Full launch name |
| `net` | `net` | No Earlier Than datetime (UTC) |
| `status_abbrev` | `status.abbrev` | e.g. `Go`, `TBD`, `Hold` |
| `status_name` | `status.name` | Human-readable status |
| `agency_name` | `launch_service_provider.name` | e.g. "SpaceX" |
| `agency_type` | `launch_service_provider.type` | e.g. "Commercial" |
| `rocket_name` | `rocket.configuration.name` | e.g. "Falcon 9 Block 5" |
| `rocket_family` | `rocket.configuration.family` | e.g. "Falcon" |
| `mission_name` | `mission.name` | May be null |
| `mission_description` | `mission.description` | Short mission summary |
| `mission_type` | `mission.type` | e.g. "Communications" |
| `pad_name` | `pad.name` | Launch pad |
| `pad_location` | `pad.location.name` | e.g. "Cape Canaveral, FL" |
| `image_url` | `image.image_url` | Launch / rocket image for the card |
| `livestream_urls` | `vidURLs` | JSON array of `{ title, url, feature_image }` objects |
| `fetched_at` | — | When this row was last synced from LL2 |

### Caching rule (differs from other datasets)

Upcoming launch data is **not** permanently immutable — NET dates slip, launches get scrubbed, new launches are added. The cache rule is therefore time-bounded:

- Before parsing any LL2 response, check the `Content-Length` header. If > 5 MB, abort and log an error — do not parse. This prevents a malicious or malfunctioning API from writing unbounded data to the DB.
- After parsing, cap individual field lengths before storing: `mission_description` max 2 000 chars, `name` max 200 chars, any other text field max 500 chars. Truncate silently and log a warning if a field exceeds the limit.
- If the parsed response contains > 100 launches, log a warning and process only the first 100.
- Store all upcoming launches returned by LL2 in the DB on each sync.
- A background sync runs **every 30 minutes** via APScheduler (`AsyncIOScheduler`, one instance per process). This is the only place the LL2 API is called; no user request ever triggers a direct LL2 call. **Important**: Uvicorn must be run as a **single worker** (`--workers 1`) to prevent multiple APScheduler instances from firing concurrent syncs and generating duplicate notifications. If multi-worker deployment is needed in future, move the scheduler to a standalone process (e.g. a separate `scheduler` Docker service running the same Python app with `--scheduler-only` flag).
- On each sync: upsert all returned launches by `ll2_id`; mark any `ll2_id` no longer in the response as `status_abbrev = "Gone"` (do not delete — keeps historical cards available).
- Launches whose `net` is more than 24 hours in the past are excluded from the `/api/v1/launches/upcoming` response but kept in the DB.
- If the backend starts and the `launches` table is empty, run one immediate sync before responding to any frontend request.

### Change detection during sync

Before upserting each launch record, `launches_service.py` reads the existing DB row (if any) and compares:

| Field compared | Notification type |
|---|---|
| `net` changed by > 5 minutes | `NET_SLIP` |
| `status_abbrev` changed | `STATUS_CHANGE` |
| Row is brand new (no prior record) | `NEW_LAUNCH` |

For each detected change, insert a row into the `pending_notifications` table referencing affected subscriptions. After all upserts complete, `notification_service.py` is called to drain the queue (see §5e).

---

## 5d. User Accounts & Authentication

### Registration requirements

| Field | Required | Notes |
|---|---|---|
| First name | Yes | |
| Last name | Yes | |
| Email address | One of email or phone required | Used for email notifications and login |
| Phone number | One of email or phone required | E.164 format (e.g. `+14155552671`); used for SMS notifications and login |
| Password | Yes | Min 8 characters; stored as bcrypt hash — never in plaintext |

Both email and phone may be provided. At least one must be present; the backend returns a `422` validation error if neither is supplied.

### `users` DB table

```
id             INTEGER  PRIMARY KEY
first_name     TEXT     NOT NULL
last_name      TEXT     NOT NULL
email          TEXT     UNIQUE NULLABLE
phone          TEXT     UNIQUE NULLABLE
password_hash  TEXT     NOT NULL
email_verified BOOLEAN  DEFAULT FALSE
phone_verified BOOLEAN  DEFAULT FALSE
created_at     DATETIME DEFAULT NOW
```

### `otps` DB table

Stores pending OTPs for email and phone verification. Deleted on successful use.

```
id          INTEGER  PRIMARY KEY
user_id     INTEGER  FK → users.id  ON DELETE CASCADE
channel     TEXT     CHECK IN ('email', 'phone')
code_hash   TEXT     NOT NULL       — bcrypt hash of the 6-digit code (never store plaintext)
expires_at  DATETIME NOT NULL       — NOW + 10 minutes
used        BOOLEAN  DEFAULT FALSE  — atomically set TRUE in the same transaction that reads it; prevents replay via concurrent requests (use SELECT … FOR UPDATE on PostgreSQL, asyncio.Lock on SQLite)
failed_attempts INTEGER DEFAULT 0  — incremented on each wrong code submission; OTP row is deleted after 5 failed attempts
created_at  DATETIME DEFAULT NOW
```

Rate limiting — two distinct limits:
1. **Send rate**: at most 5 OTP rows per `(user_id, channel)` in any 1-hour window. `POST /api/v1/auth/verify/resend` returns `429` if this is exceeded.
2. **Attempt rate**: at most 5 wrong code submissions per OTP row (`failed_attempts >= 5`). On the 5th failure, the OTP row is deleted and the user must request a new code. This prevents brute-forcing a 6-digit code (1 000 000 possible values; 5 attempts allows only 0.0005% coverage). Old unused OTPs for the same `(user_id, channel)` are deleted when a new one is issued.

### `refresh_tokens` DB table

```
id           INTEGER  PRIMARY KEY
user_id      INTEGER  FK → users.id  ON DELETE CASCADE
token_hash   TEXT     NOT NULL       — SHA-256 hash of the raw token; raw token is never stored
expires_at   DATETIME NOT NULL       — NOW + 30 days
revoked      BOOLEAN  DEFAULT FALSE  — set TRUE on logout or rotation
created_at   DATETIME DEFAULT NOW
```

On each `/api/v1/auth/refresh` call: issue a new refresh token, mark the old one `revoked = TRUE`, and return the new token. This is **refresh token rotation** — a dropped connection on the response may leave the client with an invalid token; the client must store the new token immediately.

### `login_attempts` DB table

Tracks failed login attempts for rate limiting. Rows older than 1 hour are deleted on each successful login or on a scheduled cleanup.

```
id              INTEGER  PRIMARY KEY
identifier      TEXT     NOT NULL  — email or phone submitted (hashed with SHA-256 before storage; never store plaintext)
ip_address      TEXT     NOT NULL
failed_at       DATETIME DEFAULT NOW
```

Before processing any login attempt: count rows for `(identifier_hash, ip_address)` in the last 15 minutes. If ≥ 5, return `429 Too Many Requests` with `Retry-After` header (seconds until the window resets). After a successful login, delete all rows for that `identifier_hash`.

### Authentication flow

- **JWT-based**: access token (15-minute expiry) + refresh token (30-day expiry, stored hashed in `refresh_tokens`)
- Access token sent in `Authorization: Bearer <token>` header
- Frontend stores tokens in `localStorage`. **XSS risk is mitigated at the transport layer**: the Caddyfile sets `Content-Security-Policy: default-src 'self'; script-src 'self'` which prevents inline script injection and external script loading (see §17c). Document the residual risk (compromised npm dependency) in a code comment in `src/lib/api.ts`. Additionally, log an anomaly at WARN level if the same access token is seen from two different IP addresses within the 15-minute validity window.
- Verification: after registration, a 6-digit OTP is sent to the provided email and/or phone. Notifications are only dispatched to verified channels
- Login works with either email + password or phone + password
- **Today's rule**: once `email_verified = TRUE`, subsequent calls to the verify endpoint are a no-op (return 200 with a message, not an error). Resend OTP is only allowed if `email_verified = FALSE`

### Auth API routes

```
POST /api/v1/auth/register          # create account; sends OTP to email/phone — on duplicate email/phone return the same generic error as invalid format: { "code": "REGISTRATION_FAILED", "message": "Please check your details and try again" }; never reveal whether the address is already registered (prevents account enumeration)
POST /api/v1/auth/verify/email      # { otp } — mark email verified; no-op if already verified
POST /api/v1/auth/verify/phone      # { otp } — mark phone verified; no-op if already verified
POST /api/v1/auth/verify/resend     # { channel: "email"|"phone" } — send new OTP; rate-limited to 5/hr
POST /api/v1/auth/login             # { email_or_phone, password } → { access_token, refresh_token } — rate limited: max 5 failed attempts per (email_or_phone, IP) per 15 minutes; exponential backoff after 3rd failure; lock for 15 minutes after 5th failure; send security-alert email to the user on 5th failure; always respond in constant time (no timing leak distinguishing wrong email vs wrong password)
POST /api/v1/auth/refresh           # { refresh_token } → { access_token, refresh_token } (token rotated)
POST /api/v1/auth/logout            # { refresh_token } — revoke refresh token
GET  /api/v1/auth/me                # return current user profile (requires auth) — response fields: id, first_name, last_name, email, phone, email_verified, phone_verified, created_at — NEVER include password_hash or any internal field
```

---

## 5e. Subscriptions & Notification System

### Subscription types

| Type | Description |
|---|---|
| `launch` | Subscribe to a specific launch by `ll2_id`; notified on NET slip, status change |
| `agency` | Subscribe to all launches by a given `agency_name`; notified when any of their launches changes OR a new launch from that agency is added |

### `subscriptions` DB table

```
id              TEXT     PRIMARY KEY DEFAULT (lower(hex(randomblob(16))))  — UUID v4 (opaque, prevents enumeration)
user_id         INTEGER  FK → users.id  ON DELETE CASCADE
type            TEXT     CHECK IN ('launch', 'agency')
ll2_id          TEXT     NULLABLE — set when type = 'launch'
agency_name     TEXT     NULLABLE — set when type = 'agency'
notify_email    BOOLEAN  DEFAULT FALSE — only effective if user.email_verified; explicitly set by user in SubscribeModal
notify_sms      BOOLEAN  DEFAULT FALSE — only effective if user.phone_verified; explicitly set by user in SubscribeModal
created_at      DATETIME DEFAULT NOW
UNIQUE (user_id, type, ll2_id)        — prevent duplicate subscriptions
UNIQUE (user_id, type, agency_name)
```

### `pending_notifications` DB table

Populated by change detection during LL2 sync; drained by `notification_service.py` after each sync:

```
id                INTEGER  PRIMARY KEY
subscription_id   INTEGER  FK → subscriptions.id  ON DELETE CASCADE
ll2_id            TEXT     — the launch that changed
change_type       TEXT     CHECK IN ('NET_SLIP', 'STATUS_CHANGE', 'NEW_LAUNCH')
old_value         TEXT     — previous value (old NET or old status)
new_value         TEXT     — new value
attempt_count     INTEGER  DEFAULT 0  — incremented on each failed send attempt; row deleted after 3 failures
created_at        DATETIME DEFAULT NOW
```

### `notification_log` DB table

Permanent record of every notification sent:

```
id               INTEGER  PRIMARY KEY
user_id          INTEGER  FK → users.id
ll2_id           TEXT
change_type      TEXT
channel          TEXT     CHECK IN ('email', 'sms')
delivery_status  TEXT     CHECK IN ('sent', 'failed')
error_detail     TEXT     NULLABLE  — scrubbed before storage: only exception type + message stored, never the full traceback; redact any string matching password/token/auth patterns with [REDACTED]
sent_at          DATETIME
```

### Notification message content

**Sanitisation (applies to all notification content before use):**
All data sourced from LL2 (launch name, mission description, agency name, etc.) is **external untrusted data** and must be sanitised before embedding in notifications:
- Strip all control characters, newlines (`\r`, `\n`), and null bytes from any field used in a notification subject, SMS body, or email header. Replace with a space.
- In HTML email bodies, escape `<`, `>`, `&`, `"`, `'` — use Jinja2's auto-escaping (never `| safe`).
- For SMS, validate the final body is valid GSM-7; strip any characters that would cause multi-part SMS splitting beyond what the template already accounts for.

**Email subject:** `"Space Adventures — Launch Update: <launch name>"`  ← launch name sanitised (no newlines)
- Change type heading: "NET Slip", "Status Change", or "New Launch from <agency>"
- Launch name, rocket, agency
- Old value → New value
- New NET date/time in UTC only (e.g. `"New NET: 2026-07-04 19:30 UTC"`) — email cannot know the recipient's browser timezone
- Unsubscribe link in email: `https://<APP_DOMAIN>/confirm-unsubscribe?token=<signed_token>` — this is a **frontend page**, not a direct API call. The page displays the subscription details and a single "Confirm Unsubscribe" button. Clicking that button fires `POST /api/v1/subscriptions/unsubscribe` with `{ token }` in the request body. This prevents silent unsubscription via browser prefetching (e.g., an `<img src=...>` tag in a malicious email triggering a GET).

**SMS body** (max 160 characters, strictly enforced):
`"SpaceAdv: <name truncated to 40 chars> — <change type>. NET: <YYYY-MM-DD HH:MMz>. Reply STOP to opt out."`
Launch names longer than 40 characters are truncated with `…`. The change type is one of: "NET slip", "Status: Go", "Status: Hold", "New launch". The template as constructed fits within 160 characters at all times.

### Notification delivery

`notification_service.py` iterates pending_notifications after each LL2 sync:

1. For each pending row, load the subscription → user.
2. If `notify_email` is true and `user.email_verified` → send email via SMTP (aiosmtplib).
3. If `notify_sms` is true and `user.phone_verified` → send SMS via Twilio.
4. Write to `notification_log` with delivery status.
5. Delete the `pending_notifications` row.

All sends are async and non-blocking. A failed send increments `attempt_count` on the `pending_notifications` row and logs the error at ERROR level. The row is retried on the next sync cycle. After 3 failed attempts, the row is deleted and a final ERROR log entry is written — the user is not retried further. If SMTP is misconfigured, this will surface as repeated ERROR logs per sync cycle and is detectable via the `/api/v1/health` endpoint (see §14).

### Subscription API routes

```
GET    /api/v1/subscriptions                               # list MY subscriptions (filter by current_user.id — never returns other users' data)
POST   /api/v1/subscriptions                               # create subscription (auth required)
DELETE /api/v1/subscriptions/{id}                          # remove MY subscription — verify subscriptions.user_id == current_user.id; return 404 if not found OR belongs to another user (same response prevents ID enumeration)
POST   /api/v1/subscriptions/unsubscribe                    # { token } in body — token must contain subscription_id AND user_id; DB must confirm both match; no auth required; no GET variant (prevents browser prefetch triggering silent unsubscribe)
```

---

## 6. Backend: Caching Strategy

All NASA data is stored **permanently** in the database. There are no TTLs and no automatic expiry. Once a record for a given set of parameters exists in the DB it is never re-fetched from NASA.

Every service follows this lookup pattern before hitting the NASA API:

1. Build a canonical cache key from the request parameters (e.g. `apod:2024-07-04`, `neo:2024-07-01:2024-07-07`, `mars:curiosity:1000:FHAZ:1`).
2. Query the DB for a row matching that key.
3. If a row exists → return it immediately (`cached: true`) — **no NASA call, ever again for those params**.
4. If missing → call NASA API → insert new DB row → return data (`cached: false`).

### Today's data exception

Historical dates are immutable and stored once-and-forever. However, data for **today's date** may be incomplete at query time (NASA updates intraday). The rule:

- If the requested date/range **ends before today** → treat as historical, permanent cache applies.
- If the requested date/range **includes today** → always re-fetch from NASA and upsert the DB row so the record is kept current until midnight **UTC**, at which point it becomes historical and is never re-fetched again. "Today" is always evaluated in UTC on the backend regardless of the user's local timezone.

This means the only live NASA calls the app ever makes are for the current day's data.

The `nasa_client.py` module keeps a single `httpx.AsyncClient` with a `NASA_API_KEY` header injected from config.

---

## 6b. N2YO Transaction Quota

N2YO's free tier allows **1 000 transactions per rolling hour**. The backend must enforce a configurable hard cap (default **900**) to ensure the app never crosses into the paid tier. The cap is read from the `N2YO_QUOTA_CAP` env var at startup; the quota model never hard-codes 900 in logic — it reads `settings.n2yo_quota_cap` everywhere. The default of 900 provides a 100-transaction safety buffer.

### Quota model (`n2yo_quota` table)

```
id           INTEGER PRIMARY KEY
window_start DATETIME   -- start of the current 1-hour window (UTC)
used         INTEGER    -- transactions consumed in this window
```

There is always exactly one row. On each N2YO call attempt:

1. Read the row.
2. If `NOW() - window_start >= 1 hour` → reset: set `window_start = NOW()`, `used = 0`.
3. If `used >= settings.n2yo_quota_cap` → **do not call N2YO**. Return cached data if available with `quota_exhausted: true` in the response envelope. If no cache exists, return a `429` with error code `N2YO_QUOTA_EXHAUSTED`.
4. Otherwise → call N2YO, increment `used`, upsert cache, return data.

The increment in step 4 must happen **inside a DB transaction** using `SELECT … FOR UPDATE` (SQLAlchemy: `.with_for_update()`) so concurrent requests cannot double-count. For SQLite (dev), a Python-side `asyncio.Lock` singleton is used instead since SQLite does not support row-level locks; PostgreSQL (prod) uses `SELECT … FOR UPDATE` natively. The lock must be released in a `finally` block to prevent deadlocks on exception.

### ISS position cache & polling

The positions endpoint returns **300 seconds of data in a single transaction**. The cache row stores the full 300-entry array with its `fetched_at` timestamp. All users are served from this batch until it is more than 5 minutes old, at which point the next request triggers one fresh N2YO call (1 transaction) to refresh it. This means the ISS position data costs at most **12 transactions/hour** regardless of user count.

Expected maximum hourly transaction budget:

| Endpoint | Max calls/hour | Transactions |
|---|---|---|
| Positions (5-min cache, shared) | 12 | 12 |
| TLE (6-hour cache) | 1 | 1 |
| Visual passes (1-hour cache, per unique lat/lng) | ~10 | ~10 |
| Radio passes (1-hour cache, per unique lat/lng) | ~10 | ~10 |
| **Total worst case** | | **~33** |

The 900-transaction cap is therefore a very conservative safety ceiling.

---

## 7. Backend: API Routes

All routes are prefixed `/api/v1/`.

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
GET  /api/v1/mars/rovers          # list available rovers + status

GET  /api/v1/iss/positions        # current batch of 300-second positions (shared cache)
GET  /api/v1/iss/tle              # current TLE data
GET  /api/v1/iss/passes/visual?lat=0&lng=0&alt=0    # upcoming visible passes; lat∈[-90,90], lng∈[-180,180], alt∈[0,10000] — validated, 400 if invalid
GET  /api/v1/iss/passes/radio?lat=0&lng=0&alt=0     # upcoming radio passes; same validation as above
GET  /api/v1/iss/quota            # returns { used, cap, window_start, resets_at }

GET  /api/v1/launches/upcoming    # all launches with net > now - 24h, ordered by net asc
POST /api/v1/launches/sync        # manually trigger a LL2 sync — requires Authorization: Bearer <ADMIN_API_KEY> (never a custom header that Caddy logs)

POST /api/v1/settings/nasa-api-key   # { api_key } — update NASA key in-process; never reflected back in any response
POST /api/v1/settings/n2yo-api-key   # { api_key } — update N2YO key in-process; never reflected back in any response
GET  /api/v1/settings                # returns ONLY { nasa_key_set: bool, n2yo_key_set: bool } — never the key values themselves
```

All responses return `{ data: …, cached: bool, fetched_at: ISO8601, is_today: bool }` envelope.
ISS responses additionally include `{ quota_exhausted: bool }` when the N2YO cap has been reached.
The `/api/v1/launches/upcoming` response additionally includes a top-level `last_synced_at: ISO8601` field — the `MAX(fetched_at)` across all returned launches — so the frontend has a single unambiguous timestamp to display in the "Last updated X minutes ago" line.

---

## 7b. ISS Tracker Page — Frontend Specification

### Globe

Use **Globe.gl** (MIT licence, npm package `globe.gl`, wraps Three.js). Render a full-viewport interactive 3D Earth with:

- Satellite texture map on the globe surface (day texture; switch to night texture when the globe is in shadow if feasible)
- **ISS position marker** — animated pulsing dot at the current lat/lon, updated every second by interpolating within the cached 300-entry position array (no additional API calls needed between refreshes)
- **Ground track** — polyline showing the ISS's upcoming orbital path derived from the TLE data, rendered on the globe surface
- **Visibility footprint** — semi-transparent circle on the globe surface representing the area from which the ISS is currently visible (radius derived from `sataltitude`)
- **Observer marker** — pin at the user's location (requested via the browser Geolocation API; fallback to 0°N 0°E if denied)

The globe must be responsive and support mouse/touch rotation and zoom.

### Data panels (alongside or overlaid on the globe)

Display the following in a side panel or HUD overlay:

| Field | Source | Unit |
|---|---|---|
| Current latitude | positions cache | °N/S |
| Current longitude | positions cache | °E/W |
| Altitude | positions cache | km |
| Velocity | derived from consecutive positions | km/h |
| Azimuth | positions cache | ° |
| Elevation (from observer) | positions cache | ° |
| Eclipsed (in Earth's shadow) | positions cache | Yes / No |
| Next visible pass (from observer) | visual passes cache | `formatDateTime(startUTC)` in user's local timezone + duration |
| Next radio pass (from observer) | radio passes cache | `formatDateTime(startUTC)` in user's local timezone + duration |
| N2YO quota remaining | `/api/v1/iss/quota` | X / 900 used |

### Quota warning in the UI

If the `/api/v1/iss/quota` response shows `quota_exhausted: true` OR `used >= 800`:
- Show a persistent warning badge on the ISS tab icon and at the top of the ISS page.
- Text: `"iss.quotaWarning"` (e.g. "N2YO API quota nearly exhausted — showing cached data")
- If fully exhausted: `"iss.quotaExhausted"` (e.g. "N2YO API quota exhausted for this hour. Live updates paused. Resets at {{time}}.") — `{{time}}` is rendered via `formatTime(resets_at)` in the user's local timezone

### Client-side position interpolation

The frontend holds the 300-entry position array in memory alongside the server-side `fetched_at` timestamp returned by the backend. The `setInterval` runs every 1 000 ms and computes the target offset as `Date.now() - fetched_at_ms`, then picks the entry at that index (clamped to `[0, 299]`).

**Batch exhaustion fallback**: When the computed offset exceeds 270 seconds (30 s before the 300 s batch ends), TanStack Query's query for `/api/v1/iss/positions` is manually invalidated via `queryClient.invalidateQueries()` inside a `useEffect` with a `setTimeout`. This triggers a background refetch. If the refetch has not completed by the time the batch is fully exhausted (offset ≥ 300), the ISS marker **freezes at the last known position** and a subtle "Updating…" indicator appears on the data panel. It resumes moving as soon as the new batch arrives. No extrapolation is attempted — frozen is preferable to an incorrectly extrapolated position.

The `staleTime` for the ISS positions query is set to `270_000` ms (4.5 minutes) — overriding the global `Infinity` — so TanStack Query's built-in background refetch fires automatically when the data goes stale at 4.5 minutes.

---

## 7c. Rocket Launches Page — Frontend Specification

### Layout & View Toggle

The page has two views toggled by a button pair in the top-right corner of the page header:

- **Grid view** (default) — responsive card grid; cards sorted by `net` ascending
- **Calendar view** — FullCalendar month grid; each launch is an event dot/chip on its NET date

The active view is persisted to `localStorage` under `space-adventures-launches-view`. Both views read from the same `/api/v1/launches/upcoming` query result — no additional API calls on toggle.

### Launch card (`LaunchCard.tsx`)

Each card displays:

| Element | Data | Notes |
|---|---|---|
| Hero image | `image_url` | Full-width top of card; fallback to a generic rocket silhouette SVG if null |
| Launch name | `name` | Card heading |
| Agency / company | `agency_name` + `agency_type` | e.g. "SpaceX · Commercial" |
| Rocket | `rocket_name` | e.g. "Falcon 9 Block 5" |
| Launch pad | `pad_name`, `pad_location` | e.g. "LC-39A · Kennedy Space Center, FL" |
| Mission type badge | `mission_type` | Coloured badge pill, e.g. "Communications" |
| Mission description | `mission_description` | Max 3 lines, truncated with expand toggle |
| Status badge | `status_name` | Colour-coded: green = Go, amber = TBD, red = Hold/Failure |
| Countdown | derived from `net` | Live countdown `T−Xd Xh Xm Xs`; switches to `T+…` after launch; updates every second client-side |
| Livestream button | first entry in `livestream_urls` | Button labelled `"launches.watchLive"`; opens URL in new tab; hidden if `livestream_urls` is empty |
| More streams | remaining `livestream_urls` entries | If >1 URL, a small dropdown lists them by title |
| Subscribe button | — | Bell icon button; opens `<SubscribeModal>` (see below) |

### Countdown behaviour

- Countdown runs entirely client-side using `setInterval` at 1 Hz — no polling needed.
- When `net` is in the future: shows `T− Xd Xh Xm Xs` in large monospace text.
- When `net` has passed (launch occurred): shows `T+ Xh Xm Xs` with the status badge updated to the value from the last sync.
- When `status_abbrev` is `"TBD"` or `"Hold"`: show `"NET: <date>"` instead of a live countdown, since the time is not reliable enough to count down to. The date is rendered via `formatDateTime(net)` in the user's local timezone.

### Calendar view

When in calendar view, render a FullCalendar `dayGridMonth` calendar. Each launch appears as a colour-coded event chip (green = Go, amber = TBD, red = Hold) labelled `<agency_name>: <rocket_name>`. Clicking an event chip opens the same launch card as a slide-over drawer, identical in content to the grid-view card.

### Filtering

A filter bar above the grid/calendar provides:
- **Status filter** — toggles: All / Go / TBD / Hold
- **Agency search** — text input that filters cards by `agency_name`

Filtering applies to both views and is done client-side on the already-fetched data; no extra API calls.

### Subscribe modal (`<SubscribeModal>`)

Triggered by the bell icon on any launch card or by an "Subscribe to agency" button in the agency filter area.

**If the user is not logged in:**
- Modal shows a prompt: `"launches.subscribeLoginRequired"` ("Create a free account or log in to receive launch notifications")
- Two buttons: "Log In" → `/login?return=/launches` and "Register" → `/register?return=/launches`

**If the user is logged in:**
The modal shows:

1. **Subscribe to this launch** — checkbox for the specific launch; shows launch name and NET
2. **Subscribe to all [agency\_name] launches** — checkbox for agency-wide subscription
3. **Notify me via** — checkboxes: Email (shown only if email verified), SMS (shown only if phone verified); if neither channel is verified, show inline prompt to verify from the Account page
4. Confirm button → calls `POST /api/v1/subscriptions`

A filled bell icon on the card indicates the user is already subscribed to that launch. Clicking it opens the modal pre-populated with the existing subscription (allowing unsubscribe).

### Data freshness indicator

A small line at the top of the page shows when the launch list was last synced from LL2, e.g. "Last updated 4 minutes ago". This is rendered via `formatRelative(last_synced_at)`. TanStack Query refetches `/api/v1/launches/upcoming` every **5 minutes** in the background so the page stays current without a manual reload.

---

## 7d. Auth Pages & Account Management

### Navbar user widget

The top-right corner of `Navbar.tsx` always shows one of:
- **Not logged in**: "Log In" text button → `/login`
- **Logged in**: user avatar (initials circle) + dropdown with "My Account" → `/account` and "Log Out"

### `/register` — Registration page

A single-page form with:
- First name, Last name (both required)
- Email address (optional but one of email/phone required)
- Phone number in E.164 format (optional but one of email/phone required)
- Password + confirm password (min 8 characters)
- Inline validation; submit sends `POST /api/v1/auth/register`
- On success: show OTP verification step inline (separate input fields for email OTP and phone OTP if both were provided); verified channels unlock notification delivery
- Link to `/login` for existing users

### `/login` — Login page

- Email or phone + password
- On success: store JWT tokens in localStorage; redirect to `?return=` param or `/`
- "Forgot password?" link — out of scope for v1; show a placeholder message. **Note for v2**: password reset must use a time-limited (30 min), single-use signed token sent to the verified email or phone. The endpoint must return the same success message regardless of whether the address exists in the DB (prevents user enumeration). Never send a temporary password in plaintext.

### `/account` — Account page

Accessible only when logged in (redirect to `/login` if not). Tabs:

**Profile tab:**
- Display first name, last name, email, phone
- Verification status badges next to email/phone ("Verified" / "Unverified — resend OTP")

**My Subscriptions tab:**
- List of **only the current user's** active subscriptions (filtered by `user_id = current_user.id` on the backend — never expose another user's subscription data)
- Per-subscription: notification channels (Email / SMS badges), delete button
- Notification history: shows `sent_at`, `change_type`, `channel`, `delivery_status` only — never includes notification body content or any data referencing other users
- "Subscribe to an agency" input — type an agency name → creates an agency-type subscription immediately

---

## 8. Frontend: Internationalisation (i18n)

- Library: **i18next** + **react-i18next** + **i18next-browser-languagedetector**
- Supported locales: `en`, `de`, `fr`, `ja`, `ru`, `es`
- Language stored in `localStorage` under key `space-adventures-lang`
- All user-visible strings (labels, headings, placeholders, error messages, units) must use translation keys — **no hardcoded English strings in JSX**
- NASA API data (titles, explanations) is displayed as-is (not translated); a note in the UI clarifies that scientific content is in English
- The `SettingsPage` exposes a dropdown/flag-based language switcher; a compact version also appears in the Navbar

Translation file structure (example keys for `en.json`):
```json
{
  "nav": { "apod": "Picture of the Day", "neo": "Near-Earth Objects", "spaceWeather": "Space Weather", "mars": "Mars Explorer", "iss": "ISS Tracker", "launches": "Rocket Launches", "settings": "Settings", "login": "Log In", "myAccount": "My Account", "logout": "Log Out" },
  "apod": { "title": "Astronomy Picture of the Day", "explanation": "Explanation", "copyright": "Copyright", "noImage": "No image available" },
  "neo": { "title": "Near-Earth Objects", "hazardous": "Potentially Hazardous", "diameter": "Diameter", "velocity": "Velocity", "missDistance": "Miss Distance" },
  "spaceWeather": { "title": "Space Weather", "flares": "Solar Flares", "storms": "Geomagnetic Storms", "cme": "Coronal Mass Ejections" },
  "mars": { "title": "Mars Explorer", "selectRover": "Select Rover", "selectCamera": "Select Camera", "sol": "Sol" },
  "auth": {
    "registerTitle": "Create Account", "loginTitle": "Log In",
    "firstName": "First Name", "lastName": "Last Name",
    "email": "Email Address", "phone": "Phone Number", "password": "Password", "confirmPassword": "Confirm Password",
    "emailOrPhone": "At least one of email or phone is required",
    "passwordMismatch": "Passwords do not match",
    "passwordTooShort": "Password must be at least 8 characters",
    "alreadyHaveAccount": "Already have an account?", "noAccount": "Don't have an account?",
    "verifyEmail": "Enter the code sent to your email",
    "verifyPhone": "Enter the code sent to your phone",
    "resendOtp": "Resend code", "verifyButton": "Verify",
    "logoutSuccess": "You have been logged out"
  },
  "account": {
    "title": "My Account", "profileTab": "Profile", "subscriptionsTab": "My Subscriptions",
    "verified": "Verified", "unverified": "Unverified", "resendOtp": "Resend verification code",
    "noSubscriptions": "You have no active subscriptions",
    "subscribeToAgency": "Subscribe to an agency",
    "agencyPlaceholder": "Agency name (e.g. SpaceX)",
    "channelEmail": "Email", "channelSms": "SMS",
    "unsubscribe": "Unsubscribe",
    "verifyChannelPrompt": "Verify your {{channel}} to enable notifications"
  },
  "subscriptions": {
    "subscribeButton": "Subscribe",
    "subscribedButton": "Subscribed",
    "modalTitle": "Get Launch Notifications",
    "thisLaunch": "Subscribe to this launch",
    "allFromAgency": "Subscribe to all {{agency}} launches",
    "notifyVia": "Notify me via",
    "loginRequired": "Create a free account or log in to receive launch notifications",
    "success": "Subscription saved",
    "removed": "Subscription removed"
  },
  "launches": {
    "title": "Rocket Launches",
    "lastUpdated": "Last updated {{time}}",
    "filterAll": "All", "filterGo": "Go", "filterTbd": "TBD", "filterHold": "Hold",
    "searchAgency": "Search by agency…",
    "watchLive": "Watch Live",
    "moreStreams": "More streams",
    "noStreams": "No livestream available",
    "countdownPrefix": "T−", "countdownPostfix": "T+",
    "netLabel": "NET",
    "statusGo": "Go for Launch", "statusTbd": "To Be Determined", "statusHold": "Launch Hold",
    "noLaunches": "No upcoming launches found"
  },
  "iss": {
    "title": "ISS Tracker",
    "latitude": "Latitude", "longitude": "Longitude", "altitude": "Altitude", "velocity": "Velocity",
    "azimuth": "Azimuth", "elevation": "Elevation", "eclipsed": "In Shadow",
    "yes": "Yes", "no": "No",
    "nextVisiblePass": "Next Visible Pass", "nextRadioPass": "Next Radio Pass",
    "duration": "Duration", "maxElevation": "Max Elevation",
    "quotaUsed": "API Quota: {{used}} / {{cap}} used this hour",
    "quotaWarning": "N2YO API quota nearly exhausted — showing cached data",
    "quotaExhausted": "N2YO API quota exhausted for this hour. Live updates paused. Resets at {{time}}.",
    "locationDenied": "Location access denied — using default observer position (0°N 0°E)"
  },
  "settings": { "title": "Settings", "language": "Language", "apiKey": "NASA API Key", "n2yoApiKey": "N2YO API Key" },
  "common": { "loading": "Loading…", "error": "Something went wrong", "retry": "Retry", "noData": "No data available", "cached": "Served from cache", "fetchedAt": "Fetched at" }
}
```

---

## 9. Frontend: State Management

- **Server state**: TanStack Query — one custom hook per API route (e.g. `useApod(date)`, `useNeoFeed(start, end)`)
- **UI state**: React `useState` / `useReducer` local to each page component
- **Persisted user preferences**: `localStorage` via a small `useLocalStorage` hook (language, API key, rover selection)
- No global state library (Redux / Zustand) needed for this scope

---

## 9b. Timezone Policy

### Rule

> **The backend stores and computes everything in UTC. The frontend displays every date and time in the user's local timezone as reported by the browser. No timezone is ever stored in the database or sent by the backend.**

"Today" for cache-expiry decisions is UTC midnight on the backend. What the user *sees* is always their local time — a user in Montreal (EDT, UTC−4) sees launch times 4 hours behind UTC; a user in Frankfurt (CET, UTC+1) sees them 1 hour ahead.

### Implementation

Create a shared utility module `src/lib/dateTime.ts` with the following functions used by every component that displays a date or time:

```ts
const userLocale = navigator.language          // e.g. "en-CA", "de-DE"
const userTz     = Intl.DateTimeFormat().resolvedOptions().timeZone  // e.g. "America/Toronto", "Europe/Berlin"

// Full date + time: "Jul 4, 2026, 3:45 PM EDT"
export function formatDateTime(isoUtc: string): string {
  return new Intl.DateTimeFormat(userLocale, {
    dateStyle: 'medium', timeStyle: 'short', timeZone: userTz
  }).format(new Date(isoUtc))
}

// Date only: "Jul 4, 2026"
export function formatDate(isoUtc: string): string {
  return new Intl.DateTimeFormat(userLocale, {
    dateStyle: 'medium', timeZone: userTz
  }).format(new Date(isoUtc))
}

// Time only: "3:45 PM EDT"
export function formatTime(isoUtc: string): string {
  return new Intl.DateTimeFormat(userLocale, {
    timeStyle: 'short', timeZone: userTz
  }).format(new Date(isoUtc))
}

// Relative: "4 minutes ago", "in 2 hours"
export function formatRelative(isoUtc: string): string {
  const diffMs = new Date(isoUtc).getTime() - Date.now()
  const rtf = new Intl.RelativeTimeFormat(userLocale, { numeric: 'auto' })
  // pick the largest unit that makes sense
  const abs = Math.abs(diffMs)
  if (abs < 60_000)  return rtf.format(Math.round(diffMs / 1_000), 'second')
  if (abs < 3_600_000) return rtf.format(Math.round(diffMs / 60_000), 'minute')
  if (abs < 86_400_000) return rtf.format(Math.round(diffMs / 3_600_000), 'hour')
  return rtf.format(Math.round(diffMs / 86_400_000), 'day')
}
```

These functions are the **only** way dates and times are rendered in JSX. No component may call `new Date().toLocaleString()`, `toLocaleDateString()`, or hardcode timezone strings directly.

### Where each function is used

| Feature | Data field | Function |
|---|---|---|
| APOD | `date` (YYYY-MM-DD) | `formatDate` |
| NEO close approach | `close_approach_date` | `formatDate` |
| Space weather events | event `beginTime`, `peakTime`, `endTime` | `formatDateTime` |
| Mars photos | `earth_date` | `formatDate` |
| ISS visual/radio passes | `startUTC`, `maxUTC`, `endUTC` | `formatDateTime` |
| ISS quota reset | quota `resets_at` | `formatTime` |
| Launch NET (TBD/Hold display) | `net` | `formatDateTime` |
| Launch countdown transition label | `net` | `formatDateTime` (shown when `T+` kicks in) |
| "Last updated X ago" (launches) | `last_synced_at` | `formatRelative` |
| "Fetched at" / "Cached from" badges | `fetched_at` | `formatDateTime` |
| Notification log in Account page | `sent_at` | `formatDateTime` |

### Email notifications

The backend cannot know the user's browser timezone. Email notifications show times in **UTC only**, clearly labelled:
- `"New NET: 2026-07-04 19:30 UTC"`

The email body does **not** attempt to convert to local time. Users who want local time can check the app (which uses their browser timezone).

### Date picker inputs (APOD, NEO, Mars)

Date pickers send a plain `YYYY-MM-DD` string to the backend — no timezone conversion needed for date-only inputs. The backend treats these as calendar dates, not moments in time.

---

## 10. Settings Page — Behaviour

| Setting | Type | Storage | Effect |
|---|---|---|---|
| Language | Select (6 options with flag icons) | `localStorage` | Calls `i18n.changeLanguage()` immediately |
| NASA API Key | Text input (password field) | `localStorage` | Forwarded to backend; used for all NASA calls |
| N2YO API Key | Text input (password field) | `localStorage` | Forwarded to backend via `POST /api/v1/settings/n2yo-api-key`; used for all ISS calls |

There are no TTL or cache-expiry settings — the cache is permanent by design. The Settings page does **not** expose any cache-management controls.

NASA and N2YO API keys entered in Settings are forwarded to the backend via `POST /api/v1/settings/nasa-api-key` and `POST /api/v1/settings/n2yo-api-key` respectively. The backend stores them in-process (not on disk) and uses them for all subsequent requests during that server session.

---

## 11. Docker Compose — Development Only

`docker-compose.yml` is for **local development only**. It runs HTTP (no TLS), uses `--reload` for hot-reload, and mounts source code directories only — never the full `/app` directory (which would overwrite pip-installed packages; see P30).

```yaml
# docker-compose.yml  ─── DEVELOPMENT ONLY ───
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports: ["8000:8000"]          # exposed directly for dev tools / browser access
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
    env_file: .env
    volumes:
      - ./backend/app:/app/app    # source code only — does NOT overwrite site-packages
      - sa_db_data:/app/data

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev  # runs Vite dev server with HMR
    ports: ["5173:5173"]
    environment:
      - VITE_API_BASE_URL=http://localhost:8000
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
    depends_on: [backend]

volumes:
  sa_db_data:
```

`frontend/Dockerfile.dev`:
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json .
RUN npm ci
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

**Localhost is exempt from the HTTPS requirement**, so the browser Geolocation API works in dev without TLS. For production HTTPS, see §17.

---

## 11b. Testing Requirements

### Coverage gate

**Both the backend and frontend must maintain ≥ 80 % branch coverage at all times. All tests must pass before any feature is considered complete.** Coverage is measured in branch mode (not line mode) because branch mode catches untested conditional paths that line coverage misses.

These thresholds are enforced by configuration, not just convention — the test runner exits with a non-zero code if coverage drops below 80 %, which blocks the build.

### Backend — pytest configuration

`pytest.ini` (or `pyproject.toml [tool.pytest.ini_options]`):

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts =
    --cov=app
    --cov-branch
    --cov-report=term-missing
    --cov-fail-under=80
```

Run with: `pytest`

### Frontend — Vitest configuration

`vite.config.ts` (or `vitest.config.ts`):

```ts
// Production build settings (in defineConfig's `build` section):
build: {
  sourcemap: false,   // MUST be false in production — source maps expose full TypeScript source to anyone who requests .map files
},

// Test settings:
test: {
  environment: "jsdom",
  setupFiles: ["./src/msw/setup.ts"],
  coverage: {
    provider: "v8",
    branches: 80,        // fail if branch coverage < 80 %
    reporter: ["text", "lcov"],
    include: ["src/**"],
    exclude: ["src/msw/**", "src/types/**", "src/locales/**"],
  },
}
```

Run with: `vitest run --coverage`

---

### Backend test rules

1. **No real HTTP calls in tests.** All outbound HTTP (NASA, N2YO, LL2, Twilio, SMTP) must be mocked using `pytest-mock` / `respx` (for httpx) or `unittest.mock`. Tests must never depend on network access.
2. **Use a real in-memory SQLite database** for every test that touches the DB (via a fixture that creates all tables, yields the session, then drops all tables). Do not mock the ORM or DB layer.
3. **Each router test uses `httpx.AsyncClient` with `app` mounted** — test the full request/response cycle including middleware, dependency injection, and error handlers.
4. **Test every branch of the caching logic**: cache hit, cache miss, today's date re-fetch, stale fallback.
5. **Test every error code path**: `NO_INTERNET`, `NASA_UNAVAILABLE`, `NASA_ERROR`, `NASA_AUTH_ERROR`, `N2YO_QUOTA_EXHAUSTED`, `INTERNAL_ERROR` — each must have at least one test that asserts the correct HTTP status and `code` field.
6. **Auth tests must cover**: successful registration, duplicate email/phone returns same generic error (enumeration prevention), missing both email and phone, wrong password, expired token, invalid refresh token, OTP expiry, OTP reuse (second use of same OTP must return 400), OTP brute-force lockout (6th wrong attempt must delete the OTP row), rate limit on OTP sends (6th resend in 1 hour must return 429), login rate limit (6th failed login must return 429 with `Retry-After`), **concurrent refresh token rotation** (two simultaneous `/auth/refresh` calls with the same token — assert only one succeeds and the other gets 401), open redirect rejected (`?return=https://evil.com` → redirects to `/`).
7. **Notification tests must mock** `aiosmtplib.send` and `twilio.rest.Client.messages.create`; assert call arguments for correct recipient, subject, and body content.
8. **N2YO quota tests must verify** the row-level lock behaviour: simulate two concurrent requests when `used = 899` and assert only one succeeds in calling N2YO while the other serves cached data.

### Frontend test rules

1. **MSW intercepts all API calls.** `src/msw/handlers.ts` defines handlers for every backend route. Tests import these handlers; no real network traffic occurs. **Setup**: run `npx msw init public/` once after project creation to generate `public/mockServiceWorker.js`; commit this file. `src/msw/setup.ts` calls `server.listen()` in `beforeAll`, `server.resetHandlers()` in `afterEach`, and `server.close()` in `afterAll`.
2. **Render with all required providers** (QueryClientProvider, i18next provider, Router) via a shared `renderWithProviders` test utility.
3. **Test user interactions**, not implementation details: use `userEvent` to click, type, and select; assert on visible text and ARIA roles — not on internal state or component refs.
4. **Each page test must cover**:
   - Happy path: data loads and renders correctly
   - Loading state: skeleton/spinner is shown while data is pending
   - Error state: correct `<ErrorBanner>` is shown for each error code the page can receive
   - Empty state: correct empty-state message is shown when the API returns an empty array
5. **Countdown timer tests** use `vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'setInterval', 'clearInterval'] })` — explicitly exclude `requestAnimationFrame` to avoid breaking Globe.gl. Never rely on wall-clock time in countdown tests. Restore real timers with `vi.useRealTimers()` in `afterEach`.
6. **Globe.gl tests** must use real timers (no `vi.useFakeTimers()`). Globe initialization must be wrapped in a `useEffect` with cleanup in the component (`globe.current?._destructor?.()` or equivalent). Tests for `IssPage` should mock the `globe.gl` module entirely (`vi.mock('globe.gl', () => ({ default: vi.fn(() => ({ ... })) }))`) to avoid WebGL context requirements in jsdom.
7. **`<SubscribeModal>` tests** must cover: unauthenticated user sees login prompt; authenticated user with unverified channels sees verification prompt; successful subscription POST is called with correct body; existing subscription shows unsubscribe flow.
8. **Calendar view tests** assert that toggling from grid to calendar view renders FullCalendar and that events appear with the correct label and colour class. Set `editable: false` in the FullCalendar config; assert that dragging is disabled.

9. **Timezone tests**: `src/lib/dateTime.ts` must have unit tests covering `formatDateTime`, `formatDate`, `formatTime`, and `formatRelative` with a mocked `Intl.DateTimeFormat` that simulates both a North American timezone (e.g. `America/Toronto`) and a European timezone (e.g. `Europe/Berlin`). Assert that the same UTC ISO string produces different output for different timezones. Each page test that renders a date or time must mock the `dateTime` module and assert that the correct formatting function was called — not the raw UTC string.

### What is explicitly out of scope for unit tests

- End-to-end browser tests (Playwright / Cypress) — not required for this project
- Visual regression tests
- Load / performance tests

---

## 12. Implementation Order for Claude Code

Implement in this exact order. **Every feature step includes writing tests to ≥ 80 % branch coverage and verifying all tests pass before moving to the next step.** Do not defer tests to the end.

1. **Scaffold & test harness** — initialise Vite + React + TypeScript frontend; initialise FastAPI backend; add docker-compose; configure pytest with `--cov-branch --cov-fail-under=80`; configure Vitest with `coverage.branches: 80`; add MSW setup; add `conftest.py` with DB fixture and async test client; verify both apps start and both test runners execute (zero tests is acceptable at this stage, but the harness must work).
2. **Database + Migrations** — add SQLAlchemy models for all domains; run first Alembic migration; verify DB creates on startup; write fixtures used by all subsequent backend tests.
3. **NASA Client** — implement `nasa_client.py` with API key injection, connectivity probe, and structured error translation; add `config.py`; write tests for all error branches (timeout, non-2xx, connectivity probe success/fail) using `respx` mocks.
4. **APOD feature** — backend service + router + schema; write `test_apod.py` covering cache hit, cache miss, today re-fetch, stale fallback, each error code; frontend `useApod` hook + `ApodPage`; write `ApodPage.test.tsx` covering happy path, loading, each error state, empty state; verify ≥ 80 % branch coverage on both sides.
5. **NEO feature** — backend + frontend + tests (same pattern as step 4).
6. **Space Weather feature** — backend + frontend + tests for all five DONKI event types.
7. **Mars feature** — backend + frontend + tests including rover selector, camera filter, pagination.
8. **ISS feature** — `n2yo_quota` model + quota-guard; `iss_service.py`; ISS router; Globe.gl `IssPage`; write `test_n2yo_quota.py` (concurrent request boundary at cap=900, window reset, quota_exhausted response) and `test_iss.py`; write `IssPage.test.tsx` (globe renders, data panel values, quota warning badge, countdown interpolation with fake timers).
9. **Launches feature (core)** — `ll2_client.py`; `launches` model; APScheduler sync + change detection; launches router; `LaunchesPage` with grid view, calendar toggle, countdown, filter bar, livestream button; write `test_launches.py` (upsert, change detection triggers correct `pending_notifications` rows, NET slip threshold, no notification when nothing changed, Gone marking); write `LaunchesPage.test.tsx` (grid renders cards, calendar renders events, filter reduces visible cards, countdown with fake timers, TBD shows NET label, livestream button hidden when empty).
10. **Auth feature** — `users` + `refresh_tokens` models; `auth_service.py`; auth router; `LoginPage`, `RegisterPage`, Navbar user widget; write `test_auth.py` covering all branches listed in §11b; write `LoginPage.test.tsx`, `RegisterPage.test.tsx`, `Navbar.test.tsx` (logged-in vs logged-out states).
11. **Subscriptions & Notifications** — all models; `subscription_service.py`; `notification_service.py`; change-detection wiring; `<SubscribeModal>`, bell icons, `AccountPage`; write `test_subscriptions.py` and `test_notifications.py` covering all branches in §11b (mock SMTP and Twilio); write `SubscribeModal.test.tsx` and `AccountPage.test.tsx`.
12. **i18n** — install i18next; add all six locale files; wrap all JSX strings in `t()`; add locale-switching test to each page test file asserting that a key UI string changes language correctly.
13. **Settings Page** — language switcher, API key inputs; backend settings endpoints; tests.
14. **Polish** — loading skeletons, error boundaries, empty states, responsive layout, dark mode; add/update tests for skeleton and empty-state rendering branches.
15. **Final coverage audit** — run `pytest --cov-report=html` and `vitest run --coverage`; fix any modules below 80 % branch coverage; all tests must be green.

---

## 13. Environment Variables

```dotenv
# .env.example
NASA_API_KEY=your_key_here          # Register free at https://api.nasa.gov/
N2YO_API_KEY=your_key_here          # Register free at https://www.n2yo.com/login/register/
LL2_API_KEY=                        # Optional — leave empty for unauthenticated free tier (15 req/hr)
LL2_SYNC_INTERVAL_MINUTES=30        # How often the background task syncs from Launch Library 2

# Auth
JWT_SECRET_KEY=change_me_to_a_random_256bit_secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Email notifications (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=noreply@space-adventures.app

# SMS notifications (Twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=                 # E.164 format, e.g. +14155552671
N2YO_QUOTA_CAP=900                  # Hard cap below the 1000/hour free-tier limit (quota logic reads this — never hard-code 900)
ADMIN_API_KEY=change_me             # Required header value for POST /api/v1/launches/sync
UNSUBSCRIBE_SECRET_KEY=change_me_to_a_random_256bit_secret  # Separate from JWT_SECRET_KEY — rotating JWT does not break unsubscribe links
DATABASE_URL=sqlite+aiosqlite:///./space_adventures.db
CORS_ORIGINS=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
```

---

## 14. Key Non-Functional Requirements

- **Rate limiting safety**: the backend must never fire more than one NASA request per unique (endpoint + params) combination. Historical data (any date before today) is fetched exactly once and stored forever; only today's data may be re-fetched on each request.
- **Offline-first for cached data**: if the NASA API returns an error but a cached row exists (including a today's record from earlier in the day), return the cached row with a `stale: true` flag — never show a blank page.
- **Accessibility**: all images must have `alt` text; colour contrast must meet WCAG AA; keyboard navigation must work across all tabs and controls.
- **No secrets in frontend**: the NASA API key is held only in the backend process; the frontend never calls NASA directly.
- **Test coverage**: backend and frontend must each maintain ≥ 80 % branch coverage. The test runners are configured to exit non-zero if coverage drops below this threshold. All tests must pass; a feature is not complete until its tests pass and coverage is met.
- **Startup validation**: `config.py` must use a Pydantic `model_validator` to assert all required env vars are present and non-empty on startup (`JWT_SECRET_KEY`, `UNSUBSCRIBE_SECRET_KEY`, `ADMIN_API_KEY`). The app must refuse to start and print a clear error if any required var is missing.
- **Health endpoint**: `GET /api/v1/health` has two tiers of response depending on whether the caller provides a valid `Authorization: Bearer <ADMIN_API_KEY>` header:
  - **Unauthenticated** (public): `{ status: "ok" | "degraded" }` — binary only; no internal details exposed. Used by Caddy's upstream health check.
  - **Authenticated admin**: `{ db: "ok"|"error", smtp: "ok"|"error"|"unconfigured", n2yo_quota: { status: "ok"|"warning"|"exhausted" } }` — note quota returns a status string, not the raw `used/cap` numbers, to avoid revealing usage patterns to an attacker who steals the admin key.
- **HTTPS everywhere in production**: the app is always served over HTTPS in production. Caddy handles TLS automatically via Let's Encrypt (see §17). The backend is never exposed directly — all traffic enters through Caddy. `localhost` in development is exempt from HTTPS and does not need TLS.
- **Password security**: passwords are hashed with bcrypt (cost factor ≥ 12) before storage. Plaintext passwords must never appear in logs, responses, or the DB.
- **JWT security**: `JWT_SECRET_KEY` must be a cryptographically random 256-bit value. Access tokens expire in 15 minutes. Refresh tokens are stored hashed in the DB and invalidated on logout.
- **OTP security**: OTPs are 6-digit codes, expire after 10 minutes, and are single-use. Rate-limit OTP requests to 5 per hour per user.
- **Unsubscribe token security**: one-click unsubscribe tokens are signed with a **dedicated `UNSUBSCRIBE_SECRET_KEY`** (separate from `JWT_SECRET_KEY`). Tokens include **both `subscription_id` and `user_id`** plus `exp` (30-day expiry) as claims. The endpoint must verify the signature, then query the DB and assert `subscriptions.id = subscription_id AND subscriptions.user_id = user_id` before deleting. If either check fails, return 404 (do not distinguish "invalid token" from "subscription not found" to avoid oracle attacks). This prevents an attacker with a leaked signing key from unsubscribing arbitrary users by guessing integer IDs.

---

## 15. Error Handling & User-Facing Error Messages

Errors must always produce a clear, translated, actionable message in the UI — never a blank page, a raw JSON dump, or a generic "Something went wrong."

### 15.1 Error Categories & Backend Behaviour

The backend distinguishes three error classes and returns a structured JSON error body for all of them:

```json
{ "error": { "code": "NASA_UNAVAILABLE", "message": "…", "detail": "…" } }
```

| Scenario | HTTP status returned by backend | `code` value |
|---|---|---|
| No internet connectivity (backend cannot reach any external host) | `502 Bad Gateway` | `NO_INTERNET` |
| NASA API unreachable but internet is up (NASA-specific outage) | `502 Bad Gateway` | `NASA_UNAVAILABLE` |
| NASA API returned a non-200 response (e.g. 429 rate limit, 503) | `502 Bad Gateway` | `NASA_ERROR` |
| NASA API key invalid / forbidden | `502 Bad Gateway` | `NASA_AUTH_ERROR` |
| Requested data not in DB and NASA is unreachable | `502 Bad Gateway` | `NASA_UNAVAILABLE` or `NO_INTERNET` |
| Cached (stale) data returned because NASA is down | `200 OK` with `stale: true` | — |
| N2YO hourly quota cap (900) reached — no cached data | `429 Too Many Requests` | `N2YO_QUOTA_EXHAUSTED` |
| N2YO hourly quota cap reached — cached data available | `200 OK` with `quota_exhausted: true` | — |
| Backend internal error | `500 Internal Server Error` | `INTERNAL_ERROR` |

**Distinguishing `NO_INTERNET` from `NASA_UNAVAILABLE`:** when the NASA API call fails with `httpx.ConnectError` or `httpx.TimeoutException`, `nasa_client.py` must perform a connectivity probe before returning the error:

1. Attempt a HEAD request to a reliable, neutral host (e.g. `https://www.google.com`) with a 3-second timeout.
2. If the probe also fails → set code `NO_INTERNET`.
3. If the probe succeeds → NASA is specifically down → set code `NASA_UNAVAILABLE`.

The probe must be a one-shot fire-and-forget with no retries and must not block for more than 3 seconds.

### 15.2 Frontend Error Handling

**Backend unreachable (network error / fetch fails entirely):**

- Each page's TanStack Query hook detects a network-level failure (the fetch itself throws — no HTTP response at all).
- Display a full-page or section-level `<ErrorBanner>` component with:
  - Icon: warning/disconnected symbol
  - Translated heading: `"error.backendDown"` (e.g. "Cannot reach the Space Adventures server")
  - Translated subtext: `"error.backendDownDetail"` (e.g. "The application backend is not responding. Please check your connection or try again later.")
  - A "Retry" button that re-triggers the query

**No internet connection (`NO_INTERNET`):**

- The backend returns `502` with `code: "NO_INTERNET"`.
- Display a full-page `<ErrorBanner>` (all tabs are affected — no data can be fetched at all) with:
  - Icon: no-wifi / offline symbol
  - Translated heading: `"error.noInternet"` (e.g. "No internet connection")
  - Translated subtext: `"error.noInternetDetail"` (e.g. "The server cannot reach the internet. Please check your network connection and try again.")
  - If cached data exists for the requested params, show it below the banner with a `"Showing cached data from <date>"` badge.
  - A "Retry" button.

**NASA services down (`NASA_UNAVAILABLE` or `NASA_ERROR`):**

- The backend returns `502` with a structured body.
- Display a section-level `<ErrorBanner>` (not full-page — the nav and other tabs remain usable) with:
  - Icon: satellite-dish / NASA symbol
  - Translated heading: `"error.nasaUnavailable"` (e.g. "NASA services are currently unavailable")
  - Translated subtext: `"error.nasaUnavailableDetail"` (e.g. "Live data could not be retrieved from NASA. Showing cached data if available.")
  - If cached data exists for the requested params, show it below the banner with a visible `"Showing cached data from <date>"` badge.
  - If no cached data exists, show the banner alone with no data.

**NASA API key invalid (`NASA_AUTH_ERROR`):**

- Display a `<ErrorBanner>` with:
  - Translated heading: `"error.nasaAuthError"` (e.g. "Invalid NASA API Key")
  - Translated subtext with a prompt to go to Settings and update the key: `"error.nasaAuthErrorDetail"`
  - A direct link/button to `/settings`

**Generic backend error (`INTERNAL_ERROR` / HTTP 500):**

- Display a section-level `<ErrorBanner>` with the translated key `"error.internalError"`.

### 15.3 `<ErrorBanner>` Component

Create a single reusable `src/components/ErrorBanner.tsx` component with props:

```tsx
interface ErrorBannerProps {
  titleKey: string       // i18n key for the heading
  detailKey?: string     // i18n key for the subtext
  detailValues?: object  // interpolation values for i18n (e.g. { date: "2024-07-01" })
  onRetry?: () => void   // if provided, shows a Retry button
  action?: ReactNode     // optional extra action (e.g. "Go to Settings" link)
  variant: "page" | "section"  // "page" = full viewport centred; "section" = inline within content area
}
```

### 15.4 Translation Keys to Add

Add the following keys to **all six locale files**:

```json
"error": {
  "backendDown": "Cannot reach the server",
  "backendDownDetail": "The application backend is not responding. Please check your connection or try again later.",
  "noInternet": "No internet connection",
  "noInternetDetail": "The server cannot reach the internet. Please check your network connection and try again.",
  "nasaUnavailable": "NASA services are currently unavailable",
  "nasaUnavailableDetail": "Live data could not be retrieved from NASA. Showing cached data where available.",
  "nasaAuthError": "Invalid NASA API Key",
  "nasaAuthErrorDetail": "The configured NASA API key was rejected. Please update it in Settings.",
  "internalError": "An unexpected server error occurred",
  "internalErrorDetail": "Please try again. If the problem persists, check the server logs.",
  "staleData": "Showing cached data from {{date}}"
}
```

### 15.5 TanStack Query Configuration

Configure the global `QueryClient` with:

```ts
new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 10000),
      staleTime: Infinity,   // global default — backend cache is permanent for historical data
    },
  },
})
```

**Per-query `staleTime` overrides** — two queries must override the global `Infinity` to enable automatic background refetching:

| Query | `staleTime` | Reason |
|---|---|---|
| `/api/v1/iss/positions` | `270_000` ms (4.5 min) | Triggers background refetch 30 s before 5-min batch expires |
| `/api/v1/launches/upcoming` | `300_000` ms (5 min) | Refreshes launch list every 5 minutes to reflect NET slips |

These overrides are set directly on the `useQuery` call in the respective hooks, not globally. All other queries keep `staleTime: Infinity`.

Each query hook must expose the `error` and `isError` values from TanStack Query and pass them to `<ErrorBanner>` rather than swallowing them silently.

---

## 16. Known Implementation Pitfalls

**Read this section before implementing each feature area.** These are specific failure modes that are easy to introduce and hard to debug. Each entry states the exact failure, why it is likely to happen, and the fix.

---

### 16a. Python / FastAPI / SQLAlchemy Async

**P1 — AsyncSession scoping in dependency injection**
`async def get_db(): session = SessionLocal()` without a context manager leaks sessions and causes `MissingGreenlet` or closed-session errors in services. The correct pattern is:
```python
async def get_db():
    async with AsyncSession(engine) as session:
        yield session
```
Register with `Depends(get_db)` on every route that touches the DB.

**P2 — Lazy-loaded relationships silently return `None` in async**
`subscription.user.email` accessed after the session closes returns `None` with no exception — the notification never finds the email address. Always use eager loading for relationships needed outside the initial query:
```python
select(Subscription).options(selectinload(Subscription.user))
```
Apply this to every query in `notification_service.py` and `subscription_service.py`.

**P3 — APScheduler started before the event loop exists**
Calling `scheduler.start()` at module import time raises `RuntimeError: no running event loop`. Start the scheduler exclusively inside the FastAPI `lifespan` async context manager:
```python
@asynccontextmanager
async def lifespan(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(sync_launches, "interval", minutes=30)
    scheduler.start()
    yield
    scheduler.shutdown()
```

**P4 — `asyncio.Lock` for SQLite quota guard re-created per call**
A lock defined inside a function is a new object every time — concurrent requests bypass it entirely. Define at module level in `n2yo_client.py`:
```python
_quota_lock = asyncio.Lock()   # one instance for the lifetime of the process
```

**P5 — Alembic receives the async `aiosqlite://` URL, autogenerate produces empty migrations**
Alembic requires a synchronous engine for migrations. In `alembic/env.py`, use `sqlite:///` (not `sqlite+aiosqlite:///`). Keep the async URL only for the runtime `create_async_engine()` call. Provide both URLs in `.env`:
```
DATABASE_URL=sqlite+aiosqlite:///./data/space_adventures.db
DATABASE_URL_SYNC=sqlite:///./data/space_adventures.db
```

**P6 — `httpx.AsyncClient` created per request exhausts the connection pool**
Creating a client inside every service method means a new TCP connection pool per call. Create one shared client at startup and close it on shutdown:
```python
# In lifespan:
app.state.http_client = httpx.AsyncClient(timeout=10.0)
yield
await app.state.http_client.aclose()
```
Pass via dependency injection or access via `request.app.state.http_client`.

---

### 16b. Authentication

**P7 — `CryptContext` created per request**
`CryptContext(schemes=["bcrypt"])` is expensive. Define it once at module level in `auth_service.py`, never inside a function or route handler.

**P8 — JWT expiry not verified by default in some `python-jose` versions**
Always pass `options={"verify_exp": True}` explicitly to `jwt.decode()`. Never rely on the default.

**P9 — OTP rate-limit check is not atomic**
SELECT count → check < 5 → INSERT is a read-modify-write race. Two concurrent requests both read count=4 and both insert. Fix: wrap in the SQLite asyncio.Lock (P4) or use `SELECT … FOR UPDATE` (PostgreSQL).

**P10 — Concurrent `/auth/refresh` with the same token issues two valid tokens**
Both requests read `revoked=FALSE`, both generate new tokens, only one revoke lands. Fix: use `SELECT … FOR UPDATE` on the `refresh_tokens` row at the start of the refresh handler to serialize concurrent attempts.

---

### 16c. N2YO / ISS

**P11 — N2YO position timestamps are Unix epoch seconds (integers), not ISO strings**
`position.timestamp` is an integer (e.g. `1751000000`). Multiply by 1000 before comparing to JavaScript's `Date.now()` (milliseconds). Store as-is in the DB; the backend API response should surface `timestamp_ms = timestamp * 1000` for the frontend's benefit.

**P12 — N2YO errors are HTTP 200 with `{"error": "..."}` body**
`response.status_code == 200` does not mean success for N2YO. Always inspect the body:
```python
data = response.json()
if "error" in data:
    raise N2YOError(data["error"])
```

**P13 — `globe.gl` has no `@types/globe.gl` package**
TypeScript will infer `any` or refuse to compile. Add a manual declaration file:
```ts
// src/types/globe.d.ts
declare module 'globe.gl' { const Globe: any; export default Globe; }
```

---

### 16d. Launch Library 2

**P14 — `vidURLs` may be absent (not just empty)**
Always use `launch.get('vidURLs') or []` in Python and `launch.vidURLs ?? []` in TypeScript. Never access `.length` without a null guard.

**P15 — `net` field has microseconds and `Z` suffix; `datetime.fromisoformat()` fails on Python < 3.11**
Use `dateutil.parser.isoparse(net)` (add `python-dateutil` to `requirements.txt`) which handles all ISO 8601 variants including `Z`, sub-seconds, and `+00:00`.

**P16 — LL2 response is paginated; default page is 10–25 items, not all upcoming launches**
Always pass `limit=100` and loop until `response['next']` is `None`:
```python
url = f"{LL2_BASE}/launches/upcoming/?mode=detailed&limit=100"
while url:
    r = await client.get(url); data = r.json()
    launches.extend(data["results"]); url = data["next"]
```

---

### 16e. React / Vite / TypeScript

**P17 — Globe.gl initialized before the ref element mounts (`ref.current` is `null`)**
Always guard in `useEffect`:
```ts
useEffect(() => {
  if (!containerRef.current) return;
  const globe = new Globe()(containerRef.current);
  return () => { /* cleanup */ };
}, []);
```
Never pass `containerRef.current` outside a `useEffect`.

**P18 — FullCalendar renders unstyled without explicit CSS imports**
Add to the component file (not `vite.config.ts`):
```ts
import '@fullcalendar/core/main.css';
import '@fullcalendar/daygrid/main.css';
```

**P19 — `i18next-browser-languagedetector` returns `en-US`, i18n config expects `en`**
Set `load: 'languageOnly'` in the i18next init options so `en-US` resolves to `en.json`.

**P20 — MSW v2 API is `http.get()`, not `rest.get()` (v1)**
Every handler must use the v2 import:
```ts
import { http, HttpResponse } from 'msw';
export const handlers = [
  http.get('http://localhost:8000/api/v1/launches/upcoming', () =>
    HttpResponse.json({ data: [], cached: false })
  ),
];
```

**P21 — `?return=` query param must be encoded AND validated to prevent open redirect**
```ts
// Writing:
`/login?return=${encodeURIComponent(location.pathname + location.search)}`

// Reading — validate before using:
function safeReturnUrl(): string {
  const raw = decodeURIComponent(new URLSearchParams(location.search).get('return') ?? '/');
  // Must be a relative path — reject anything with a protocol or host
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('://')) return '/';
  return raw;
}
```
An attacker crafting `/login?return=https://evil.com` is silently redirected to `/` instead.

**P22 — Vite proxy target `localhost` unreachable inside Docker**
In `vite.config.ts`, read the proxy target from the env:
```ts
proxy: { '/api': { target: process.env.VITE_API_BASE_URL ?? 'http://localhost:8000' } }
```
Set `VITE_API_BASE_URL=http://backend:8000` in `docker-compose.yml` for the frontend service.

---

### 16f. Database / Alembic / SQLite

**P23 — Alembic emits `DEFAULT NOW()` which SQLite does not support**
Edit generated migrations to replace `NOW()` with `CURRENT_TIMESTAMP`. In models, use `server_default=text("CURRENT_TIMESTAMP")` rather than `server_default=func.now()` to avoid the issue at generation time.

**P24 — Alembic autogenerate silently omits `CHECK` constraints on SQLite**
After every `op.create_table()` in a migration, manually add:
```python
op.create_check_constraint('ck_otps_channel', 'otps', "channel IN ('email','phone')")
```
Do this for every `CHECK IN (...)` constraint defined in the models.

**P25 — SQLite foreign key enforcement is OFF by default; `ON DELETE CASCADE` does nothing**
Add this event listener in `database.py`:
```python
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

---

### 16g. Testing

**P26 — `TestClient` (sync) mixed with `async def` tests causes event loop conflicts**
Never use `TestClient` in async test functions. Always use:
```python
async with httpx.AsyncClient(
    transport=httpx.ASGITransport(app=app), base_url="http://test"
) as client:
    response = await client.get("/api/v1/...")
```

**P27 — `respx` mocks are only active inside the `with respx.mock:` block**
If the HTTP call happens in a service called from a background task or a fixture, the mock is not active. Use the `@pytest.mark.respx(assert_all_called=False)` decorator or `respx.mock` as a pytest fixture for test-wide mocking.

**P28 — `vi.mock()` is hoisted; variables defined below it are `undefined`**
Use `vi.hoisted()` for any value referenced in a mock factory:
```ts
const { mockInstance } = vi.hoisted(() => ({
  mockInstance: { method: vi.fn() }
}));
vi.mock('globe.gl', () => ({ default: vi.fn(() => mockInstance) }));
```

**P29 — `@testing-library/user-event` v14 calls are async; missing `await` causes silent false passes**
Every `userEvent` call must be awaited:
```ts
await userEvent.click(button);
await userEvent.type(input, 'hello');
```
Lint rule: add `@typescript-eslint/no-floating-promises` to the ESLint config so unawaited promises are caught statically.

---

### 16h. Docker / Deployment

**P30 — Bind mount `./backend:/app` overwrites `pip install`'d packages**
Mount only the application code, not the entire `/app` directory:
```yaml
volumes:
  - ./backend/app:/app/app        # source code only
  - sa_db_data:/app/data          # persisted DB
```
Install dependencies into a layer that the bind mount does not overlay.

**P31 — `/app/data/` directory missing in container; SQLite file creation fails silently**
Add to `backend/Dockerfile`:
```dockerfile
RUN mkdir -p /app/data
```

---

### 16i. Miscellaneous

**P32 — Twilio SDK is synchronous; calling it directly in an async route blocks the event loop**
Wrap every Twilio call:
```python
await asyncio.to_thread(
    twilio_client.messages.create,
    to=phone, from_=TWILIO_FROM, body=sms_body
)
```

**P33 — `aiosmtplib` STARTTLS vs SMTPS: wrong parameter for the port**
- Port 587 (STARTTLS): `aiosmtplib.SMTP(hostname=..., port=587, start_tls=True)`
- Port 465 (SMTPS): `aiosmtplib.SMTP(hostname=..., port=465, use_tls=True)`
Mixing these causes silent connection failures with no exception.

**P34 — jsdom's `Intl` implementation is incomplete; some IANA timezone names throw**
In timezone unit tests, only use well-known zones: `America/New_York`, `Europe/London`, `Asia/Tokyo`. Do not rely on jsdom for timezone rendering; mock `Intl.DateTimeFormat` in `dateTime.test.ts` and test the formatting logic independently of the runtime's Intl support.

**P35 — `passlib[bcrypt]` on a minimal Linux Docker image falls back to slow pure-Python bcrypt**
The C extension requires system packages. Add to `backend/Dockerfile`:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev python3-dev gcc && rm -rf /var/lib/apt/lists/*
```
Without this, bcrypt hashing takes ~10 seconds per password instead of ~100 ms, causing registration and login timeouts.

---

## 17. Deployment

### 17a. Architecture Overview

```
Internet
   │  HTTPS (443) / HTTP (80 → redirect)
   ▼
┌─────────────────────────────────────┐
│  Caddy (reverse proxy + TLS)        │
│  • Provisions Let's Encrypt certs   │
│  • Enforces HTTPS, HSTS             │
│  • Serves frontend static files     │
│  • Proxies /api/* → backend:8000    │
└────────────────┬────────────────────┘
                 │ Docker internal network (not exposed)
                 ▼
┌────────────────────────────────────┐
│  Backend (Uvicorn, single worker)  │
│  port 8000 — NOT publicly exposed  │
└────────────────────────────────────┘
         │
         ▼
  /app/data/space_adventures.db  (named volume, persisted)
```

The frontend is **not a running container in production**. It is built into static files (`npm run build`) and served directly by Caddy. This eliminates an entire container tier and simplifies the stack.

---

### 17b. Dockerfiles

**`backend/Dockerfile`** (production):
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Required for bcrypt C extension (P35)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev python3-dev gcc curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# Data directory for SQLite (P31)
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**`frontend/Dockerfile`** (multi-stage production build):
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
RUN npm run build          # outputs to /app/dist

# Export stage — just the built assets; Caddy serves them via bind mount
FROM scratch AS dist
COPY --from=builder /app/dist /dist
```

> In practice the frontend is built on the host or in CI, not inside a running container. The `dist/` output folder is bind-mounted into the Caddy container (see §17d).

---

### 17c. Caddyfile

```caddy
# Caddyfile — place at repository root

{
    email {$CADDY_TLS_EMAIL}        # Let's Encrypt account email (set in .env.prod)
}

{$APP_DOMAIN} {
    encode gzip zstd               # response compression

    # Security headers
    header {
        Strict-Transport-Security  "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options     "nosniff"
        X-Frame-Options            "DENY"
        X-XSS-Protection           "1; mode=block"
        Referrer-Policy            "strict-origin-when-cross-origin"
        Permissions-Policy         "geolocation=(self)"
        Content-Security-Policy    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'"
        -Server                    # remove Caddy version header
        # Never log Authorization header — admin key and user tokens must not appear in access logs
    }

    # Strip Authorization header from access logs
    log {
        format filter {
            wrap json
            fields {
                request>headers>Authorization delete
                request>headers>X-Admin-Key delete
            }
        }
    }

    # Proxy all API and auth traffic to the backend container
    reverse_proxy /api/* backend:8000 {
        health_uri     /api/v1/health
        health_interval 30s
    }

    # Serve the pre-built React SPA
    root * /srv
    try_files {path} /index.html   # SPA fallback for React Router
    file_server
}
```

Caddy automatically:
- Provisions and renews the Let's Encrypt certificate for `APP_DOMAIN`
- Redirects all HTTP (port 80) traffic to HTTPS (port 443) with a 308 permanent redirect
- Enables HTTP/3 (QUIC) on UDP 443

---

### 17d. docker-compose.prod.yml

```yaml
# docker-compose.prod.yml  ─── PRODUCTION ───

services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"               # HTTP/3
    environment:
      - APP_DOMAIN=${APP_DOMAIN}
      - CADDY_TLS_EMAIL=${CADDY_TLS_EMAIL}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/srv:ro     # pre-built React app (read-only)
      - caddy_data:/data            # TLS certificates — NEVER delete this volume
      - caddy_config:/config
    depends_on:
      backend:
        condition: service_healthy

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
    env_file: .env.prod
    volumes:
      - sa_db_data:/app/data        # persisted SQLite DB
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    # No `ports:` entry — backend is not reachable from outside the Docker network

volumes:
  caddy_data:     # TLS certs — must persist across deployments
  caddy_config:   # Caddy internal config cache
  sa_db_data:     # SQLite database
```

---

### 17e. Environment Files

**`.env.example`** (development — copy to `.env`):
```dotenv
# Development — HTTP only, no TLS required
NASA_API_KEY=DEMO_KEY
N2YO_API_KEY=
LL2_API_KEY=
LL2_SYNC_INTERVAL_MINUTES=30
JWT_SECRET_KEY=dev_jwt_secret_change_in_prod
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
UNSUBSCRIBE_SECRET_KEY=dev_unsub_secret_change_in_prod
ADMIN_API_KEY=dev_admin_key
N2YO_QUOTA_CAP=900
DATABASE_URL=sqlite+aiosqlite:///./data/space_adventures.db
DATABASE_URL_SYNC=sqlite:///./data/space_adventures.db
CORS_ORIGINS=http://localhost:5173
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@localhost
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

**`.env.prod.example`** (production — copy to `.env.prod` on the server, fill all values):
```dotenv
# Production — all values are mandatory; app refuses to start if any are missing
APP_DOMAIN=space-adventures.example.com
CADDY_TLS_EMAIL=admin@example.com

NASA_API_KEY=your_registered_nasa_api_key
N2YO_API_KEY=your_n2yo_api_key
LL2_API_KEY=your_ll2_api_key_optional
LL2_SYNC_INTERVAL_MINUTES=30

# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
UNSUBSCRIBE_SECRET_KEY=
ADMIN_API_KEY=

N2YO_QUOTA_CAP=900
DATABASE_URL=sqlite+aiosqlite:///./data/space_adventures.db
DATABASE_URL_SYNC=sqlite:///./data/space_adventures.db
CORS_ORIGINS=https://space-adventures.example.com

# Email (SMTP)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=notifications@example.com
SMTP_PASSWORD=
SMTP_FROM=noreply@space-adventures.example.com

# SMS (Twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

---

### 17f. First Deployment Runbook

Run these steps on the server in order. Every step must succeed before moving to the next.

**Prerequisites on the server:**
- Docker Engine ≥ 26 and Docker Compose v2 installed
- Ports 80 and 443 open in the firewall
- A domain name pointing at the server's public IP (DNS must resolve before starting Caddy, or Let's Encrypt will fail)

**Step 1 — Clone and configure**
```bash
git clone <repo-url> space-adventures && cd space-adventures
cp .env.prod.example .env.prod
chmod 600 .env.prod               # owner read/write only — verify with: ls -l .env.prod → -rw-------
# Fill in all values in .env.prod — especially JWT_SECRET_KEY, UNSUBSCRIBE_SECRET_KEY,
# ADMIN_API_KEY (generate each with: python -c "import secrets; print(secrets.token_hex(32))")
# .env.prod must be listed in .gitignore — never commit it to version control
```

**Step 2 — Build the frontend**
```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://<APP_DOMAIN> npm run build
# Verify: ls dist/index.html  (must exist)
cd ..
```

**Step 3 — Run database migrations**
```bash
docker compose -f docker-compose.prod.yml run --rm backend \
  alembic upgrade head
```

**Step 4 — Start the stack**
```bash
docker compose -f docker-compose.prod.yml up -d
```

**Step 5 — Verify**
```bash
# Backend health
curl -sf https://<APP_DOMAIN>/api/v1/health | python -m json.tool

# TLS certificate
curl -sv https://<APP_DOMAIN> 2>&1 | grep "SSL certificate"

# Check logs for errors
docker compose -f docker-compose.prod.yml logs --tail=50
```

Caddy provisions the Let's Encrypt certificate on first request. This takes 5–30 seconds. If it fails, check that DNS resolves correctly and that port 80 is reachable from the internet (Let's Encrypt uses HTTP-01 challenge).

---

### 17g. Redeployment (Updates)

```bash
# Pull changes
git pull

# Rebuild and restart backend if Python code changed
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml up -d backend

# Run any new migrations
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# Rebuild frontend if React code changed
cd frontend && npm ci && VITE_API_BASE_URL=https://<APP_DOMAIN> npm run build && cd ..
# Caddy picks up the new files immediately — no restart needed
```

---

### 17h. TLS Certificate Notes

- Caddy stores certificates in the `caddy_data` Docker volume. **Never delete this volume** — Let's Encrypt rate-limits certificate issuance (5 duplicate certs per week). If the volume is lost, wait up to a week before a new cert can be issued for the same domain.
- Caddy renews certificates automatically ≥ 30 days before expiry. No manual action is required.
- The `Strict-Transport-Security` header is set with `preload` in the Caddyfile. **Do NOT submit the domain to the HSTS preload list (`hstspreload.org`) during initial deployment.** Only submit after HTTPS has been running stably for at least one month with no certificate issues. Reason: once preloaded, browsers refuse HTTP connections for up to 1 year — if HTTPS ever breaks, the domain becomes completely inaccessible to all users with no emergency workaround. Remove `preload` from the header if this risk is unacceptable.
- `Permissions-Policy: geolocation=(self)` ensures only the app's own origin can request geolocation — no embedded third-party frames can request it silently.

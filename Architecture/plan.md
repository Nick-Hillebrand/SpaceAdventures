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
| Calendar | FullCalendar React (`@fullcalendar/react` + `@fullcalendar/daygrid`, MIT) |
| Auth (backend) | python-jose[cryptography] (JWT) + passlib[bcrypt] (password hashing) |
| Email (backend) | aiosmtplib — async SMTP, works with any provider (Gmail, SendGrid, etc.) |
| SMS (backend) | Twilio Python SDK |
| Backend testing | pytest + pytest-asyncio + pytest-cov + httpx (AsyncClient for route tests) |
| Frontend testing | Vitest + React Testing Library + @testing-library/user-event + MSW (mock service worker) |
| Coverage enforcement | pytest-cov (backend, branch mode); @vitest/coverage-v8 (frontend, branch mode) |
| Containerisation | Docker + docker-compose |
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
│   └── Dockerfile
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
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
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

- Store all upcoming launches returned by LL2 in the DB on each sync.
- A background sync runs **every 30 minutes** (APScheduler). This is the only place the LL2 API is called; no user request ever triggers a direct LL2 call.
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

### Authentication flow

- **JWT-based**: access token (15-minute expiry) + refresh token (30-day expiry, stored in the DB as `refresh_tokens` table)
- Access token sent in `Authorization: Bearer <token>` header
- Frontend stores tokens in `localStorage`
- Verification: after registration, a 6-digit OTP is sent to the provided email and/or phone. Notifications are only dispatched to verified channels
- Login works with either email + password or phone + password

### Auth API routes

```
POST /api/v1/auth/register          # create account; sends OTP to email/phone
POST /api/v1/auth/verify/email      # { otp } — mark email verified
POST /api/v1/auth/verify/phone      # { otp } — mark phone verified
POST /api/v1/auth/login             # { email_or_phone, password } → { access_token, refresh_token }
POST /api/v1/auth/refresh           # { refresh_token } → new access_token
POST /api/v1/auth/logout            # invalidate refresh token
GET  /api/v1/auth/me                # return current user profile (requires auth)
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
id              INTEGER  PRIMARY KEY
user_id         INTEGER  FK → users.id  ON DELETE CASCADE
type            TEXT     CHECK IN ('launch', 'agency')
ll2_id          TEXT     NULLABLE — set when type = 'launch'
agency_name     TEXT     NULLABLE — set when type = 'agency'
notify_email    BOOLEAN  DEFAULT TRUE  — only effective if user.email_verified
notify_sms      BOOLEAN  DEFAULT FALSE — only effective if user.phone_verified
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
error_detail     TEXT     NULLABLE
sent_at          DATETIME
```

### Notification message content

**Email subject:** `"Space Adventures — Launch Update: <launch name>"`

**Email body (plain text + HTML):**
- Change type heading: "NET Slip", "Status Change", or "New Launch from <agency>"
- Launch name, rocket, agency
- Old value → New value
- New NET date/time in UTC and local time
- Unsubscribe link: `GET /api/v1/subscriptions/unsubscribe?token=<signed_token>`

**SMS body** (max 160 characters):
`"Space Adventures: <launch name> — <change>. New NET: <date UTC>. Reply STOP to opt out."`

### Notification delivery

`notification_service.py` iterates pending_notifications after each LL2 sync:

1. For each pending row, load the subscription → user.
2. If `notify_email` is true and `user.email_verified` → send email via SMTP (aiosmtplib).
3. If `notify_sms` is true and `user.phone_verified` → send SMS via Twilio.
4. Write to `notification_log` with delivery status.
5. Delete the `pending_notifications` row.

All sends are async and non-blocking. A failed send logs the error and retries on the next sync cycle (max 3 attempts, tracked via an `attempt_count` column in `pending_notifications`).

### Subscription API routes

```
GET    /api/v1/subscriptions                               # list my subscriptions (auth required)
POST   /api/v1/subscriptions                               # create subscription (auth required)
DELETE /api/v1/subscriptions/{id}                          # remove subscription (auth required)
GET    /api/v1/subscriptions/unsubscribe?token=<token>     # one-click unsubscribe from email link (no auth)
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
- If the requested date/range **includes today** → always re-fetch from NASA and upsert the DB row so the record is kept current until midnight, at which point it becomes historical and is never re-fetched again.

This means the only live NASA calls the app ever makes are for the current day's data.

The `nasa_client.py` module keeps a single `httpx.AsyncClient` with a `NASA_API_KEY` header injected from config.

---

## 6b. N2YO Transaction Quota

N2YO's free tier allows **1 000 transactions per rolling hour**. The backend must enforce a hard cap of **900 transactions per hour** (100-unit safety buffer) to ensure the app never crosses into the paid tier, regardless of how many users are active.

### Quota model (`n2yo_quota` table)

```
id           INTEGER PRIMARY KEY
window_start DATETIME   -- start of the current 1-hour window (UTC)
used         INTEGER    -- transactions consumed in this window
```

There is always exactly one row. On each N2YO call attempt:

1. Read the row.
2. If `NOW() - window_start >= 1 hour` → reset: set `window_start = NOW()`, `used = 0`.
3. If `used >= 900` → **do not call N2YO**. Return cached data if available with `quota_exhausted: true` in the response envelope. If no cache exists, return a `429` with error code `N2YO_QUOTA_EXHAUSTED`.
4. Otherwise → call N2YO, increment `used`, upsert cache, return data.

The increment in step 4 must happen **inside a DB transaction** with a row-level lock so concurrent requests cannot double-count.

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
GET  /api/v1/iss/passes/visual?lat=0&lng=0&alt=0    # upcoming visible passes for observer
GET  /api/v1/iss/passes/radio?lat=0&lng=0&alt=0     # upcoming radio passes for observer
GET  /api/v1/iss/quota            # returns { used, cap, window_start, resets_at }

GET  /api/v1/launches/upcoming    # all launches with net > now - 24h, ordered by net asc
POST /api/v1/launches/sync        # manually trigger a LL2 sync (admin / debug use)

POST /api/v1/settings/nasa-api-key   # { api_key } — update NASA key in-process
POST /api/v1/settings/n2yo-api-key   # { api_key } — update N2YO key in-process
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
| Next visible pass (from observer) | visual passes cache | local time + duration |
| Next radio pass (from observer) | radio passes cache | local time + duration |
| N2YO quota remaining | `/api/v1/iss/quota` | X / 900 used |

### Quota warning in the UI

If the `/api/v1/iss/quota` response shows `quota_exhausted: true` OR `used >= 800`:
- Show a persistent warning badge on the ISS tab icon and at the top of the ISS page.
- Text: `"iss.quotaWarning"` (e.g. "N2YO API quota nearly exhausted — showing cached data")
- If fully exhausted: `"iss.quotaExhausted"` (e.g. "N2YO API quota exhausted for this hour. Live updates paused. Resets at {{time}}.")

### Client-side position interpolation

The frontend holds the 300-entry position array in memory. A `setInterval` running every 1 000 ms picks the entry closest to `now` and moves the ISS marker. When the batch is within 30 seconds of expiry, TanStack Query's background refetch triggers a new `/api/v1/iss/positions` call (1 transaction) to top up the array. This gives smooth 1-second animation with no per-second API calls.

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
- When `status_abbrev` is `"TBD"` or `"Hold"`: show `"NET: <date>"` instead of a live countdown, since the time is not reliable enough to count down to.

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

A small line at the top of the page shows when the launch list was last synced from LL2 (the `fetched_at` of the most recently updated record), e.g. "Last updated 4 minutes ago". TanStack Query refetches `/api/v1/launches/upcoming` every **5 minutes** in the background so the page stays current without a manual reload.

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
- "Forgot password?" link — out of scope for v1; show a placeholder message

### `/account` — Account page

Accessible only when logged in (redirect to `/login` if not). Tabs:

**Profile tab:**
- Display first name, last name, email, phone
- Verification status badges next to email/phone ("Verified" / "Unverified — resend OTP")

**My Subscriptions tab:**
- List of all active subscriptions (launch name + NET, or agency name)
- Per-subscription: notification channels (Email / SMS badges), delete button
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

## 10. Settings Page — Behaviour

| Setting | Type | Storage | Effect |
|---|---|---|---|
| Language | Select (6 options with flag icons) | `localStorage` | Calls `i18n.changeLanguage()` immediately |
| NASA API Key | Text input (password field) | `localStorage` | Forwarded to backend; used for all NASA calls |
| N2YO API Key | Text input (password field) | `localStorage` | Forwarded to backend via `POST /api/v1/settings/n2yo-api-key`; used for all ISS calls |

There are no TTL or cache-expiry settings — the cache is permanent by design. The Settings page does **not** expose any cache-management controls.

NASA and N2YO API keys entered in Settings are forwarded to the backend via `POST /api/v1/settings/nasa-api-key` and `POST /api/v1/settings/n2yo-api-key` respectively. The backend stores them in-process (not on disk) and uses them for all subsequent requests during that server session.

---

## 11. Docker Compose

```yaml
# docker-compose.yml (generated)
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./space_adventures.db
      - NASA_API_KEY=${NASA_API_KEY:-DEMO_KEY}
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    environment:
      - VITE_API_BASE_URL=http://localhost:8000
    depends_on: [backend]
```

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
6. **Auth tests must cover**: successful registration, duplicate email, duplicate phone, missing both email and phone, wrong password, expired token, invalid refresh token, OTP expiry, OTP reuse, rate limit on OTP.
7. **Notification tests must mock** `aiosmtplib.send` and `twilio.rest.Client.messages.create`; assert call arguments for correct recipient, subject, and body content.
8. **N2YO quota tests must verify** the row-level lock behaviour: simulate two concurrent requests when `used = 899` and assert only one succeeds in calling N2YO while the other serves cached data.

### Frontend test rules

1. **MSW intercepts all API calls.** `src/msw/handlers.ts` defines handlers for every backend route. Tests import these handlers; no real network traffic occurs.
2. **Render with all required providers** (QueryClientProvider, i18next provider, Router) via a shared `renderWithProviders` test utility.
3. **Test user interactions**, not implementation details: use `userEvent` to click, type, and select; assert on visible text and ARIA roles — not on internal state or component refs.
4. **Each page test must cover**:
   - Happy path: data loads and renders correctly
   - Loading state: skeleton/spinner is shown while data is pending
   - Error state: correct `<ErrorBanner>` is shown for each error code the page can receive
   - Empty state: correct empty-state message is shown when the API returns an empty array
5. **Countdown timer tests** mock `Date.now()` / `setInterval` via Vitest's fake timers — never rely on wall-clock time.
6. **`<SubscribeModal>` tests** must cover: unauthenticated user sees login prompt; authenticated user with unverified channels sees verification prompt; successful subscription POST is called with correct body; existing subscription shows unsubscribe flow.
7. **Calendar view tests** assert that toggling from grid to calendar view renders FullCalendar and that events appear with the correct label and colour class.

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
N2YO_QUOTA_CAP=900                  # Hard cap below the 1000/hour free-tier limit
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
- **Password security**: passwords are hashed with bcrypt (cost factor ≥ 12) before storage. Plaintext passwords must never appear in logs, responses, or the DB.
- **JWT security**: `JWT_SECRET_KEY` must be a cryptographically random 256-bit value. Access tokens expire in 15 minutes. Refresh tokens are stored hashed in the DB and invalidated on logout.
- **OTP security**: OTPs are 6-digit codes, expire after 10 minutes, and are single-use. Rate-limit OTP requests to 5 per hour per user.
- **Unsubscribe token security**: one-click unsubscribe tokens are signed with the JWT secret and include an expiry of 30 days; they unsubscribe only the specific subscription embedded in the token.

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
      retry: 2,                  // retry failed requests twice before showing error UI
      retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 10000),
      staleTime: Infinity,       // data never goes stale on the client — cache is permanent on the backend
    },
  },
})
```

Each query hook must expose the `error` and `isError` values from TanStack Query and pass them to `<ErrorBanner>` rather than swallowing them silently.

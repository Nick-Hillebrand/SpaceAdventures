# Space Adventures

A multilingual web application that fetches, caches, and visualises NASA data and live space events.

**Features**

- **APOD** — Astronomy Picture of the Day with date picker and HD image viewer
- **ISS Tracker** — Live 3D globe tracking the International Space Station
- **Rocket Launches** — Upcoming launches in grid or calendar view with countdown timers and livestream links.
  Each launch also has a crawlable detail page (`/launches/:id`, language-prefixed variants) with server-injected
  SEO meta/OG/JSON-LD tags and a slip-history teaser, plus an XML sitemap at `/sitemap.xml`
- **Mars Explorer** — Curiosity, Opportunity, Spirit and Perseverance rover photos with lightbox and camera/sol filters
- **Near-Earth Objects** — Sortable asteroid table with close-approach data and hazard flags
- **Space Weather** — Solar flares, geomagnetic storms, CMEs, SEP and radiation belt events
- **Solar System Explorer** — 3D true-scale/didactic-scale simulator of the Sun, planets and major moons
- **Mission Replay** — 3D playback of historic spaceflight trajectories (Apollo 11, Mars Pathfinder) with a
  timeline scrubber and milestone cards, at `/missions`, `/missions/:slug` and a chrome-less `/missions/:slug/embed`,
  and as an in-context panel on the Solar System page. Key milestones (Apollo 11 landing/first EVA, Pathfinder
  EDL/rover deployment) can open a close-up 3D "vignette" — the real NASA/JPL glTF model, staged with an
  orbit camera and narration
- **User accounts** — JWT auth (httpOnly-cookie refresh tokens) with email/SMS OTP verification, launch
  notification subscriptions, notification-consent recording, and self-service account data export/deletion

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, React Query, React Router, i18next |
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Database | SQLite (local dev, zero-setup) — PostgreSQL 17 (production and CI) |
| Auth | JWT (PyJWT), httpOnly-cookie refresh tokens, bcrypt (passlib), OTP via email (aiosmtplib) or SMS (Twilio) |
| Testing | Vitest + Testing Library + MSW (frontend), pytest + pytest-asyncio + respx (backend) |
| Reverse proxy (prod) | Caddy |

---

## Project Structure

```
SpaceAdventures/
├── backend/
│   ├── app/
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── routers/        # FastAPI route handlers
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # Business logic and external API clients
│   │   ├── config.py       # Pydantic-settings configuration
│   │   ├── database.py     # Async SQLAlchemy engine and session
│   │   └── main.py         # FastAPI app factory and lifespan
│   ├── alembic/            # Database migrations
│   ├── tests/              # pytest test suite
│   │   ├── security/       # Route-authorization matrix (Architecture/25-security-testing.md)
│   │   └── perf/           # Query-count / N+1 guard (Architecture/26-performance.md)
│   ├── create_dev_user.py  # Dev helper — seeds a verified test user
│   ├── scripts/
│   │   ├── build_mission.py         # Dev-only generator for public/missions/*.json (not deployed, not imported by app/)
│   │   └── check_module_coverage.py # Per-module branch coverage gate (>= 80% for every app/**/*.py with branches)
│   ├── Dockerfile          # Production image
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/     # Shared UI components (Navbar, ErrorBanner, MissionPanel, etc.)
    │   ├── hooks/          # React Query data hooks
    │   ├── routes/         # Page components
    │   ├── solar/          # Solar-system 3D scene engine, orbit math, mission data model
    │   ├── lib/            # API client, date helpers
    │   ├── locales/        # i18n translation files (en, de, es, fr, ja, ru)
    │   └── msw/            # Mock Service Worker handlers for tests
    ├── public/missions/    # Static mission JSON (index.json + one file per mission slug)
    ├── public/models/      # Static 3D assets (rover viewer + mission vignette glTF models, CREDITS.md)
    ├── scripts/
    │   ├── validate-missions.mjs # Validates public/missions/*.json against the mission schema
    │   └── vrml-convert/   # Dev-only VRML(.wrl)→glTF converter used to produce mission vignette assets
    ├── __tests__/          # Vitest test suite
    ├── Dockerfile.dev      # Dev image (Vite HMR)
    └── vite.config.ts
```

---

## Environment Variables

Copy the example file and fill in values before starting the backend.

```bash
cp .env.example backend/.env
```

| Variable | Required | Description |
|---|---|---|
| `NASA_API_KEY` | No | NASA Open APIs key. `DEMO_KEY` works for dev (30 req/hr). Get a free key at [api.nasa.gov](https://api.nasa.gov). |
| `N2YO_API_KEY` | No | N2YO satellite tracking key. ISS page works without it but won't fetch live positions. |
| `DEEPL_API_KEY` | No | DeepL API key used to translate launch/APOD/etc. text into de/fr/es/ja/ru. Leave blank to fall back to English text (the sync never fails because of it). |
| `DEEPL_BASE_URL` | No | DeepL API base URL. Defaults to the free-tier endpoint `https://api-free.deepl.com`; use `https://api.deepl.com` for a paid plan. |
| `JWT_SECRET_KEY` | **Yes** | Secret used to sign access tokens. Use any long random string in dev. |
| `UNSUBSCRIBE_SECRET_KEY` | **Yes** | Secret used to sign unsubscribe tokens. |
| `ADMIN_API_KEY` | **Yes** | Key for protected admin endpoints. |
| `DATABASE_URL` | No | SQLAlchemy async URL. Defaults to `sqlite+aiosqlite:///./data/app.db`. Set to `postgresql+asyncpg://user:pass@host:5432/dbname` in production and CI. |
| `DATABASE_URL_SYNC` | No | Sync URL used by Alembic migrations only. Defaults to `sqlite:///./data/app.db`. Set to `postgresql+psycopg://user:pass@host:5432/dbname` in production and CI (must point at the same database as `DATABASE_URL`). |
| `DB_POOL_SIZE` | No | SQLAlchemy connection pool size. Only applied when `DATABASE_URL` is `postgresql+asyncpg://…` (ignored for SQLite). Defaults to `10`. |
| `DB_MAX_OVERFLOW` | No | Extra connections allowed beyond `DB_POOL_SIZE` under load. Only applied for Postgres. Defaults to `20`. |
| `FRONTEND_ORIGIN` | No | CORS allowed origin, and the base URL used to build canonical/OG/sitemap URLs for the SEO launch pages. Defaults to `http://localhost:5173`. |
| `FRONTEND_DIST_PATH` | No | Filesystem path to the built frontend (`frontend/dist`) — the SEO launch-page and sitemap routes (`/launches/:id`, `/sitemap.xml`) read `index.html` and `missions/index.json` from here. Defaults to `../frontend/dist`. In production this must point at the same `frontend-dist` volume Caddy serves static files from (see `docker-compose.prod.yml`); a crawler hitting these routes before the frontend has been built gets a 503. |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | No | Leave blank to disable email sending in dev. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | No | Leave blank to disable SMS in dev. |
| `COOKIE_SECURE` | No | `Secure` attribute on the refresh-token cookie. Defaults to `true`; set to `false` only for plain-HTTP local dev. |
| `TRUST_PROXY_HEADERS` | No | Honor `X-Forwarded-For` for IP-based rate limiting. Defaults to `false`; set to `true` only when running behind a proxy you control (Caddy in prod) — trusting it otherwise lets clients spoof their rate-limit bucket. |
| `EXPOSE_DOCS` | No | Serve `/docs` and `/openapi.json`. Defaults to `false`; enable only in non-prod deploys. |
| `SCHEDULER_IN_APP` | No | Run the APScheduler job registry inside this process. Defaults to `false`. `docker-compose.yml` sets this for the dev backend container; set it in your own `.env` too if you run `uvicorn` directly instead of via docker compose. Never set in prod — the dedicated `worker` service (`python -m app.worker`) runs jobs there instead. |
| `WEB_CONCURRENCY` | No | Uvicorn worker process count for the backend service in production (`docker-compose.prod.yml`). Defaults to `4`. Safe to scale — the web tier is stateless and never schedules jobs. Not used in dev (dev pins `--workers 1`). |
| `SENTRY_DSN` | No | Sentry error reporting DSN, read by both the `backend` and `worker` processes. Leave blank to disable — Sentry is never a hard dependency. |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | No | Web Push VAPID keypair (raw base64url, not PEM) — see the generation snippet in `.env.example`. Leave blank to disable push sending; `/api/v1/push/vapid-public-key` returns an empty key and the frontend won't offer the push channel. |
| `VAPID_CLAIMS_EMAIL` | No | Contact email sent in the VAPID JWT `sub` claim (`mailto:` prefix added automatically), used by push services to reach you about your server's push traffic. |

> **Note:** The backend starts without the three required secrets (`JWT_SECRET_KEY`, `UNSUBSCRIBE_SECRET_KEY`, `ADMIN_API_KEY`) when `APP_REQUIRE_SECRETS` is not set to `1` (the default for dev). When required, each must be at least 32 characters. Auth endpoints still work without them in dev; JWT tokens are signed with whatever key is configured.
>
> **Note:** Refresh tokens are issued as an httpOnly `Secure` cookie (not returned in the response body), and `/login`, `/refresh`, `/verify/resend` are IP rate-limited (sliding window, backed by `rate_limit_events` so it works correctly across multiple web workers) — see `app/rate_limit.py`.

---

## Development Deployment

Requirements: Python 3.12+, Node 20+.

### 1 — Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment file
cp ../.env.example .env
# At minimum set JWT_SECRET_KEY, UNSUBSCRIBE_SECRET_KEY, ADMIN_API_KEY

# Run database migrations
alembic upgrade head

# Start with hot reload (single worker — see SCHEDULER_IN_APP below)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --workers 1
```

Set `SCHEDULER_IN_APP=1` in your `.env` if you want background jobs (LL2 sync,
notifications, etc.) to run locally when starting the backend this way. Two
`--workers` would both run the scheduler with nothing to serialize them under
SQLite (`FOR UPDATE` is a no-op there), so keep `--workers 1` whenever
`SCHEDULER_IN_APP=1`. Alternatively, run the worker as its own process:

```bash
python -m app.worker
```

The API is now available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 2 — Frontend

```bash
cd frontend

npm install
npm run dev
```

The app is available at `http://localhost:5173`. The Vite dev server proxies `/api/*` requests to `http://localhost:8000`.

### 3 — Test user

SMTP is not required in dev. Use the seed script to create a pre-verified account you can log in with immediately:

```bash
cd backend
source .venv/bin/activate

python create_dev_user.py
# Created dev user (id=1):
#   Email:    dev@local.test
#   Password: devpassword123
```

Custom credentials:

```bash
python create_dev_user.py --email you@example.com --password mypassword --first Jane --last Doe
```

Running the script twice with the same email is safe — it detects the existing user and does nothing.

Log in at `http://localhost:5173/login`.

---

## Production Deployment

The production stack is **4 containers** (see `docker-compose.prod.yml`): **Caddy** (reverse proxy + TLS),
**backend** (stateless Uvicorn web tier, `WEB_CONCURRENCY` workers — safe to scale, it never schedules jobs),
**worker** (dedicated `python -m app.worker` process — the only process that runs scheduled jobs, each job
guarded by a Postgres advisory lock), and **db** (PostgreSQL 17). Full first-deploy runbook, environment file
template, and the backup/restore procedure: `Architecture/12-deployment.md`.

### 1 — Backend

```bash
cp .env.prod.example .env.prod   # fill in secrets, POSTGRES_PASSWORD, etc. — see 12-deployment.md
chmod 600 .env.prod

# Start Postgres first, then run migrations against it
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend alembic upgrade head

# Start the rest of the stack
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

Run migrations again after any schema change:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

### 2 — Frontend

Build the static bundle and serve it from Caddy:

```bash
cd frontend
npm ci
VITE_SENTRY_DSN=<your-frontend-dsn> npm run build   # outputs to frontend/dist/
```

`VITE_SENTRY_DSN` is optional — leave it unset to skip Sentry entirely (the SDK
is lazily imported and never lands in the bundle when unset). Copy
`frontend/dist/` to your server (e.g. `/srv/space-adventures/`).

### 3 — Caddy

Caddy terminates TLS, serves the static frontend, and reverse-proxies API calls to the backend. The
`/launches/*` and `/sitemap.xml` paths must also be proxied to the backend rather than served as static
files — it reads the same built `index.html` off the shared `frontend-dist` volume and injects SEO
meta/OG/JSON-LD tags before returning it (`Architecture/23-seo-widgets-and-growth.md` B2). Minimal `Caddyfile`:

```caddy
yourdomain.com {
    root * /srv/space-adventures/dist
    file_server

    # Proxy API requests to the backend
    reverse_proxy /api/* localhost:8000

    # SEO launch pages + sitemap — must hit the backend, not file_server
    @seo path /launches/* /*/launches/* /sitemap.xml
    reverse_proxy @seo localhost:8000

    # SPA fallback — non-asset routes serve index.html
    try_files {path} /index.html
}
```

See the repo-root `Caddyfile` for the full production config (HSTS/CSP headers, rate limiting,
`/robots.txt`, health checks).

---

## Mission Replay Content Tooling

Mission Replay data (`frontend/public/missions/*.json`) is static content generated
offline — nothing in this section runs in production or is imported by the app.

```bash
cd backend
source .venv/bin/activate

# Curated keyframes (crewed missions with no Horizons ephemeris, e.g. Apollo 11)
python scripts/build_mission.py from-yaml scripts/data/apollo11-keyframes.yaml \
  --sample-step-seconds 900

# Real JPL Horizons trajectory (e.g. Mars Pathfinder)
python scripts/build_mission.py horizons \
  --spk -530 --frame heliocentric --bodies earth,mars \
  --start 1996-12-04 --stop 1997-07-04 --step 1d \
  --slug mars-pathfinder --name-key missions.marsPathfinder.name \
  --milestones scripts/data/mars-pathfinder-milestones.yaml
```

Both paths write `frontend/public/missions/<slug>.json` and update
`frontend/public/missions/index.json`. Validate the output against the mission
schema (also run in CI) before committing:

```bash
cd frontend
npm run validate:missions
```

A milestone can optionally reference a 3D vignette (`vignette.model`, `.environment`,
`.cameraOrbit`, `.narrationKey`) — see `Architecture/27-mission-simulations-3d.md`.
Vignette glTF assets live in `frontend/public/models/missions/`; provenance and the
VRML→glTF conversion pipeline used for the Pathfinder assets are documented in
`frontend/public/models/CREDITS.md`.

```sh
# Re-run the VRML(.wrl)→glTF conversion for a mission vignette asset
cd frontend
node scripts/vrml-convert/convert.mjs <input.wrl> <output.glb>
```

---

## Running Tests

### Backend

```bash
cd backend
source .venv/bin/activate

# All tests with branch coverage (minimum 80 %)
pytest --cov=app --cov-branch --cov-fail-under=80

# HTML report
pytest --cov=app --cov-branch --cov-report=html
open htmlcov/index.html

# Per-module coverage gate — fails if any app/**/*.py file with >= 1 branch
# is below 80%, even if the global number above looks fine. pytest.ini already
# writes coverage.json on every run (--cov-report=json), so this just needs:
python scripts/check_module_coverage.py
```

`tests/security/` (route-authorization matrix) and `tests/perf/` (query-count /
N+1 guard) run as part of the normal `pytest` invocation above — see
`Architecture/25-security-testing.md` and `Architecture/26-performance.md`.

The suite runs against an in-memory SQLite database by default. To run it
against Postgres instead (as CI does — `16-postgres-migration.md` P2.5), point
`DATABASE_URL` at a running Postgres instance before invoking pytest:

```bash
docker run -d --rm --name sa-test-pg -e POSTGRES_USER=sa -e POSTGRES_PASSWORD=sa \
  -e POSTGRES_DB=sa_test -p 5432:5432 postgres:17-alpine
DATABASE_URL=postgresql+asyncpg://sa:sa@localhost:5432/sa_test pytest --cov=app --cov-branch
```

### Frontend

```bash
cd frontend

# All tests
npm test

# With branch coverage report (minimum 80 %)
npm run test:coverage
```

---

## External API Keys

| Service | Where to get it | Free tier |
|---|---|---|
| NASA Open APIs | [api.nasa.gov](https://api.nasa.gov) | 1 000 req/day |
| N2YO | [n2yo.com/login](https://www.n2yo.com/login/) | 1 000 transactions/hr |

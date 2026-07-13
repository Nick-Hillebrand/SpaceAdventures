# Space Adventures

A multilingual web application that fetches, caches, and visualises NASA data and live space events.

**Features**

- **APOD** — Astronomy Picture of the Day with date picker and HD image viewer
- **ISS Tracker** — Live 3D globe tracking the International Space Station
- **Rocket Launches** — Upcoming launches in grid or calendar view with countdown timers and livestream links
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
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, SQLite |
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
│   ├── create_dev_user.py  # Dev helper — seeds a verified test user
│   ├── scripts/
│   │   └── build_mission.py # Dev-only generator for public/missions/*.json (not deployed, not imported by app/)
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
| `JWT_SECRET_KEY` | **Yes** | Secret used to sign access tokens. Use any long random string in dev. |
| `UNSUBSCRIBE_SECRET_KEY` | **Yes** | Secret used to sign unsubscribe tokens. |
| `ADMIN_API_KEY` | **Yes** | Key for protected admin endpoints. |
| `DATABASE_URL` | No | SQLAlchemy async URL. Defaults to `sqlite+aiosqlite:///./data/app.db`. |
| `FRONTEND_ORIGIN` | No | CORS allowed origin. Defaults to `http://localhost:5173`. |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | No | Leave blank to disable email sending in dev. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | No | Leave blank to disable SMS in dev. |
| `COOKIE_SECURE` | No | `Secure` attribute on the refresh-token cookie. Defaults to `true`; set to `false` only for plain-HTTP local dev. |
| `TRUST_PROXY_HEADERS` | No | Honor `X-Forwarded-For` for IP-based rate limiting. Defaults to `false`; set to `true` only when running behind a proxy you control (Caddy in prod) — trusting it otherwise lets clients spoof their rate-limit bucket. |
| `EXPOSE_DOCS` | No | Serve `/docs` and `/openapi.json`. Defaults to `false`; enable only in non-prod deploys. |

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

# Start with hot reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --workers 1
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

The production setup runs the backend behind **Caddy** as a reverse proxy. Uvicorn must always use `--workers 1` because the APScheduler launch-sync job is process-local.

### 1 — Backend

```bash
cd backend

# Build the Docker image
docker build -t space-adventures-backend .

# Run — supply all required env vars
docker run -d \
  --name sa-backend \
  -p 127.0.0.1:8000:8000 \
  -v sa-data:/app/data \
  -e APP_REQUIRE_SECRETS=1 \
  -e NASA_API_KEY=your-nasa-key \
  -e N2YO_API_KEY=your-n2yo-key \
  -e JWT_SECRET_KEY=long-random-secret \
  -e UNSUBSCRIBE_SECRET_KEY=long-random-secret \
  -e ADMIN_API_KEY=long-random-secret \
  -e FRONTEND_ORIGIN=https://yourdomain.com \
  -e SMTP_HOST=smtp.example.com \
  -e SMTP_USER=no-reply@example.com \
  -e SMTP_PASSWORD=... \
  -e SMTP_FROM=no-reply@example.com \
  space-adventures-backend
```

Run migrations on first deploy and after any schema changes:

```bash
docker exec sa-backend alembic upgrade head
```

### 2 — Frontend

Build the static bundle and serve it from Caddy:

```bash
cd frontend
npm ci
npm run build          # outputs to frontend/dist/
```

Copy `frontend/dist/` to your server (e.g. `/srv/space-adventures/`).

### 3 — Caddy

Caddy terminates TLS, serves the static frontend, and reverse-proxies API calls to the backend. Minimal `Caddyfile`:

```caddy
yourdomain.com {
    root * /srv/space-adventures/dist
    file_server

    # Proxy API requests to the backend
    reverse_proxy /api/* localhost:8000

    # SPA fallback — non-asset routes serve index.html
    try_files {path} /index.html
}
```

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

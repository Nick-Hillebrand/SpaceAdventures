# Stack, Repository Structure & Navigation

## Tech Stack

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
| Caching layer | Database-backed permanent cache (see `03-caching-strategy.md`) |
| 3D Globe | Globe.gl (MIT licence, Three.js-based) |
| Calendar | FullCalendar React v6 (`@fullcalendar/react` + `@fullcalendar/daygrid`). Both packages are MIT in v6 when used without premium plugins. Do NOT add any `@fullcalendar/premium` or scheduler plugins. Set `editable: false` (calendar is read-only). |
| Auth (backend) | python-jose[cryptography] (JWT) + passlib[bcrypt] (password hashing) |
| Email (backend) | aiosmtplib — async SMTP, works with any provider |
| SMS (backend) | Twilio Python SDK |
| Backend testing | pytest + pytest-asyncio + pytest-cov + httpx (AsyncClient for route tests) + respx (httpx mock) |
| Frontend testing | Vitest + React Testing Library + @testing-library/user-event + MSW v2 |
| Coverage enforcement | pytest-cov branch mode; @vitest/coverage-v8 branch mode |
| Reverse proxy / TLS | Caddy v2 (automatic Let's Encrypt, HTTP→HTTPS redirect, static file serving) |
| Containerisation | Docker + docker-compose (dev) / docker-compose.prod.yml (production) |
| Linting / formatting | Ruff (Python), ESLint + Prettier (TS) |

---

## Repository Structure

```
space-adventures/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, router registration, lifespan
│   │   ├── config.py                # Settings via pydantic-settings (reads .env); startup validation
│   │   ├── database.py              # Async SQLAlchemy engine + session factory + SQLite FK pragma
│   │   ├── models/
│   │   │   ├── apod.py
│   │   │   ├── neo.py
│   │   │   ├── space_weather.py
│   │   │   ├── mars.py
│   │   │   ├── iss.py
│   │   │   ├── launches.py
│   │   │   ├── user.py
│   │   │   ├── subscription.py
│   │   │   ├── notification_log.py
│   │   │   └── n2yo_quota.py
│   │   ├── routers/
│   │   │   ├── apod.py
│   │   │   ├── neo.py
│   │   │   ├── space_weather.py
│   │   │   ├── mars.py
│   │   │   ├── iss.py
│   │   │   ├── launches.py
│   │   │   ├── auth.py
│   │   │   └── subscriptions.py
│   │   ├── services/
│   │   │   ├── nasa_client.py       # Shared httpx.AsyncClient + connectivity probe
│   │   │   ├── n2yo_client.py       # N2YO client with quota guard
│   │   │   ├── ll2_client.py        # Launch Library 2 client
│   │   │   ├── apod_service.py
│   │   │   ├── neo_service.py
│   │   │   ├── space_weather_service.py
│   │   │   ├── mars_service.py
│   │   │   ├── iss_service.py
│   │   │   ├── launches_service.py  # sync + change detection + notification dispatch
│   │   │   ├── auth_service.py
│   │   │   ├── subscription_service.py
│   │   │   └── notification_service.py
│   │   └── schemas/
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
│   │   ├── conftest.py
│   │   ├── test_apod.py
│   │   ├── test_neo.py
│   │   ├── test_space_weather.py
│   │   ├── test_mars.py
│   │   ├── test_iss.py
│   │   ├── test_n2yo_quota.py
│   │   ├── test_launches.py
│   │   ├── test_auth.py
│   │   ├── test_subscriptions.py
│   │   └── test_notifications.py
│   ├── pytest.ini
│   ├── requirements.txt
│   └── Dockerfile                   # production (installs libffi-dev/gcc for bcrypt)
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/
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
│   │   ├── components/
│   │   │   ├── Navbar.tsx
│   │   │   ├── LanguageSwitcher.tsx
│   │   │   ├── SubscribeModal.tsx
│   │   │   └── ErrorBanner.tsx
│   │   ├── hooks/
│   │   ├── lib/
│   │   │   ├── api.ts               # fetch wrapper; stores JWT in localStorage (XSS risk documented here)
│   │   │   ├── i18n.ts
│   │   │   └── dateTime.ts          # ONLY place that formats dates/times — see 09-frontend-shared.md
│   │   ├── locales/
│   │   │   ├── en.json
│   │   │   ├── de.json
│   │   │   ├── fr.json
│   │   │   ├── ja.json
│   │   │   ├── ru.json
│   │   │   └── es.json
│   │   ├── types/
│   │   └── msw/
│   │       └── handlers.ts
│   ├── __tests__/
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
│   │   └── hooks/
│   ├── public/                      # includes mockServiceWorker.js (generated once by npx msw init public/)
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── Dockerfile                   # production multi-stage build
│   └── Dockerfile.dev               # dev: runs Vite dev server
├── docker-compose.yml               # development only
├── docker-compose.prod.yml          # production
├── Caddyfile
├── .env.example
├── .env.prod.example
└── Architecture/
    ├── CLAUDE.md                    # root manifest (also at repo root)
    ├── 00-stack-and-structure.md    # this file
    ├── 01-database-schemas.md
    ├── 02-api-routes.md
    ├── 03-caching-strategy.md
    ├── 04-nasa-apis.md
    ├── 05-iss-tracker.md
    ├── 06-launches.md
    ├── 07-auth.md
    ├── 08-subscriptions.md
    ├── 09-frontend-shared.md
    ├── 10-security.md
    ├── 11-testing.md
    └── 12-deployment.md
```

---

## Navigation & Pages

The app uses a persistent top navigation bar:

| Route | Page | Description |
|---|---|---|
| `/` | Astronomy Picture of the Day | Hero image/video, title, explanation, date picker |
| `/neo` | Near-Earth Objects | Sortable table, date-range picker, detail drawer |
| `/space-weather` | Space Weather | Solar flares, geomagnetic storms, CMEs, SEP, RBE |
| `/mars` | Mars Explorer | Rover selector, sol/date picker, camera filter, photo grid |
| `/iss` | ISS Tracker | Live 3D globe, position data panel, pass predictions |
| `/launches` | Rocket Launches | Card grid + calendar toggle, countdown, livestream links |
| `/settings` | Settings | Language selector, API key entry |
| `/login` | Login | Not in nav — via user icon top-right |
| `/register` | Register | Not in nav — linked from Login |
| `/account` | My Account | Not in nav — via user icon dropdown when logged in |
| `/confirm-unsubscribe?token=…` | Confirm Unsubscribe | Not in nav — linked from notification emails; requires explicit POST to complete |

# Space Adventures — Claude Code Manifest

Space Adventures is a multilingual web app that fetches, caches, and visualises NASA data and live space events. Frontend: React 18 + TypeScript + Vite. Backend: Python 3.12 + FastAPI + SQLAlchemy async + SQLite.

All detailed specs live in `Architecture/`. Read only the files listed for each step — do not load the entire Architecture folder into context at once.

---

## Non-Negotiable Rules (always apply, every step)

1. **Tests ship with the feature.** Every step ends with ≥ 80 % branch coverage and all tests green. Never defer tests. See `Architecture/11-testing.md`.
2. **Security rules are absolute.** Read `Architecture/10-security.md` before writing any auth, subscription, or notification code. Never skip a security constraint.
3. **No hardcoded English strings in JSX.** Every user-visible string uses an i18n key via `t()`. See `Architecture/09-frontend-shared.md`.
4. **All dates/times in the UI use `src/lib/dateTime.ts`.** Never call `.toLocaleString()` or hardcode a timezone. See `Architecture/09-frontend-shared.md`.
5. **Read `Architecture/11-testing.md` §Pitfalls (P1–P35) before implementing each feature area.** These are known failure modes — do not reproduce them.
6. **The backend is always behind Caddy in production.** Never expose Uvicorn directly. See `Architecture/12-deployment.md`.
7. **`--workers 1` always.** APScheduler requires a single Uvicorn process. See `Architecture/06-launches.md`.

---

## Implementation Order

Implement in this exact sequence. Do not start a step until the previous step's tests pass and coverage is ≥ 80 %.

### Step 1 — Scaffold & test harness
**Read:** `Architecture/00-stack-and-structure.md`, `Architecture/11-testing.md`

- Initialise Vite + React + TypeScript frontend
- Initialise FastAPI backend with a hello-world route
- Add `docker-compose.yml` (dev only)
- Configure pytest: `--cov-branch --cov-fail-under=80`
- Configure Vitest: `coverage.branches: 80`, `build.sourcemap: false`
- Add MSW: run `npx msw init public/`, commit `public/mockServiceWorker.js`, write `src/msw/setup.ts`
- Add `conftest.py` with async DB session fixture and `httpx.AsyncClient` test client
- Verify both apps start and both test runners execute

### Step 2 — Database + Migrations
**Read:** `Architecture/01-database-schemas.md`, `Architecture/11-testing.md` §P23–P25

- Implement all SQLAlchemy ORM models
- Add Alembic; run first migration (use sync URL — see P5)
- Add SQLite foreign key pragma (P25)
- Verify DB creates on startup
- Write shared DB fixtures used by all subsequent backend tests

### Step 3 — NASA Client & config
**Read:** `Architecture/03-caching-strategy.md`, `Architecture/02-api-routes.md`, `Architecture/10-security.md`, `Architecture/11-testing.md` §P1, P6

- Implement `config.py` with pydantic-settings and startup validation
- Implement `nasa_client.py`: shared `httpx.AsyncClient` (lifespan-scoped, P6), connectivity probe, structured error codes
- Write tests for all error branches using `respx` (P27)

### Step 4 — APOD feature
**Read:** `Architecture/04-nasa-apis.md` §APOD, `Architecture/02-api-routes.md`, `Architecture/03-caching-strategy.md`, `Architecture/09-frontend-shared.md`, `Architecture/11-testing.md`

- Backend: `apod_service.py`, `routers/apod.py`, `schemas/apod.py`
- Frontend: `useApod` hook, `ApodPage.tsx` with date picker, hero display, cached/live badge
- Tests: `test_apod.py` (cache hit, miss, today re-fetch, stale fallback, all error codes), `ApodPage.test.tsx` (happy, loading, error, empty)

### Step 5 — NEO feature
**Read:** `Architecture/04-nasa-apis.md` §NEO, same shared files as Step 4

- Backend: `neo_service.py`, router, schema
- Frontend: `NeoPage.tsx` with date-range picker, sortable table, detail drawer
- Tests: same pattern as Step 4

### Step 6 — Space Weather feature
**Read:** `Architecture/04-nasa-apis.md` §Space Weather, same shared files

- Backend: `space_weather_service.py`, router, schema (five DONKI event types)
- Frontend: `SpaceWeatherPage.tsx` with tabbed sub-sections
- Tests: cover all five event types

### Step 7 — Mars feature
**Read:** `Architecture/04-nasa-apis.md` §Mars, same shared files

- Backend: `mars_service.py`, router, schema
- Frontend: `MarsPage.tsx` with rover selector, sol/date picker, camera filter, paginated photo grid
- Tests: rover selector, camera filter, pagination branches

### Step 8 — ISS feature
**Read:** `Architecture/05-iss-tracker.md`, `Architecture/01-database-schemas.md` §N2YO, `Architecture/02-api-routes.md`, `Architecture/10-security.md`, `Architecture/11-testing.md` §P4, P11–P13, P17

- Backend: `n2yo_quota` model, quota-guard with asyncio.Lock (P4), `n2yo_client.py` (P12), `iss_service.py`, ISS router
- Frontend: Globe.gl `IssPage.tsx` (P13, P17), position interpolation, data panel, quota badge
- Tests: `test_n2yo_quota.py` (concurrent boundary, window reset), `test_iss.py`, `IssPage.test.tsx` (mock globe.gl entirely — P28)

### Step 9 — Launches feature
**Read:** `Architecture/06-launches.md`, `Architecture/01-database-schemas.md` §Launches, `Architecture/02-api-routes.md`, `Architecture/09-frontend-shared.md`, `Architecture/11-testing.md` §P3, P14–P16, P18

- Backend: `ll2_client.py` (P14–P16), `launches` model, APScheduler sync in lifespan (P3), change detection, launches router
- Frontend: `LaunchesPage.tsx` — grid view, calendar toggle (P18), countdown, filter bar, livestream button
- Tests: `test_launches.py` (upsert, change detection, NET slip threshold, Gone marking), `LaunchesPage.test.tsx`

### Step 10 — Auth feature
**Read:** `Architecture/07-auth.md`, `Architecture/01-database-schemas.md` §Auth, `Architecture/02-api-routes.md`, `Architecture/10-security.md`, `Architecture/11-testing.md` §P7–P10

- Backend: `users`, `otps`, `refresh_tokens`, `login_attempts` models; `auth_service.py`; auth router
- Frontend: `LoginPage.tsx`, `RegisterPage.tsx` with inline OTP step, Navbar user widget
- Tests: all branches in `Architecture/11-testing.md` §Auth tests

### Step 11 — Subscriptions & Notifications
**Read:** `Architecture/08-subscriptions.md`, `Architecture/01-database-schemas.md` §Subscriptions, `Architecture/02-api-routes.md`, `Architecture/10-security.md`, `Architecture/11-testing.md` §P2, P32, P33

- Backend: `subscription_service.py`, `notification_service.py` (P32, P33), change-detection wiring in `launches_service.py`
- Frontend: `<SubscribeModal>`, bell icons on launch cards, `AccountPage.tsx`, `/confirm-unsubscribe` route
- Tests: `test_subscriptions.py`, `test_notifications.py` (mock SMTP + Twilio), `SubscribeModal.test.tsx`, `AccountPage.test.tsx`

### Step 12 — i18n
**Read:** `Architecture/09-frontend-shared.md` §i18n, `Architecture/11-testing.md` §P19

- Install i18next; set `load: 'languageOnly'` (P19)
- Create all six locale files (`en`, `de`, `fr`, `ja`, `ru`, `es`) with all keys
- Wrap every JSX string in `t()`
- Add locale-switching assertion to each existing page test

### Step 13 — Settings Page
**Read:** `Architecture/09-frontend-shared.md` §Settings, `Architecture/02-api-routes.md`, `Architecture/10-security.md`

- `SettingsPage.tsx`: language switcher, NASA key input, N2YO key input
- Backend: `GET /api/v1/settings`, `POST /api/v1/settings/nasa-api-key`, `POST /api/v1/settings/n2yo-api-key`
- Tests: settings endpoints, frontend form

### Step 14 — Polish
**Read:** `Architecture/09-frontend-shared.md` §Error Handling

- Loading skeletons, error boundaries, empty-state illustrations
- Responsive layout, dark mode (Tailwind `dark:` classes)
- Add/update tests for skeleton and empty-state branches

### Step 15 — Final coverage audit
- Run `pytest --cov-report=html` — fix any module below 80 % branch coverage
- Run `vitest run --coverage` — fix any module below 80 % branch coverage
- All tests must be green before done

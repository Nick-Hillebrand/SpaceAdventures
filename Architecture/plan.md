# Space Adventures — Implementation Plan

This document is the authoritative specification for Claude Code to implement the **Space Adventures** web application. Follow it top-to-bottom; every section contains decisions already made — do not re-ask the user about them.

---

## 1. Project Overview

**Space Adventures** is a multilingual, data-rich web application that fetches, caches, and visualises data from the free NASA APIs. The frontend is React; the backend is Python (FastAPI). All NASA data is persisted in a local database to minimise API calls and stay well within NASA's rate limits (1 000 requests / hour on the demo key; use a registered key).

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
│   │   │   └── mars.py
│   │   ├── routers/                 # FastAPI routers (one per tab)
│   │   │   ├── apod.py
│   │   │   ├── neo.py
│   │   │   ├── space_weather.py
│   │   │   └── mars.py
│   │   ├── services/                # Business logic: fetch NASA → cache → return
│   │   │   ├── nasa_client.py       # Shared async httpx client + rate-limit guard
│   │   │   ├── apod_service.py
│   │   │   ├── neo_service.py
│   │   │   ├── space_weather_service.py
│   │   │   └── mars_service.py
│   │   └── schemas/                 # Pydantic response schemas (mirrors frontend types)
│   │       ├── apod.py
│   │       ├── neo.py
│   │       ├── space_weather.py
│   │       └── mars.py
│   ├── alembic/
│   ├── tests/
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
│   │   │   └── SettingsPage.tsx
│   │   ├── components/              # Shared UI components
│   │   │   ├── Navbar.tsx
│   │   │   ├── LanguageSwitcher.tsx
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
| `/settings` | Settings | Language selector, API key entry, cache TTL configuration |

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
```

All responses return `{ data: …, cached: bool, fetched_at: ISO8601, is_today: bool }` envelope.

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
  "nav": { "apod": "Picture of the Day", "neo": "Near-Earth Objects", "spaceWeather": "Space Weather", "mars": "Mars Explorer", "settings": "Settings" },
  "apod": { "title": "Astronomy Picture of the Day", "explanation": "Explanation", "copyright": "Copyright", "noImage": "No image available" },
  "neo": { "title": "Near-Earth Objects", "hazardous": "Potentially Hazardous", "diameter": "Diameter", "velocity": "Velocity", "missDistance": "Miss Distance" },
  "spaceWeather": { "title": "Space Weather", "flares": "Solar Flares", "storms": "Geomagnetic Storms", "cme": "Coronal Mass Ejections" },
  "mars": { "title": "Mars Explorer", "selectRover": "Select Rover", "selectCamera": "Select Camera", "sol": "Sol" },
  "settings": { "title": "Settings", "language": "Language", "apiKey": "NASA API Key" },
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

There are no TTL or cache-expiry settings — the cache is permanent by design. The Settings page does **not** expose any cache-management controls.

The API key entered in Settings is forwarded from the frontend to the backend via a `POST /api/v1/settings/api-key` endpoint; the backend stores it in-process (not on disk) and uses it for all subsequent NASA requests during that server session.

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

## 12. Implementation Order for Claude Code

Implement in this exact order to keep the app runnable at each step:

1. **Scaffold** — initialise Vite + React + TypeScript frontend; initialise FastAPI backend with hello-world route; add docker-compose; verify both start.
2. **Database + Migrations** — add SQLAlchemy models for all four domains; run first Alembic migration; verify DB creates on startup.
3. **NASA Client** — implement `nasa_client.py` with API key injection and error handling; add `config.py` with pydantic-settings.
4. **APOD feature** — backend service + router + Pydantic schema; frontend `useApod` hook + `ApodPage` with date picker, hero display, cached/live badge.
5. **NEO feature** — backend service + router; frontend `useNeoFeed` hook + `NeoPage` with date-range picker, sortable table, detail drawer.
6. **Space Weather feature** — backend services for all five DONKI endpoints; frontend `SpaceWeatherPage` with tabbed sub-sections per event type and timeline/card layout.
7. **Mars feature** — backend service + router; frontend `MarsPage` with rover selector, sol/date picker, camera filter, paginated photo grid with lightbox.
8. **i18n** — install i18next; wire `i18n.ts`; add all six locale files with complete keys; wrap all JSX strings in `t()`; test language switching.
9. **Settings Page** — language switcher, API key input; connect to backend `POST /api/v1/settings/api-key` endpoint.
10. **Polish** — loading skeletons, error boundaries, empty-state illustrations, responsive layout, dark mode (Tailwind `dark:` classes).

---

## 13. Environment Variables

```dotenv
# .env.example
NASA_API_KEY=your_key_here          # Register free at https://api.nasa.gov/
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

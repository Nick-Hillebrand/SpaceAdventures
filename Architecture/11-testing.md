# Testing Requirements

---

## Coverage Gate

**≥ 80 % branch coverage on both backend and frontend at all times.** Test runners exit non-zero if coverage drops below this. A feature is not done until tests pass and coverage is met.

### Backend — pytest.ini

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

Run: `pytest`

### Frontend — vite.config.ts

```ts
build: {
  sourcemap: false,  // MUST be false in production
},
test: {
  environment: "jsdom",
  setupFiles: ["./src/msw/setup.ts"],
  coverage: {
    provider: "v8",
    branches: 80,
    reporter: ["text", "lcov"],
    include: ["src/**"],
    exclude: ["src/msw/**", "src/types/**", "src/locales/**"],
  },
}
```

Run: `vitest run --coverage`

---

## Backend Test Rules

1. **No real HTTP calls.** Mock NASA, N2YO, LL2, Twilio, SMTP with `respx` (for httpx) or `unittest.mock`. Never depend on network access.
2. **Real in-memory SQLite DB** for every test (create tables in fixture, drop after). Do not mock the ORM.
3. **Use `httpx.AsyncClient` with `ASGITransport`** for route tests — never `TestClient` in async test functions (causes event loop conflicts).
4. **Test every caching branch:** cache hit, cache miss, today re-fetch, stale fallback.
5. **Test every error code:** `NO_INTERNET`, `NASA_UNAVAILABLE`, `NASA_ERROR`, `NASA_AUTH_ERROR`, `N2YO_QUOTA_EXHAUSTED`, `INTERNAL_ERROR`, `MARS_ARCHIVE_UNAVAILABLE`, `MARS_NO_LIVE_SOURCE`.
6. **Auth tests must cover:**
   - Successful registration
   - Duplicate email/phone returns same generic error (enumeration prevention)
   - Missing both email and phone → 422
   - Wrong password
   - Expired access token
   - Invalid refresh token
   - OTP expiry
   - OTP reuse (second use → 400)
   - OTP brute-force lockout (6th wrong attempt deletes the OTP row)
   - OTP send-rate limit (6th resend in 1 hr → 429)
   - Login rate limit (6th failed attempt → 429 with `Retry-After`)
   - Concurrent refresh token rotation (two simultaneous calls with same token → only one succeeds, other gets 401)
   - Open redirect rejected (`?return=https://evil.com` → redirects to `/`)
7. **Notification tests:** mock `aiosmtplib.send` and `twilio.rest.Client.messages.create`; assert recipient, subject, body content.
8. **N2YO quota tests:** simulate two concurrent requests at `used = 899`; assert only one calls N2YO, the other returns cached data.

---

## Frontend Test Rules

1. **MSW v2 intercepts all API calls.** Use `http.get(...)` not `rest.get(...)`.
   - Setup: run `npx msw init public/` once; commit `public/mockServiceWorker.js`
   - `src/msw/setup.ts`: `server.listen()` in `beforeAll`, `server.resetHandlers()` in `afterEach`, `server.close()` in `afterAll`

2. **`renderWithProviders` utility** — wraps everything in QueryClientProvider, i18next provider, Router.

3. **Test user interactions via `userEvent`** — assert on visible text and ARIA roles, not internal state.
   - **Every `userEvent` call must be `await`ed** (v14 is fully async — missing `await` causes silent false passes).
   - Add `@typescript-eslint/no-floating-promises` to ESLint to catch this statically.

4. **Each page test must cover:**
   - Happy path
   - Loading state (skeleton/spinner visible)
   - Error state (correct `<ErrorBanner>` for each possible error code)
   - Empty state

5. **Countdown timers:** `vi.useFakeTimers({ toFake: ['Date','setTimeout','setInterval','clearInterval'] })` — explicitly exclude `requestAnimationFrame`. Restore with `vi.useRealTimers()` in `afterEach`.

6. **Globe.gl tests:** mock the entire module — do not test WebGL rendering:
   ```ts
   const { mockGlobe } = vi.hoisted(() => ({ mockGlobe: { _destructor: vi.fn() } }));
   vi.mock('globe.gl', () => ({ default: vi.fn(() => mockGlobe) }));
   ```
   Globe tests must use real timers (no `vi.useFakeTimers()`).

7. **`<SubscribeModal>` tests:** unauthenticated prompt, unverified channel prompt, successful POST with correct body, unsubscribe flow.

8. **Calendar view tests:** toggling to calendar renders FullCalendar; events have correct label and colour class; dragging is disabled (`editable: false`).

9. **Timezone tests (`src/lib/dateTime.ts`):** mock `Intl.DateTimeFormat` to simulate `America/New_York` and `Europe/London`; assert same UTC string produces different output per timezone. Each page test that renders a date/time must assert the correct `dateTime.ts` function was called — not the raw UTC string. Use only well-known IANA names (`America/New_York`, `Europe/London`, `Asia/Tokyo`) — jsdom's Intl is incomplete.

---

## `vi.mock()` Hoisting Pitfall

`vi.mock()` is hoisted to the top of the file. Variables defined below it are `undefined` at hoist time. Use `vi.hoisted()`:

```ts
const { mockInstance } = vi.hoisted(() => ({ mockInstance: { method: vi.fn() } }));
vi.mock('globe.gl', () => ({ default: vi.fn(() => mockInstance) }));
```

---

## Known Pitfalls (P1–P37)

Read the relevant pitfall before implementing each area. All pitfalls have an exact failure mode, cause, and fix.

### P1–P6: Python / FastAPI / SQLAlchemy Async
- **P1** `AsyncSession`: use `async with AsyncSession(engine) as session: yield session` — not `session = SessionLocal()`
- **P2** Lazy-loading: use `selectinload()` for any relationship accessed outside the initial query
- **P3** APScheduler: start inside `lifespan` context manager — never at module import time
- **P4** asyncio.Lock: define at module level in `n2yo_client.py` — not inside a function
- **P5** Alembic URL: use `sqlite:///` (sync) in `alembic.ini` / `env.py` — not `sqlite+aiosqlite://`
- **P6** httpx.AsyncClient: create one shared client in lifespan — not per request

### P7–P10: Authentication
- **P7** CryptContext: module-level singleton — not per request
- **P8** JWT decode: always `options={"verify_exp": True}` explicitly
- **P9** OTP rate-limit check: atomic — use Lock or `SELECT … FOR UPDATE`
- **P10** Refresh token rotation: `SELECT … FOR UPDATE` to prevent concurrent double-issue

### P11–P13: N2YO / ISS
- **P11** N2YO timestamps: Unix epoch integers — multiply by 1000 for `timestamp_ms`
- **P12** N2YO errors: HTTP 200 with `{"error": "..."}` body — always check body
- **P13** globe.gl types: no `@types/globe.gl` — add `src/types/globe.d.ts` with `declare module 'globe.gl' { const Globe: any; export default Globe; }`

### P14–P16: Launch Library 2
- **P14** `vidURLs`: may be absent — use `launch.get('vidURLs') or []`
- **P15** `net` field: use `dateutil.parser.isoparse()` — `datetime.fromisoformat()` fails on `Z` suffix in Python < 3.11
- **P16** Pagination: loop until `response['next']` is None with `limit=100`

### P17–P22: React / Vite / TypeScript
- **P17** Globe.gl ref: guard `if (!containerRef.current) return;` inside `useEffect`
- **P18** FullCalendar CSS: import `'@fullcalendar/core/main.css'` and `'@fullcalendar/daygrid/main.css'` in the component file
- **P19** i18next detector: set `load: 'languageOnly'` — `navigator.language` returns `"en-US"`, not `"en"`
- **P20** MSW v2: use `http.get()` and `HttpResponse.json()` — not `rest.get()` (v1 API)
- **P21** `?return=` redirect: encode on write; validate with `safeReturnUrl()` on read
- **P22** Vite proxy in Docker: use `process.env.VITE_API_BASE_URL ?? 'http://localhost:8000'` as target

### P23–P25: Database / Alembic / SQLite
- **P23** `DEFAULT NOW()`: SQLite has no `NOW()` — use `server_default=text("CURRENT_TIMESTAMP")`
- **P24** CHECK constraints: Alembic autogenerate omits them on SQLite — add manually after `op.create_table()`
- **P25** Foreign keys: add `PRAGMA foreign_keys=ON` via engine connect event listener in `database.py`

### P26–P29: Testing
- **P26** TestClient + async tests: use `httpx.AsyncClient(transport=ASGITransport(app=app))` — not `TestClient`
- **P27** respx scope: use `@pytest.mark.respx` decorator for test-wide mocking
- **P28** vi.mock() hoisting: use `vi.hoisted()` for variables referenced in mock factories
- **P29** userEvent v14: every call must be `await`ed

### P30–P31: Docker / Deployment
- **P30** Bind mount: mount only `./backend/app:/app/app` — not `./backend:/app` (overwrites pip packages)
- **P31** SQLite data dir: add `RUN mkdir -p /app/data` to Dockerfile

### P32–P35: Miscellaneous
- **P32** Twilio: wrap in `asyncio.to_thread()` — Twilio SDK is synchronous
- **P33** aiosmtplib: port 587 → `start_tls=True`; port 465 → `use_tls=True`
- **P34** jsdom Intl: only use well-known IANA timezone names in tests
- **P35** bcrypt C extension: add `libffi-dev python3-dev gcc` to Dockerfile before `pip install`
- **P36** three.js: no bundled types — add `src/types/three-jsm.d.ts` with loose `declare module` stubs for `'three'`, `'three/examples/jsm/loaders/GLTFLoader.js'`, and `'.../controls/OrbitControls.js'` (same convention as P13). Because `THREE` is then typed `any`, define local structural interfaces for anything that needs a shape (see `Disposable`/`MeshLike`/`Object3DLike` in `roverScene.ts`) instead of referencing `THREE.Object3D` as a type. In tests, mock `three`/`GLTFLoader`/`OrbitControls` at the module level — jsdom has no WebGL context and `THREE.WebGLRenderer`'s constructor throws (unlike 2D canvas, which returns `null` gracefully). Every scene instance registers a real `window` resize listener; track and `dispose()` each one in `afterEach`, or listeners leak across tests in the same file and a later `dispatchEvent(new Event("resize"))` fires all of them at once.
- **P37** NASA's `api.nasa.gov/mars-photos` backend (the `corincerami/mars-photo-api` Heroku app) is permanently dead — every route 404s regardless of rover or params. Replaced with `mars.nasa.gov`'s own public raw-image galleries (`mars_raw_images_client.py`), which need no API key. Only Curiosity (`/api/v1/raw_image_items/`) and Perseverance (`/rss/api/?feed=raw_images`) have a live source there; Opportunity/Spirit have none anywhere on NASA's current infrastructure (`mars_service.LIVE_ROVERS` excludes them — they serve cache-only and raise `MARS_NO_LIVE_SOURCE` otherwise). Neither live endpoint supports server-side `earth_date` filtering reliably, so `earth_date` queries approximate a sol from each rover's landing date + Mars sol length (`88775.244`s), fetch sol±1 as candidates, and filter the accurate per-item date client-side. Perseverance's raw-image items have no numeric id (`imageid` is a string) — synthesize one via `sha256(imageid)[:8]` masked to 63 bits (rejected 32-bit CRC32: ~116 expected collisions across ~1M images at that scale). Curiosity's instrument codes are more granular than the UI's camera list (`FHAZ_LEFT_A`/`_B`, `NAV_RIGHT_A`/`_B`, etc.) and must be normalized back down (`MSL_CAMERA_MAP`) rather than exposed raw. See `Architecture/14-mars-raw-images-migration.md`.

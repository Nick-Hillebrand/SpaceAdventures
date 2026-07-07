# Performance Budgets & Testing

Performance is a product feature: launch pages spike during events (the exact
moment new users judge the app), the kiosk renders 24/7 on weak hardware, and
alert latency is the product's core promise. This file defines the budgets and
how they are enforced. Budgets are CI gates, not aspirations — a change that
breaks a budget is treated like a failing test.

The capacity contract (`16-postgres-migration.md` P2.7) covers *load*; this
file covers *per-request/per-page* performance at any load.

---

## 1. Backend budgets

### 1.1 Latency (p95, measured by the k6 suite and asserted as thresholds)

| Endpoint class | p95 budget |
|---|---|
| Cached reads (launches list, APOD, NEO, ephemerides, sky events, aurora) | 150 ms |
| Auth flows (login, refresh, register) | 400 ms (bcrypt dominates — that is the budget's floor, do not "fix" it by lowering cost factor) |
| SEO-injected pages (`/launches/{id}`, `/embed/*`) | 100 ms (these take crawler + spike traffic) |
| Everything else | 300 ms |

k6 scripts in `backend/loadtest/` declare these as `thresholds` — the load-test
gate fails on breach.

### 1.2 Query budget & N+1 guard (CI-enforced)

- **Rule: a request handler executes ≤ 5 SQL statements.** List endpoints use
  explicit `selectinload()` for any relationship they serialize (P2 in
  `11-testing.md`) — lazy-load in a serializer loop is the classic breach.
- Enforcement: `tests/perf/test_query_counts.py` — a fixture registers a
  SQLAlchemy `before_cursor_execute` listener that counts statements per
  request; parametrized over every list endpoint with a seeded dataset of 100
  rows, asserts count ≤ 5 **and independent of row count** (run at 10 rows and
  100 rows; counts must be equal — that equality is the N+1 detector).
- Every new list endpoint added by any spec registers itself in this test's
  table (same pattern as the security route matrix, `25-…` §2.1).

### 1.3 Query plans & indexes

- Every new table ships its indexes in the same migration (specs 15–24 already
  enumerate them). No table without a stated index plan.
- Any query filtering/ordering on a column combination not covered by an index
  needs either a new index in the same PR or a comment justifying the seq scan
  (small table, admin-only path).
- Pagination is mandatory on every list endpoint: `limit` (default 50,
  max 200, validated) + keyset or offset. Unbounded result sets are a defect.

### 1.4 Response conventions

- `Cache-Control` on anonymous read endpoints (values already specified per
  spec: 60 s embeds, 300 s SEO pages, 3600 s ephemerides/sitemap; default for
  other anonymous cached reads: `public, max-age=60`). Authenticated responses:
  `private, no-store` unless a spec says otherwise (ical: `private, max-age=900`).
- Compression: Caddy `encode zstd gzip` on all text responses (add to the
  Caddyfile block in `12-deployment.md` during Step P3).
- Response size: list endpoints return only fields the frontend consumes —
  no `raw_json` passthrough columns in API schemas. Budget: 100 KB per list
  response at max page size; asserted in the query-count test module.

### 1.5 Worker job budgets

| Job | Budget (log + Sentry warn on breach) |
|---|---|
| `notification_drain` batch | 60 s |
| `pass_precompute`, `train_precompute` full run | 5 min |
| `noaa_poll`, `worker_heartbeat` | 10 s |
| All others | 2 min |

- Each job logs its duration (structlog field `duration_ms`) — the budget check
  is a log-based Sentry alert rule, plus a unit test asserting the timing
  wrapper is applied to every registered job.
- Long loops yield (`await asyncio.sleep(0)` per 50 items — rule from `21-…`)
  so the heartbeat never starves; the load-test gate already asserts heartbeat
  freshness under load.

---

## 2. Frontend budgets

### 2.1 Bundle size (CI gate via `size-limit` or rollup-plugin-visualizer + script)

| Chunk | Budget (gzipped) |
|---|---|
| Initial JS (entry + vendor, everything needed for first paint of `/`) | 250 KB |
| Any lazy route chunk | 200 KB |
| Three.js/Globe.gl chunks | lazy-only — **must never be in the initial chunk** |
| Embed page total (`23-…`) | 30 KB (already specified) |
| CSS total | 50 KB |

- Route-level code splitting via `React.lazy` for: SolarSystemPage, IssPage
  (globe), MarsPage (rover 3D), missions routes, kiosk. The test: build output
  script (`frontend/scripts/check-bundle.mjs`, run in CI) parses
  `dist/assets/*` and fails on budget breach or on three.js appearing in the
  entry chunk (checks by module banner comment / chunk name).
- i18n: locale JSONs are lazy-loaded per language (i18next backend or dynamic
  import) — six locales must not all ship in the initial bundle.

### 2.2 Core Web Vitals (Lighthouse CI gate)

`lighthouserc.json` in `frontend/`, run in CI against the built app (static
serve + mocked API via MSW-node or a seeded backend container):

| Metric | Budget (mobile emulation) |
|---|---|
| Performance score | ≥ 85 |
| LCP | ≤ 2.5 s |
| CLS | ≤ 0.1 |
| TBT | ≤ 300 ms |

Pages audited: `/` (APOD), `/launches`, one SEO launch page, `/missions/:slug`
(replay), `/embed/next-launch`. Kiosk is exempt from LCP (it's a persistent
display) but not from TBT.

### 2.3 Media

- All images `loading="lazy"` except the LCP hero (APOD image gets
  `fetchpriority="high"`).
- APOD/Mars/launch imagery: render the standard-res URL in layout, HD only in
  the lightbox. Fixed aspect-ratio containers (Tailwind `aspect-*`) on every
  image slot — CLS budget depends on it.
- No image proxying through the backend (NASA hosts serve their own images;
  CSP `img-src https:` already allows it).

### 2.4 3D scenes (simulator, globe, replay, kiosk)

- `renderer.setPixelRatio(Math.min(devicePixelRatio, 2))` — uncapped retina
  pixel ratios are the #1 frame-budget killer.
- Render loop pauses when the tab is hidden (`visibilitychange`) and when the
  scene is scrolled out of view (IntersectionObserver) — kiosk exempt from the
  visibility pause (it's always visible) but must still cap at 30 fps
  (`setAnimationLoop` with frame skip) to survive weak museum hardware.
- Dispose discipline per P36: every geometry/material/texture disposed on
  unmount; the existing resize-listener rule holds.
- Trajectory/orbit polylines: decimated to ≤ 5k points (rule from `22-…`);
  orbit paths computed once and cached, not per frame. Per-frame allocations
  (new `Vector3` in the loop) are banned — reuse scratch objects; add an
  ESLint-visible convention comment in each scene module.
- Target: 60 fps desktop / 30 fps kiosk floor. Manual verification per scene
  change; no automated gate (WebGL in CI is not worth the flake), but the
  budgets above are code-reviewable facts.

### 2.5 Data fetching

- React Query defaults: `staleTime` ≥ 60 s for launch/APOD/NEO data;
  `refetchOnWindowFocus: false` app-wide (spiky and pointless for
  slow-changing space data); ISS position polling is the deliberate exception
  (its own interval, already specified).
- No polling faster than the data changes: launches 60 s, aurora 5 min,
  sky events 5 min. A hook polling faster than its backing sync job is a
  defect — cross-check against the job table in `17-…` P3.2.

---

## 3. Perceived performance

- Every page keeps its v1 skeleton states; data-dependent sections render
  skeletons, never layout-shifting spinners (CLS budget).
- Optimistic UI on subscription toggles and settings writes (mutate cache,
  roll back on error) — alert setup must feel instant.
- SEO/OG pages: the injected meta mechanism (`23-…`) means link unfurls work
  even before JS loads — that is a perceived-performance feature; do not
  regress it by moving meta injection client-side.

---

## 4. CI wiring summary (added in Step P1/P3 alongside the other gates)

| Gate | Tool | Fails on |
|---|---|---|
| Query count / N+1 | pytest `tests/perf/` | count > 5 or row-count-dependent |
| Bundle budgets | `check-bundle.mjs` | any table-2.1 breach |
| Web vitals | Lighthouse CI | any table-2.2 breach |
| Latency under load | k6 thresholds (pre-launch + weekly, not per-PR) | any table-1.1 breach |
| Job duration | Sentry alert rule (runtime, not CI) | table-1.5 breach |

Per-PR CI stays fast (< 10 min): Lighthouse and bundle checks run on the built
frontend already produced by the test job; k6 is scheduled, not per-PR.

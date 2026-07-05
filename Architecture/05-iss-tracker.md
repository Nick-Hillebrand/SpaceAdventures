# ISS Tracker

Data source: N2YO API (`https://api.n2yo.com/rest/v1/satellite/`)
ISS NORAD ID: `25544`
Auth: `&apiKey=<N2YO_API_KEY>` on every request.

---

## N2YO Quota Guard

Free tier: 1 000 transactions/hour. Hard cap: `settings.n2yo_quota_cap` (default 900, read from `N2YO_QUOTA_CAP` env var — never hard-coded).

### `n2yo_quota` table
One row, always. See `01-database-schemas.md`.

### Quota check algorithm (every N2YO call)

1. Acquire asyncio.Lock (SQLite) or `SELECT … FOR UPDATE` (PostgreSQL) on the quota row.
2. If `NOW() - window_start >= 1 hour` → reset `window_start = NOW()`, `used = 0`.
3. If `used >= settings.n2yo_quota_cap` → do NOT call N2YO. Return cached data with `quota_exhausted: true`, or 429 `N2YO_QUOTA_EXHAUSTED` if no cache.
4. Call N2YO → increment `used` → upsert cache → release lock.

Lock must be released in a `finally` block to prevent deadlocks on exception.

### N2YO response validation

N2YO returns HTTP 200 even on errors. Always check the body:
```python
data = response.json()
if "error" in data:
    raise N2YOError(data["error"])
```

### Expected hourly budget

| Endpoint | Max calls/hr | Transactions |
|---|---|---|
| Positions (5-min cache) | 12 | 12 |
| TLE (6-hr cache) | 1 | 1 |
| Visual passes (1-hr cache) | ~10 | ~10 |
| Radio passes (1-hr cache) | ~10 | ~10 |
| **Total worst case** | | **~33** |

---

## N2YO Endpoints

| N2YO endpoint | Purpose | Cache |
|---|---|---|
| `positions/25544/{lat}/{lng}/{alt}/300` | 300 s of positions | 5 min; shared across all users |
| `tle/25544` | TLE data | 6 hours |
| `visualpasses/25544/{lat}/{lng}/{alt}/7/10` | Visible passes, 7 days, min 10° elevation | 1 hour per unique observer |
| `radiopasses/25544/{lat}/{lng}/{alt}/7/10` | Radio passes | 1 hour per unique observer |

**Parameter validation** (backend, before forwarding to N2YO):
- `lat` ∈ [-90, 90]
- `lng` ∈ [-180, 180]
- `alt` ∈ [0, 10000]
- Return 400 Bad Request if any value is out of range.

**Position timestamp note:** N2YO returns `timestamp` as a Unix epoch **integer** (seconds). The backend must surface `timestamp_ms = timestamp * 1000` in the API response for the frontend's arithmetic.

---

## ISS Page Frontend (`IssPage.tsx`)

### Globe

Use **Globe.gl** (npm: `globe.gl`). No `@types/globe.gl` exists — add `src/types/globe.d.ts`:
```ts
declare module 'globe.gl' { const Globe: any; export default Globe; }
```

Initialize only inside `useEffect`, after checking `containerRef.current !== null`:
```ts
useEffect(() => {
  if (!containerRef.current) return;
  const g = new Globe()(containerRef.current);
  return () => { g._destructor?.(); };
}, []);
```

Globe features:
- Day texture on the Earth surface
- ISS position marker — animated pulsing dot, updated every second by client-side interpolation
- Ground track polyline derived from TLE data
- Visibility footprint — semi-transparent circle (radius from `sataltitude`)
- Observer marker at user's Geolocation API location (fallback: 0°N 0°E if denied)

### Client-side Position Interpolation

The frontend holds the 300-entry position array and the `fetched_at` timestamp in memory.

Every 1 000 ms: `offset = Math.floor((Date.now() - fetched_at_ms) / 1000)` → pick `positions[clamp(offset, 0, 299)]`.

When `offset > 270` (30 s before batch end): invalidate the positions query via `queryClient.invalidateQueries()` in a `useEffect` + `setTimeout`.

If offset ≥ 300 and the new batch has not arrived yet: **freeze the marker at `positions[299]`** and show a subtle "Updating…" indicator. Do not extrapolate.

`staleTime` for the positions query: `270_000` ms (overrides global `Infinity`).

### Data Panel

| Field | Source | Display |
|---|---|---|
| Latitude | positions | °N/S |
| Longitude | positions | °E/W |
| Altitude | positions | km |
| Velocity | derived from consecutive positions | km/h |
| Azimuth | positions | ° |
| Elevation (from observer) | positions | ° |
| Eclipsed | positions | Yes / No |
| Next visible pass | visual passes | `formatDateTime(startUTC)` in user timezone + duration |
| Next radio pass | radio passes | `formatDateTime(startUTC)` in user timezone + duration |
| N2YO quota | `/api/v1/iss/quota` | X / cap used |

### Quota Warning

- `used >= 800` → warning badge on ISS tab icon + page header (`"iss.quotaWarning"`)
- `quota_exhausted: true` → exhausted banner with reset time via `formatTime(resets_at)` (`"iss.quotaExhausted"`)

### Test Strategy

Mock `globe.gl` entirely in tests — do not test WebGL:
```ts
const { mockGlobe } = vi.hoisted(() => ({ mockGlobe: { _destructor: vi.fn() } }));
vi.mock('globe.gl', () => ({ default: vi.fn(() => mockGlobe) }));
```
Use `vi.useFakeTimers({ toFake: ['Date','setTimeout','setInterval','clearInterval'] })` for interpolation tests — explicitly exclude `requestAnimationFrame`.

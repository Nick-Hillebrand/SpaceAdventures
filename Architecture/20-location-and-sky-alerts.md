# User Location & Sky Alerts: ISS Passes + Aurora Nowcasting (v2 Steps L1, G1)

The flagship Pro features: "walk outside now" alerts. Two features share the
location foundation: ISS visual passes (#3, Step L1) and aurora nowcasting
(#6, Step G1).

---

## Foundation — User location (privacy-first)

**Design rule: city-level only, ever.** No GPS, no precise coordinates, no
IP geolocation. The user types a city; we geocode once and store the city's
coordinates rounded to 2 decimals (~1 km — sufficient for passes and aurora).

```
users (add columns)
  location_name  TEXT NULLABLE      -- "Vancouver, CA" as confirmed by user
  location_lat   REAL NULLABLE      -- rounded to 2 decimals
  location_lng   REAL NULLABLE      -- rounded to 2 decimals
  location_tz    TEXT NULLABLE      -- IANA name, from geocoder
```

- Geocoding: **Open-Meteo Geocoding API** (`geocoding-api.open-meteo.com`,
  free, no key, returns lat/lng + timezone). New `geocode_client.py` following
  the `nasa_client.py` pattern (shared client, error codes
  `GEOCODE_UNAVAILABLE`, `GEOCODE_NO_RESULT`). Backend proxies it:
  `GET /api/v1/location/search?q=` (auth, rate-limit bucket `geocode`
  20/hour/user) → top 5 candidates. Frontend never calls Open-Meteo directly.
- `POST /api/v1/location` (auth) stores a chosen candidate;
  `DELETE /api/v1/location` clears all four columns.
- Privacy: include location in the `15-…` P1.10 export; deletion cascades via
  user row; privacy policy names city-level location + purpose. Validate
  `lat ∈ [-90,90], lng ∈ [-180,180]` server-side (10-security.md input rules).
- Frontend: AccountPage "My sky location" — search box, candidate list,
  current location display, clear button. All strings via `t()`.

**Tests:** rounding applied on store; validation rejects out-of-range; clear
nulls all columns; geocode proxy error branches; rate-limit bucket enforced.

---

## L1 — ISS visual pass alerts (Pro flagship)

### Data

N2YO `visualpasses` endpoint (existing client + quota guard):
`/visualpasses/{id}/{lat}/{lng}/{alt}/{days}/{min_visibility}` with ISS NORAD id
25544, alt 0, days 2, min_visibility 120 (seconds).

```
iss_passes
  id            INTEGER PK AUTOINCREMENT
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
  start_utc     DATETIME NOT NULL
  end_utc       DATETIME NOT NULL
  max_el        REAL NOT NULL         -- degrees
  start_az      REAL; end_az REAL; mag REAL NULLABLE
  notified      BOOLEAN NOT NULL DEFAULT FALSE
  fetched_at    DATETIME
  UNIQUE (user_id, start_utc)
  INDEX (notified, start_utc)
```

### Worker jobs (register per `17-…` P3.2)

- `pass_precompute` (every 6 h): for each Pro user with location AND an active
  `iss_pass` subscription, fetch passes for the next 2 days, upsert. **Batch by
  rounded coordinate**: users sharing the same (lat,lng) rounded pair reuse ONE
  N2YO call (dedupe dict per run) — this is what keeps the 1000/hr quota viable
  at thousands of users. Quota guard applies per call as always; on quota
  exhaustion the job stops and resumes next run (never busy-waits).
- `pass_notify` (every 5 min): passes with `notified = FALSE AND start_utc
  BETWEEN now()+25min AND now()+35min AND max_el >= 25` → enqueue outbox
  notification (push preferred, email fallback), set `notified = TRUE` in the
  same transaction. Message: direction, time (user's `location_tz` — backend
  formats using stored tz for notifications ONLY; UI still uses `dateTime.ts`),
  max elevation, duration.

### Subscription & UI

- New subscription type: `subscriptions.kind = 'iss_pass'` (extend existing
  model per `08-subscriptions.md` conventions; Pro-gated at POST).
- IssPage: "Tonight over {city}" card (next pass from `GET
  /api/v1/iss/passes`, auth; free users see the card with the next pass but a
  Pro prompt replaces the "alert me" toggle).

**Tests:** batching (3 users, same rounded coords → 1 N2YO call — assert via
respx call count); notify window boundaries (24 min / 36 min out → not
selected); elevation floor; `notified` set atomically (no double-enqueue on
concurrent runs — postgres_only); quota-exhaustion mid-run stops cleanly;
tz formatting in message; Pro gating.

---

## G1 — Aurora nowcasting (NOAA OVATION)

### Data source

NOAA SWPC, free JSON, no key:

- `https://services.swpc.noaa.gov/json/ovation_aurora_latest.json` — global
  aurora probability grid (lat/lng → probability %), ~5 min cadence.
- `https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json` — Kp.

New `noaa_client.py` (shared-client pattern; error code `NOAA_UNAVAILABLE`).

```
aurora_state          -- single-row current state (id=1)
  id INTEGER PK CHECK (id = 1)
  fetched_at DATETIME
  kp REAL
  grid JSON             -- downsampled OVATION grid (see below)

aurora_alerts_sent
  user_id INTEGER; sent_date TEXT (YYYY-MM-DD)   -- dedupe: max 1/night/user
  PRIMARY KEY (user_id, sent_date)
```

### Worker job

`noaa_poll` (every 5 min): fetch OVATION, downsample the grid to 2° cells
(store max probability per cell — the raw grid is ~7 MB; downsampled ≈ 30 KB),
upsert `aurora_state`. **This is the one job whose staleness pages:** if
`fetched_at` lags > 15 min, admin health shows `stale` and Sentry warns
(`17-…` P3.5 wiring).

`aurora_notify` (every 10 min): for each Pro user with location + `aurora`
subscription: look up their 2° cell probability; if ≥ 40 (setting
`aurora_prob_threshold`) AND local darkness (sun below −6° at their lat/lng —
compute with a small solar-position function in `app/services/solar.py`; no
new dependency, standard NOAA algorithm ~30 lines) AND no row in
`aurora_alerts_sent` for tonight → enqueue push/email, insert dedupe row.

### API & UI

- `GET /api/v1/aurora` (public): `{kp, fetched_at, probability_at?}` —
  `probability_at` only for authed users with location.
- SpaceWeatherPage: aurora banner (Kp + "chance at your location" when
  available); subscription toggle (Pro) in the existing subscribe surface.

**Tests:** downsampling (fixture grid → known cell maxima); threshold and
darkness gates (parametrized: bright night → no alert even at prob 90);
1-per-night dedupe; staleness → health degraded; solar-position function
against 4 known reference values (NOAA calculator, ±0.5°); grid lookup at cell
boundaries; public endpoint hides `probability_at` for anonymous.

---

## Security notes (both features)

- All alert computations happen in the worker — **no per-request SGP4/grid
  scans in the web tier**. API routes read precomputed rows only.
- Location endpoints authenticated; responses never include other users' data
  (IDOR tests per `25-…`).
- NOAA/N2YO/Open-Meteo responses are untrusted: size-cap (5 MB rule from
  `10-security.md`), schema-validate before storage, sanitise anything that
  reaches a notification.

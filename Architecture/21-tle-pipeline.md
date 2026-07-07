# TLE Pipeline: Starlink Trains, Transit Finder, Reentries (v2 Steps G2, T1)

Satellite infrastructure beyond the ISS. Gates roadmap #4 (Starlink trains,
Step G2), #5 (transit finder, Step T1), #18 (reentry alerts, later), #34
(AMSAT, later). Requires `20-…` location foundation.

---

## Foundation — TLE sync & propagation

### Source & schema

CelesTrak GP data, free, no key. Be a polite consumer: bulk group files only,
never per-satellite queries; refresh ≤ 4×/day; honor cache headers.

- `https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json`
- `https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json`
  (ISS + Tiangong), `GROUP=visual` (bright satellites).

```
tle_sets
  norad_id     INTEGER PRIMARY KEY
  name         TEXT NOT NULL
  group_name   TEXT NOT NULL          -- 'starlink' | 'stations' | 'visual'
  epoch        DATETIME NOT NULL
  tle_json     JSON NOT NULL          -- CelesTrak GP JSON (OMM fields)
  launch_date  TEXT NULLABLE          -- from SATCAT for starlink recency filter
  fetched_at   DATETIME NOT NULL
  INDEX (group_name, epoch)
```

Worker job `tle_sync` (every 8 h): fetch each group, upsert by `norad_id`,
delete rows absent from source for > 14 days (decayed). Size-cap responses
(10 MB for starlink group), schema-validate every element before storage.

### Propagation

`pip install sgp4` (pure C-accelerated, no system deps). New
`app/services/propagation.py`:

- `positions(tle_json, t0, t1, step_s) -> list[(t, lat, lng, alt_km)]` via
  `Satrec.sgp4` + TEME→geodetic conversion (implement WGS84 conversion here —
  ~40 lines, no extra dependency; validate against 4 reference values from
  Skyfield in a one-off script, embed expected values in tests).
- `is_sunlit(t, lat, lng, alt_km) -> bool` and observer-frame
  `look_angles(observer, sat) -> (az, el, range_km)`.
- **CPU rule:** propagation runs ONLY in worker jobs, never in request
  handlers. Batch loops must `await asyncio.sleep(0)` every 50 satellites to
  keep the worker loop responsive.

---

## G2 — Starlink-train visibility alerts

A "train" is a recently-launched batch still in low, compact orbits —
spectacular for ~2 weeks after launch.

### Detection & precompute

Worker job `train_precompute` (every 6 h):

1. Candidate sats: `group_name='starlink' AND launch_date >= today − 21 days`
   (populate `launch_date` via CelesTrak SATCAT csv once per sync for new ids).
2. Cluster by orbital plane (RAAN within 2°, mean anomaly spread < 40°) —
   clusters of ≥ 10 sats = a train. Take the cluster's lead satellite as
   representative.
3. For each distinct rounded user location (same dedupe-by-coordinate strategy
   as `20-…` pass batching): compute visible passes of each train for the next
   36 h — observer sees it when `el > 20°`, satellite sunlit, sun below −6°
   (functions from the foundation).
4. Upsert into `sky_events` (shared table, also used by transit finder):

```
sky_events
  id          INTEGER PK AUTOINCREMENT
  kind        TEXT CHECK IN ('starlink_train','iss_lunar_transit','iss_solar_transit','reentry')
  lat_r       REAL NOT NULL; lng_r REAL NOT NULL     -- rounded location key
  start_utc   DATETIME NOT NULL
  detail      JSON NOT NULL      -- kind-specific payload (az/el path, duration, train size…)
  computed_at DATETIME NOT NULL
  UNIQUE (kind, lat_r, lng_r, start_utc)
  INDEX (kind, lat_r, lng_r, start_utc)
```

### Notify & display

- `train_notify` job (15 min): same shape as `pass_notify` (`20-…`) — window
  now+25..35 min, Pro users with `starlink_train` subscription at that rounded
  location, dedupe via `notified`-equivalent (add `notified BOOLEAN` to
  `sky_events` consumers via a join table `sky_event_notifications(user_id,
  sky_event_id) PK`).
- Free surface: banner on IssPage/home when a train is visible tonight at the
  user's location (`GET /api/v1/sky-events?kind=starlink_train`, auth,
  reads precomputed rows only).

**Tests:** clustering on a fixture constellation (known RAAN/anomaly spread →
expected clusters, including a non-train control group); recency filter;
sunlit/darkness gates; dedupe join table blocks double-notify; precompute
dedupes by rounded location; API returns only caller's location events.

---

## T1 — ISS lunar/solar transit finder (Pro, "Astro" audience)

Predict ISS crossing the Moon/Sun disc for a location — precision matters
(events last < 2 s and have ~5 km-wide ground tracks).

### Computation (worker job `transit_precompute`, daily)

For each Pro user location (rounded to 2 decimals is NOT enough here — this
feature stores an optional precise site):

```
users (add)  astro_lat REAL NULLABLE; astro_lng REAL NULLABLE; astro_alt_m REAL NULLABLE
```

Explicitly opt-in precise site for astrophotography ("astro site"), separate
from city location; same privacy handling (export/delete). UI copy must say
why precision is needed.

Algorithm per site, next 7 days: sample ISS ground track at 1 s; compute
angular separation ISS↔Moon and ISS↔Sun (solar/lunar position: extend
`app/services/solar.py` with a low-precision lunar ephemeris — Meeus truncated
series, ±0.3° is sufficient because we re-check separation < 0.35°); where
separation < disc radius + 0.1° margin → candidate event; refine with 0.05 s
steps. Store as `sky_events` kind `iss_lunar_transit`/`iss_solar_transit` with
`detail = {center_line_km_offset, duration_s, sun_alt, iss_range_km}`.

**Solar transit safety:** every solar-transit surface (UI + notification) must
include the solar-filter safety warning (`t("transits.solarSafety")`) — legal
exposure otherwise.

### API & UI

- `GET /api/v1/sky-events?kind=iss_lunar_transit` (Pro) — next events for the
  user's astro site.
- IssPage "Transits" tab: table (event, local time via `dateTime.ts`,
  duration, offset), astro-site editor, safety note on solar rows.
- Notification: 12 h ahead + 1 h ahead (two-stage), push+email.

**Tests:** separation math against 2 published historical transit events
(transit-finder archives; embed expected time ±5 s, offset ±2 km as fixtures);
refinement step convergence; solar safety string asserted present in both email
template and UI; astro-site CRUD + export/delete inclusion; Pro gating; daily
job skips users without astro site.

---

## Later (same foundation, do not build now)

- **Reentry alerts (#18):** Space-Track `decay` predictions → `sky_events`
  kind `reentry`. Needs Space-Track account + their rate rules (≤ 30 req/min,
  auth session). Spec when prioritized.
- **AMSAT passes (#34):** `GROUP=amateur` + same pass machinery. Trivial add.

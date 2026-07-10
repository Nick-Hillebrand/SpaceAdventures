# Ephemeris Cache, Live Spacecraft & Mission Replay (v2 Steps B3, G3)

The education/brand engine. Live spacecraft (#10, Step B3 — beta) and mission
replay (#11, Step G3 — timed to the Artemis window). Builds on the existing
simulator: `frontend/src/solar/orbits.ts` already solves Kepler's equation from
J2000 elements; this spec adds real ephemerides for objects Kepler elements
can't represent (powered flight, spacecraft).

> **Sequencing update (2026-07-09):** the G3 replay *engine* is pulled forward
> as **Step S1** (before Milestone P) in static-content scope: everything in
> the G3 section below **except** any dependency on the Horizons cache/API —
> the foundation section of this doc stays in B3 untouched. In S1,
> `build_mission.py` is the only Horizons consumer (offline, dev-run, courtesy
> rules apply) and gains a `--from-yaml` keyframe path for pre-Horizons
> missions (Apollo 11) — see `27-mission-simulations-3d.md`. Also deferred
> out of S1: the OG-meta/prerender line below (needs `23-…`, lands with B2)
> — the plain embed route itself ships in S1. Step G3 then shrinks to
> Artemis content + the Horizons-backed generator path + the deferred OG
> meta. The 3D vignette layer on top is Step S2 (`27-…`).

---

## Foundation — JPL Horizons cache

### Source rules

Horizons API (`https://ssd.jpl.nasa.gov/api/horizons.api`), free, no key.
**Courtesy rules are hard requirements:** batch queries, cache for days,
NEVER proxy user requests to JPL. All Horizons traffic originates from one
worker job.

New `horizons_client.py` (shared-client pattern; error `HORIZONS_UNAVAILABLE`;
response size-cap 5 MB). Query form: `COMMAND='<spk_id>'`,
`EPHEM_TYPE='VECTORS'`, `CENTER='500@10'` (heliocentric), `CSV_FORMAT='YES'`,
step per config.

### Tracked objects & schema

```
tracked_objects
  spk_id       TEXT PRIMARY KEY      -- Horizons COMMAND id, e.g. '-170' (JWST)
  slug         TEXT UNIQUE NOT NULL  -- 'jwst', 'voyager-1', …
  name_key     TEXT NOT NULL         -- i18n key: 'spacecraft.jwst'
  kind         TEXT CHECK IN ('spacecraft','small_body')
  active       BOOLEAN DEFAULT TRUE
  step_hours   INTEGER DEFAULT 24    -- sampling density

ephemerides
  spk_id   TEXT NOT NULL REFERENCES tracked_objects(spk_id) ON DELETE CASCADE
  t_utc    DATETIME NOT NULL
  x_au REAL; y_au REAL; z_au REAL    -- heliocentric ecliptic J2000
  PRIMARY KEY (spk_id, t_utc)
```

Seed set (migration data): JWST (`-170`), Voyager 1 (`-31`), Voyager 2 (`-32`),
Parker Solar Probe (`-96`), New Horizons (`-98`). Adding an object = one row —
no code change.

Worker job `ephemeris_sync` (daily): for each active object, ensure coverage
`now − 7 d … now + 30 d`; fetch only missing ranges (one Horizons call per
object per run max). Trajectories are physics — cache is effectively permanent;
never re-fetch covered ranges.

### API

`GET /api/v1/ephemerides/{slug}?from=&to=` (public, `Cache-Control: public,
max-age=3600`): `{slug, name_key, points: [{t, x, y, z}, …]}`. Validate range
≤ 90 days. 404 unknown slug.

**Tests:** client error branches (respx); coverage gap-fill logic (existing
range not re-fetched — assert call count); range validation; cache headers;
CSV parsing against a captured real Horizons response fixture.

---

## B3 — Live spacecraft in the simulator (free, beta milestone)

**Frontend only, consuming the API above.**

- `useEphemerides(slug)` React Query hook; fetch once per session per object
  (staleTime 1 h).
- `solar/spacecraft.ts`: interpolate position at current sim time
  (linear between bracketing points is sufficient at 24 h sampling for
  cruise trajectories; document the error bound in a comment), render as a
  distinct marker (diamond sprite + label) with a trail line (past 90 d from
  the same data).
- SolarSystemPage: "Spacecraft" toggle layer listing tracked objects
  (localized via `name_key`); clicking focuses camera and shows an info card
  (distance from Sun/Earth in AU + km via existing formatting helpers,
  velocity derived from adjacent points).
- Simulator time controls (existing) apply — spacecraft positions follow sim
  time within the cached window; outside the window the marker dims with a
  `t("simulator.noData")` tooltip.

**Tests (frontend):** interpolation math (fixture points → known midpoint);
marker renders per object; out-of-window dimming; locale label switching;
scene mocked per P36 conventions.

---

## G3 — Mission replay mode (free, growth milestone — Artemis-timed)

### Content pipeline (offline, not runtime)

Replays ship as **static JSON files** in `frontend/public/missions/` — zero
runtime Horizons dependency during traffic spikes:

```
missions/<slug>.json
{
  "slug": "artemis-2",
  "name_key": "missions.artemis2.name",
  "frame": "geocentric" | "heliocentric",
  "t0": "...", "t1": "...",
  "trajectory": [{"t": ..., "x": ..., "y": ..., "z": ...}, ...],
  "milestones": [
    {"t": ..., "key": "missions.artemis2.tli", "lat": null, "lng": null},
    ...
  ],
  "bodies": ["earth","moon"],         -- which bodies the scene must show
  "bodyCalibration": {                -- optional; see Engine integration
    "moon": { "phaseDeg": 213.7 }
  }
}
```

Generator script `backend/scripts/build_mission.py` (dev tool, not deployed):
pulls the trajectory from Horizons (historical missions) and writes the JSON;
milestones curated by hand in a YAML source per mission. Initial set:
Artemis 1 (historical), Apollo 11 (historical), Artemis 2 (add when Horizons
publishes it / from published state vectors).

### Engine integration — one engine, two entry points (decided 2026-07-09)

"Reuses the simulator engine" means a **shared module, not copied patterns**:
mission replay is a *mode* of the solar-system scene engine
(`solar/scene.ts`), never a second scene implementation.

- `SolarSceneHandle` gains a mission sub-API: `mission.load(spec)` adds the
  trajectory polyline, craft marker, and milestone ticks; clamps the sim
  clock to `[t0, t1]`; tweens the camera to the mission's frame (e.g. the
  Earth–Moon system). `mission.clear()` removes the layer and restores the
  prior clock, camera, and scale mode.
- **Scale-mode lock:** mission mode always renders true-scale geometry — a
  real trajectory cannot terminate at the visible-mode Moon, which sits at a
  decorative display distance. Entering from visible mode tweens to true
  scale; the scale toggle is disabled with a `t("missions.scaleLocked")`
  tooltip while a mission is loaded.
- **Moon calibration:** the scene's moons start at arbitrary display phases
  (137.5° spread) — fatal for Apollo 11, whose trajectory must end where the
  Moon actually was on 1969-07-20. Mission JSON gains optional
  `"bodyCalibration": { "moon": { "phaseDeg": … } }`, computed by
  `build_mission.py` from real ephemeris at the mission's anchor epoch
  (mean-period drift across a mission-length window is negligible). If a
  future mission needs better accuracy, a body may instead ship a trajectory
  array in the same shape as the craft's — the format allows it; don't build
  it until needed.
- Mission UI (mission picker, timeline scrubber with milestone ticks,
  milestone cards) lives in a standalone `MissionPanel` component shared by
  both entry points — this keeps `SolarSystemPage` from becoming a
  god-component.

Two entry points, one canonical:

1. **`/missions` (index) + `/missions/:slug` (+ `/embed`) — canonical.** The
   SEO, widget/kiosk, and deep-link surface (per `23-…` and the business
   plan's growth strategy). Mounts the engine directly in mission mode. Nav
   entry `t("nav.missions")`.
2. **Solar-system tab — in-context entry.** A "Missions" panel (list from a
   static `missions/index.json`) calls `mission.load()` on the already-
   mounted scene: the clock jumps to the mission window, the trajectory
   appears, the camera tweens over. The panel links to the canonical URL
   for sharing. This is the discovery surface for the education audience.

### Frontend

- Replay behavior (both entry points, via `MissionPanel`): trajectory
  polyline; craft marker animated along it; **timeline scrubber** with
  play/pause/speed (1×–10000×), milestone ticks — click jumps to milestone,
  shows localized description card. Geocentric frame support: Earth center,
  Moon via `moonPosition` with the calibrated phase above.
- All milestone/mission text via i18n keys in all six locales — mission
  content is translated content, a real differentiator.
- Embeddable variant: `/missions/:slug/embed` — chrome-less scene + attribution
  link (feeds `23-…` widgets; same-origin only until widget spec lands).
- OG meta for `/missions/:slug` via the prerender mechanism (`23-…`).

**Tests:** JSON schema validation in a build-time check (script validates all
mission files; wired into CI); scrubber logic (time↔position mapping,
milestone jump); geocentric frame math (Moon position sanity vs. `orbits.ts`
values, calibrated phase places the Moon at the trajectory terminus); mission
mode load/clear (clock clamped to window, scale-mode lock + restore, layer
objects removed and disposed on `clear()`); solar-tab entry (panel `load()`s
into the mounted scene, canonical-URL link present); locale switching on
milestone cards; embed route renders without nav.

**Performance:** trajectory files ≤ 500 KB (decimate to what the scrubber can
visually resolve — ~5k points max); lazy-load the mission route chunk
(`React.lazy`) so the main bundle is unaffected.

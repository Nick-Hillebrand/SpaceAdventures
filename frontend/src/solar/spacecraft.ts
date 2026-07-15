// Live-spacecraft math (Architecture/22-ephemeris-and-mission-replay.md, B3).
//
// Pure, framework-free position/velocity interpolation over a cached
// ephemeris sample series — kept separate from scene.ts so it's testable
// without a three.js/jsdom mock.

export interface EphemerisSample {
  /** Epoch ms. */
  t: number;
  /** Heliocentric ecliptic J2000 AU — same frame as `solar/orbits.ts`. */
  x: number;
  y: number;
  z: number;
}

export interface Vector3Like {
  x: number;
  y: number;
  z: number;
}

/** Fixed catalog mirroring the backend seed migration
 * (`9cd57e6874ae_add_tracked_objects_and_ephemerides.py`). There is no
 * discovery endpoint — `GET /api/v1/ephemerides/{slug}` requires already
 * knowing the slug — so the frontend duplicates the small, rarely-changing
 * set of tracked objects here. Adding an object still needs this array
 * updated (unlike the backend, which only needs one migration row). */
export interface TrackedSpacecraftCatalogEntry {
  slug: string;
  nameKey: string;
}

export const TRACKED_SPACECRAFT: TrackedSpacecraftCatalogEntry[] = [
  { slug: "jwst", nameKey: "spacecraft.jwst" },
  { slug: "voyager-1", nameKey: "spacecraft.voyager1" },
  { slug: "voyager-2", nameKey: "spacecraft.voyager2" },
  { slug: "parker-solar-probe", nameKey: "spacecraft.parkerSolarProbe" },
  { slug: "new-horizons", nameKey: "spacecraft.newHorizons" },
];

/** Trailing window requested from the API: exactly `MAX_RANGE_DAYS` back on
 * the backend (`ephemerides_service.MAX_RANGE_DAYS`), ending "now" — fetched
 * once per session (React Query `staleTime`), not per sim-date scrub. This
 * fetch window is also the window the UI dims outside of (`isWithinCoverage`
 * below) — scrubbing into the future dims the marker, matching the fact that
 * no future range was requested. */
export const EPHEMERIDES_FETCH_PAST_DAYS = 90;

/** Trail length shown on the scene (spec: "trail line (past 90 d)"). */
export const TRAIL_PAST_DAYS = 90;

/** What `scene.ts`'s `spacecraft.setObjects()` renders one of. */
export interface SpacecraftRenderObject {
  /** Tracked-object slug — also used as the marker's raycast/selection id. */
  id: string;
  /** Pre-resolved display name (`t(nameKey)`) — re-passed on locale change. */
  label: string;
  points: EphemerisSample[];
}

function findBracket(points: EphemerisSample[], atMs: number): [number, number] {
  const last = points.length - 1;
  if (atMs <= points[0].t) return [0, 0];
  if (atMs >= points[last].t) return [last, last];
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (points[mid].t <= atMs) lo = mid;
    else hi = mid;
  }
  return [lo, hi];
}

/**
 * Position at `atMs`, linearly interpolated between the bracketing samples.
 * Linear interpolation is a good approximation at the catalog's 24h sampling
 * density for the smooth cruise trajectories being tracked (no powered-
 * flight segments) — the worst-case deviation from the true curve over a
 * single 24h step is a small fraction of the sampling interval's own travel
 * distance, negligible at the marker's on-screen scale.
 *
 * Clamped to the first/last sample when `atMs` falls outside the fetched
 * range, so the marker freezes at the edge instead of vanishing — dimming
 * for "outside the cached window" is a separate concern, see
 * `isWithinCoverage`. Returns `null` only when there is no data at all.
 */
export function interpolatePosition(points: EphemerisSample[], atMs: number): Vector3Like | null {
  if (points.length === 0) return null;
  if (points.length === 1) {
    const [p] = points;
    return { x: p.x, y: p.y, z: p.z };
  }
  const [lo, hi] = findBracket(points, atMs);
  const a = points[lo];
  const b = points[hi];
  const span = b.t - a.t;
  const f = span > 0 ? (atMs - a.t) / span : 0;
  return {
    x: a.x + (b.x - a.x) * f,
    y: a.y + (b.y - a.y) * f,
    z: a.z + (b.z - a.z) * f,
  };
}

/** Whether `atMs` falls within the fetched sample range (inclusive). */
export function isWithinCoverage(points: EphemerisSample[], atMs: number): boolean {
  if (points.length === 0) return false;
  return atMs >= points[0].t && atMs <= points[points.length - 1].t;
}

const AU_ORIGIN: Vector3Like = { x: 0, y: 0, z: 0 };

/** Euclidean distance in AU between two heliocentric points (defaults `b` to
 * the Sun, i.e. "distance from Sun"). */
export function distanceAu(a: Vector3Like, b: Vector3Like = AU_ORIGIN): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

const MS_PER_DAY = 86_400_000;

/**
 * Velocity in AU/day, derived from the pair of adjacent samples bracketing
 * `atMs` (spec: "velocity derived from adjacent points"). `null` outside the
 * covered range or with fewer than 2 samples.
 */
export function velocityAuPerDay(points: EphemerisSample[], atMs: number): number | null {
  if (points.length < 2 || !isWithinCoverage(points, atMs)) return null;
  const [lo, hi] = findBracket(points, atMs);
  const i = lo === hi ? (lo === points.length - 1 ? lo - 1 : lo) : lo;
  const a = points[i];
  const b = points[i + 1];
  const dtDays = (b.t - a.t) / MS_PER_DAY;
  return dtDays > 0 ? distanceAu(a, b) / dtDays : 0;
}

/** Samples within `[atMs - pastDays, atMs]`, for the trail line. */
export function trailPoints(
  points: EphemerisSample[],
  atMs: number,
  pastDays: number = TRAIL_PAST_DAYS,
): EphemerisSample[] {
  const cutoff = atMs - pastDays * MS_PER_DAY;
  return points.filter((p) => p.t >= cutoff && p.t <= atMs);
}

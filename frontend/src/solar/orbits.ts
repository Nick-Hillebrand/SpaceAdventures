// Keplerian orbit propagation for the solar system simulator.
//
// Planets use J2000 osculating elements from data.ts and are propagated with
// a fixed mean motion (n = 360°/period). This ignores secular drift of the
// elements, which stays well under a degree over ±a century — plenty for a
// teaching visualization, and it keeps the math easy to explain.

import type { OrbitalElements } from "./data";

const DEG = Math.PI / 180;

/** J2000 epoch as a JS timestamp (2000-01-01T12:00:00Z, i.e. JD 2451545.0). */
export const J2000_MS = Date.UTC(2000, 0, 1, 12);

/** Days elapsed since J2000 for a given Date. */
export function daysSinceJ2000(date: Date): number {
  return (date.getTime() - J2000_MS) / 86_400_000;
}

/** Solve Kepler's equation M = E - e·sin(E) for E (radians) via Newton's method. */
export function solveKepler(meanAnomalyRad: number, e: number): number {
  let E = e < 0.8 ? meanAnomalyRad : Math.PI;
  for (let iter = 0; iter < 12; iter++) {
    const dE = (E - e * Math.sin(E) - meanAnomalyRad) / (1 - e * Math.cos(E));
    E -= dE;
    if (Math.abs(dE) < 1e-9) break;
  }
  return E;
}

export interface HeliocentricPosition {
  /** Ecliptic coordinates in the unit of `a` (AU for planets). */
  x: number;
  y: number;
  z: number;
  /** Distance from the focus, same unit. */
  r: number;
}

/**
 * Heliocentric ecliptic position for a body at `daysFromJ2000`.
 *
 * Returned axes: x toward the vernal equinox, z toward the north ecliptic
 * pole, y completing the right-handed set.
 */
export function heliocentricPosition(
  orbit: OrbitalElements,
  daysFromJ2000: number,
): HeliocentricPosition {
  const n = 360 / orbit.periodDays; // mean motion, deg/day
  const M = ((orbit.L - orbit.w + n * daysFromJ2000) % 360) * DEG;
  const E = solveKepler(M, orbit.e);

  // Position in the orbital plane, perihelion along +x'.
  const xOrb = orbit.a * (Math.cos(E) - orbit.e);
  const yOrb = orbit.a * Math.sqrt(1 - orbit.e * orbit.e) * Math.sin(E);
  const r = Math.hypot(xOrb, yOrb);

  // Rotate by argument of perihelion ω = ϖ − Ω, inclination i, node Ω.
  const w = (orbit.w - orbit.om) * DEG;
  const om = orbit.om * DEG;
  const i = orbit.i * DEG;

  const cosW = Math.cos(w), sinW = Math.sin(w);
  const cosOm = Math.cos(om), sinOm = Math.sin(om);
  const cosI = Math.cos(i), sinI = Math.sin(i);

  const x =
    (cosW * cosOm - sinW * sinOm * cosI) * xOrb +
    (-sinW * cosOm - cosW * sinOm * cosI) * yOrb;
  const y =
    (cosW * sinOm + sinW * cosOm * cosI) * xOrb +
    (-sinW * sinOm + cosW * cosOm * cosI) * yOrb;
  const z = sinW * sinI * xOrb + cosW * sinI * yOrb;

  return { x, y, z, r };
}

/**
 * Sample one full revolution of an orbit as ecliptic points, for drawing the
 * orbit line. Points are in the same unit as `orbit.a`.
 */
export function orbitPath(orbit: OrbitalElements, segments = 256): HeliocentricPosition[] {
  const points: HeliocentricPosition[] = [];
  const period = Math.abs(orbit.periodDays);
  for (let s = 0; s <= segments; s++) {
    points.push(heliocentricPosition(orbit, (s / segments) * period));
  }
  return points;
}

/**
 * Position of a moon relative to its parent, on a circular orbit in the
 * parent's equatorial plane (approximated as the ecliptic plane here).
 * `a` is in 10^3 km; the result is in the same unit.
 */
export function moonPosition(
  aThousandKm: number,
  periodDays: number,
  daysFromJ2000: number,
  phaseDeg = 0,
): { x: number; y: number; z: number } {
  const angle = (phaseDeg + (360 / periodDays) * daysFromJ2000) * DEG;
  return { x: aThousandKm * Math.cos(angle), y: aThousandKm * Math.sin(angle), z: 0 };
}

import { describe, expect, it } from "vitest";
import { PLANETS } from "@/solar/data";
import {
  J2000_MS,
  daysSinceJ2000,
  heliocentricPosition,
  moonPosition,
  orbitPath,
  solveKepler,
} from "@/solar/orbits";

const earth = PLANETS.find((p) => p.id === "earth")!;
const mercury = PLANETS.find((p) => p.id === "mercury")!;

describe("daysSinceJ2000", () => {
  it("is zero at the J2000 epoch and counts forward in days", () => {
    expect(daysSinceJ2000(new Date(J2000_MS))).toBe(0);
    expect(daysSinceJ2000(new Date(J2000_MS + 86_400_000))).toBe(1);
    expect(daysSinceJ2000(new Date(J2000_MS - 43_200_000))).toBe(-0.5);
  });
});

describe("solveKepler", () => {
  it("returns the mean anomaly for a circular orbit", () => {
    expect(solveKepler(1.234, 0)).toBeCloseTo(1.234, 9);
  });

  it("satisfies Kepler's equation for eccentric orbits", () => {
    for (const e of [0.1, 0.5, 0.9]) {
      for (const M of [0.3, Math.PI / 2, 2.5]) {
        const E = solveKepler(M, e);
        expect(E - e * Math.sin(E)).toBeCloseTo(M, 8);
      }
    }
  });
});

describe("heliocentricPosition", () => {
  it("puts Earth near perihelion distance at the J2000 epoch (early January)", () => {
    const p = heliocentricPosition(earth.orbit, 0);
    expect(p.r).toBeGreaterThan(0.982);
    expect(p.r).toBeLessThan(0.986);
    // True ecliptic longitude at J2000 is ~100°.
    const lonDeg = (Math.atan2(p.y, p.x) * 180) / Math.PI;
    expect(lonDeg).toBeGreaterThan(98);
    expect(lonDeg).toBeLessThan(102);
  });

  it("returns to the same position after one full period", () => {
    const p0 = heliocentricPosition(mercury.orbit, 10);
    const p1 = heliocentricPosition(mercury.orbit, 10 + mercury.orbit.periodDays);
    expect(p1.x).toBeCloseTo(p0.x, 5);
    expect(p1.y).toBeCloseTo(p0.y, 5);
    expect(p1.z).toBeCloseTo(p0.z, 5);
  });

  it("keeps the radius between perihelion and aphelion", () => {
    for (const planet of PLANETS) {
      const { a, e, periodDays } = planet.orbit;
      for (let d = 0; d < periodDays; d += periodDays / 17) {
        const { r } = heliocentricPosition(planet.orbit, d);
        expect(r).toBeGreaterThanOrEqual(a * (1 - e) - 1e-6);
        expect(r).toBeLessThanOrEqual(a * (1 + e) + 1e-6);
      }
    }
  });

  it("stays in the ecliptic plane for zero inclination and leaves it otherwise", () => {
    expect(heliocentricPosition(earth.orbit, 42).z).toBeCloseTo(0, 9);
    const zs = [0, 20, 40, 60].map((d) => Math.abs(heliocentricPosition(mercury.orbit, d).z));
    expect(Math.max(...zs)).toBeGreaterThan(0.01);
  });
});

describe("orbitPath", () => {
  it("samples a closed loop of segments+1 points", () => {
    const points = orbitPath(earth.orbit, 64);
    expect(points).toHaveLength(65);
    expect(points[64].x).toBeCloseTo(points[0].x, 5);
    expect(points[64].y).toBeCloseTo(points[0].y, 5);
  });
});

describe("moonPosition", () => {
  it("orbits at a constant distance and closes after one period", () => {
    const a = 384.4;
    const period = 27.322;
    const p0 = moonPosition(a, period, 3);
    expect(Math.hypot(p0.x, p0.y)).toBeCloseTo(a, 6);
    const p1 = moonPosition(a, period, 3 + period);
    expect(p1.x).toBeCloseTo(p0.x, 4);
    expect(p1.y).toBeCloseTo(p0.y, 4);
  });

  it("offsets the start by the phase angle", () => {
    const p0 = moonPosition(100, 10, 0, 0);
    const p90 = moonPosition(100, 10, 0, 90);
    expect(p0.x).toBeCloseTo(100, 6);
    expect(p90.y).toBeCloseTo(100, 6);
  });
});

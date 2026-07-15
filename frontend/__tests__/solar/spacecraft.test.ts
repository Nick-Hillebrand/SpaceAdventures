import { describe, it, expect } from "vitest";
import {
  distanceAu,
  interpolatePosition,
  isWithinCoverage,
  trailPoints,
  velocityAuPerDay,
  type EphemerisSample,
} from "@/solar/spacecraft";

const DAY = 86_400_000;
const T0 = Date.parse("2026-01-01T00:00:00Z");

function samples(): EphemerisSample[] {
  return [
    { t: T0, x: 1, y: 0, z: 0 },
    { t: T0 + DAY, x: 2, y: 0, z: 0 },
    { t: T0 + 2 * DAY, x: 4, y: 0, z: 0 },
  ];
}

describe("solar/spacecraft", () => {
  describe("interpolatePosition", () => {
    it("returns null for an empty series", () => {
      expect(interpolatePosition([], T0)).toBeNull();
    });

    it("returns the single point verbatim when only one sample exists", () => {
      const pos = interpolatePosition([{ t: T0, x: 5, y: 6, z: 7 }], T0 + DAY);
      expect(pos).toEqual({ x: 5, y: 6, z: 7 });
    });

    it("returns the exact sample when atMs lands on a grid point", () => {
      expect(interpolatePosition(samples(), T0 + DAY)).toEqual({ x: 2, y: 0, z: 0 });
    });

    it("linearly interpolates the known midpoint between two bracketing samples", () => {
      const pos = interpolatePosition(samples(), T0 + DAY / 2);
      expect(pos!.x).toBeCloseTo(1.5, 10);
      expect(pos!.y).toBeCloseTo(0, 10);
      expect(pos!.z).toBeCloseTo(0, 10);
    });

    it("clamps to the first sample when atMs is before the series", () => {
      expect(interpolatePosition(samples(), T0 - DAY)).toEqual({ x: 1, y: 0, z: 0 });
    });

    it("clamps to the last sample when atMs is after the series", () => {
      expect(interpolatePosition(samples(), T0 + 10 * DAY)).toEqual({ x: 4, y: 0, z: 0 });
    });
  });

  describe("isWithinCoverage", () => {
    it("is false for an empty series", () => {
      expect(isWithinCoverage([], T0)).toBe(false);
    });

    it("is true at the inclusive boundaries and inside the range", () => {
      const pts = samples();
      expect(isWithinCoverage(pts, T0)).toBe(true);
      expect(isWithinCoverage(pts, T0 + 2 * DAY)).toBe(true);
      expect(isWithinCoverage(pts, T0 + DAY / 2)).toBe(true);
    });

    it("is false just outside either boundary", () => {
      const pts = samples();
      expect(isWithinCoverage(pts, T0 - 1)).toBe(false);
      expect(isWithinCoverage(pts, T0 + 2 * DAY + 1)).toBe(false);
    });
  });

  describe("distanceAu", () => {
    it("defaults to distance from the origin (Sun)", () => {
      expect(distanceAu({ x: 3, y: 4, z: 0 })).toBeCloseTo(5, 10);
    });

    it("computes Euclidean distance between two arbitrary points", () => {
      expect(distanceAu({ x: 1, y: 1, z: 1 }, { x: 4, y: 5, z: 1 })).toBeCloseTo(5, 10);
    });
  });

  describe("velocityAuPerDay", () => {
    it("is null with fewer than two samples", () => {
      expect(velocityAuPerDay([{ t: T0, x: 0, y: 0, z: 0 }], T0)).toBeNull();
    });

    it("is null outside the covered range", () => {
      expect(velocityAuPerDay(samples(), T0 - DAY)).toBeNull();
    });

    it("derives velocity from the bracketing pair (1 AU/day over the first day)", () => {
      expect(velocityAuPerDay(samples(), T0 + DAY / 2)).toBeCloseTo(1, 10);
    });

    it("derives velocity from the second bracketing pair (2 AU/day)", () => {
      expect(velocityAuPerDay(samples(), T0 + 1.5 * DAY)).toBeCloseTo(2, 10);
    });

    it("uses the trailing pair when atMs lands exactly on the last sample", () => {
      expect(velocityAuPerDay(samples(), T0 + 2 * DAY)).toBeCloseTo(2, 10);
    });

    it("uses the leading pair when atMs lands exactly on the first sample", () => {
      expect(velocityAuPerDay(samples(), T0)).toBeCloseTo(1, 10);
    });
  });

  describe("trailPoints", () => {
    it("keeps only samples within [atMs - pastDays, atMs]", () => {
      const pts = samples();
      const trail = trailPoints(pts, T0 + 2 * DAY, 1);
      expect(trail).toEqual([pts[1], pts[2]]);
    });

    it("excludes samples after atMs even if within the past window", () => {
      const pts = samples();
      const trail = trailPoints(pts, T0 + DAY, 90);
      expect(trail).toEqual([pts[0], pts[1]]);
    });

    it("defaults to TRAIL_PAST_DAYS (90) when pastDays is omitted", () => {
      const pts = samples();
      expect(trailPoints(pts, T0 + 2 * DAY)).toEqual(pts);
    });
  });
});

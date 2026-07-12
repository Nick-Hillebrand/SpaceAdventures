import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join, basename } from "node:path";
import {
  MAX_FILE_BYTES,
  MAX_MISSION_MODEL_BYTES,
  MAX_MODEL_FILE_BYTES,
  MAX_TRAJECTORY_POINTS,
  validateIndexSpec,
  validateMissionFileText,
  validateMissionSpec,
} from "../../scripts/validateMissionSchema.mjs";

const MISSIONS_DIR = join(process.cwd(), "public", "missions");

// Loosely typed on purpose: individual tests mutate/delete fields to
// construct intentionally malformed specs, which a strict interface would
// reject at compile time.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function validSpec(): any {
  return {
    slug: "test-mission",
    name_key: "missions.testMission.name",
    frame: "geocentric",
    t0: "2020-01-01T00:00:00Z",
    t1: "2020-01-02T00:00:00Z",
    trajectory: [
      { t: "2020-01-01T00:00:00Z", x: 0, y: 0, z: 0 },
      { t: "2020-01-01T12:00:00Z", x: 10, y: 10, z: 0 },
      { t: "2020-01-02T00:00:00Z", x: 20, y: 20, z: 0 },
    ],
    milestones: [{ t: "2020-01-01T12:00:00Z", key: "missions.testMission.midpoint" }],
    bodies: ["earth", "moon"],
    bodyCalibration: { moon: { phaseDeg: 180 } },
  };
}

describe("validateMissionSpec", () => {
  it("accepts a well-formed spec", () => {
    expect(validateMissionSpec(validSpec())).toEqual([]);
  });

  it("accepts a spec without optional bodyCalibration", () => {
    const spec = validSpec();
    delete spec.bodyCalibration;
    expect(validateMissionSpec(spec)).toEqual([]);
  });

  it("accepts milestones without lat/lng", () => {
    expect(validateMissionSpec(validSpec())).toEqual([]);
  });

  it("rejects a non-object payload", () => {
    expect(validateMissionSpec(null)).toHaveLength(1);
    expect(validateMissionSpec([1, 2, 3])).toHaveLength(1);
    expect(validateMissionSpec("nope")).toHaveLength(1);
  });

  it("flags a missing slug", () => {
    const spec = validSpec();
    delete spec.slug;
    expect(validateMissionSpec(spec).some((e) => e.includes("slug"))).toBe(true);
  });

  it("flags a slug/filename mismatch", () => {
    const errors = validateMissionSpec(validSpec(), { fileName: "other-slug.json" });
    expect(errors.some((e) => e.includes("does not match file name"))).toBe(true);
  });

  it("flags a missing name_key", () => {
    const spec = validSpec();
    spec.name_key = "";
    expect(validateMissionSpec(spec).some((e) => e.includes("name_key"))).toBe(true);
  });

  it("rejects an invalid frame value", () => {
    const spec = validSpec();
    spec.frame = "areocentric";
    expect(validateMissionSpec(spec).some((e) => e.includes("frame"))).toBe(true);
  });

  it("rejects malformed t0/t1", () => {
    const spec = validSpec();
    spec.t0 = "not-a-date";
    expect(validateMissionSpec(spec).some((e) => e.includes("t0"))).toBe(true);
  });

  it("rejects t0 >= t1", () => {
    const spec = validSpec();
    spec.t0 = spec.t1;
    expect(validateMissionSpec(spec).some((e) => e.includes("must be before"))).toBe(true);
  });

  it("rejects a trajectory with fewer than 2 points", () => {
    const spec = validSpec();
    spec.trajectory = [spec.trajectory[0]];
    expect(validateMissionSpec(spec).some((e) => e.includes("at least 2 points"))).toBe(true);
  });

  it("rejects a trajectory exceeding the point budget", () => {
    const spec = validSpec();
    const start = Date.parse(spec.t0);
    const end = Date.parse(spec.t1);
    const n = MAX_TRAJECTORY_POINTS + 1;
    spec.trajectory = Array.from({ length: n }, (_, i) => ({
      t: new Date(start + ((end - start) * i) / (n - 1)).toISOString(),
      x: i,
      y: i,
      z: 0,
    }));
    expect(validateMissionSpec(spec).some((e) => e.includes("performance budget"))).toBe(true);
  });

  it("rejects a trajectory point outside [t0, t1]", () => {
    const spec = validSpec();
    spec.trajectory[0].t = "2019-01-01T00:00:00Z";
    expect(validateMissionSpec(spec).some((e) => e.includes("falls outside"))).toBe(true);
  });

  it("rejects an out-of-order trajectory", () => {
    const spec = validSpec();
    spec.trajectory[1].t = "2020-01-01T00:00:00Z";
    spec.trajectory[0].t = "2020-01-01T06:00:00Z";
    expect(validateMissionSpec(spec).some((e) => e.includes("chronological order"))).toBe(true);
  });

  it("rejects non-numeric trajectory coordinates", () => {
    const spec = validSpec();
    spec.trajectory[0].x = "oops";
    expect(validateMissionSpec(spec).some((e) => e.includes("trajectory[0].x"))).toBe(true);
  });

  it("rejects a milestone outside [t0, t1] (regression: the roverDeploy bug)", () => {
    const spec = validSpec();
    spec.milestones[0].t = "2020-01-03T00:00:00Z";
    expect(validateMissionSpec(spec).some((e) => e.includes("milestones[0].t"))).toBe(true);
  });

  it("rejects a milestone missing its key", () => {
    const spec = validSpec();
    delete spec.milestones[0].key;
    expect(validateMissionSpec(spec).some((e) => e.includes("milestones[0].key"))).toBe(true);
  });

  it("accepts a milestone with numeric lat/lng and rejects non-numeric ones", () => {
    const spec = validSpec();
    spec.milestones[0].lat = 12.3;
    spec.milestones[0].lng = -45.6;
    expect(validateMissionSpec(spec)).toEqual([]);

    spec.milestones[0].lat = "north";
    expect(validateMissionSpec(spec).some((e) => e.includes("milestones[0].lat"))).toBe(true);
  });

  it("rejects an empty bodies array", () => {
    const spec = validSpec();
    spec.bodies = [];
    expect(validateMissionSpec(spec).some((e) => e.includes("bodies"))).toBe(true);
  });

  it("rejects a non-numeric bodyCalibration.moon.phaseDeg", () => {
    const spec = validSpec();
    spec.bodyCalibration.moon.phaseDeg = "big";
    expect(validateMissionSpec(spec).some((e) => e.includes("phaseDeg"))).toBe(true);
  });
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function validVignette(): any {
  return {
    model: "/models/missions/apollo11-lm.glb",
    environment: "moon-surface",
    modelCredit: "missions.credit.nasa",
    cameraOrbit: { distanceM: 18, elevationDeg: 12 },
    narrationKey: "missions.apollo11.landing.narration",
  };
}

const vignetteOptions = {
  knownModelFiles: new Set(["apollo11-lm.glb"]),
  modelFileSizes: new Map([["apollo11-lm.glb", 1024]]),
  localeKeySets: new Map([
    ["en", new Set(["missions.credit.nasa", "missions.apollo11.landing.narration"])],
    ["de", new Set(["missions.credit.nasa", "missions.apollo11.landing.narration"])],
  ]),
};

describe("validateMissionSpec vignettes", () => {
  it("accepts a well-formed vignette", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = validVignette();
    expect(validateMissionSpec(spec, vignetteOptions)).toEqual([]);
  });

  it("accepts a milestone without a vignette (optional field)", () => {
    const spec = validSpec();
    expect(validateMissionSpec(spec, vignetteOptions)).toEqual([]);
  });

  it("rejects a vignette model path outside /models/missions/", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = { ...validVignette(), model: "/models/apollo11-lm.glb" };
    const errors = validateMissionSpec(spec, vignetteOptions);
    expect(errors.some((e) => e.includes("must be under /models/missions/"))).toBe(true);
  });

  it("flags a vignette model file missing from public/models/missions/", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = { ...validVignette(), model: "/models/missions/ghost.glb" };
    const errors = validateMissionSpec(spec, vignetteOptions);
    expect(errors.some((e) => e.includes('model file "ghost.glb" does not exist'))).toBe(true);
  });

  it("rejects an unknown vignette environment", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = { ...validVignette(), environment: "underwater" };
    const errors = validateMissionSpec(spec, vignetteOptions);
    expect(errors.some((e) => e.includes("environment must be one of"))).toBe(true);
  });

  it("flags a vignette i18n key missing from a locale", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = { ...validVignette(), modelCredit: "missions.credit.unknown" };
    const errors = validateMissionSpec(spec, vignetteOptions);
    expect(errors.some((e) => e.includes('modelCredit "missions.credit.unknown" is missing from locale(s)'))).toBe(
      true,
    );
  });

  it("rejects a non-finite cameraOrbit field", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = {
      ...validVignette(),
      cameraOrbit: { distanceM: "far", elevationDeg: 12 },
    };
    const errors = validateMissionSpec(spec, vignetteOptions);
    expect(errors.some((e) => e.includes("cameraOrbit.distanceM"))).toBe(true);
  });

  it("flags a model file exceeding the per-file size budget", () => {
    const spec = validSpec();
    spec.milestones[0].vignette = validVignette();
    const errors = validateMissionSpec(spec, {
      ...vignetteOptions,
      modelFileSizes: new Map([["apollo11-lm.glb", MAX_MODEL_FILE_BYTES + 1]]),
    });
    expect(errors.some((e) => e.includes("per-file budget"))).toBe(true);
  });

  it("flags a mission whose vignette models exceed the per-mission size budget", () => {
    const spec = validSpec();
    spec.milestones.push({ ...spec.milestones[0], key: "missions.testMission.second" });
    spec.milestones[0].vignette = { ...validVignette(), model: "/models/missions/one.glb" };
    spec.milestones[1].vignette = { ...validVignette(), model: "/models/missions/two.glb" };
    const bigHalf = Math.ceil(MAX_MISSION_MODEL_BYTES / 2) + 1;
    const errors = validateMissionSpec(spec, {
      knownModelFiles: new Set(["one.glb", "two.glb"]),
      modelFileSizes: new Map([
        ["one.glb", bigHalf],
        ["two.glb", bigHalf],
      ]),
      localeKeySets: vignetteOptions.localeKeySets,
    });
    expect(errors.some((e) => e.includes("per-mission budget"))).toBe(true);
  });
});

describe("validateMissionFileText", () => {
  it("parses and validates well-formed JSON text", () => {
    const { errors, data } = validateMissionFileText(JSON.stringify(validSpec()), {
      fileName: "test-mission.json",
    });
    expect(errors).toEqual([]);
    expect((data as { slug: string }).slug).toBe("test-mission");
  });

  it("reports invalid JSON without throwing", () => {
    const { errors, data } = validateMissionFileText("{ not json", { fileName: "bad.json" });
    expect(errors.some((e) => e.includes("invalid JSON"))).toBe(true);
    expect(data).toBeNull();
  });

  it("enforces the 500 KB file size budget", () => {
    const spec = validSpec();
    // Pad well past the budget with a bogus-but-parseable extra field.
    spec.padding = "x".repeat(MAX_FILE_BYTES + 1024);
    const { errors } = validateMissionFileText(JSON.stringify(spec), { fileName: "huge.json" });
    expect(errors.some((e) => e.includes("performance budget"))).toBe(true);
  });
});

describe("validateIndexSpec", () => {
  it("accepts a well-formed index referencing known slugs", () => {
    const data = { missions: [{ slug: "apollo-11", name_key: "missions.apollo11.name" }] };
    expect(validateIndexSpec(data, { knownSlugs: new Set(["apollo-11"]) })).toEqual([]);
  });

  it("rejects a missing missions array", () => {
    expect(validateIndexSpec({})[0]).toContain("missions");
  });

  it("flags a slug with no matching mission file", () => {
    const data = { missions: [{ slug: "ghost-mission", name_key: "x" }] };
    const errors = validateIndexSpec(data, { knownSlugs: new Set(["apollo-11"]) });
    expect(errors.some((e) => e.includes("ghost-mission"))).toBe(true);
  });

  it("flags an entry missing name_key", () => {
    const data = { missions: [{ slug: "apollo-11" }] };
    const errors = validateIndexSpec(data, { knownSlugs: new Set(["apollo-11"]) });
    expect(errors.some((e) => e.includes("name_key"))).toBe(true);
  });
});

describe("real mission files in frontend/public/missions", () => {
  const files = readdirSync(MISSIONS_DIR).filter((f) => f.endsWith(".json"));
  const missionFiles = files.filter((f) => f !== "index.json");
  const knownSlugs = new Set(missionFiles.map((f) => basename(f, ".json")));

  it("has at least one mission file plus index.json", () => {
    expect(missionFiles.length).toBeGreaterThan(0);
    expect(files).toContain("index.json");
  });

  it.each(missionFiles)("%s passes schema validation", (fileName) => {
    const text = readFileSync(join(MISSIONS_DIR, fileName), "utf8");
    const { errors } = validateMissionFileText(text, { fileName });
    expect(errors).toEqual([]);
  });

  it("index.json passes schema validation and references only real files", () => {
    const text = readFileSync(join(MISSIONS_DIR, "index.json"), "utf8");
    const data = JSON.parse(text);
    expect(validateIndexSpec(data, { knownSlugs })).toEqual([]);
  });
});

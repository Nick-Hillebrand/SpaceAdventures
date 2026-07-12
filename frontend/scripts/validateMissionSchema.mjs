// Pure validation logic for the mission JSON schema (Architecture/22-
// ephemeris-and-mission-replay.md, "G3 — Mission replay mode" section). No
// file I/O here so it can be unit-tested directly; see validate-missions.mjs
// for the CLI that walks frontend/public/missions/.

export const MAX_TRAJECTORY_POINTS = 5000;
export const MAX_FILE_BYTES = 500 * 1024;

const VALID_FRAMES = new Set(["geocentric", "heliocentric"]);

function isFiniteNumber(v) {
  return typeof v === "number" && Number.isFinite(v);
}

function isNonEmptyString(v) {
  return typeof v === "string" && v.length > 0;
}

function parseIso(v) {
  if (typeof v !== "string") return null;
  const ms = Date.parse(v);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Validates a parsed mission spec against the schema. Returns an array of
 * human-readable error strings; empty array means valid.
 */
export function validateMissionSpec(data, { fileName } = {}) {
  const errors = [];
  const tag = (msg) => (fileName ? `${fileName}: ${msg}` : msg);

  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return [tag("mission spec must be a JSON object")];
  }

  if (!isNonEmptyString(data.slug)) {
    errors.push(tag("missing or empty required field: slug"));
  } else if (fileName && `${data.slug}.json` !== fileName) {
    errors.push(
      tag(`slug "${data.slug}" does not match file name (expected ${data.slug}.json)`),
    );
  }

  if (!isNonEmptyString(data.name_key)) {
    errors.push(tag("missing or empty required field: name_key"));
  }

  if (!VALID_FRAMES.has(data.frame)) {
    errors.push(tag(`frame must be "geocentric" or "heliocentric", got ${JSON.stringify(data.frame)}`));
  }

  const t0 = parseIso(data.t0);
  const t1 = parseIso(data.t1);
  if (t0 === null) errors.push(tag("t0 is missing or not a valid ISO 8601 timestamp"));
  if (t1 === null) errors.push(tag("t1 is missing or not a valid ISO 8601 timestamp"));
  if (t0 !== null && t1 !== null && t0 >= t1) {
    errors.push(tag(`t0 (${data.t0}) must be before t1 (${data.t1})`));
  }

  if (!Array.isArray(data.trajectory)) {
    errors.push(tag("missing required field: trajectory (array)"));
  } else {
    if (data.trajectory.length < 2) {
      errors.push(tag("trajectory must have at least 2 points"));
    }
    if (data.trajectory.length > MAX_TRAJECTORY_POINTS) {
      errors.push(
        tag(`trajectory has ${data.trajectory.length} points, exceeds the ${MAX_TRAJECTORY_POINTS}-point performance budget`),
      );
    }
    let prevT = -Infinity;
    data.trajectory.forEach((point, i) => {
      const pt = parseIso(point?.t);
      if (pt === null) {
        errors.push(tag(`trajectory[${i}].t is missing or not a valid ISO 8601 timestamp`));
        return;
      }
      if (pt < prevT) {
        errors.push(tag(`trajectory[${i}].t is out of chronological order`));
      }
      prevT = pt;
      if (t0 !== null && t1 !== null && (pt < t0 || pt > t1)) {
        errors.push(tag(`trajectory[${i}].t (${point.t}) falls outside [t0, t1]`));
      }
      for (const axis of ["x", "y", "z"]) {
        if (!isFiniteNumber(point?.[axis])) {
          errors.push(tag(`trajectory[${i}].${axis} must be a finite number`));
        }
      }
    });
  }

  if (!Array.isArray(data.milestones)) {
    errors.push(tag("missing required field: milestones (array)"));
  } else {
    data.milestones.forEach((m, i) => {
      if (!isNonEmptyString(m?.key)) {
        errors.push(tag(`milestones[${i}].key is missing or empty`));
      }
      const mt = parseIso(m?.t);
      if (mt === null) {
        errors.push(tag(`milestones[${i}].t is missing or not a valid ISO 8601 timestamp`));
      } else if (t0 !== null && t1 !== null && (mt < t0 || mt > t1)) {
        errors.push(tag(`milestones[${i}].t (${m.t}) falls outside [t0, t1]`));
      }
      for (const axis of ["lat", "lng"]) {
        const v = m?.[axis];
        if (v !== undefined && v !== null && !isFiniteNumber(v)) {
          errors.push(tag(`milestones[${i}].${axis} must be a finite number or null`));
        }
      }
    });
  }

  if (!Array.isArray(data.bodies) || data.bodies.length === 0) {
    errors.push(tag("bodies must be a non-empty array"));
  } else if (!data.bodies.every(isNonEmptyString)) {
    errors.push(tag("bodies must contain only non-empty strings"));
  }

  if (data.bodyCalibration !== undefined) {
    if (typeof data.bodyCalibration !== "object" || data.bodyCalibration === null) {
      errors.push(tag("bodyCalibration must be an object"));
    } else if (data.bodyCalibration.moon !== undefined) {
      const phaseDeg = data.bodyCalibration.moon?.phaseDeg;
      if (!isFiniteNumber(phaseDeg)) {
        errors.push(tag("bodyCalibration.moon.phaseDeg must be a finite number"));
      }
    }
  }

  return errors;
}

/**
 * Validates raw JSON text: enforces the 500 KB size budget before parsing,
 * then delegates to validateMissionSpec. Returns { errors, data }.
 */
export function validateMissionFileText(text, { fileName } = {}) {
  const byteLength = Buffer.byteLength(text, "utf8");
  const errors = [];
  const tag = (msg) => (fileName ? `${fileName}: ${msg}` : msg);

  if (byteLength > MAX_FILE_BYTES) {
    errors.push(tag(`file is ${byteLength} bytes, exceeds the ${MAX_FILE_BYTES}-byte performance budget`));
  }

  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    return { errors: [...errors, tag(`invalid JSON: ${err.message}`)], data: null };
  }

  return { errors: [...errors, ...validateMissionSpec(data, { fileName })], data };
}

/**
 * Validates the missions/index.json shape and cross-checks each listed slug
 * against the set of mission slugs actually present on disk.
 */
export function validateIndexSpec(data, { knownSlugs } = {}) {
  const errors = [];

  if (typeof data !== "object" || data === null || !Array.isArray(data.missions)) {
    return ["index.json: missing or invalid required field: missions (array)"];
  }

  data.missions.forEach((entry, i) => {
    if (!isNonEmptyString(entry?.slug)) {
      errors.push(`index.json: missions[${i}].slug is missing or empty`);
    } else if (knownSlugs && !knownSlugs.has(entry.slug)) {
      errors.push(`index.json: missions[${i}].slug "${entry.slug}" has no matching <slug>.json file`);
    }
    if (!isNonEmptyString(entry?.name_key)) {
      errors.push(`index.json: missions[${i}].name_key is missing or empty`);
    }
  });

  return errors;
}

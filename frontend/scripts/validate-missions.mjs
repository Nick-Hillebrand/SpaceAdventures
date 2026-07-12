#!/usr/bin/env node
// Build-time validator for frontend/public/missions/*.json (Architecture/22-
// ephemeris-and-mission-replay.md, G3 "Tests" requirement). Run via
// `npm run validate:missions`; wire into CI once a pipeline exists (P3).

import { readdirSync, readFileSync } from "node:fs";
import { join, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { validateMissionFileText, validateIndexSpec } from "./validateMissionSchema.mjs";

const MISSIONS_DIR = fileURLToPath(new URL("../public/missions", import.meta.url));

function main() {
  const allErrors = [];
  const files = readdirSync(MISSIONS_DIR).filter((f) => f.endsWith(".json"));
  const missionFiles = files.filter((f) => f !== "index.json");
  const knownSlugs = new Set(missionFiles.map((f) => basename(f, ".json")));

  for (const fileName of missionFiles) {
    const text = readFileSync(join(MISSIONS_DIR, fileName), "utf8");
    const { errors } = validateMissionFileText(text, { fileName });
    allErrors.push(...errors);
  }

  if (files.includes("index.json")) {
    const text = readFileSync(join(MISSIONS_DIR, "index.json"), "utf8");
    let indexData;
    try {
      indexData = JSON.parse(text);
    } catch (err) {
      allErrors.push(`index.json: invalid JSON: ${err.message}`);
      indexData = null;
    }
    if (indexData) {
      allErrors.push(...validateIndexSpec(indexData, { knownSlugs }));
    }
  } else {
    allErrors.push("missions/index.json is missing");
  }

  if (allErrors.length > 0) {
    console.error(`Mission schema validation failed with ${allErrors.length} error(s):`);
    for (const err of allErrors) console.error(`  - ${err}`);
    process.exit(1);
  }

  console.log(`Validated ${missionFiles.length} mission file(s) + index.json — all OK.`);
}

main();

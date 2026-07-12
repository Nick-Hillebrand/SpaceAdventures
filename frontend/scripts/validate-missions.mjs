#!/usr/bin/env node
// Build-time validator for frontend/public/missions/*.json (Architecture/22-
// ephemeris-and-mission-replay.md, G3 "Tests" requirement). Run via
// `npm run validate:missions`; wire into CI once a pipeline exists (P3).

import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { validateMissionFileText, validateIndexSpec } from "./validateMissionSchema.mjs";

const MISSIONS_DIR = fileURLToPath(new URL("../public/missions", import.meta.url));
const MODELS_DIR = fileURLToPath(new URL("../public/models/missions", import.meta.url));
const LOCALES_DIR = fileURLToPath(new URL("../src/locales", import.meta.url));
const LOCALES = ["de", "en", "es", "fr", "ja", "ru"];

/** Flattens a nested i18n object into a Set of dotted key paths, e.g. {a:{b:1}} -> "a.b". */
function flattenKeys(obj, prefix = "", out = new Set()) {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      flattenKeys(value, path, out);
    } else {
      out.add(path);
    }
  }
  return out;
}

function loadModelFileData() {
  const knownModelFiles = new Set();
  const modelFileSizes = new Map();
  if (existsSync(MODELS_DIR)) {
    for (const f of readdirSync(MODELS_DIR)) {
      knownModelFiles.add(f);
      modelFileSizes.set(f, statSync(join(MODELS_DIR, f)).size);
    }
  }
  return { knownModelFiles, modelFileSizes };
}

function loadLocaleKeySets() {
  const localeKeySets = new Map();
  for (const locale of LOCALES) {
    const text = readFileSync(join(LOCALES_DIR, `${locale}.json`), "utf8");
    localeKeySets.set(locale, flattenKeys(JSON.parse(text)));
  }
  return localeKeySets;
}

function main() {
  const allErrors = [];
  const files = readdirSync(MISSIONS_DIR).filter((f) => f.endsWith(".json"));
  const missionFiles = files.filter((f) => f !== "index.json");
  const knownSlugs = new Set(missionFiles.map((f) => basename(f, ".json")));
  const { knownModelFiles, modelFileSizes } = loadModelFileData();
  const localeKeySets = loadLocaleKeySets();

  for (const fileName of missionFiles) {
    const text = readFileSync(join(MISSIONS_DIR, fileName), "utf8");
    const { errors } = validateMissionFileText(text, {
      fileName,
      knownModelFiles,
      modelFileSizes,
      localeKeySets,
    });
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

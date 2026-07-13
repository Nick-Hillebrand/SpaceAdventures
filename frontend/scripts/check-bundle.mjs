#!/usr/bin/env node
// Bundle budget gate (26-performance.md §2.1). Run after `npm run build`.
// Walks the real Vite manifest (dist/.vite/manifest.json) rather than
// guessing from filenames, so the check tracks the actual chunk graph.
import { readFileSync, existsSync } from "node:fs";
import { gzipSync } from "node:zlib";
import path from "node:path";

const DIST = path.resolve(import.meta.dirname, "..", "dist");
const MANIFEST_PATH = path.join(DIST, ".vite", "manifest.json");

const KB = 1024;
const BUDGETS = {
  initialJsKb: 250,
  lazyChunkKb: 200,
  cssKb: 50,
  embedKb: 30,
};

// Marker string literal that survives minification inside three.js/globe.gl
// output (e.g. the "THREE.WebGLRenderer: ..." warning text) — used to detect
// chunks in the three.js/globe.gl family, which are lazy-only with no size
// cap of their own (table 2.1), instead of the generic 200 KB lazy budget.
const THREE_FAMILY_MARKER = "WebGLRenderer";

if (!existsSync(MANIFEST_PATH)) {
  console.error(
    `check-bundle: no manifest at ${MANIFEST_PATH} — run \`npm run build\` first.`,
  );
  process.exit(1);
}

const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf-8"));

const fileGzipSizeCache = new Map();
function gzipSizeOf(file) {
  if (fileGzipSizeCache.has(file)) return fileGzipSizeCache.get(file);
  const bytes = readFileSync(path.join(DIST, file));
  const size = gzipSync(bytes).length;
  fileGzipSizeCache.set(file, size);
  return size;
}

function fileContains(file, marker) {
  return readFileSync(path.join(DIST, file), "utf-8").includes(marker);
}

const entryKey = Object.keys(manifest).find((k) => manifest[k].isEntry);
if (!entryKey) {
  console.error("check-bundle: no entry chunk found in manifest.");
  process.exit(1);
}

// Recursively collects the *static* (non-dynamic) import closure of a
// manifest entry — the set of chunks the browser must fetch before that
// entry can run, excluding anything only reachable via a dynamic import
// (those are separately lazy-loaded and audited on their own).
function staticClosure(key, seen = new Set()) {
  if (seen.has(key)) return seen;
  seen.add(key);
  const entry = manifest[key];
  for (const dep of entry.imports ?? []) {
    if (dep !== "index.html") staticClosure(dep, seen);
  }
  return seen;
}

function isThreeFamily(key) {
  const files = [...staticClosure(key)].map((k) => manifest[k].file);
  return files.some((f) => fileContains(f, THREE_FAMILY_MARKER));
}

function totalGzip(key) {
  const files = new Set([...staticClosure(key)].map((k) => manifest[k].file));
  let total = 0;
  for (const f of files) total += gzipSizeOf(f);
  return total;
}

let failed = false;
function check(label, actualBytes, budgetKb) {
  const budgetBytes = budgetKb * KB;
  const ok = actualBytes <= budgetBytes;
  const actualKb = (actualBytes / KB).toFixed(1);
  console.log(
    `${ok ? "PASS" : "FAIL"}  ${label}: ${actualKb} KB (budget ${budgetKb} KB)`,
  );
  if (!ok) failed = true;
}

// --- Initial JS (entry + everything it statically pulls in) ---
const initialBytes = totalGzip(entryKey);
check("Initial JS", initialBytes, BUDGETS.initialJsKb);

if (isThreeFamily(entryKey)) {
  console.error(
    "FAIL  three.js/globe.gl detected in the initial chunk — it must be lazy-only.",
  );
  failed = true;
} else {
  console.log("PASS  three.js/globe.gl is absent from the initial chunk");
}

// --- CSS ---
const entryCss = manifest[entryKey].css ?? [];
const cssBytes = entryCss.reduce((sum, f) => sum + gzipSizeOf(f), 0);
check("CSS total", cssBytes, BUDGETS.cssKb);

// --- Lazy chunks (every dynamic entry point) ---
const dynamicEntries = Object.entries(manifest).filter(
  ([, v]) => v.isDynamicEntry,
);

for (const [key] of dynamicEntries) {
  const bytes = totalGzip(key);
  const label = manifest[key].name ?? key;
  if (isThreeFamily(key)) {
    console.log(
      `SKIP  ${label}: ${(bytes / KB).toFixed(1)} KB — three.js/globe.gl family, lazy-only (no size cap)`,
    );
    continue;
  }
  check(`Lazy chunk ${label}`, bytes, BUDGETS.lazyChunkKb);
}

// --- Embed page (Milestone L / 23-seo-widgets-and-growth.md) ---
// `/embed/next-launch` ships with Step L3 (Embeddable widgets), not this
// step — skip until that route exists rather than budgeting a page that
// isn't built yet.
const embedEntry = Object.entries(manifest).find(
  ([, v]) => v.src === "src/routes/EmbedNextLaunchPage.tsx",
);
if (embedEntry) {
  const [key] = embedEntry;
  check("Embed page total", totalGzip(key), BUDGETS.embedKb);
} else {
  console.log(
    "SKIP  Embed page total — /embed/next-launch not yet implemented (Step L3)",
  );
}

if (failed) {
  console.error("\ncheck-bundle: budget breach — see FAIL lines above.");
  process.exit(1);
}
console.log("\ncheck-bundle: all budgets passed.");

#!/usr/bin/env node
/**
 * Dev-only VRML97 (.wrl) -> glTF binary (.glb) converter.
 *
 * Not part of the deployed app and not imported by `src/` — run manually,
 * by hand, when adding legacy-VRML mission assets (e.g. the Mars Pathfinder /
 * Sojourner models from mars.nasa.gov's dead vrml/ directory, recovered via
 * the Wayback Machine). See `Architecture/27-mission-simulations-3d.md`.
 *
 * Uses three.js's own loader/exporter pair (the same three version the app
 * ships) so geometry, and any features the app's scene understands, round-
 * trip faithfully: `VRMLLoaderPatched.js` (a vendored copy of
 * `three/examples/jsm/loaders/VRMLLoader.js` with a bugfix — see that file's
 * header) parses the legacy scene graph, then the stock
 * `three/examples/jsm/exporters/GLTFExporter.js` writes it back out as
 * binary glTF. No Blender, no headless browser: three's loader/exporter pair
 * is plain JS and runs fine in Node once fed raw file text.
 *
 * Usage:
 *   node scripts/vrml-convert/convert.mjs <input.wrl> <output.glb>
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

// VRMLLoader's ImageTexture handling goes through three's TextureLoader ->
// ImageLoader, which calls `document.createElementNS(...)` synchronously
// even in Node. `rover_complex.wrl` has one `ImageTexture { url "solar.jpg" }`
// reference; that sibling file was never captured by the Wayback Machine
// (checked its CDX index for mars.nasa.gov/MPF/vrml/ — only HTML-preview
// thumbnails were crawled, not the raw texture atlases next to the .wrl
// models), so the load will 404/fail — asynchronously, after export, so it
// doesn't block conversion. This DOM only needs to exist so the synchronous
// part of ImageLoader.load doesn't throw; the mesh keeps its real flat
// `Material` diffuseColor from the VRML file with no texture layered on.
// GLTFExporter's binary-export path also reaches for bare globals like
// `FileReader`/`Blob` (assuming a browser), so copy every jsdom window
// global that Node doesn't already provide rather than hand-picking one at
// a time as new "X is not defined" errors surface.
// A concrete (non-opaque) origin so storage-backed getters (localStorage,
// etc.) don't throw when swept up by the blanket copy below.
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (key in globalThis) continue;
  try {
    globalThis[key] = dom.window[key];
  } catch {
    // Some window getters (e.g. storage) can still throw in edge cases;
    // skip rather than abort the whole bridge — GLTFExporter/VRMLLoader
    // don't touch storage APIs.
  }
}
globalThis.document = dom.window.document;
globalThis.window = dom.window;
globalThis.self = globalThis;
// Node already has a native `Blob`/`File`, so the blanket copy above skipped
// them — but jsdom's `FileReader` only accepts its own `Blob` class
// (instanceof check), and GLTFExporter constructs Blobs via the bare global,
// which would otherwise resolve to Node's incompatible native one. Force
// jsdom's versions so both sides agree.
globalThis.Blob = dom.window.Blob;
globalThis.File = dom.window.File;

const { VRMLLoader } = await import("./VRMLLoaderPatched.js");
const { GLTFExporter } = await import("three/examples/jsm/exporters/GLTFExporter.js");

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function countTriangles(scene) {
  let triangles = 0;
  scene.traverse((object) => {
    if (!object.isMesh || !object.geometry) return;
    const geometry = object.geometry;
    const count = geometry.index ? geometry.index.count / 3 : geometry.attributes.position.count / 3;
    triangles += count;
  });
  return triangles;
}

async function convert(inPath, outPath) {
  const text = fs.readFileSync(inPath, "utf8");
  const loader = new VRMLLoader();
  const scene = loader.parse(text, inPath);

  const triangles = countTriangles(scene);

  const exporter = new GLTFExporter();
  const glb = await new Promise((resolve, reject) => {
    exporter.parse(scene, resolve, reject, { binary: true });
  });

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, Buffer.from(glb));

  const bytes = fs.statSync(outPath).size;
  console.log(
    `${path.relative(process.cwd(), inPath)} -> ${path.relative(process.cwd(), outPath)}: ` +
      `${triangles.toLocaleString()} triangles, ${(bytes / 1024).toFixed(0)} KB`,
  );
}

const [, , inArg, outArg] = process.argv;
if (!inArg || !outArg) {
  console.error("usage: node scripts/vrml-convert/convert.mjs <input.wrl> <output.glb>");
  process.exit(1);
}

convert(path.resolve(inArg), path.resolve(outArg)).catch((err) => {
  console.error("conversion failed:", err.stack || err.message);
  process.exit(1);
});

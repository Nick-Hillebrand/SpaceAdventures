# Mars Rover 3D Model Viewer

Lets the user rotate/zoom an interactive 3D model of the rover currently selected
in the Mars Explorer dropdown (`curiosity`, `opportunity`, `spirit`, `perseverance`),
inside a collapsed-by-default disclosure on `MarsPage`.

---

## Model Assets

Official NASA/JPL-Caltech glTF binaries (`.glb`), downloaded from NASA's public
3D Resources pages and committed to `frontend/public/models/`:

| File | Rover(s) | Source |
|---|---|---|
| `curiosity.glb` | Curiosity | https://science.nasa.gov/resource/curiosity-rover-3d-model/ |
| `perseverance.glb` | Perseverance | https://science.nasa.gov/resource/mars-perseverance-rover-3d-model/ |
| `mer.glb` | Spirit, Opportunity | https://science.nasa.gov/resource/spirit-and-opportunity-rover-3d-model/ |

NASA only publishes one combined twin-rover model for the Mars Exploration Rovers,
so both `opportunity` and `spirit` map to `mer.glb`. See
`frontend/public/models/CREDITS.md` for the full licensing note.

**Licensing:** NASA 3D model files, texture maps, and polygon data are generally
not copyrighted in the US. Commercial use is fine as long as the material does not
state or imply NASA's endorsement, and the NASA/JPL insignia is not used as a logo.
See https://www.nasa.gov/nasa-brand-center/images-and-media/. The in-app credit
line is `"Model: NASA/JPL-Caltech"` (`mars.rover3dCredit`).

---

## Dependency

`three` (`^0.185.1`) — already a transitive dependency of `globe.gl`/`three-globe`
(used by the ISS tracker), promoted to a direct `dependencies` entry since it's now
imported directly. Two addons load from `three/examples/jsm/`:
`GLTFLoader.js` (model loading) and `OrbitControls.js` (mouse/touch orbit).

`three` ships **no bundled TypeScript types** in this resolution, and neither addon
has an `@types` package. Following the same convention as `globe.gl` (see
`src/types/globe.d.ts`), ambient module stubs live in `src/types/three-jsm.d.ts`:
```ts
declare module 'three';
declare module 'three/examples/jsm/loaders/GLTFLoader.js';
declare module 'three/examples/jsm/controls/OrbitControls.js';
```
Because `THREE` is therefore typed as `any`, code that needs to reference a
three.js shape (e.g. disposing a loaded model's geometry/materials) defines local
structural interfaces instead of `THREE.Object3D`/`THREE.Mesh` — see
`Disposable`/`MeshLike`/`Object3DLike` in `roverScene.ts`.

---

## Architecture

Split into two layers so each can be tested independently and both clear the
project's per-file branch-coverage bar:

### `src/lib/roverScene.ts` — pure three.js wrapper

`createRoverScene(container: HTMLElement): RoverScene` returns `{ loadModel(url),
dispose() }`. Owns scene/camera/renderer/lights/`OrbitControls` setup, an
internal render loop (`requestAnimationFrame`), and a `window` resize listener.

`loadModel(url)`:
1. Disposes the previously-loaded model (`scene.remove` + geometry/material
   `dispose()` via `Object3D.traverse`), if any.
2. Loads the new glTF via `GLTFLoader`.
3. Computes a `THREE.Box3` bounding box around the loaded scene, then
   auto-centers and uniformly scales it so `max(size.x, size.y, size.z)` maps to
   `TARGET_MODEL_SIZE = 2.2` world units — this normalizes wildly different
   real-world rover dimensions (Curiosity vs. the much smaller MER twins) to a
   consistent on-screen size without hardcoded per-model magic numbers.
4. Resets the camera/orbit target and resolves.

`dispose()` tears down the resize listener, cancels the render loop, disposes
`OrbitControls` and the renderer, disposes the current model, and detaches the
canvas from the container.

### `src/components/RoverViewer.tsx` — thin React wrapper

`<RoverViewer rover="curiosity" />`:
- Mounts a container `<div>`, creates the scene once on mount (`useEffect` with
  `[]` deps), disposes it on unmount.
- A second `useEffect` (deps: `[rover]`) maps the rover name to its model URL and
  calls `loadModel()`, tracking `loading` / `ready` / `error` status. An
  unmapped rover name is treated as an immediate error (no network call).
- Guards against a stale `loadModel()` resolving after the rover prop has
  changed or the component has unmounted, via a `cancelled` flag closed over by
  the effect.

### `MarsPage.tsx` integration

The viewer sits behind a `<details className="mars-rover-3d">` disclosure
(mirroring the TLE `<details>` on `IssPage`), tracked via `onToggle` into a
`show3d` boolean. `<RoverViewer rover={rover} />` is only mounted when
`show3d` is true — this avoids forcing the ~11 MB model download on every visit
to the Mars tab; it only fires once the user opts in.

---

## Test Strategy

jsdom has no WebGL context. Unlike 2D `canvas.getContext("2d")` (which jsdom
returns as `null` gracefully — see `NeoOrbitSimulation.tsx`), `THREE.WebGLRenderer`
**throws** in its constructor when it can't acquire a context. Any test that
constructs a `RoverScene` must mock `three`, `GLTFLoader`, and `OrbitControls`
at the module level — never let the real renderer instantiate.

`__tests__/lib/roverScene.test.ts` mocks all three modules via `vi.hoisted()`
state (P28 pattern) and covers: container sizing + zero-dimension fallback,
bounding-box-based centering/scaling math, load-error handling (`Error` and
non-`Error` rejection paths), model-switch disposal (single material, array
materials, geometry-less/material-less children), window resize handling, and
full `dispose()` teardown. Every `createRoverScene()` call is tracked in an
`activeScenes` array and disposed in `afterEach` — otherwise each test's real
`window.addEventListener("resize", …)` call leaks into later tests sharing the
same jsdom `window`, and a later `dispatchEvent(new Event("resize"))` fires
every previously-registered listener at once.

`__tests__/components/RoverViewer.test.tsx` mocks `@/lib/roverScene` entirely
(a hoisted `{ loadModel, dispose }` pair), and asserts on prop-driven behavior:
correct model URL per rover (including the shared `mer.glb` for both twins),
loading/ready/error status text, re-loading on rover prop change without
recreating the scene, disposal on unmount, and that a late resolution after
unmount doesn't throw or update state.

`__tests__/routes/MarsPage.test.tsx` mocks `@/components/RoverViewer` itself
(same pattern IssPage's tests use for `globe.gl`) and only checks: the viewer is
not mounted until the disclosure opens, it receives the currently-selected
rover, it re-renders with a new rover after switching, and it unmounts when the
disclosure collapses.

See `Architecture/11-testing.md` pitfall **P36** for the mocking/typing details.

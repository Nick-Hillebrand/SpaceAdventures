# Mission Simulations — 3D Models & Close-Up Phases (v2 Step S2)

Extends mission replay (`22-ephemeris-and-mission-replay.md` G3) from
marker-on-a-trajectory into full mission simulations: at key milestones the
replay transitions into a close-up 3D scene showing the real spacecraft model
(landing, surface operations, splashdown). Initial missions: **Apollo 11**
(first crewed Moon landing) and **Mars Pathfinder / Sojourner** (first rover on
Mars, 1997). The schema and pipeline are designed so every further mission is
data + assets only — no new code.

**Prerequisite:** Step S1 — the replay engine (mission JSON format, replay
scene, scrubber), i.e. the G3 section of `22-…` in its pulled-forward
static-content scope (no Horizons cache/API — see the sequencing note in
`22-…`). **Supersedes nothing** — purely additive; mission files without
vignettes keep working unchanged.

---

## Model assets

### Sources & licensing

Same legal basis as the rover viewer (`13-mars-rover-3d-model.md`): NASA 3D
models are not copyrighted in the US; commercial use is fine provided no
NASA endorsement is implied and the insignia is not used as a logo
(https://www.nasa.gov/nasa-brand-center/images-and-media/). The Smithsonian
Apollo 11 scans are **CC0** — no conditions at all. Every asset gets a
provenance entry (source URL, license, conversion steps) in
`frontend/public/models/CREDITS.md`; in-app credit line
`t("missions.modelCredit")` shows "Model: NASA/JPL-Caltech" or
"Model: Smithsonian Institution (CC0)" per asset.

| Asset | Mission | Source | License | Format as published |
|---|---|---|---|---|
| Lunar Module | Apollo 11 | https://science.nasa.gov/3d-resources/apollo-lunar-module/ | NASA (public domain) | web-friendly, ~700 KB |
| CSM Columbia (exterior) | Apollo 11 | https://3d.si.edu/collections/apollo11 | **CC0** | photogrammetry scan — heavy, must decimate |
| Pathfinder lander + Sojourner | Pathfinder | https://mars.nasa.gov/MPF/vrml/vrml.html + `nasa/NASA-3D-Resources` GitHub | NASA (public domain) | VRML / legacy CAD — must convert |

**Do not source from Sketchfab/CGTrader community uploads** — licenses vary
and provenance is unverifiable. NASA + Smithsonian only.

### Conversion pipeline (offline, not runtime)

Committed `.glb` files in `frontend/public/models/missions/`, produced
offline and documented per asset in `CREDITS.md`:

1. Legacy formats (VRML, `.3ds`, `.obj`) → glTF via headless Blender
   (`blender --background --python …`).
2. Optimize via `gltf-transform`: weld/dedup, decimate scan meshes,
   resize textures to ≤ 2048², `meshopt` compression.
3. Budget check (enforced by the CI script below): **≤ 2 MB per `.glb`**,
   **≤ 6 MB total per mission**.

The exact commands per asset live in `CREDITS.md` so a re-conversion is
reproducible. No runtime fetching from third-party hosts (CSP stays strict;
rule 9 does not apply at runtime because assets are committed, reviewed
files).

---

## The scale problem — three rendering contexts

A 10 m spacecraft is sub-pixel at system scale. Continuous seamless zoom from
AU to meters is an explicit **non-goal** (float precision + effort). Instead:

| Context | Scale | What renders | Provided by |
|---|---|---|---|
| Trajectory | AU / body-centric | marker + trajectory polyline + milestone ticks | G3, unchanged |
| Approach | body radii | model as billboard sprite at exaggerated scale near the body | this spec (cheap: sprite, not mesh) |
| **Vignette** | real meters | self-contained close-up scene: glTF model, surface/space environment, own camera + lighting | this spec (core) |

Vignettes are honest staging, not physics: the trajectory is the *true* part
(real ephemerides, the differentiator per roadmap #11); the vignette
illustrates the milestone (LM on the regolith, airbags on Ares Vallis). EDL
sequences (parachute, airbag bounces) are curated camera+animation
choreography, not simulation. UI labels vignettes
`t("missions.vignette.illustration")` to keep the "it's true, not an
animation" claim clean.

---

## Mission JSON schema extension

Additive to the G3 format (`frontend/public/missions/<slug>.json`).
A milestone gains an optional `vignette`:

```jsonc
"milestones": [
  { "t": "1969-07-20T20:17:40Z", "key": "missions.apollo11.landing",
    "vignette": {
      "model": "/models/missions/apollo11-lm.glb",
      "environment": "moon-surface",     // "moon-surface" | "mars-surface" | "space"
      "modelCredit": "missions.credit.nasa",
      "cameraOrbit": { "distanceM": 18, "elevationDeg": 12 },
      "narrationKey": "missions.apollo11.landing.narration"
    } }
]
```

Environments are code (three per this spec, reusable by every mission):
ground plane with a public-domain NASA surface texture + matched light color
and sky; `"space"` reuses the existing starfield. The build-time schema
validator from G3 is extended: vignette model paths must exist in
`public/models/missions/`, environment must be a known id, all keys present
in all six locales.

### Trajectory data for the initial missions

- **Pathfinder cruise:** Horizons carries historical spacecraft; verify
  coverage for Mars Pathfinder (SPK `-53`) in `build_mission.py`. Frame
  heliocentric, `bodies: ["earth","mars"]`.
- **Apollo 11:** Horizons has **no** Apollo trajectories. Source: NASA's
  published as-flown trajectory reconstruction (Apollo 11 Mission Report /
  Apollo Flight Journal state vectors), curated as keyframes in the mission
  YAML with the source cited; `build_mission.py` gains a `--from-yaml`
  path that interpolates keyframes instead of querying Horizons. Frame
  geocentric, `bodies: ["earth","moon"]` (both supported by G3).

---

## Frontend

- `src/solar/missionVignette.ts` — imperative module (same pattern as
  `solar/scene.ts` / `lib/roverScene.ts`):
  `createVignette(container, spec, getLabel) → { play(), dispose() }`.
  Owns its own renderer/scene/camera; loads the glTF via `GLTFLoader`;
  auto-center/scale via the bounding-box normalization already proven in
  `roverScene.ts` — **extract that into `src/lib/gltfNormalize.ts`** and use
  it from both (refactor called out to `13-…`; behavior unchanged, its tests
  move).
- Replay UI: vignettes attach to `MissionPanel`, so they work identically
  from both entry points — the `/missions/:slug` route and the solar-tab
  Missions panel (see "Engine integration" in `22-…`). When the scrubber
  enters a milestone with a vignette, the milestone card offers
  `t("missions.enterVignette")`; entering crossfades the trajectory scene
  out (paused), mounts the vignette, and back on exit.
  No auto-entry — scrubbing stays uninterrupted; keyboard/screen-reader
  accessible (button, not hover).
- Models load **only on vignette entry** (never with the route chunk),
  disposed on exit (`13-…` disposal patterns apply). Loading state +
  `t("missions.vignette.error")` fallback to the milestone card on failure.
- Embed variant (`/missions/:slug/embed`): vignettes included — they are the
  shareable moment — but models still lazy-load on interaction only.

### Initial mission content

| Mission | Vignettes (v1 scope) | Models |
|---|---|---|
| `apollo-11` | landing (LM on surface), first EVA (LM + flag-less surface scene), splashdown optional — cut if budget tight | `apollo11-lm.glb`; CSM sprite at approach scale, Columbia scan close-up **deferred** until decimation proves ≤ 2 MB |
| `mars-pathfinder` | EDL (airbag descent choreography), surface ops (lander petals open, Sojourner rolled off) | `pathfinder-lander.glb`, `sojourner.glb` |

Keep v1 tight: two missions, two environments (moon/mars surface) + space.
The mission library grows afterward at data+asset cost only — candidate next
entries per roadmap #11: Artemis 1, Perseverance + Ingenuity (models already
in `public/models/`), Voyager grand tour (space vignettes only).

---

## Performance budgets (per `26-performance.md`)

- Mission route chunk unchanged (vignette module lazy inside the already-lazy
  route; three.js stays lazy-only).
- Per-model `.glb` ≤ 2 MB, per-mission total ≤ 6 MB — enforced by a size
  check in the mission-validation CI script (extension of the G3 check).
- Vignette scene: ≤ 100k triangles after decimation, textures ≤ 2048²,
  single directional + ambient light, no shadows in v1.
- Dispose verified: entering/leaving a vignette 10× must not grow GPU
  memory (manual QA note; automated via disposal unit tests).

---

## Tests

Per P36: never instantiate a real `WebGLRenderer` in jsdom — mock `three`,
`GLTFLoader` at module level.

- `lib/gltfNormalize.test.ts` — normalization math moves here from the
  `roverScene` tests it was extracted from.
- `solar/missionVignette.test.ts` — model URL loading, environment selection,
  load-error path, full dispose teardown, credit-line lookup.
- Replay UI tests — vignette button appears only for milestones that
  declare one; enter mounts / exit unmounts and disposes (mocked module);
  scrubbing while a vignette is open pauses trajectory time; vignette entry
  works from the solar-tab panel, not only the dedicated route; locale
  switching on narration cards.
- Build-time validator — schema extension: missing model file, unknown
  environment, missing locale keys, size-budget breach each fail the check.
- Coverage: ≥ 80 % branch per touched module (rule 1), all six locales
  (rule 3), dates via `dateTime.ts` (rule 4).

---

## Rollout order inside the step

1. Schema extension + validator + environments + vignette module (tested,
   no content).
2. **Apollo 11** end-to-end — validates the curated-trajectory path and the
   NASA LM asset (already web-friendly; lowest asset risk).
3. **Pathfinder/Sojourner** — validates the legacy-format conversion
   pipeline (VRML → glb) and the Mars surface environment.
4. Only then: evaluate the Columbia CC0 scan decimation as a follow-up
   content PR, and open the mission library cadence.

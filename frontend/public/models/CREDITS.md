# 3D Model Credits

All models are official NASA/JPL-Caltech assets, downloaded from NASA's public
3D Resources pages (binary glTF, `.glb`). NASA content — including 3D model
files, texture maps, and polygon data — is generally not copyrighted in the
United States and may be used for commercial purposes, provided the material
does not state or imply NASA's endorsement of a commercial product or service,
and the NASA/JPL insignia is not used as a logo. See
https://www.nasa.gov/nasa-brand-center/images-and-media/ for the full policy.

## Rover viewer (`13-mars-rover-3d-model.md`)

| File | Rover(s) | Source |
|---|---|---|
| `curiosity.glb` | Curiosity | https://science.nasa.gov/resource/curiosity-rover-3d-model/ |
| `perseverance.glb` | Perseverance | https://science.nasa.gov/resource/mars-perseverance-rover-3d-model/ |
| `mer.glb` | Spirit, Opportunity | https://science.nasa.gov/resource/spirit-and-opportunity-rover-3d-model/ |

Credit line shown in-app: "Model: NASA/JPL-Caltech".

## Mission vignettes (`27-mission-simulations-3d.md`, Step S2)

| File | Mission / milestone | Source | Conversion |
|---|---|---|---|
| `missions/apollo11-lm.glb` | Apollo 11 — landing, first EVA | https://science.nasa.gov/3d-resources/apollo-lunar-module/ (direct `.glb` download from `assets.science.nasa.gov`) | None — already web-friendly (~700 KB, 12 materials, ~98k triangles, textures ≤ 900²). |
| `missions/pathfinder-lander.glb` | Mars Pathfinder — EDL | `lander_light.wrl`, recovered via the Wayback Machine from `mars.nasa.gov/MPF/vrml/lander_light.wrl` (the live page now 302s to `science.nasa.gov/mission/mars-pathfinder/`; the original VRML directory is gone). NASA (public domain). | `scripts/vrml-convert/convert.mjs lander_light.wrl pathfinder-lander.glb` — see below. |
| `missions/pathfinder-surface-ops.glb` | Mars Pathfinder — surface ops (rover deployed) | `lander_rover.wrl`, recovered the same way from `mars.nasa.gov/MPF/vrml/lander_rover.wrl`. NASA (public domain). | `scripts/vrml-convert/convert.mjs lander_rover.wrl pathfinder-surface-ops.glb` — combined lander + deployed Sojourner scene, satisfies the "Sojourner rolled off" framing without a separate rover-only asset. |

Credit line shown in-app: `t("missions.credit.nasa")` → "Model: NASA/JPL-Caltech".

### Pathfinder/Sojourner conversion pipeline

The legacy `.wrl` (VRML97) files linked from the dead `mars.nasa.gov/MPF/vrml/`
directory were recovered from the Wayback Machine's CDX index. Blender was not
available in the environment that produced these assets, so
`scripts/vrml-convert/convert.mjs` converts them directly with three.js's own
`VRMLLoader`/`GLTFExporter` (the exact three version this app ships) run under
plain Node, with a `jsdom` document/window bridged in for the handful of
browser globals those loaders assume (`document`, `FileReader`, `Blob`). See
that script's header and `VRMLLoaderPatched.js`'s header comment for the
upstream VRMLLoader bug it patches (a mixed `USE`/node `children [...]` array
losing nested `DEF`s) and the non-visual-node (`TouchSensor`) `USE` crash it
also fixes.

**Not used:** `rover_complex.wrl` (a separate, more detailed standalone Sojourner
model also recovered from the Wayback Machine) references an external
`solar.jpg` texture that was never captured by the crawler — checked the CDX
index for the whole `mars.nasa.gov/MPF/vrml/` path; only HTML-preview
thumbnails were archived, not the raw texture atlases the VRML files sit next
to. Rather than ship the model with a missing/fabricated texture,
`pathfinder-surface-ops.glb` (from `lander_rover.wrl`, no external texture
dependency) is used instead — it already shows the deployed rover next to the
lander, which is what the "surface ops" milestone needs.

Re-running the conversion (from `frontend/`):

```sh
node scripts/vrml-convert/convert.mjs <input.wrl> <output.glb>
```

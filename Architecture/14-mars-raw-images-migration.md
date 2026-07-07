# Mars Photo Source Migration

`api.nasa.gov/mars-photos` — the API described in `Architecture/04-nasa-apis.md`
as the source for Mars Explorer — has been **permanently decommissioned**.
Its backend was `corincerami/mars-photo-api`, hosted on Heroku and reverse-proxied
by `api.nasa.gov`; that Heroku app no longer exists, so every route under the
prefix (`/photos`, `/manifests/{rover}`, `/rovers`) now returns Heroku's generic
"no such app" page with HTTP 404, for every rover and every parameter combination.
This is not a rate limit or a bad request — the upstream service is gone.

`app/services/mars_raw_images_client.py` replaces it with NASA's own public
raw-image gallery APIs (`mars.nasa.gov`), which are free, need no API key, and
are licensed the same as all other NASA/JPL imagery (see Licensing below).

---

## Sources

| Rover | Endpoint | Notes |
|---|---|---|
| Curiosity (MSL) | `https://mars.nasa.gov/api/v1/raw_image_items/` | Real pagination (`per_page`, `page`), `condition_N` filter DSL |
| Perseverance (Mars2020) | `https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020,ingenuity` | Different schema; pagination params are silently ignored once `sol` is set — a single call returns every image for that sol |
| Opportunity, Spirit (MER) | **none** | See "No live source for MER" below |

Both live endpoints were reverse-engineered by inspecting the public raw-image
browser pages' own JS bundles (`https://mars.nasa.gov/js/raw-images/m20/...`) —
neither is documented for third-party use, so field names and behavior were
confirmed by direct testing rather than a spec, and could change without notice.
If they start failing, the fallback path (`stale` cache, then
`MARS_ARCHIVE_UNAVAILABLE`) is what protects the app, not a version pin.

### Camera-name normalization

Curiosity's API reports more granular instrument codes than the app's UI/DB
schema uses (left/right, A-side/B-side): `FHAZ_LEFT_A`, `RHAZ_RIGHT_B`,
`NAV_LEFT_A`, `MAST_LEFT`, `CHEMCAM_RMI`, `MAHLI`, `MARDI`, etc. These are
mapped back onto the existing 7-bucket list (`FHAZ`, `RHAZ`, `MAST`, `CHEMCAM`,
`MAHLI`, `MARDI`, `NAVCAM`) via `MSL_CAMERA_MAP` so the dropdown and cached rows
stay unchanged from before the migration.

Perseverance's instrument codes (`MCZ_LEFT`, `NAVCAM_LEFT`,
`FRONT_HAZCAM_LEFT_A`, `SKYCAM`, `SHERLOC_WATSON`, `SUPERCAM_RMI`, ...) already
match `ROVER_CAMERAS["perseverance"]` almost exactly — only `SUPERCAM_RMI` was
missing and has been added. No normalization needed for this rover.

### earth_date filtering (approximated, not server-side)

Neither endpoint reliably filters by earth date server-side (tested
`condition_N=value:date_taken:gte/lt` on MSL — returned 0 results for a known-
valid range; M20 silently ignores date-range params entirely regardless of
`sol`). Instead, `sol_estimate()`/`sol_candidates()` approximate the sol from
the requested earth_date using each rover's landing epoch and the Mars sol
length (`88775.244` seconds):

- Curiosity landing: 2012-08-06 05:17:57 UTC
- Perseverance landing: 2021-02-18 20:55:00 UTC

The client queries sol-1, sol, and sol+1 as candidates (to absorb estimation
drift near a sol boundary), then filters the combined results by each item's
real, accurate `date_taken`/`date_taken_utc` field client-side. This means an
earth_date query costs up to 3x the network calls of a sol query — acceptable
given the permanent cache in front of it.

### Synthetic IDs for Perseverance

`MarsPhoto.id` is an `Integer` primary key. MSL's raw-image items have a real
numeric `id`. M20's raw-image items only have `imageid`, a string
(e.g. `"NLG_1911_0836586201_237ECM_N0892450NCAM00500_00_2I4J"`) with no numeric
counterpart anywhere in the response. A stable synthetic ID is derived via
`sha256(imageid)`, truncated to the first 8 bytes, masked to a positive 63-bit
integer (`synthetic_id()`). 32-bit CRC32 was considered and rejected: at
~1,007,431 total M20 images (per the API's own `total_images` count observed
during testing), a 32-bit hash's birthday bound predicts ~116 collisions —
unacceptable for a primary key. SHA-256 truncated to 64 bits has negligible
collision probability at this scale.

---

## No live source for MER (Opportunity, Spirit)

Opportunity's and Spirit's raw images only ever lived behind the now-dead
Heroku mirror. Every mission-slug variant tried against the MSL-style API
(`opportunity`, `spirit`, `mera`, `merb`, `mer-a`, `mer-b`, ...) returns
`total: 0`, and the dedicated MER gallery pages under `mars.nasa.gov/mer/`
redirect away. Their imagery is only available via NASA's PDS Imaging Node,
which has no simple per-sol JSON REST endpoint — a much larger integration
effort than mirroring MSL/M20's raw-image APIs, and out of scope here.

`mars_service.LIVE_ROVERS = {"curiosity", "perseverance"}` encodes this gap
explicitly. For `opportunity`/`spirit`, `fetch_photos()`:
- serves cached rows if any exist for the requested sol/earth_date/camera/page
  (never attempts a live fetch — there's nothing to attempt), or
- raises `NasaClientError("MARS_NO_LIVE_SOURCE", ...)`, a **distinct** code
  from `MARS_ARCHIVE_UNAVAILABLE` (a live source exists but errored) and from
  the generic `NASA_UNAVAILABLE` used by other NASA API consumers, so the
  frontend can show "no live photos for this rover" rather than implying a
  transient outage.

Both rovers remain selectable in the Mars Explorer dropdown (not removed) —
if the DB is later backfilled from the PDS archive, they'll start working
automatically the moment `LIVE_ROVERS` is updated to include them.

---

## Error codes

| Code | Meaning | Raised by |
|---|---|---|
| `MARS_ARCHIVE_UNAVAILABLE` | mars.nasa.gov unreachable, non-2xx, or invalid JSON | `MarsRawImagesClient._get()` |
| `MARS_NO_LIVE_SOURCE` | Rover has no live source and no cached rows exist | `mars_service.fetch_photos()` |

Both reuse `NasaClientError` (code/message/status_code, default 502) so the
existing `@app.exception_handler(NasaClientError)` in `main.py` covers them
without a new handler.

---

## Licensing

Per JPL's official image-use policy
(https://www.jpl.nasa.gov/jpl-image-use-policy): commercial use is permitted
without prior permission. Required credit line: **"Courtesy NASA/JPL-Caltech"**.
The NASA insignia, NASA logotype, NASA seal, and JPL logo require prior written
approval to use — do not use them as a substitute credit. No image may be used
to state or imply NASA/JPL/Caltech endorsement of a commercial product or
service. Same terms as the 3D rover models (`Architecture/13-mars-rover-3d-model.md`).

See `Architecture/11-testing.md` P37 for the testing-relevant summary of all of
the above.

# NASA APIs

Base URL for all NASA APIs: `https://api.nasa.gov/`
API key: injected from `NASA_API_KEY` env var. Never expose in any response.

---

## APOD — Astronomy Picture of the Day

**Endpoint:** `GET https://api.nasa.gov/planetary/apod`

**Key params:** `date` (YYYY-MM-DD), `start_date`, `end_date`, `thumbs`

**Fields stored:** `date`, `title`, `explanation`, `url`, `hdurl`, `media_type`, `copyright`, `thumbnail_url`

### Frontend: `ApodPage.tsx`

- Full-viewport hero image (or embedded video for `media_type: "video"`)
- Date picker to browse historical APODs (any date from 1995-06-16 onwards)
- Title, explanation text, copyright attribution below the image
- `cached`/`live` badge; `stale` warning banner if served from degraded cache
- Empty state if `url` is null

---

## NeoWs — Near-Earth Object Web Service

**Endpoint:** `GET https://api.nasa.gov/neo/rest/v1/feed`

**Key params:** `start_date`, `end_date` (max 7-day window per request)

**Fields stored:** `id`, `name`, `absolute_magnitude_h`, `estimated_diameter_min_km`, `estimated_diameter_max_km`, `is_potentially_hazardous`, `close_approach_date`, `relative_velocity_kph`, `miss_distance_km`, `orbiting_body`, `nasa_jpl_url`

### Frontend: `NeoPage.tsx`

- Date-range picker (max 7 days)
- Sortable table: name, diameter, velocity, miss distance, hazardous badge
- Clicking a row opens a detail drawer with all stored fields
- Hazardous NEOs highlighted in red
- `close_approach_date` rendered via `formatDate()` in user's local timezone

---

## DONKI — Space Weather

**Base URL:** `https://api.nasa.gov/DONKI/`

**Five endpoints** (all GET, params `startDate` / `endDate`):

| Sub-endpoint | Type | Stored as |
|---|---|---|
| `FLR` | Solar Flares | Full JSON per event |
| `GST` | Geomagnetic Storms | Full JSON per event |
| `RBE` | Radiation Belt Enhancements | Full JSON per event |
| `SEP` | Solar Energetic Particles | Full JSON per event |
| `CME` | Coronal Mass Ejections | Full JSON per event |

Each event stored in `space_weather_event` table with `event_type` discriminator.

### Frontend: `SpaceWeatherPage.tsx`

- Five sub-tabs (one per event type)
- Each tab shows a timeline/card list of events for the selected date range
- Event start/peak/end times rendered via `formatDateTime()` in user's local timezone
- Date-range picker shared across all tabs

---

## Mars Rover Photos

**Endpoint:** `GET https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/photos`

**Rovers:** `curiosity`, `opportunity`, `spirit`, `perseverance`

**Key params:** `sol` OR `earth_date`, `camera`, `page`

**Fields stored:** `id`, `sol`, `earth_date`, `rover_name`, `camera_name`, `img_src`

### Frontend: `MarsPage.tsx`

- Rover selector dropdown
- Toggle between sol input and earth_date picker
- Camera selector (populated from the available cameras for the selected rover/sol)
- Paginated photo grid with lightbox on click
- `earth_date` rendered via `formatDate()` in user's local timezone
- All images must have descriptive `alt` text (accessibility)

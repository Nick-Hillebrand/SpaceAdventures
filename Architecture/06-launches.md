# Rocket Launches

Data source: Launch Library 2 (LL2) — `https://ll.thespacedevs.com/2.3.0/`
Auth: none for free tier (15 req/hr); optional `Authorization: Token <LL2_API_KEY>` header.

---

## LL2 Sync

A background `AsyncIOScheduler` task runs every 30 minutes (configurable via `LL2_SYNC_INTERVAL_MINUTES`).

**CRITICAL:** Uvicorn must run with `--workers 1`. Multiple workers spawn multiple schedulers → duplicate syncs → duplicate notifications. If multi-worker is ever needed, move the scheduler to a standalone process.

Start the scheduler inside the FastAPI `lifespan` context manager — never at module import time (causes `RuntimeError: no running event loop`).

### Sync algorithm

1. Fetch all upcoming launches with pagination:
```python
url = f"{LL2_BASE}/launches/upcoming/?mode=detailed&limit=100&ordering=net"
while url:
    r = await client.get(url)
    data = r.json()
    launches.extend(data["results"])
    url = data["next"]
```

2. **Safety limits before processing:**
   - Reject response if `Content-Length > 5 MB`
   - Process max 100 launches; log warning if more
   - Truncate fields: `name` → 200 chars, `mission_description` → 2 000 chars, all others → 500 chars

3. **Defensive field access** — LL2 fields may be absent (not just null):
```python
livestream_urls = launch.get("vidURLs") or []
mission_desc = (launch.get("mission") or {}).get("description") or ""
```

4. **Parse `net` field safely** — may have microseconds, `Z` suffix, or `+00:00`:
```python
from dateutil.parser import isoparse
net = isoparse(launch["net"])  # add python-dateutil to requirements.txt
```

5. For each launch, before upserting, read the existing DB row and compare:
   - `net` changed by > 5 minutes → insert `NET_SLIP` into `pending_notifications`
   - `status_abbrev` changed → insert `STATUS_CHANGE` into `pending_notifications`
   - Row is brand new → insert `NEW_LAUNCH` into `pending_notifications` (for agency subscribers)

6. Upsert by `ll2_id`. Mark launches no longer returned as `status_abbrev = "Gone"` (do not delete).

7. After all upserts, call `notification_service.drain_queue()`.

8. On backend startup, if `launches` table is empty → run one immediate sync.

---

## Fields Stored Per Launch

See `01-database-schemas.md` §launches table.

---

## Backend API

```
GET  /api/v1/launches/upcoming    # net > now-24h, ordered by net asc; includes last_synced_at field
POST /api/v1/launches/sync        # admin — Authorization: Bearer <ADMIN_API_KEY>
```

Response envelope includes `last_synced_at: ISO8601` = `MAX(fetched_at)` across all returned rows.

---

## Frontend: `LaunchesPage.tsx`

### View Toggle

Two views, toggled by a button pair top-right:
- **Grid view** (default) — responsive card grid, sorted by `net` ascending
- **Calendar view** — FullCalendar `dayGridMonth`

Persist active view in `localStorage` under `space-adventures-launches-view`. Both views read from the same TanStack Query result — no extra API calls on toggle.

`staleTime` for the launches query: `300_000` ms (5 minutes) — overrides global `Infinity`.

### `LaunchCard.tsx`

| Element | Source | Notes |
|---|---|---|
| Hero image | `image_url` | Fallback: rocket silhouette SVG |
| Launch name | `name` | Heading |
| Agency | `agency_name` + `agency_type` | e.g. "SpaceX · Commercial" |
| Rocket | `rocket_name` | |
| Launch pad | `pad_name`, `pad_location` | |
| Mission type badge | `mission_type` | Colour pill |
| Mission description | `mission_description` | 3 lines max, expand toggle |
| Status badge | `status_name` | green=Go, amber=TBD, red=Hold |
| Countdown | derived from `net` | Live T−Xd Xh Xm Xs, 1 Hz `setInterval` |
| Livestream button | `livestream_urls[0]` | Hidden if empty; opens in new tab |
| More streams | `livestream_urls[1…]` | Dropdown by title |
| Subscribe bell | — | Opens `<SubscribeModal>` |

### Countdown Behaviour

- Future: `T− Xd Xh Xm Xs` in monospace
- Past: `T+ Xh Xm Xs`
- `status_abbrev` is `"TBD"` or `"Hold"`: show `"NET: <date>"` via `formatDateTime(net)` — no countdown
- Check `status_abbrev` before every tick; use `useMemo` to avoid re-renders
- Use `vi.useFakeTimers` (excluding `requestAnimationFrame`) in tests — never rely on wall-clock time

### Calendar View

FullCalendar `dayGridMonth`:
- Import CSS explicitly in the component file (not in vite.config.ts):
```ts
import '@fullcalendar/core/main.css';
import '@fullcalendar/daygrid/main.css';
```
- Set `editable: false` — calendar is read-only
- Events: colour-coded chips (green/amber/red) labelled `<agency_name>: <rocket_name>`
- Clicking a chip opens the same launch card as a slide-over drawer

### Filtering

Above grid/calendar:
- Status toggles: All / Go / TBD / Hold
- Agency search: text input, client-side filter on `agency_name`

Filtering applies to both views; no extra API calls.

### Subscribe Modal (`<SubscribeModal>`)

Triggered by bell icon on card or "Subscribe to agency" in filter area.

**Not logged in:** show login prompt with buttons → `/login?return=/launches` and `/register?return=/launches`

**Logged in:**
1. Checkbox: "Subscribe to this launch" (shows name + NET)
2. Checkbox: "Subscribe to all [agency] launches"
3. Checkboxes: Email (only if `email_verified`), SMS (only if `phone_verified`); if neither is verified, show prompt to verify in Account page
4. Confirm → `POST /api/v1/subscriptions`

Filled bell = already subscribed. Clicking opens modal pre-populated for unsubscribe.

### Data Freshness

Top of page: `formatRelative(last_synced_at)` e.g. "Last updated 4 minutes ago".

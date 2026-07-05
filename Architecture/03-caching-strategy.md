# Caching Strategy

---

## NASA Data — Permanent Cache

All NASA data is stored permanently. Once a record exists in the DB for a given set of parameters, it is **never** re-fetched.

### Lookup pattern (all NASA services)

1. Build a canonical cache key from request params: e.g. `apod:2024-07-04`, `neo:2024-07-01:2024-07-07`, `mars:curiosity:1000:FHAZ:1`
2. Query DB for a matching row.
3. Row exists → return immediately (`cached: true`). No upstream call.
4. Row missing → call NASA API → insert row → return (`cached: false`).

### Today's data exception

"Today" is always evaluated as the current date in **UTC** on the backend, regardless of the user's local timezone.

- Date range **ends before today** → permanent cache; never re-fetched.
- Date range **includes today (UTC)** → always re-fetch from NASA and upsert the row. At UTC midnight, the date becomes historical and is never re-fetched again.

### Stale fallback

If the NASA API call fails (any error) but a cached row exists (including a today's record from earlier in the day), return the cached row with `stale: true`. Never show a blank page.

### Connectivity probe

When a NASA call fails with a connection error, `nasa_client.py` must:
1. Send a HEAD request to `https://www.google.com` with a 3-second timeout (one shot, no retries).
2. Probe fails → return error code `NO_INTERNET`.
3. Probe succeeds → NASA is specifically down → return `NASA_UNAVAILABLE`.

---

## ISS / N2YO — TTL-Based Cache

ISS position data changes constantly; N2YO charges per API call.

| Data | Cache duration | Notes |
|---|---|---|
| Position batch | 5 minutes | 300 entries served to all users; one N2YO call refreshes the whole batch |
| TLE | 6 hours | Changes infrequently |
| Visual passes | 1 hour | Per unique (lat, lng, alt) combination |
| Radio passes | 1 hour | Per unique (lat, lng, alt) combination |

The N2YO quota guard (see `05-iss-tracker.md`) enforces a hard cap on transactions. If the cap is reached, return cached data with `quota_exhausted: true`. If no cached data exists, return 429.

---

## Launch Data — 30-Minute Sync

Launch data is mutable (NET dates slip). A background APScheduler task syncs from LL2 every 30 minutes. No user request ever triggers a direct LL2 API call.

- Upsert all returned launches by `ll2_id`.
- Mark launches no longer in the LL2 response as `status_abbrev = "Gone"` (do not delete).
- Launches with `net` more than 24 hours in the past are excluded from the API response but kept in the DB.
- On startup, if the `launches` table is empty, run an immediate sync before serving any request.

---

## TanStack Query (Frontend)

Global default:
```ts
staleTime: Infinity  // historical data never goes stale on the client
```

Per-query overrides (set on the individual `useQuery` call, not globally):

| Query | staleTime | Reason |
|---|---|---|
| `/api/v1/iss/positions` | `270_000` ms | Triggers refetch 30 s before 5-min batch expires |
| `/api/v1/launches/upcoming` | `300_000` ms | Refreshes every 5 minutes to catch NET slips |

Global retry config:
```ts
retry: 2
retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 10000)
```

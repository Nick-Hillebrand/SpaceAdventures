# Space Adventures — Production Readiness: Required Improvements & Refactorings

*Last updated: 2026-07-06*

This document lists what must change before real (and especially paying) users
touch this app, in priority order. Findings reference actual code locations.

Legend: 🔴 blocker (do before any public users) · 🟡 required for launch ·
🟢 required for scale/paid product.

---

## 1. 🔴 Security: unauthenticated global settings endpoints

**Problem.** `backend/app/routers/settings.py` — `POST /api/v1/settings/nasa-api-key`
and `POST /api/v1/settings/n2yo-api-key` have **no authentication** and mutate the
*server-wide* API keys on `app.state.settings`. Any anonymous visitor can overwrite
the production NASA/N2YO keys with garbage and break every feature. The keys are
also not persisted, so they silently reset on restart.

**Fix.**
- For production, drop the "bring your own key" model entirely: the server runs on
  its own keys from environment variables, and the existing caching layer keeps
  usage within quota. Remove or admin-gate (via `ADMIN_API_KEY` header dependency)
  the two POST endpoints; `GET /api/v1/settings` can stay public (it only exposes
  booleans).
- If per-user keys are ever wanted, they must be stored per user in the DB and
  passed per request — never on shared app state (see §5).

---

## 2. 🔴 Bug: `DATABASE_URL` env var is ignored

**Problem.** `backend/app/database.py` hardcodes

```python
DATABASE_URL = "sqlite+aiosqlite:///./data/app.db"
engine = create_async_engine(DATABASE_URL, future=True)
```

at import time, ignoring `Settings.database_url`. The `DATABASE_URL` variable
documented in the README does nothing. This blocks the Postgres migration outright.

**Fix.** Build the engine from settings, lazily:

- Move engine/sessionmaker construction into a factory
  (`init_engine(settings) -> None` or an `get_engine(settings)` accessor) called
  from `create_app()` / lifespan, not at module import.
- Update `alembic/env.py` to read `database_url_sync` from settings/env as well.
- Keep the SQLite FK pragma listener, but make it conditional on the dialect
  (`if engine.dialect.name == "sqlite"`), so it is a no-op on Postgres.

---

## 3. 🔴 Migrate SQLite → PostgreSQL

**Problem.** SQLite is single-writer and file-bound. Combined with `--workers 1`
(see §4) it pins the whole app to one process on one machine. It also makes
backups, concurrent notification writes, and any future multi-node setup painful.

**Fix.**
1. Add `asyncpg` (async) and `psycopg[binary]` (sync, for Alembic) to
   `requirements.txt`.
2. Fix §2 first, then set `DATABASE_URL=postgresql+asyncpg://...` and
   `DATABASE_URL_SYNC=postgresql+psycopg://...`.
3. Audit models/migrations for SQLite-isms:
   - Any `sqlite_autoincrement` or JSON-stored-as-TEXT columns → use native
     `JSONB` on Postgres (translation columns are the likely candidates).
   - Datetime columns: ensure timezone-aware (`DateTime(timezone=True)`) —
     SQLite is forgiving here, Postgres is not.
   - Boolean stored as int, string-collation assumptions in ORDER BY.
4. Regenerate/verify Alembic migrations against a fresh Postgres instance;
   consider squashing to a clean initial migration before first prod deploy
   (no production data exists yet — this is the cheapest moment to do it).
5. Run the full pytest suite against Postgres in CI (service container), not only
   against SQLite, so dialect regressions are caught.
6. Add `pool_size`/`max_overflow` to `create_async_engine` (start:
   `pool_size=10, max_overflow=20` per worker; tune later).

Postgres also unlocks: `SELECT ... FOR UPDATE` (needed in §4), full-text search
(feature roadmap), and standard `pg_dump` backups.

---

## 4. 🔴 Extract the scheduler; remove the `--workers 1` constraint

**Problem.** APScheduler runs inside the web process
(`backend/app/main.py`, lifespan). This forces `--workers 1` everywhere
(CLAUDE.md rule 7), i.e. one event loop on one core for all traffic — the hard
scalability ceiling. The notification outbox drain
(`notification_service.drain_queue`, called from
`launches_service.sync_launches`) rides on the same in-process job, so a slow
Twilio/SMTP call also runs inside the web process.

Additionally, correctness currently depends on **process-local locks** that break
silently with >1 worker:

- `n2yo_client._QUOTA_LOCK` (N2YO hourly quota guard)
- `auth_service._REFRESH_LOCK` and `_OTP_LOCK` (refresh rotation, OTP issuance)

**Fix.**
1. Create a separate **worker entrypoint** (`backend/app/worker.py`) that runs
   APScheduler standalone: launch sync + `drain_queue` on their intervals. Deploy
   it as a second container sharing the same image
   (`command: python -m app.worker`).
2. Remove scheduler startup from the FastAPI lifespan (keep client setup/teardown).
3. Replace process-local locks with DB-level concurrency control (now possible on
   Postgres):
   - N2YO quota: `SELECT ... FOR UPDATE` on the `n2yo_quota` row.
   - Refresh-token rotation: `FOR UPDATE` on the token row, or rely on an atomic
     `UPDATE ... WHERE token_hash = :h AND revoked = false` returning rowcount.
   - OTP issuance: unique constraint + atomic upsert.
4. Make the launch-sync job itself safe against accidental double-running:
   Postgres advisory lock (`pg_advisory_lock`) at job start — belt and braces.
5. Then run Uvicorn with multiple workers (start with 4) behind Caddy. Delete
   CLAUDE.md rule 7 once done.

This single section is the difference between "hundreds" and "thousands" of
concurrent users on one machine.

---

## 5. 🔴 Secrets & configuration hygiene

- `backend/.env` exists in the working tree — verify it is gitignored and has
  never been committed with real secrets (`git log --all -- backend/.env`);
  rotate anything that ever landed in history.
- Enforce `APP_REQUIRE_SECRETS=1` in every production compose/deploy file so the
  app refuses to boot without `JWT_SECRET_KEY`, `UNSUBSCRIBE_SECRET_KEY`,
  `ADMIN_API_KEY`.
- Generate secrets with `openssl rand -hex 32`; store them only on the server
  (compose `.env` with `chmod 600`) — no secrets manager needed at this scale.
- Add `JWT_SECRET_KEY` rotation notes to the runbook (rotating it logs everyone
  out — acceptable, but should be a decision, not a surprise).

---

## 6. 🟡 Auth hardening

- **Move refresh tokens out of `localStorage`.** `frontend/src/lib/api.ts` stores
  both access and refresh tokens in `localStorage` (the code even carries an XSS
  warning comment). Minimum viable fix: deliver the refresh token as an
  `httpOnly; Secure; SameSite=Strict` cookie scoped to the refresh endpoint path;
  keep the short-lived (15 min) access token in memory only. This requires the
  CSRF-safety review below but removes the "one XSS = permanent account takeover"
  failure mode.
- **Rate limiting.** `login_attempts` exists at the account level; add IP-level
  throttling for `/auth/*` and OTP endpoints (`slowapi`, or Caddy `rate_limit`)
  to blunt credential stuffing and OTP-SMS pumping (each SMS costs money — this
  is also a financial attack surface).
- **python-jose is in maintenance limbo** — migrate to `PyJWT` (small, active,
  drop-in for HS256 encode/decode).
- CORS: `allow_methods=["*"], allow_headers=["*"]` with `allow_credentials=True`
  (`main.py`) is broader than needed; enumerate the real methods/headers.

---

## 7. 🟡 Replace `deep-translator` (unofficial Google Translate scraper)

**Problem.** `backend/app/services/translation_service.py` uses
`deep_translator.GoogleTranslator` — an unofficial, key-less scraper. For a
commercial product this is a TOS violation and will be IP-blocked at volume.
It also creates a new `GoogleTranslator` per field per language inside a loop,
serially — a full launch-table sync with 5 languages is slow.

**Fix.** Swap the implementation behind the existing `translate_fields` interface
(good design — only one call site in `main.py` wires it) for **DeepL API**
(free tier: 500k chars/month, likely sufficient since translations are cached in
the DB) or Google Cloud Translation. Add a `TRANSLATION_API_KEY` setting; on
missing key, fall back to English rather than the scraper. Batch requests per
language instead of per field.

---

## 8. 🟡 Observability & operations

Currently there is no structured logging, error tracking, or metrics. Before
launch (roughly a day of work total):

- **Error tracking:** Sentry SDK for FastAPI *and* the React frontend.
- **Structured logs:** JSON logs to stdout (e.g. `structlog`); Docker captures
  them. Log every notification send attempt/outcome — delivery success rate is a
  core business KPI (see business plan §10).
- **Health & uptime:** `/api/v1/health` exists; extend it to check DB
  connectivity, and add a worker heartbeat (worker writes a timestamp row;
  health check flags it stale). Point an external uptime monitor at it.
- **Backups:** nightly `pg_dump` to object storage (Hetzner/S3), 30-day
  retention, and **test a restore once** before launch.
- **Metrics (nice-to-have):** `prometheus-fastapi-instrumentator` for request
  latency/error rates.

---

## 9. 🟡 Email deliverability

`aiosmtplib` against a raw SMTP host will land in spam for a fresh domain.
Notifications *are* the product — deliverability is not optional.

- Use a transactional email provider (Postmark, AWS SES, Mailgun) — keep the
  SMTP interface, just point at their relay, or use their HTTP API.
- Set up SPF, DKIM, DMARC on the sending domain before the first beta invite.
- Keep the existing unsubscribe-token flow (already implemented — good, and
  legally required); add the `List-Unsubscribe` header for one-click unsubscribe
  (Gmail/Yahoo now require it for senders at volume).

---

## 10. 🟡 Production deployment definition

The repo has only a dev `docker-compose.yml` (bind-mounts source, runs
`--reload`, Vite dev server). Add `docker-compose.prod.yml`:

```
services: caddy (TLS, static frontend, /api reverse proxy)
          backend (uvicorn, multi-worker, no reload, APP_REQUIRE_SECRETS=1)
          worker  (python -m app.worker)          # §4
          db      (postgres:17, volume, healthcheck)
```

- Multi-stage frontend Dockerfile (or CI step) that runs `npm run build` and
  ships `dist/` into the Caddy image/volume — `Dockerfile.dev` is dev-only.
- Containers restart `unless-stopped`; backend depends on db healthcheck.
- Run Alembic migrations as an explicit deploy step (compose `run --rm backend
  alembic upgrade head`), not implicitly at app startup.
- Pin the Caddyfile from the README into the repo (`deploy/Caddyfile`) with
  security headers (`Strict-Transport-Security`, `X-Content-Type-Options`,
  a reasonable `Content-Security-Policy`).

---

## 11. 🟡 CI/CD

No CI config exists in the repo. Minimum GitHub Actions pipeline:

1. Backend: `pytest --cov-branch --cov-fail-under=80` against **Postgres**
   (service container) and lint (`ruff`).
2. Frontend: `npm run test:coverage` + `tsc --noEmit` + build.
3. On tag/main: build and push Docker images; deploy = SSH pull + `compose up -d`
   + migration step. Boring and sufficient.

---

## 12. 🔴 Slip-history recording (moat foundation — do in Phase 0)

The v2 feature roadmap's Tier 0. `launches_service.py` already detects NET
changes for notifications but discards the history. Add a `launch_net_changes`
table (launch id, old/new NET, change type, provider, rocket, pad, detected-at)
and insert a row on every detected change during sync. ~1 day including the
Alembic migration and tests.

This is deliberately in the *production-readiness* doc, not just the roadmap:
the dataset's value is proportional to elapsed recording time, so it must ship
with the first production deploy. Nothing consumes it yet — that's fine; the
reliability-score and slip-risk features (roadmap #7/#8) read from it later.

---

## 13. 🟢 Data & compute foundations for the v2 roadmap

Infrastructure the new feature tracks require. None of it blocks launch, but
sequencing matters — each item gates several features.

### 13.1 TLE pipeline (gates Starlink trains #4, transit finder #5, AMSAT #34)

- Worker job fetching TLEs from **CelesTrak** (bulk GP files, refresh 2–4×/day —
  be a polite consumer, cache aggressively, honor their guidelines) into a
  `tle_sets` table; optional **Space-Track** account for reentry data (#18).
- SGP4 propagation: `sgp4` (python) in the backend for alert computation;
  `satellite.js` in the frontend only for live visuals. **Pass/visibility
  computation is CPU-bound** — it must run in the worker (precomputed per
  user-location on a schedule), never per-request in the web process.

### 13.2 Ephemeris cache (gates live spacecraft #10, mission replay #11)

- Worker job querying **JPL Horizons** for tracked spacecraft/bodies; store
  state vectors in an `ephemerides` table. Horizons is free but rate-courteous:
  batch queries, cache for days (trajectories don't change), never proxy
  user requests straight to JPL.
- Mission replays ship as *static JSON trajectory files* generated offline —
  no runtime Horizons dependency for the high-traffic press moments.

### 13.3 NOAA SWPC polling (gates aurora nowcasting #6)

- Worker job polling SWPC JSON feeds (incl. OVATION grid) every few minutes.
  Nowcast alerts are latency-sensitive: this is the one sync whose failure
  should page (Sentry alert on staleness > 15 min).

### 13.4 User location data (gates #3, #4, #5, #6)

Privacy design decision, not just a column: store **city-level lat/lon**
(user-entered city, geocoded once), never precise GPS. Document it in the
privacy policy (PIPEDA/GDPR — location is personal data; city-level +
clear purpose keeps compliance simple). Include location in the deletion/export
endpoints (§14 GDPR item).

### 13.5 Kiosk mode operational requirements (gates B2B track #28)

Institutions buying screens expect boring reliability:

- Kiosk auth: long-lived signed display tokens (revocable per institution) —
  not user JWTs.
- Display page must **degrade gracefully offline** (cache last data, keep
  cycling) — museum Wi-Fi is bad; a frozen error screen kills renewals.
- Public status page + uptime target once the first paying institution signs.
  This is the point where "single VPS, restart on failure" stops being enough —
  budget for a second small instance or managed Postgres *then*, not before.

---

## 14. 🟢 Scale & product-readiness items (post-launch)

- **Notification queue robustness:** the outbox pattern
  (`notification_log` + `drain_queue`) is already the right design. Extend it
  with per-row retry counts/backoff and a dead-letter state so one permanently
  failing address can't wedge the queue; alert (Sentry) on dead-letters. No
  Celery/Redis needed at this scale — the DB outbox drained by the worker is enough.
- **Caching:** the DB-backed cache for NASA data is fine. If DB load ever becomes
  an issue, add Redis *then*, not preemptively. Add `Cache-Control` headers on
  read-only API responses so browsers/Caddy absorb repeat traffic.
- **SEO prerendering:** the SPA serves `index.html` for everything — per-launch
  pages are invisible to search engines, and per-launch SEO is the #1 growth
  channel (business plan §8). Options in ascending effort: `vite-plugin-ssr`/
  prerender of launch pages at sync time, or server-rendered OG/meta tags via a
  small Caddy → backend HTML route for `/launches/:id`. Also add sitemap.xml
  generation from the launches table.
- **PWA + Web Push:** service worker + push subscriptions gives free
  mobile-style notifications without app stores and reduces SMS cost pressure.
- **Per-user rate limits & SMS caps:** monthly SMS cap per Pro user (financial
  self-protection).
- **GDPR endpoints:** account deletion (cascade subscriptions, logs, tokens) and
  data export. Required once real EU users sign up; trivial to build now, painful
  under a deadline letter later.
- **Load test before public launch:** a 30-minute `k6` run (browse + auth flows)
  against the prod stack to validate the multi-worker setup; target p95 < 300 ms
  at 200 concurrent users.

---

## Suggested execution order

| Order | Item | Effort |
|---|---|---|
| 1 | §1 settings auth + §5 secrets | 0.5 day |
| 2 | §2 database URL fix | 0.5 day |
| 3 | §3 Postgres migration + CI against Postgres (§11) | 2–3 days |
| 4 | §4 worker extraction + DB locking + multi-worker | 2–3 days |
| 5 | **§12 slip-history recording** (dataset value = elapsed time; ship with first deploy) | 1 day |
| 6 | §10 prod compose + Caddy + §8 backups/Sentry | 1–2 days |
| 7 | §6 auth hardening, §7 translation swap, §9 email provider | 2–3 days |
| 8 | §13 foundations, in feature-roadmap sequence (TLE → ephemeris → NOAA → location → kiosk) | per feature |
| 9 | §14 items, driven by beta feedback | ongoing |

Total to "safe for beta": **~2.5 weeks** of focused work.

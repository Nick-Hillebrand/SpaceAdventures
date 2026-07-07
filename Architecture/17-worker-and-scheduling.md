# Worker Process, Scheduling & Multi-Worker Web Tier (v2 Step P3)

Removes the `--workers 1` constraint (CLAUDE.md v1 rule 7 — **deleted** once
this step is done). After this step: the web tier runs 4–8 stateless Uvicorn
workers; ALL background jobs run in one dedicated worker container.

Requires `16-postgres-migration.md` complete.

---

## P3.1 — Worker entrypoint

New file `backend/app/worker.py`, run as `python -m app.worker` in its own
container (same image as the backend):

```python
# Structure (not verbatim):
async def main() -> None:
    settings = Settings()                     # APP_REQUIRE_SECRETS honored
    init_engine(settings)
    clients = build_clients(settings)         # nasa/n2yo/ll2/mars/… (same lifespan set)
    scheduler = AsyncIOScheduler()
    register_jobs(scheduler, settings, clients)   # single registry, see P3.2
    scheduler.start()
    await shutdown_event.wait()               # SIGTERM/SIGINT → graceful drain
    scheduler.shutdown(wait=True)
    await close_clients(clients); await dispose_engine()
```

- Graceful shutdown: trap SIGTERM, let the in-flight job finish (compose
  `stop_grace_period: 60s`).
- `main.py` lifespan: **remove** scheduler creation and the startup sync
  entirely. The web process never schedules anything. Keep client setup for
  request-path use.
- Dev convenience: `SCHEDULER_IN_APP=1` env flag lets the dev compose keep
  running jobs inside the web process (single container, SQLite). Prod compose
  never sets it. Guard in `main.py` lifespan: only when flag set.

## P3.2 — Job registry

Single module `app/jobs.py` owning every recurring job. Each job entry:
`(name, coroutine, trigger, interval, jitter)`. Jobs as of this step, with the
future jobs other specs will add:

| Job name | Interval | Spec |
|---|---|---|
| `launches_sync` | 30 min (existing setting) | `06-launches.md` |
| `notification_drain` | 1 min | `08-subscriptions.md` + `19-…` retry rules |
| `rate_limit_purge` | 24 h | `15-…` P1.6 |
| `worker_heartbeat` | 30 s | P3.5 |
| *(later)* `tle_sync`, `pass_precompute`, `noaa_poll`, `ephemeris_sync`, `digest_send`, `social_post` | — | specs 20–23 |

Rules:

- Every job body: acquire a **Postgres advisory lock**
  (`SELECT pg_try_advisory_lock(:job_key)`; key = stable 64-bit hash of job
  name) and **skip silently if not acquired** — makes accidental double-worker
  deployment safe. On SQLite (dev) the helper no-ops. Provide
  `app/services/advisory_lock.py` with `try_job_lock(session, name) -> bool` /
  `release_job_lock(...)`.
- Every job wrapped in a try/except that logs (structured) and reports to
  Sentry — one failing job must never kill the scheduler.
- Every job records `last_success_at` in the `job_status` table (P3.5).
- `notification_drain` moves OUT of `launches_service.sync_launches` (currently
  called inline there) into its own 1-minute job. `sync_launches` only enqueues.

## P3.3 — Kill process-local locks (multi-worker correctness)

Three module-level `asyncio.Lock`s are correct only under one process. Replace
with DB-level concurrency (P4/P9/P10 in `11-testing.md` are superseded
accordingly):

| Lock | Replacement |
|---|---|
| `n2yo_client._QUOTA_LOCK` | `SELECT … FOR UPDATE` on the single `n2yo_quota` row inside one transaction: lock row → check window/count → increment → commit → then call N2YO. Keep the asyncio.Lock *in addition* as a fast-path courtesy within one process (optional), but correctness must not depend on it. |
| `auth_service._REFRESH_LOCK` | Already-specified `SELECT … FOR UPDATE` on the refresh-token row (10-security.md) becomes the ONLY mechanism. Delete the module lock. Concurrent rotation test must pass under Postgres. |
| `auth_service._OTP_LOCK` | Atomic guard: `INSERT` OTP only after a locked count query (`SELECT count(*) … FOR UPDATE` on the user row) — lock the *user* row as the serialization point for send-rate checks. Delete the module lock. |

Comment convention from `16-…` P2.4 applies at each site.

**Tests:** the concurrency tests (concurrent refresh rotation, concurrent quota
boundary at 899, concurrent OTP resend at limit) must run against **Postgres in
CI** — on SQLite they degrade to single-writer serialization and prove nothing.
Mark them `@pytest.mark.postgres_only` (skip when the session fixture dialect
is SQLite).

## P3.4 — Multi-worker web tier

- `backend/Dockerfile` CMD →
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`.
- Prod compose: backend `command` likewise (workers count via env
  `WEB_CONCURRENCY`, default 4). Dev compose stays `--workers 1 --reload` with
  `SCHEDULER_IN_APP=1`.
- Statelessness audit — grep for and eliminate any remaining cross-request
  mutable module/app state: `app.state.settings` mutation is gone (15-P1.1);
  locks gone (P3.3); anything else found → move to DB or make read-only.
- `12-deployment.md` compose/diagram updated: `caddy`, `backend (×4 workers)`,
  `worker`, `db (postgres:17 + healthcheck + volume)`. Backend and worker
  `depends_on: db: condition: service_healthy`.
- Migrations run as an explicit deploy step:
  `docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head`
  — never implicitly at app startup (two racing workers would double-migrate).

## P3.5 — Worker heartbeat & health

```
job_status
  job_name         TEXT PRIMARY KEY
  last_success_at  DATETIME
  last_error       TEXT NULLABLE   -- scrubbed via notification_service.scrub_error
```

- `worker_heartbeat` job upserts its own row every 30 s.
- `GET /api/v1/health` (public) → `{"status": "ok" | "degraded"}`; `degraded`
  when DB unreachable OR worker heartbeat older than 5 min.
- Admin health (existing tiered endpoint, `10-security.md`) additionally
  returns per-job staleness as status strings (`"ok" | "stale"`), never raw
  errors.
- External uptime monitor watches `/api/v1/health` for `"ok"`.

**Tests:** health degraded on stale heartbeat; advisory lock contention (second
acquire returns False, job skips); job exception is contained (scheduler
continues, Sentry hook called, `last_error` scrubbed); drain job independent of
launch sync (a Twilio outage cannot delay `launches_sync`).

## P3.6 — Observability baseline (ships with this step)

- `structlog` JSON logging to stdout in both web and worker (request id,
  job name, duration). Uvicorn access logs stay on.
- Sentry SDK initialized in `main.py` and `worker.py` when `SENTRY_DSN` set
  (setting, empty default). `traces_sample_rate=0.05`.
- Frontend: Sentry browser SDK behind the same env switch
  (`VITE_SENTRY_DSN`), lazily imported so the bundle stays lean when unset.
- Every notification attempt logs a structured event
  (`notification.sent|failed`, channel, scrubbed reason) — this feeds the
  delivery-rate KPI.

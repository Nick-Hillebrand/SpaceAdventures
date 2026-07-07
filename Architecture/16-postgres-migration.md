# PostgreSQL Migration & Capacity Targets (v2 Step P2)

SQLite is single-writer and file-bound; the business plan targets 100k+ MAU
(optimistic scenario) with headroom beyond. Postgres is the prerequisite for
everything in `17-worker-and-scheduling.md`.

---

## P2.1 — Fix the engine construction defect first

`database.py` currently hardcodes the SQLite URL at import time and **ignores
`Settings.database_url` entirely**. Replace module-level engine creation with a
factory:

```python
# database.py — target shape
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

def init_engine(settings: Settings) -> None:
    global _engine, _sessionmaker
    kwargs: dict = {"future": True}
    if settings.database_url.startswith("postgresql"):
        kwargs |= {"pool_size": settings.db_pool_size,        # default 10
                   "max_overflow": settings.db_max_overflow,  # default 20
                   "pool_pre_ping": True}
    _engine = create_async_engine(settings.database_url, **kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

def get_sessionmaker() -> async_sessionmaker[AsyncSession]: ...   # raises if not initialised
async def get_db() -> AsyncIterator[AsyncSession]: ...            # unchanged signature
async def dispose_engine() -> None: ...                           # for lifespan shutdown
```

- `create_app()` calls `init_engine(settings)`; lifespan shutdown calls
  `dispose_engine()`. The worker entrypoint (`17-…`) calls the same pair.
- Every `AsyncSessionLocal()` call site migrates to `get_sessionmaker()()`.
- The SQLite FK pragma listener becomes **dialect-conditional**: attach it inside
  `init_engine` on the engine's sync engine only when the URL is SQLite —
  not via the global `Engine` class event (which would fire for Postgres too).
- `alembic/env.py` reads `DATABASE_URL_SYNC` from the environment, falling back
  to `Settings().database_url_sync`. Never hardcode either URL again.

**Tests:** `init_engine` respects a Postgres URL (assert pool kwargs on the
engine); FK pragma listener attached only for SQLite; `get_sessionmaker()` before
`init_engine()` raises a clear `RuntimeError`.

## P2.2 — Dependencies & URLs

- Add `asyncpg` (runtime) and `psycopg[binary]` (Alembic/sync) to
  `requirements.txt`.
- Prod URLs: `postgresql+asyncpg://sa:***@db:5432/space_adventures` /
  `postgresql+psycopg://…` for sync.
- Dev default stays SQLite — zero-setup local dev is preserved. **CI and prod
  run Postgres** (see P2.5).

## P2.3 — Dialect audit of models & migrations

Audit every model/migration for SQLite-isms; fix in a single migration wave:

| Pattern | Required state |
|---|---|
| `DateTime` columns | `DateTime(timezone=True)` everywhere; all values written as aware UTC (`datetime.now(timezone.utc)`). Postgres will not silently coerce naive datetimes the way SQLite does. |
| JSON stored as TEXT (`raw_json`, translation columns) | Type as `sa.JSON()` — renders `JSONB` on Postgres, `TEXT` on SQLite. Callers stop `json.loads`-ing manually. |
| `server_default=text("CURRENT_TIMESTAMP")` | Valid on both dialects — keep (P23 still holds for dev SQLite). |
| CHECK constraints added manually post-`create_table` (P24) | Keep — harmless on Postgres. |
| String PKs / UUIDs | Keep as `TEXT`/`String` — do not churn to native UUID type now. |
| Autoincrement integer PKs | `sa.Integer` + `autoincrement=True` works on both — verify no `sqlite_autoincrement` table args. |
| `ORDER BY` on text dates (`YYYY-MM-DD`) | Lexicographic == chronological for ISO dates — acceptable, keep. |

**Migration strategy:** there is no production data yet. **Squash to a single
clean initial migration** (`alembic revision --autogenerate` against empty DB
after model fixes; delete old version files). This is the last cheap moment to
do it. Verify `alembic upgrade head` from scratch on BOTH SQLite and Postgres.

## P2.4 — Concurrency primitives unlocked (contract for later specs)

Postgres enables the row/advisory locking that `17-worker-and-scheduling.md`
requires. Contract established here:

- `with_for_update()` on SQLite is a silent no-op — any code path relying on
  `SELECT … FOR UPDATE` for correctness (refresh rotation, N2YO quota, OTP
  rate-count) is **only correct on Postgres**. Such paths must carry a comment
  `# CONCURRENCY: requires Postgres row lock in multi-worker deployments`.
- Dev on SQLite stays single-worker (dev compose unchanged) so the no-op is
  harmless locally.

## P2.5 — CI against Postgres

GitHub Actions backend job runs the full pytest suite **twice**: once on SQLite
(dev parity), once against a `postgres:17` service container
(`DATABASE_URL=postgresql+asyncpg://…`). Both must pass with per-module ≥ 80 %
branch coverage. `conftest.py` reads `DATABASE_URL` from env for fixtures;
table create/drop per test session, transaction-rollback isolation per test
(begin nested transaction in fixture, roll back after each test — pattern:
`async with engine.connect() as conn: trans = await conn.begin(); …; await trans.rollback()`).

## P2.6 — Backups (deploy requirement)

- Nightly `pg_dump -Fc` via a cron/systemd-timer on the host (not in-container
  crond), uploaded to object storage, 30-day retention.
- **A restore must be rehearsed once before beta** and documented as a runbook
  section in `12-deployment.md` (drop DB → restore dump → app healthy).

## P2.7 — Capacity model & scale targets

Design targets the **optimistic business-plan scenario with 5× headroom**:

| Metric | Target |
|---|---|
| Registered users | 500k |
| MAU | 100k (design headroom: 500k) |
| Peak concurrent (launch event spike) | 2,000 concurrent clients |
| API p95 latency (cached reads) | < 300 ms at peak |
| Notification fan-out | 50k emails + 5k pushes within 15 min of a launch change |
| Single-host footprint | 8 vCPU / 16 GB VPS runs the whole stack at these targets |

Why this holds architecturally:

1. Reads are DB-cache-backed (see `03-caching-strategy.md`) — user traffic does
   NOT scale into upstream NASA/LL2/N2YO calls. Upstream volume is a function of
   sync schedules only.
2. Web tier: 4–8 Uvicorn workers (`17-…`) behind Caddy; stateless once P1.4 and
   `17-…` land (no in-process locks, no in-process scheduler) — can scale to a
   second host behind Caddy `reverse_proxy` with zero code change.
3. Postgres with the pool settings above handles this read profile trivially;
   the write profile (notifications, sync upserts, rate-limit rows) is worker-
   dominated and low-rate.
4. **Do not add Redis preemptively.** Add it only when measured DB latency on
   hot cached reads exceeds budget. `Cache-Control: public, max-age=60` headers
   on anonymous read-only endpoints (APOD, launches list, ISS position) let
   Caddy/browsers absorb launch-event spikes first.

**Load test gate (pre-public-launch):** k6 script driving browse (80 %),
auth+account (10 %), ISS polling (10 %) at 2,000 VUs for 30 min against the prod
stack → p95 < 300 ms, error rate < 0.1 %, no worker job starvation (heartbeat
stays fresh throughout). Ship the script in `backend/loadtest/` with a README.

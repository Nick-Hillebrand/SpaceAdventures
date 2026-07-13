# Space Adventures — Claude Code Manifest (v2)

Space Adventures is a multilingual web app that fetches, caches, and visualises
NASA data and live space events, monetised via Pro alerting subscriptions and a
B2B kiosk/education track. Frontend: React 18 + TypeScript + Vite. Backend:
Python 3.12 + FastAPI + SQLAlchemy async. Database: **PostgreSQL in production
and CI, SQLite for local dev**.

All detailed specs live in `Architecture/`. Read only the files listed for the
step you are implementing — do not load the entire folder into context.
Business context (why features exist, tier gating): `BusinessPlan/`,
`FeatureIdeas/feature-roadmap.md`, `ProductionReadiness/production-readiness.md`.

**v1 (Steps 1–15) is complete** — the app described in `00`–`14` is built, with
all tests green. v2 hardens it for production and implements the feature
roadmap. The v1 specs remain authoritative for everything they cover unless a
v2 spec explicitly supersedes them (each supersession is called out in the v2
spec).

---

## Non-Negotiable Rules (always apply, every step)

1. **Tests ship with the feature — per-module gate.** Every step ends with
   **≥ 80 % branch coverage in every module it touches** (not just globally)
   and all tests green. Enforcement:
   - Backend: `pytest --cov=app --cov-branch --cov-report=json` +
     `python scripts/check_module_coverage.py` (fails if any `app/**/*.py`
     file with ≥ 1 branch is below 80 %; zero-branch files pass). Add this
     script in Step P1 and wire it into CI.
   - Frontend: vitest `coverage.thresholds: { perFile: true, branches: 80 }`.
2. **Security rules are absolute.** `Architecture/10-security.md` before any
   auth/subscription/notification code; **`Architecture/25-security-testing.md`
   before every step** — every new route lands in the route-authorization
   matrix in the same PR, every new external data source lands in the
   injection fixture matrix. Security tests are part of definition-of-done.
3. **No hardcoded English strings in JSX.** Every user-visible string uses an
   i18n key via `t()`, added to all six locales. See `09-frontend-shared.md`.
4. **All dates/times in the UI use `src/lib/dateTime.ts`.** Never
   `.toLocaleString()`, never a hardcoded timezone. (Backend notification
   templates may format with the user's stored `location_tz` — that is the
   only exception, see `20-…`.)
5. **Read `11-testing.md` §Pitfalls (P1–P37) before each feature area.**
   P4/P9/P10 are superseded by DB-level locking once Step P3 lands (see
   `17-worker-and-scheduling.md` P3.3).
6. **The backend is always behind Caddy in production.** Never expose Uvicorn.
   See `12-deployment.md` (+ deltas in `17-…` and `23-…`).
7. **All background/scheduled work runs in the worker process** (`app/worker.py`),
   never in the web tier. Every job takes a Postgres advisory lock. Web
   processes are stateless: no process-local locks, no mutable module/app
   state, no in-process schedulers (dev-only exception: `SCHEDULER_IN_APP=1`).
8. **CPU-bound computation (SGP4, transits, grid scans) runs only in worker
   jobs** — request handlers read precomputed rows. See `20-…`/`21-…`.
9. **Upstream data is untrusted input.** Everything from LL2, NASA, N2YO,
   NOAA, CelesTrak, Horizons, Open-Meteo is sanitised/size-capped/schema-
   validated before storage, and escaped per output context (HTML, ICS, meta,
   JSON-LD, SMS, social). See `10-…` + `25-…` §2.3.
10. **Migrations are explicit deploy steps** (`alembic upgrade head` via
    `compose run`), never implicit at startup. CI runs the suite on SQLite
    **and** Postgres; concurrency tests are `postgres_only`.
11. **Pro gating happens server-side** (`users.is_pro` dependency), never by
    hiding UI. Free tier must remain genuinely useful (business plan §4).
12. **Performance budgets are CI gates** — `Architecture/26-performance.md`.
    Every request handler: ≤ 5 SQL statements, row-count-independent (the N+1
    guard test); every list endpoint paginated and registered in
    `tests/perf/`; initial JS bundle ≤ 250 KB gzipped with three.js
    lazy-only; Lighthouse budgets (LCP ≤ 2.5 s, CLS ≤ 0.1) on the audited
    pages. A budget breach is a failing test, not a follow-up.

---

## Implementation Order

Do not start a step until the previous step's tests pass and per-module
coverage is met. Steps within a milestone are ordered; milestones are strictly
sequential (P → B → L → G → T).

### Milestone S — Mission simulations ✅ complete (pulled forward 2026-07-09, shipped 2026-07-12)

Frontend-only + offline dev tooling — no new routes, DB tables, or worker
jobs, so it did not collide with Milestone P hardening. Both steps below are
built and merged to `dev`; G3 (Artemis content + Horizons-backed generator)
remains scoped to the Growth milestone.

**Step S1 — Mission replay engine (static-content scope).**
Read: `22-ephemeris-and-mission-replay.md` (Engine integration + G3
sections), `26-performance.md` (3D/scene + page-chunk rules)
- Mission mode as a mode of the shared solar-scene engine
  (`mission.load()`/`mission.clear()` on `SolarSceneHandle` — one engine,
  two entry points): canonical `/missions/:slug` routes **and** the
  solar-tab Missions panel, `MissionPanel` UI shared by both, scrubber,
  milestone cards, mission JSON from static files in
  `frontend/public/missions/`. **No Horizons cache/API/DB** — that backend
  foundation stays in B3. Apollo 11 trajectory from curated keyframes
  (`build_mission.py --from-yaml`, see `27-…`); Pathfinder via a one-off
  offline Horizons pull in the dev script (courtesy rules apply to the
  script; nothing runtime).

**Step S2 — 3D vignette layer.**
Read: `27-mission-simulations-3d.md`, `13-mars-rover-3d-model.md`
- Content order: Apollo 11 first (lowest asset risk), then
  Pathfinder/Sojourner (validates the VRML→glb conversion pipeline).

### Milestone P — Production readiness ⭐ current focus (blocks public users; resumed here after S, 2026-07-12)

**Step P1 — Hardening.** ✅ complete (shipped 2026-07-13, see status below)
Read: `15-production-hardening.md`, `10-security.md`, `25-security-testing.md`,
`26-performance.md` §1.2, §4
- Remove settings key-mutation endpoints; secrets enforcement; PyJWT migration;
  refresh-token → httpOnly cookie; CORS tightening; IP rate limiting; DeepL
  translation swap; List-Unsubscribe; consent recording; account
  deletion/export. Add `scripts/check_module_coverage.py`, `tests/security/`
  skeleton with the route-authorization matrix, and `tests/perf/` skeleton
  with the query-count/N+1 guard over existing list endpoints.
  - ✅ Shipped 2026-07-12: secrets enforcement (P1.2), PyJWT migration (P1.3),
    httpOnly refresh-token cookie (P1.4), IP rate limiting (P1.6), consent
    recording (P1.9), account deletion/export (P1.10).
  - ✅ Shipped 2026-07-13: DeepL translation swap (P1.7), List-Unsubscribe +
    SPF/DKIM/DMARC deliverability runbook (P1.8), `scripts/check_module_coverage.py`
    (wired into the backend test flow), `tests/security/test_route_matrix.py`
    (route-authorization matrix), `tests/perf/test_query_counts.py`
    (query-count/N+1 guard), root `SECURITY.md`. Dependency security sweep:
    fastapi 0.115→0.139 (fixes starlette CVEs), PyJWT→2.13.0, aiosmtplib→5.1.2,
    pytest/pytest-asyncio/pytest-cov bumped; frontend vite→6.4.3, vitest→3.2.7,
    @vitest/coverage-v8→3.2.7 (fixes a critical vitest-UI arbitrary-file-read
    CVE). `pip-audit` and `npm audit --audit-level=high` both clean.
  - Step P1 is now complete — all sub-items shipped, per-module coverage gate
    green, security/perf test suites in place.

**Step P2 — PostgreSQL.** ✅ complete (shipped 2026-07-13)
Read: `16-postgres-migration.md`, `01-database-schemas.md`
- Engine factory (fixes ignored `DATABASE_URL`), dialect audit, squashed
  initial migration, CI on Postgres, pool config, backup runbook.
  - ✅ Shipped 2026-07-13: `init_engine`/`get_sessionmaker`/`dispose_engine`
    factory in `app/database.py` (Postgres pool_size/max_overflow only
    applied for `postgresql+asyncpg://`, SQLite FK pragma scoped to its own
    engine instead of the global `Engine` class); `UTCDateTime` type
    decorator normalizing SQLite's naive read-back to aware UTC; full
    dialect audit (all `DateTime` columns → `UTCDateTime`, all JSON-as-TEXT
    columns → `sa.JSON()`, SQLite-only `randomblob()` subscription-id
    default replaced with a Python-side `secrets.token_hex`); `alembic/env.py`
    reads `DATABASE_URL_SYNC` (env wins, falls back to `Settings()`); prior
    incremental migrations squashed into one initial migration (no
    production data existed yet); `docker-compose.prod.yml` gets a `db`
    (postgres:17-alpine) service with healthcheck and `pg_data` volume,
    `DATABASE_URL`/`DATABASE_URL_SYNC` built in the compose file's
    `environment:` (not left in `.env.prod`, since `env_file:` values aren't
    `${...}`-expanded); backup/restore runbook (nightly `pg_dump -Fc` via
    host cron, 30-day retention, documented restore rehearsal) added to
    `12-deployment.md`. `tests/conftest.py`'s `db_engine` fixture already
    read `DATABASE_URL` for dialect selection, so CI-on-Postgres is a
    workflow-authoring task left to Step P3 (which owns CI/CD per its own
    bullet below). 534 backend tests green, per-module branch coverage gate
    passed (27 modules with branches, all ≥ 80%), route-authorization matrix
    and injection-fixture suites unaffected (no new routes or external data
    sources this step).
  - Step P2 is now complete. Next: Step P3 (Worker & scale).

**Step P3 — Worker & scale.** ✅ complete (shipped 2026-07-13)
Read: `17-worker-and-scheduling.md`, `12-deployment.md`, `26-performance.md`
- `app/worker.py`, job registry, advisory locks, delete process-local locks,
  multi-worker web tier, prod compose (caddy/backend/worker/db + `encode zstd
  gzip`), heartbeat + health, structlog + Sentry (incl. job-duration fields).
  CI/CD pipeline per `16-…` P2.5 + `25-…` §4 + `26-…` §4 (bundle-budget
  script, Lighthouse CI, route-chunk splitting with three.js lazy-only, lazy
  locale loading).
  - ✅ Shipped 2026-07-13: `app/jobs.py` job registry + `app/worker.py`
    dedicated worker entrypoint (AsyncIOScheduler, signal-driven graceful
    shutdown); process-local locks replaced with Postgres advisory locks
    (`app/services/advisory_lock.py`) and `SELECT … FOR UPDATE` row locks
    (N2YO quota in `iss_service.py`, refresh-token rotation + OTP
    rate-count in `auth_service.py`) — both `postgres_only`-marked where
    SQLite would only prove single-writer serialization; `main.py` lifespan
    rewritten around `SCHEDULER_IN_APP` (dev-only in-process scheduler) with
    a tiered/degraded `/api/v1/health` endpoint backed by a new
    `job_status` table (heartbeat per job); `app/observability.py`
    (structlog JSON logging + Sentry SDK) wired into both the web and
    worker processes, plus structured `notification.sent|failed` events in
    `notification_service.py`. Multi-worker web tier: `backend/Dockerfile`
    defaults to `--workers 4`, `docker-compose.prod.yml` adds a dedicated
    `worker` service (same image, `python -m app.worker` entrypoint) beside
    Caddy/Backend/db — 4 containers in prod; dev stays single-container
    SQLite with `SCHEDULER_IN_APP=1`. Frontend: `@sentry/react` lazy-loaded
    behind `VITE_SENTRY_DSN` (never a hard dependency); `IssPage`/
    `MarsPage`/`SolarSystemPage` routes and 5 of 6 locales (`en` stays
    bundled) lazy-loaded via `React.lazy`/dynamic `import()`;
    `scripts/check-bundle.mjs` walks the Vite manifest's real chunk graph
    (three.js/globe.gl family detected via the `WebGLRenderer` string
    marker, since globe.gl inlines into `IssPage`'s own chunk) to gate the
    26-performance.md §2.1 budgets; `lighthouserc.json` gates §2.2 web
    vitals on `/apod`, `/launches`, `/missions/apollo-11` (the SEO launch
    page and `/embed/next-launch` are deferred to Steps B2/L3, which don't
    exist yet). `.github/workflows/ci.yml`: backend suite runs twice
    (SQLite + a `postgres:17-alpine` service container, the latter also
    smoke-checking `alembic upgrade head`), frontend job runs
    build+test+bundle-check, a separate job runs Lighthouse CI against the
    build artifact, plus dependency/static scanning (`ruff check --select
    S`, `pip-audit`, `npm audit --omit=dev --audit-level=high`, gitleaks).
    579 backend tests green, per-module branch coverage gate passed (31
    modules with branches, all ≥ 80%), 409 frontend tests green with
    per-file branch coverage ≥ 80%. Route-authorization matrix and
    injection-fixture suites unaffected (no new routes or external data
    sources this step — the new `/api/v1/health` route was already in the
    matrix pre-P3).
  - Step P3 is now complete. Next: Step P4 (Slip-history recording).

**Step P4 — Slip-history recording.** ✅ complete (shipped 2026-07-13)
Read: `18-slip-history-and-reliability.md` (Stage 1 only)
- `launch_net_changes` table + append-only writes in sync. Ships with first
  prod deploy — the dataset's value is elapsed time.
  - ✅ Shipped 2026-07-13: `LaunchNetChange` model (`app/models/launch_net_changes.py`)
    with CHECK constraint, CASCADE FK on `launches.ll2_id`, and composite
    indexes on `(launch_id, detected_at)` / `(provider_name, detected_at)`;
    Alembic migration `c3f7a2d01e4b`; `_record_change()` helper in
    `launches_service.py` sanitises all LL2-supplied strings before storage
    and is called in the same transaction as the launch upsert for NET slips,
    status changes, and Gone-markings (both the partial-feed and empty-feed
    paths). Unsubscribed launches are recorded; Gone marks the row rather than
    deleting it (FK row stays alive). 8 new tests in
    `test_launches_service_unit.py` cover all spec-required scenarios (net
    slip, status, unchanged, unsubscribed, gone, sanitisation); injection
    fixture matrix (`tests/security/test_injection.py`) parametrized over 8
    LL2 payloads, plus an AST-based SQL-injection guard for
    `launches_service.py`. 621 backend tests green, per-module branch
    coverage gate passed (31 modules ≥ 80%), route-authorization matrix
    unaffected (no new routes in Stage 1).
  - Step P4 is now complete. Next: Step B1 (Outbox hardening + Web Push).

### Milestone B — Beta (50–100 users; the test is notification correctness)

**Step B1 — Outbox hardening + Web Push.**
Read: `19-notification-channels-v2.md` (B1 sections), `08-subscriptions.md`
**Step B2 — SEO launch pages + sitemap.**
Read: `23-seo-widgets-and-growth.md` (B2), `06-launches.md`
**Step B3 — Live spacecraft in simulator.**
Read: `22-ephemeris-and-mission-replay.md` (foundation + B3)

### Milestone L — Public launch (time to a major launch event)

**Step L1 — Location + ISS visual pass alerts (Pro flagship).**
Read: `20-location-and-sky-alerts.md` (foundation + L1), `05-iss-tracker.md`
**Step L2 — iCal feeds.**
Read: `19-notification-channels-v2.md` (L2)
**Step L3 — Embeddable widgets.**
Read: `23-seo-widgets-and-growth.md` (L3)
- Pre-launch gates: k6 load test (`16-…` P2.7), ZAP baseline + ASVS L1 pass
  (`25-…` §6), deployed-headers smoke test green, backup restore rehearsed.

All B/L/G/T steps that add endpoints, pages, jobs, or scenes inherit the
matching budget tables from `26-performance.md` (query counts + pagination for
endpoints, chunk budgets + vitals for pages, duration budgets for jobs, the 3D
rules for scenes) — read the relevant section with each step.

### Milestone G — Growth (months 2–6; order may follow beta feedback)

**Step G1 — Aurora nowcasting.** Read: `20-…` (G1)
**Step G2 — Starlink-train alerts.** Read: `21-tle-pipeline.md` (foundation + G2)
**Step G3 — Mission replay: Artemis content + Horizons-backed generator
(engine already built in S1/S2; this is content + `build_mission.py`
Horizons path, Artemis-timed).** Read: `22-…` (G3)
**Step G4 — Reliability scores + slip-risk (needs ≥ 3 months of P4 data).**
Read: `18-…` (Stage 2)
**Step G5 — Daily digest.** Read: `19-…` (G5)
**Step G6 — Social bot.** Read: `23-…` (G6)
**Step G7 — Kiosk pilot slice.** Read: `24-kiosk-mode.md` (pilot only — stop at
the marked line until 5 institutions have seen it)

### Milestone T — After traction

**Step T1 — ISS transit finder.** Read: `21-…` (T1)
Later, spec-before-build: reentry alerts, AMSAT, retention pack
(streaks/follows), community features, education tier, post-pilot kiosk —
per `FeatureIdeas/feature-roadmap.md` sequencing.

---

## Scale & capacity contract

Design target: 100k MAU with 5× headroom, 2 000 concurrent peak, p95 < 300 ms
on cached reads, 50k-notification fan-out in 15 min — on one 8 vCPU/16 GB host.
The load-test suite in `backend/loadtest/` is the executable form of this
contract (`16-…` P2.7). Do not add Redis, queues, or extra services
preemptively; the DB-backed cache + outbox + worker is the architecture until
measurements say otherwise.

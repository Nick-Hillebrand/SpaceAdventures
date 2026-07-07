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
   *(Replaces v1 rule 7 "`--workers 1` always" from Step P3 onward; until P3
   is complete, v1 rule 7 still holds.)*
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

---

## Implementation Order

Do not start a step until the previous step's tests pass and per-module
coverage is met. Steps within a milestone are ordered; milestones are strictly
sequential (P → B → L → G → T).

### Milestone P — Production readiness (blocks everything; no public users before P4)

**Step P1 — Hardening.**
Read: `15-production-hardening.md`, `10-security.md`, `25-security-testing.md`
- Remove settings key-mutation endpoints; secrets enforcement; PyJWT migration;
  refresh-token → httpOnly cookie; CORS tightening; IP rate limiting; DeepL
  translation swap; List-Unsubscribe; consent recording; account
  deletion/export. Add `scripts/check_module_coverage.py` + `tests/security/`
  skeleton with the route-authorization matrix.

**Step P2 — PostgreSQL.**
Read: `16-postgres-migration.md`, `01-database-schemas.md`
- Engine factory (fixes ignored `DATABASE_URL`), dialect audit, squashed
  initial migration, CI on Postgres, pool config, backup runbook.

**Step P3 — Worker & scale.**
Read: `17-worker-and-scheduling.md`, `12-deployment.md`
- `app/worker.py`, job registry, advisory locks, delete process-local locks,
  multi-worker web tier, prod compose (caddy/backend/worker/db), heartbeat +
  health, structlog + Sentry. CI/CD pipeline per `16-…` P2.5 + `25-…` §4.
  After this step, delete v1 rule 7 references from docs.

**Step P4 — Slip-history recording.**
Read: `18-slip-history-and-reliability.md` (Stage 1 only)
- `launch_net_changes` table + append-only writes in sync. Ships with first
  prod deploy — the dataset's value is elapsed time.

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

### Milestone G — Growth (months 2–6; order may follow beta feedback)

**Step G1 — Aurora nowcasting.** Read: `20-…` (G1)
**Step G2 — Starlink-train alerts.** Read: `21-tle-pipeline.md` (foundation + G2)
**Step G3 — Mission replay mode (Artemis-timed).** Read: `22-…` (G3)
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

# Notification Channels v2: Web Push, iCal, Digest, Outbox Hardening (v2 Steps B1, L2, G5)

Extends `08-subscriptions.md`. The outbox pattern (`pending_notifications` →
`drain_queue`) stays; this spec adds channels and makes the queue
production-grade.

---

## B1.1 — Outbox hardening (ships in beta step B1)

Extend `pending_notifications`:

```
attempt_count   INTEGER  NOT NULL DEFAULT 0     -- exists per 01-…; keep
next_attempt_at DATETIME NOT NULL server_default CURRENT_TIMESTAMP
dead            BOOLEAN  NOT NULL DEFAULT FALSE
INDEX (dead, next_attempt_at)
```

Drain rules (job `notification_drain`, every 1 min per `17-…`):

- Select batch: `dead = FALSE AND next_attempt_at <= now()` ordered by
  `created_at`, `LIMIT 100`, **`FOR UPDATE SKIP LOCKED`** (Postgres) so a slow
  batch never blocks the next drain tick.
- Failure → `attempt_count += 1`, `next_attempt_at = now() + backoff` where
  backoff = 1 min, 5 min, 30 min, 2 h, 12 h.
- `attempt_count >= 5` → `dead = TRUE` + Sentry event (scrubbed). Dead rows are
  visible in the admin health payload as a count.
- Per-user monthly SMS cap: `users.sms_sent_month INTEGER`, `sms_month TEXT
  (YYYY-MM)`; drain checks cap (default 30, setting) before sending SMS —
  over cap → convert that notification to email + log. Financial self-protection.

**Tests:** backoff schedule exact; dead-letter at 5; SKIP LOCKED semantics
(postgres_only: two concurrent drains never double-send — assert send mock
called once per row); SMS cap converts to email at boundary; month rollover
resets counter.

## B1.2 — Web Push channel (Step B1)

**Backend:**

- `pip install pywebpush`; settings `vapid_private_key`, `vapid_public_key`,
  `vapid_claims_email`. Generate keys once (`vapid` CLI), store in `.env.prod`.
- Schema:

```
push_subscriptions
  id           TEXT PK (UUID)
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
  endpoint     TEXT NOT NULL UNIQUE
  p256dh       TEXT NOT NULL
  auth         TEXT NOT NULL
  created_at   DATETIME server_default CURRENT_TIMESTAMP
  INDEX (user_id)
```

- Routes: `POST /api/v1/push/subscribe` (auth; body = browser
  `PushSubscription.toJSON()`; upsert on endpoint),
  `DELETE /api/v1/push/subscribe` (auth; by endpoint),
  `GET /api/v1/push/vapid-public-key` (public).
- `notification_service`: third channel `push` next to email/SMS.
  `pywebpush.webpush()` is sync → `asyncio.to_thread` (same rule as Twilio,
  P32). HTTP 404/410 from the push service → delete that subscription row
  silently (browser revoked it).
- Channel selection: push is FREE-tier for basic launch reminders; slip/status
  streams and location alerts remain Pro (`08-subscriptions.md` channel matrix
  extended: `subscriptions.channel` gains `'push'`).

**Frontend (PWA):**

- `vite-plugin-pwa` with `injectManifest`; custom `src/sw.ts` service worker:
  `push` event → `showNotification(title, {body, data.url})`; `notificationclick`
  → `clients.openWindow(data.url)`. Precache app shell only — never API
  responses (stale launch data is worse than no cache).
- `usePush` hook: permission state machine (`default/granted/denied`),
  subscribe flow (get VAPID key → `pushManager.subscribe` → POST), unsubscribe.
- UI: bell-with-browser icon in `<SubscribeModal>` channel choices +
  AccountPage device list. Never prompt for permission on page load — only on
  explicit user action (browser vendors punish unsolicited prompts).
- `mockServiceWorker.js` (MSW) and the PWA SW must not conflict: PWA SW
  registered only in production builds (`import.meta.env.PROD`).

**Tests:** backend — subscribe upsert, 410 pruning, `asyncio.to_thread` wrapping
(mock pywebpush, assert called with correct keys/payload), channel routing.
Frontend — permission-denied state renders guidance; subscribe flow POSTs
correct body (mock `PushManager`); no auto-prompt on mount.

## L2 — iCal feeds (Step L2, public-launch milestone)

- `users.ical_token TEXT UNIQUE NULLABLE` — random 32-byte urlsafe token,
  generated on first request, regenerable (`POST /api/v1/ical/rotate`, auth).
  Capability-URL auth: the token IS the auth (calendar apps can't send
  headers). Rotation invalidates the old URL.
- `GET /api/v1/ical/{token}.ics` (public, token-authed): VCALENDAR of the
  user's subscribed launches. `VEVENT` per launch: `UID = launch_id@domain`,
  `DTSTART` = NET (UTC), `SUMMARY` = mission name, `DESCRIPTION` includes
  status + livestream URL, `SEQUENCE` increments on every NET change (calendar
  clients update in place — this is why slips matter), `STATUS:CANCELLED` for
  Gone launches. Content-Type `text/calendar`. Cache-Control `private, max-age=900`.
- Pro-gated: non-Pro token → 403 (`is_pro` gate from `18-…`).
- Escape per RFC 5545 (commas, semicolons, newlines) — LL2 data is untrusted;
  write `ical_escape()` next to `sanitise()`.
- Frontend: AccountPage "Calendar feed" section — copyable `webcal://` URL,
  rotate button with confirm dialog.

**Tests:** valid ICS parsed by the `icalendar` lib in tests (add as dev dep);
SEQUENCE increments after a NET change; CANCELLED on gone; token rotation kills
old URL (404); non-Pro → 403; escaping (`SUMMARY` containing `;,\n` round-trips).

## G5 — "Today in Space" digest (Step G5, growth milestone)

- `users.digest TEXT CHECK IN ('off','weekly','daily') DEFAULT 'off'`,
  `digest_hour_utc INTEGER DEFAULT 8`.
- Worker job `digest_send` hourly: select users where digest due for their hour
  (daily = Pro-gated; weekly = free, sent Mondays), compose per user **from
  cache tables only** (never triggers upstream fetches): APOD thumb, launches
  next 48 h (subscribed first), NEO close approaches today, active space
  weather, tonight's ISS pass if location set (`20-…`).
- Rendered per user locale from the stored translation columns; enqueue into
  the outbox as channel email/push (respects consent per `15-…` P1.9 and
  List-Unsubscribe per P1.8).
- One digest = one outbox row; the digest job composes and enqueues, drain
  sends. No inline SMTP from the digest job.

**Tests:** hour/timezone selection logic; weekly-vs-daily gating (non-Pro
daily → skipped); composition from empty caches (sections omitted, never
errors); locale rendering; unsubscribe honored (digest='off' users skipped).

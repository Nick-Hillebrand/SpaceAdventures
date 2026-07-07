# Kiosk Mode — B2B Display Product (v2 Step G7, pilot-gated)

Museum/planetarium/science-center displays. **Build the pilot slice only**
(§Pilot below) until 5 institutions have seen it; the rest of this spec
activates when the first one signs.

---

## Pilot slice (Step G7 — ~3 days)

- Route `/kiosk` in the SPA: full-screen, chrome-less auto-cycling display —
  rotates every 45 s through: live ISS globe (existing IssPage scene),
  next-launch countdown (existing card, enlarged), APOD hero, aurora/space-
  weather banner. `?lang=` and `?panels=iss,launch,apod,weather` query params
  control language and rotation set.
- No auth in the pilot (it shows only public data); `?kiosk=1` styling: hide
  nav, cursor auto-hide after 5 s, no focus outlines, `wake lock` API request
  (screen must not sleep).
- **Offline tolerance (the B2B make-or-break):** all kiosk data hooks use
  React Query with `staleTime: 60s`, `refetchInterval: 60s`, and
  `keepPreviousData` — on fetch failure the display keeps cycling with the
  last data + a small unobtrusive "updated X min ago" stamp (`dateTime.ts`
  relative formatter). A frozen error screen on museum Wi-Fi kills renewals;
  the kiosk NEVER renders `<ErrorBanner>`.
- This is enough to demo. Stop here until pilot feedback.

**Tests:** rotation timing (fake timers); panel param filtering; offline
behavior (MSW network-error handlers → last data still rendered + stamp
visible, no error banner); cursor/nav hidden; lang param drives i18n.

---

## Post-pilot (activate on first signed institution)

### Display tokens

```
kiosk_licenses
  id            TEXT PK (UUID)
  institution   TEXT NOT NULL
  token_hash    TEXT NOT NULL UNIQUE     -- SHA-256 of the display token
  panels        JSON NOT NULL
  expires_at    DATETIME NOT NULL        -- annual renewal
  revoked       BOOLEAN DEFAULT FALSE
  created_at    DATETIME
```

- `/kiosk?token=…` validates against the table (constant-time hash compare);
  invalid/expired/revoked → the pilot free rotation with a license notice
  panel. Licensed mode unlocks configured panels + hides attribution.
- Admin management via `ADMIN_API_KEY`-gated routes
  (`POST/DELETE /api/v1/admin/kiosk-licenses`) — same auth pattern as
  `/launches/sync` (`10-security.md`: Bearer, never custom headers).
- Tokens are capability URLs handed to institutions; rotation = new row +
  revoke old.

### Operational commitments

- Public status page (uptime monitor's hosted page is sufficient) linked in
  license emails.
- `/kiosk` availability is the SLA surface — the load-test suite (`16-…` P2.7)
  adds a kiosk scenario; alerting on kiosk route 5xx via Sentry.
- Per-license usage ping (kiosk POSTs a heartbeat with its license id every
  10 min) → `kiosk_licenses.last_seen_at` — renewal conversations need usage
  data, and silent-dead screens are churn.

**Tests:** token validation branches (valid/expired/revoked/absent →
constant-time compare used); admin CRUD auth (no key → 401, wrong → 401,
correct → 200); heartbeat updates `last_seen_at`; licensed vs. free panel
gating.

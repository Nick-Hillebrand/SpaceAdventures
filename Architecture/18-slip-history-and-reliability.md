# Slip History & Reliability Products (v2 Steps P4, G4)

Two stages sharing one dataset. **Stage 1 (recording) ships with the first
production deploy** — the dataset's value equals elapsed recording time.
Stage 2 (reliability scores #7, slip-risk #8) ships later and only reads.

---

## Stage 1 — Recording (Step P4, ~1 day, Phase 0)

### Schema

```
launch_net_changes
  id             INTEGER  PK AUTOINCREMENT
  launch_id      TEXT     NOT NULL REFERENCES launches(id) ON DELETE CASCADE
  change_type    TEXT     NOT NULL CHECK IN ('net','status','gone')
  old_value      TEXT     NULLABLE   -- ISO datetime for 'net'; status string for 'status'
  new_value      TEXT     NULLABLE
  provider_name  TEXT     NOT NULL   -- denormalized at write time (survives launch row edits)
  rocket_name    TEXT     NOT NULL   -- denormalized
  pad_name       TEXT     NULLABLE   -- denormalized
  detected_at    DATETIME NOT NULL server_default CURRENT_TIMESTAMP
  INDEX (launch_id, detected_at)
  INDEX (provider_name, detected_at)
```

### Write path

In `launches_service.sync_launches` change detection, wherever a NET change,
status change, or Gone-marking is detected **for any launch** (not only
subscribed ones — record everything), insert one row in the same transaction as
the launch upsert. Notification enqueueing is unchanged and independent.

Also record the **terminal outcome**: when a launch transitions to a terminal
status (`Success`, `Failure`, `Partial Failure`), the `'status'` row for that
transition is the outcome marker — no extra table needed.

### Rules

- Never update or delete rows (append-only). No API exposure in Stage 1.
- Denormalize provider/rocket/pad from the launch row at write time.
- Values sanitized with `notification_service.sanitise` before storage (LL2 is
  untrusted input — `10-security.md`).

**Tests:** NET slip inserts exactly one row with correct old/new; status change
inserts; unchanged launch inserts nothing; unsubscribed launches still recorded;
row survives launch deletion? No — CASCADE removes it; assert the launches
`gone` flow marks rather than deletes rows (existing behavior), so history
persists. Sanitisation applied.

---

## Stage 2 — Reliability products (Step G4, after ≥ 3 months of data)

### Aggregation

Nightly worker job `reliability_rollup` (register per `17-…` P3.2) computes into:

```
provider_reliability
  provider_name        TEXT PRIMARY KEY
  launches_observed    INTEGER   -- terminal launches with ≥ 1 observed NET
  on_time_24h_pct      REAL      -- launched within 24h of first-observed NET
  median_slip_hours    REAL
  scrub_rate_pct       REAL      -- ≥1 NET slip after entering final 24h window
  sample_window_start  DATETIME
  computed_at          DATETIME
```

Providers with `launches_observed < 5` are excluded from public display
(statistically meaningless; show `t("reliability.insufficientData")`).

### Slip-risk score (Pro)

Per upcoming launch: probability its current NET holds within 24 h, computed as
the historical hold-rate for `(provider, rocket)` falling back to `(provider)`
falling back to global, weighted by days-until-NET bucket (>30d, 7–30d, <7d).
Store on the `launches` row (`net_confidence REAL NULLABLE`, updated by the
rollup job). This is a deliberately simple frequency model — do NOT introduce
ML; the moat is the data, not the model.

### API

| Route | Auth | Response |
|---|---|---|
| `GET /api/v1/reliability` | Public | All providers meeting the sample floor |
| `GET /api/v1/launches` (existing) | — | Adds `net_confidence` **only for Pro users** (`None` otherwise) — see `24-…`/billing spec note below |
| `GET /api/v1/launches/{id}/history` | Pro | The launch's own NET-change timeline |

Until a billing system exists, gate "Pro" fields behind `users.is_pro BOOLEAN
server_default false` (admin-settable; the billing integration later flips it —
keep the gate mechanism, swap the setter).

### Frontend

- `/reliability` page: provider table (sortable), methodology note, `dateTime.ts`
  for all dates, all six locales.
- Launch cards: confidence badge for Pro (`t("launches.confidence", {pct})`),
  upgrade hint otherwise.

**Tests:** rollup math on a fixture set with known answers (on-time %, median,
scrub rate — hand-computed expected values in the test); sample floor exclusion;
fallback chain provider+rocket → provider → global; Pro gating (non-Pro sees
`net_confidence: null` and history → 403); frontend badge renders per locale;
empty state below sample floor.

**Security:** history endpoint is read-only public data — but still Pro-gated at
the query level (`is_pro` check in dependency), not filtered client-side.

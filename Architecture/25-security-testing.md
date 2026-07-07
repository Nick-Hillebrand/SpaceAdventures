# Security Testing Program

Security tests are part of every feature's definition of done — a feature
without its security tests is not done, same rule as coverage. This file
defines what "security tested" means. `10-security.md` defines the controls;
this file defines how they are verified, continuously.

---

## 1. Threat model (keep current)

Assets: user credentials/PII (email, phone, city location, astro site),
notification consent records, API keys/secrets, the slip dataset, service
availability (kiosk SLA), **outbound SMS spend** (financial).

Adversaries: opportunistic scanners, credential stuffers, SMS-pump abusers,
scraper bots, a malicious registered user (IDOR/escalation), XSS via upstream
data (LL2/NASA payloads are untrusted input).

Out of scope: nation-state, physical, DDoS beyond basic rate limiting
(Caddy/host firewall handles volumetric).

Update this section whenever a spec adds an asset or input source.

## 2. Mandatory security test suite — `tests/security/`

Backend directory `tests/security/`, run in CI as part of the normal suite.
Every route added by any spec MUST be registered in
`tests/security/test_route_matrix.py`:

### 2.1 Route authorization matrix (the core artifact)

A single parametrized test over a declared table of
`(method, path, auth_level)` where auth_level ∈
`public | user | pro | admin | capability(token)`:

- Every route in `app.routes` MUST appear in the table — the test **fails if a
  route exists that isn't declared** (this catches "forgot to protect the new
  endpoint" structurally; it is the single highest-value security test).
- For each non-public route: no credentials → 401/403; wrong-tier credentials
  (user on pro, user on admin) → 403; malformed/expired token → 401.
- Capability routes (ical, unsubscribe, kiosk): wrong token → 404/403, never
  a different error shape than "not found" (no oracle).

### 2.2 IDOR suite

For every resource with a user_id (subscriptions, push subscriptions, location,
astro site, sky events, notification history, exports): user A creating,
user B reading/deleting by id → 404 (identical to nonexistent — enumeration
rule from `10-security.md`).

### 2.3 Injection & untrusted-data suite

- Every field that flows from LL2/NASA/N2YO/NOAA/CelesTrak/Horizons into HTML
  email, SEO meta/JSON-LD, ICS, social posts, or notifications: parametrized
  fixture payloads (`<script>`, `"'>{{7*7}}`, CRLF, null bytes, 10 kB field,
  RTL-override chars) → asserted escaped/stripped/truncated per the sanitise
  rules.
- SQL injection: ORM-only access is the control; the test greps the codebase
  for `text(` / raw `execute(` with string interpolation — allowlist file for
  the few legitimate uses (advisory locks), fail on new ones.

### 2.4 Auth abuse suite

Everything in `11-testing.md` §Auth stays, plus: rate-limit buckets (`15-…`
P1.6) boundary tests; OTP/SMS pumping (over-cap converts to email — `19-…`);
constant-time login (mock timer, assert both branches call the same hash
work); cookie attributes (`HttpOnly`, `Secure`, `SameSite`, `Path`); session
fixation (refresh rotation invalidates prior); `alg:none` and wrong-key JWTs.

### 2.5 SSRF & upstream-response suite

All upstream clients: oversized response (> cap) rejected; redirect to
non-allowlisted host not followed (`httpx` `follow_redirects=False` on all
clients — assert); connect/read timeouts enforced (`settings.http_timeout_seconds`);
error bodies never propagated verbatim into API responses (scrubbed codes only).

## 3. Frontend security tests

- Open-redirect suite (`safeReturnUrl` cases incl. `//evil.com`, `/\evil`,
  `https:/…`).
- No secrets in bundle: CI step greps `dist/` for known env var names and the
  string `sk_`/`API_KEY` patterns; `build.sourcemap: false` asserted from
  config in a test.
- XSS: any component rendering upstream-derived HTML-ish strings (there should
  be none — React escapes by default) — a lint rule bans
  `dangerouslySetInnerHTML` repo-wide (ESLint `react/no-danger`: error;
  allowlist empty).
- localStorage: test asserts no auth material written (after `15-…` P1.4).

## 4. Dependency & static scanning (CI, every PR)

| Tool | Gate |
|---|---|
| `pip-audit` | fail on high/critical |
| `npm audit --omit=dev --audit-level=high` | fail |
| `ruff` with `flake8-bandit` rules enabled (`S` codes) | fail on new findings; committed allowlist with justification comments |
| `gitleaks` (secret scan, full history on main, diff on PR) | fail on any hit |
| Dependabot/Renovate | weekly, security PRs auto-labeled |

## 5. Runtime headers & TLS (deploy-time, verified by test)

Caddy sets on all app routes (embed routes override frame-ancestors per
`23-…`):

```
Strict-Transport-Security: max-age=31536000
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; img-src 'self' data: https:;
  script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self';
  connect-src 'self' https://*.ingest.sentry.io
Permissions-Policy: geolocation=(), camera=(), microphone=()
```

(`img-src https:` is required — APOD/Mars/launch images come from many NASA and
agency hosts. `style-src 'unsafe-inline'` is required by Tailwind's injected
styles in dev only — tighten to hashes if the audit shows prod doesn't need it.)

A **deployed-environment smoke test** (`backend/scripts/check_headers.py`, run
in the deploy pipeline against the live domain): asserts every header above,
TLS grade basics (no TLS < 1.2), `/api/v1/health` ok, and that
`/docs` + `/openapi.json` are **disabled in production**
(`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` when
`settings.expose_docs` is False — default False in prod).

## 6. Periodic exercises

- **Before public launch and twice yearly:** OWASP ZAP baseline scan against
  staging (`zap-baseline.py -t https://staging…`) — triage every alert; store
  the report in `SecurityReviews/` (gitignored folder name documented here) or
  the issue tracker.
- **Before public launch:** one manual pass over the OWASP ASVS L1 checklist;
  record exceptions with reasoning.
- **On every new external data source** (spec 20–23 add five): add its fields
  to the §2.3 fixture matrix in the same PR.
- Abuse-cost review quarterly: SMS spend per user distribution, geocode/OTP
  bucket hit rates — attackers show up in these curves before they show up
  anywhere else.

## 7. Incident basics

- `SECURITY.md` at repo root: security contact (`security@{domain}`),
  90-day coordinated disclosure.
- Runbook section in `12-deployment.md`: secret rotation procedure per secret
  (JWT/unsubscribe/admin/VAPID/DeepL/SMTP/Twilio/social), and "compromised
  dependency" response (pin, audit, rotate, notify if data touched — PIPEDA
  breach-notification duty applies).

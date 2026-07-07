# SEO Launch Pages, Widgets & Social Bot (v2 Steps B2, L3, G6)

Growth surfaces. Per-launch SEO pages are the #1 acquisition channel
(business plan §8); widgets are the distribution loop; the social bot is
zero-marginal-cost reach.

---

## B2 — Per-launch public pages with server-rendered meta (beta milestone)

### Problem

The SPA serves one `index.html` — crawlers and link unfurlers see nothing
launch-specific. Full SSR is out of scope; we do **server-rendered meta +
client-rendered content**, which captures ~90 % of the SEO/unfurl value.

### Mechanism

- New backend router `seo.py`: `GET /launches/{id}` and `GET /{lang}/launches/{id}`
  (lang ∈ six locales) returns the **built `index.html` with injected tags**:
  `<title>`, `<meta name="description">`, OG/Twitter card tags (mission name,
  localized status line, NET date, pad), `<link rel="canonical">` +
  `hreflang` alternates for all six languages, and a `schema.org/Event`
  JSON-LD block (`startDate` = NET, `eventStatus` mapped from launch status —
  `EventScheduled`/`EventPostponed`/`EventCancelled`, `location` = pad).
  Read from the launches cache table + stored translations; **never trigger an
  upstream fetch from this route**.
- Caddy routing: `/launches/*` and `/{lang}/launches/*` →
  `reverse_proxy backend` (before the SPA `try_files` fallback); everything
  else unchanged. Update `12-deployment.md` Caddyfile block accordingly.
- The backend reads the built `index.html` from a shared volume
  (`frontend-dist:/srv/dist:ro` mounted into both caddy and backend) at
  startup; inject via a placeholder comment `<!--seo-head-->` added to
  `index.html` template. Unknown launch id → serve untouched index (SPA shows
  its own 404) with `X-Robots-Tag: noindex`.
- `Cache-Control: public, max-age=300` on these responses.
- Frontend: route `/launches/:id` (and language-prefixed variant) renders the
  launch detail from the API as today — no frontend change beyond ensuring the
  route exists standalone (deep-linkable, currently grid-only → add
  `LaunchDetailPage.tsx`: countdown, status, slip history teaser, stream link,
  subscribe button).

### Sitemap

- `GET /sitemap.xml` (backend): all upcoming + past-90-day launch URLs × six
  languages with `hreflang`, plus static routes and `/missions/*` slugs.
  Regenerated on request, `Cache-Control: max-age=3600`. `robots.txt` served by
  Caddy points at it.

**Tests:** meta injection (title/OG/JSON-LD present, correctly localized per
lang prefix, HTML-escaped — mission names are untrusted LL2 data: assert a
name containing `<script>` is escaped in meta AND JSON-LD); unknown id →
noindex header + vanilla index; canonical/hreflang cross-links complete;
sitemap validates against the XML schema (use `lxml` in tests); no upstream
call during render (respx asserts zero calls).

---

## L3 — Embeddable widgets (public-launch milestone)

### Surface

`GET /embed/next-launch` (+ `?provider=` filter, `?lang=`) — a minimal,
self-contained HTML page (countdown, mission, NET local-formatted client-side,
"Powered by Space Adventures" backlink). Served by the backend (same injected-
template mechanism as B2, but a dedicated tiny template — NOT the SPA bundle;
budget ≤ 30 KB total).

- Consumers embed via `<iframe src="https://{domain}/embed/next-launch">`.
- CSP on embed routes: `frame-ancestors *` (embeds are meant to be framed) —
  while the main app sets `frame-ancestors 'self'` (clickjacking protection;
  add both in Caddy headers, see `25-…`).
- No cookies, no auth, no personal data on embed routes — they must be safe to
  frame anywhere. `Cache-Control: public, max-age=60`.
- The backlink is the payment: attribution link must be visible, not
  removable via query param (white-label is a later B2B feature with signed
  tokens — do not build now).
- Docs page `/widgets` in the SPA: copy-paste snippet generator (iframe code,
  provider filter dropdown, language dropdown, live preview).

**Tests:** embed HTML self-contained (no external requests except the API poll
it makes — assert asset list); provider filter; lang rendering; headers
(CSP frame-ancestors, no Set-Cookie); size budget check in CI (fail > 30 KB);
snippet generator copies correct URL.

---

## G6 — Automated social posting (growth milestone)

Worker job `social_post` (every 5 min, advisory-locked per `17-…`):

- Triggers: launch T−60 min (per launch, once — dedupe table
  `social_posts(kind, ref_id, posted_at) PK(kind, ref_id)`), daily APOD at
  12:00 UTC.
- Targets v1: **Mastodon** (`POST /api/v1/statuses`, instance + token via
  settings `mastodon_base_url`, `mastodon_token`) and **Bluesky**
  (`com.atproto.repo.createRecord`; `bsky_handle`, `bsky_app_password`).
  Multi-account: settings hold a JSON list `social_accounts` —
  `[{platform, lang, credentials…}]` — so de/ja/es accounts post localized
  text from stored translations.
- Post content passes `sanitise()`; links point at the B2 launch pages (UTM
  `?utm_source={platform}`).
- Failures: log + Sentry, never retry more than once (a missed toot is not an
  incident); never block other jobs.

**Tests:** dedupe (same launch never posted twice, including across restarts);
T−60 window selection; per-language account routing; both clients mocked
(respx) incl. auth failure branch; sanitisation of mission names in post text.

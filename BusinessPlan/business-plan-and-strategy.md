# Space Adventures — Business Plan & Strategy

*Last updated: 2026-07-09 — mission-simulation library folded into the
education engine (§3.4, §4, §7); content-treadmill risk and cadence rule
added (§9); reflects the S1/S2 pull-forward in `CLAUDE.md` / roadmap v2.2.*

---

## 1. Executive Summary

Space Adventures is a multilingual web app that aggregates NASA data and live space
events (APOD, ISS tracking, rocket launches, Mars rover photos, near-Earth objects,
space weather) and turns them into personalized, reliable notifications.

**The product thesis:** space data is free and abundant, but it is scattered,
English-only, and passive. Nobody will pay for NASA's public data — but people will
pay for *"tell me, in my language, when something I care about is about to happen."*
The raw data is not the moat; the moat is built deliberately from four compounding
assets (see §3): a proprietary launch-slip dataset, alerting breadth, the
simulator as education/brand engine, and B2B distribution (museum kiosks,
education).

**The business thesis:** this is a niche lifestyle-business product with a real
but bounded B2B upside. Realistic success looks like CAD $40k–190k/year in
revenue within two years on top of a very low cost base (~$30–75/month
infrastructure) — see §6 Financial Projections. The first year is about building
an audience and the slip dataset; conversion follows both.

**Operating base:** Canada (relevant for legal/compliance — see §7 Phase 0 —
and for payment/tax setup).

---

## 2. Market & Competition

### Audience

- **Core:** space enthusiasts ("space nerds") — launch watchers, amateur
  astronomers, ISS spotters, Mars mission followers. Highly engaged, community
  organized (Reddit, Discord, Mastodon, YouTube), and willing to spend on their hobby
  (telescopes, merch, launch trips).
- **Secondary:** educators, students, science communicators, non-English-speaking
  space fans (significantly underserved — most space apps are English-only).

### Competition

| Competitor | What they do | Our angle against them |
|---|---|---|
| NASA's own sites/apps | Authoritative source data | Fragmented across dozens of sites; no unified alerts |
| Space Launch Now, Next Spaceflight | Launch tracking + notifications (mobile) | Mobile-first, English-only, launch-only; we aggregate more domains |
| ISS Detector, Heavens-Above | Satellite pass prediction | Single-purpose; dated UX |
| Generic news apps / X accounts | Launch news | Noisy, not personalized, not reliable for time-critical alerts |

### Differentiators

1. **One place** for launches, ISS, Mars, NEOs, space weather, and APOD.
2. **Six languages** (en, de, fr, es, ja, ru) — the multilingual angle is genuinely
   underserved and widens the addressable audience beyond the crowded English market.
3. **Reliable alerting** including launch NET-slip detection (already implemented) —
   the single most painful problem for launch watchers is schedule slips.
4. **Web-first** — no app-store install friction, works everywhere, embeddable.
5. **Proprietary slip-history data** (§3) — the only differentiator that
   *compounds* and cannot be fast-followed.

---

## 3. Moat Strategy

Alerting is a feature; features get copied. A moat is anything that **compounds
with time and can't be replicated by a competitor's two-week sprint**. Four
assets, in order of defensibility:

### 3.1 The slip-history dataset (highest conviction)

The launch sync already detects NET slips; storing every slip permanently
(roadmap Tier 0) builds a dataset nobody else keeps. After 12–18 months it
yields:

- **Provider reliability scores** — "Falcon 9 launches within 24 h of announced
  NET 87 % of the time." Press-bait, SEO gold, visible proof of the moat.
- **Slip-risk confidence on alerts** — "this date is 60 % likely to hold." A Pro
  feature that *improves with every month of operation*; a fast-follower starts
  from zero data no matter how fast they code.
- Downstream: slip-aware launch-viewing trip planning, licensable datasets for
  space media.

Cost: a schema change and an insert. **Start recording before launch — every
month of delay is lost data.**

### 3.2 Alerting breadth via free APIs

Each new event type deepens the "the app that always tells me first" position:
Starlink-train visibility (CelesTrak), aurora *nowcasting* (NOAA OVATION — "go
outside in 30 minutes", not "possible tonight"), ISS lunar/solar transits for
astrophotographers, reentry events, exoplanet discoveries. No single alert is a
moat; the *breadth × six languages × one reliable pipeline* is hard to match.

### 3.3 Switching costs & community data

Personal space logs, streaks, sighting reports, calendar feeds embedded in
users' daily tools — the user's own history lives in the app. Sighting reports
double as validation data for prediction accuracy (community-generated data
moat, the only content moat available to an indie product).

### 3.4 Education & B2B distribution — the mission-simulation library

The simulator (real Keplerian mechanics already implemented) becomes the
brand/education engine: live spacecraft positions, **mission replay mode**
(real trajectories — true, not animated; Artemis-timed press moments), and on
top of it the **mission-simulation library**: replays with real spacecraft 3D
models at close-up phases (landing, surface ops) plus structured technical
facts, starting with Apollo 11 and Mars Pathfinder/Sojourner (specs
`Architecture/22` + `27`).

Why this compounds like a moat asset:

- **The inputs are free; the curation is the moat.** NASA 3D models are
  public domain and the Smithsonian's Apollo 11 scans are CC0 — but a
  fast-follower still has to redo asset conversion, trajectory research
  (Apollo-era missions require hand-curated as-flown data), milestone
  editorial, and six-locale translation, mission by mission.
- **Marginal cost falls to data + assets** once the engine ships — no code
  per new mission — and every mission added makes both B2B products below
  more valuable simultaneously.
- **Evergreen multilingual SEO**: "Apollo 11 simulation" in German or
  Japanese has effectively no competition, and mission pages don't expire
  the way launch pages do.

**Cadence rule (guards against the treadmill — see §9):** after the first
two missions, a new mission is built only on a trigger: (a) a press window
(Artemis, Starship milestones), (b) a paying kiosk/education customer asks
for it, or (c) assets + trajectory are nearly free to acquire. Technical
information ships as **structured fact panels** (mass, delta-v, durations,
crew — cheap to translate, doesn't rot), never long-form prose. "All
meaningful missions" is the eventual shape, not an upfront commitment.

It feeds two B2B surfaces where institutions, not consumers, pay:
**museum/planetarium kiosk mode** and a **classroom education tier** in six
languages. B2B contracts renew annually and don't churn like consumers —
distribution embedded in institutions is itself a moat.

---

## 4. Business Model

### Freemium subscription (core model)

| | Free | Pro (~CAD $4–5/month or ~$40/year) |
|---|---|---|
| Browse all features (APOD, ISS, Mars, NEO, weather, launches) | ✅ | ✅ |
| Email notifications | Up to 3 active launch subscriptions | Unlimited |
| SMS notifications | ❌ (costs us real Twilio money per message) | ✅ |
| NET-slip / schedule-change alerts | ❌ | ✅ |
| Slip-risk confidence scores ("60 % likely to hold") | ❌ | ✅ |
| iCal calendar feed of subscribed launches | ❌ | ✅ |
| Location-based "ISS visible over your city tonight" alerts | ❌ | ✅ |
| Starlink-train visibility alerts | Banner only | ✅ |
| Aurora nowcasting alerts (NOAA OVATION) | Conditions banner | ✅ |
| ISS lunar/solar transit finder (astrophotographers) | ❌ | ✅ |
| Ads | None (see below) | None |

Pricing rationale: below the "think about it" threshold, comparable to a coffee,
and the yearly plan front-loads cash flow. Use Stripe (or Paddle as merchant of
record to offload EU VAT and international sales-tax handling — strongly
recommended for a solo Canadian operator selling to six language markets).

### Explicitly rejected: display ads

At niche-community scale, display ads earn near-nothing and destroy the "beautiful
space app" experience that is the actual differentiator. Do not add them.

### B2B revenue streams (second engine — see roadmap "B2B Track")

1. **Museum / planetarium / science-center kiosk mode** — full-screen live
   displays (ISS globe, launch countdowns, **mission simulations**),
   multilingual and auto-updating. Institutions pay ~$250–500/screen/year for
   exactly this and the product is ~90 % built. The mission-simulation
   library (§3.4) is the strongest asset in the pilot pitch — an auto-cycling
   Apollo 11 landing in six languages is a product a science center
   understands instantly, in a way a countdown widget is not. **Validate with
   5 pilot institutions before building beyond a full-screen toggle.** Annual
   contracts; near-zero churn.
2. **Education tier** — classroom mode over the simulator + guided mission
   simulations with structured technical fact panels + quiz layers, in six
   languages (Spanish/French classroom markets are underserved). Teacher
   plans first; school-board pricing later. Mission demand from teachers and
   pilot institutions is trigger (b) in the §3.4 cadence rule — the library
   grows toward what classrooms ask for, not toward completionism.
3. **Media & data licensing** — translated event feeds, embeddable mission
   visualizations for non-English outlets during big missions, reliability-score
   datasets. Inbound-driven: publish the data, let media come.

### Side channels (later, in priority order)

1. **Affiliate revenue** — telescope/binocular gear guides tied to sky events
   (e.g. "how to watch tonight's ISS pass" → recommended binoculars). Space
   enthusiasts buy equipment; the transit finder and viewing guides feed this.
2. **Embeddable widgets (growth loop)** — launch-countdown, ISS, and
   mission-replay embeds for space YouTubers, bloggers, Discord servers. Free
   with attribution and a backlink (SEO + acquisition), white-label for a fee.
3. **Launch-viewing travel layer** — viewing-spot guides per pad with
   slip-risk-aware trip planning (the slip dataset is the differentiator);
   hotel/tour affiliates.
4. **Donations / "Supporter" tier** — some community members pay simply to support
   an indie project; a $10/month supporter tier with a Discord badge costs nothing
   to offer.

### What NOT to monetize

- The data itself (public domain, free elsewhere).
- API access to raw NASA data (we'd just be reselling free data with extra steps).
- Anything that gates *browsing* — free browsing is the top of the funnel.

---

## 5. Cost Structure

All figures CAD/month.

| Item | Estimate / month | Notes |
|---|---|---|
| VPS | $15–30 | Hetzner (EU) or OVH Canada — either works; single machine runs everything at launch scale |
| Domain + email sending | $8–20 | Use a transactional provider (Postmark/SES), not raw SMTP |
| Twilio SMS | Variable | ~$0.01–0.10/SMS depending on destination country — must be Pro-only, cap per user |
| Translation API (DeepL/Google Cloud) | $0–35 | Replaces the free scraper (TOS risk); volume is low since translations are cached in DB |
| Backups + monitoring | $0–15 | Object storage for Postgres dumps; free tiers cover uptime monitoring |
| Payment processing | ~3–5% of revenue | Stripe/Paddle fees |

**Break-even is roughly 10–20 Pro subscribers.** This is the key strategic fact:
the downside is tiny, so the rational play is to launch, learn, and iterate.

---

## 6. Financial Projections & Market Sizing

All figures CAD. Assumes the full feature roadmap
(`FeatureIdeas/feature-roadmap.md`) is shipped, the app is production-ready per
`ProductionReadiness/production-readiness.md`, rollout is executed well, and a
modest marketing budget is deployed.

### Market sizing: language reach ≠ market size

The six languages cover ~2.8B speakers, but the funnel narrows sharply:

| Funnel stage | Rough size |
|---|---|
| Speakers of the six languages | ~2.8B |
| Online + casually interested in space | low hundreds of millions |
| Engaged enough to use a *dedicated* space app | ~10–30M globally |
| Realistically reachable by an indie web app, years 1–3 | 20k–500k MAU |
| Paying (freemium consumer utility conversion) | 1–5% of engaged users |

Calibration from incumbents: ISS Detector and the official NASA app each have
~10M *lifetime* Android downloads after a decade, and downloads overstate active
users by 5–10×. Space Launch Now — the closest analog — remains a side-project-
scale business. The global "dedicated space enthusiast" audience is tens of
millions, already served by free options. That is the pond, regardless of UI
languages.

Where multilingual genuinely helps: the non-English slices of that pond have
almost no competition. Ranking for "Starship Start heute" or "ISS 通過時間" is far
easier than for the English equivalents. This plausibly doubles or triples
realistic capture; it does not change the order of magnitude.

### Revenue scenarios (~2 years post-launch, full v2 roadmap shipped)

Blended ARPU ≈ $38–40/year per Pro subscriber (mix of monthly and discounted
annual plans). The v2 roadmap (moat features + B2B track) raises both conversion
assumptions (more Pro-only alert types: aurora nowcast, Starlink trains, transit
finder, slip-risk scores) and adds an institutional revenue line. **B2B figures
are speculative until the 5-institution kiosk pilot validates pricing** — treat
them as the swing variable between scenarios. The mission-simulation library
(§3.4) strengthens the kiosk/education *pitch* but changes no number here
until the pilot converts — it is pitch material, not validated revenue.
Mission simulations themselves stay free (brand/funnel); they monetize only
through the B2B lines.

| Scenario | MAU | Conv. | Subs | Subscriptions | B2B (kiosk + edu)* | Side channels** | Total / year |
|---|---|---|---|---|---|---|---|
| **Realistic** (most likely) | 30k | 2–2.5% | ~700 | ~$28k | ~10–20 institutions → ~$5k | ~$7k | **~$40k** |
| **Optimistic** (top ~10%, execution + pilot succeeds) | 100k | 3% | ~3,000 | ~$115k | ~100–150 institutions + teacher plans → ~$40–50k | ~$25k | **~$180–190k** |
| Exceptional (top ~1%, viral moment + B2B scale) | 400–500k | 3–3.5% | ~15k | ~$600k | ~300+ institutions + licensing → ~$150–250k | ~$50–100k | **~$800k–1M** |

\* Kiosk at ~$250–500/screen/year; education tier; media/data licensing in the
upper rows. Institutional revenue renews annually with near-zero churn — it
compounds across years in a way consumer subs don't.
\** Affiliate gear guides, white-label widgets, API tier, travel layer,
supporter tier.

Compared to the v1 projection (base ~$30k / good ~$125k / ceiling ~$700k), the
uplift comes from three places, in order of confidence:

1. **More Pro-only alert types** → conversion assumption moves from 2% toward
   3% (high confidence — this is standard freemium behavior: more exclusive
   value, better conversion).
2. **B2B kiosk/education line** (medium confidence — the market demonstrably
   exists and pays, but *our* pricing and sales motion are unvalidated until
   the pilot).
3. **Slip-data products** improving retention and press coverage (directional —
   hard to attribute, but it's also what makes every other line defensible).

The exceptional row still requires a viral moment (a Starship milestone, an
Artemis landing — mission replay mode is specifically positioned to catch
these) plus years of compounding SEO and dataset advantage. Plan for the
realistic case; the optimistic case is a genuine 1-in-10 outcome, not a pitch
deck number.

### Marketing budget guidance

**Paid ads on cold audiences will not pay back** for a ~$40/year consumer
product: realistic CAC via Meta/Google is $20–80 per subscriber after free-tier
conversion — more than 1–2 years of revenue, before churn. Spend where the niche
actually lives instead (roughly $1–3k/month is enough to matter):

1. **Space-creator sponsorships** — Everyday Astronaut, NASASpaceflight, smaller
   launch-stream channels, and their German/Spanish/Japanese counterparts. A $500
   read during a launch stream reaches exactly the funnel.
2. **Newsletter sponsorships** — Payload, The Orbital Index.
3. **Event-timed pushes** — concentrate budget into major mission windows, when
   attention and search volume spike 10–50×.
4. **Non-English content production** — organic is where the multilingual edge
   actually pays.

### Bottom line

Built and rolled out correctly, the product comfortably clears its ~$500/month
cost base and plausibly reaches solid side-income to modest-salary revenue
(**realistic ~$40k/year, optimistic ~$180–190k/year**) within two years. It is
still very unlikely to become venture-scale on consumer subscriptions alone —
the ceiling is the size of the engaged space-fan population. The two levers that
raise the ceiling are now *in* the plan rather than hypothetical: the B2B
kiosk/education track (institutions pay 10–100× consumer prices, renew annually)
and the slip-history dataset (the only asset that compounds regardless of user
growth).

---

## 7. Roll-Out Plan

### Current (pre-Phase 0) — Mission simulations S1/S2 (owner decision 2026-07-09)

The mission-replay engine and 3D simulation layer (Steps S1/S2, specs
`Architecture/22` G3 + `27`) are being built *before* production hardening.
This is workable because the scope is frontend-only + offline tooling — no
new routes, tables, or worker jobs — so nothing in Phase 0 is blocked or
complicated by it. Two constraints keep it honest:

- **Timebox: two missions** (Apollo 11, Pathfinder/Sojourner), then move to
  Phase 0. The library grows later only via the §3.4 cadence rule.
- **The opportunity cost is the slip dataset**: §3.1's clock starts only when
  production launches. Every week S runs long is unrecoverable dataset time —
  the strongest argument against letting this phase expand.

Upside of the ordering: the kiosk pilot (Phase 3) can be pitched with real
mission simulations from day one, and the public launch (Phase 2) lands with
the app's most shareable content already live.

### Phase 0 — Production hardening (1–2 weeks)

Complete the blockers in `ProductionReadiness/production-readiness.md`:
Postgres migration, scheduler extraction, settings-endpoint auth, secrets handling,
observability, backups. **Do not take real users before this phase is done** —
the settings endpoints in particular are an open vandalism vector today.

Also in this phase: **start permanent slip-history recording** (roadmap Tier 0).
It is ~1 day of work, and the dataset it produces (§3.1) grows only with elapsed
time — every month of delay is unrecoverable.

Also complete legal housekeeping (required before *any* public users, since we
store emails and phone numbers). Operating base is Canada, but users will be
worldwide, so three regimes apply:

- **CASL (Canada's Anti-Spam Legislation)** — directly relevant because
  notifications *are* the product. Requires express consent and a functioning
  unsubscribe mechanism for commercial electronic messages, **including SMS**,
  with substantial penalties. The existing OTP verification (consent evidence)
  and unsubscribe-token flow already cover the mechanics; document consent
  capture and keep records.
- **PIPEDA** — Canadian federal privacy law: privacy policy, purpose limitation,
  access/deletion on request.
- **GDPR** — applies to EU users regardless of where the operator is based:
  privacy policy, data export/deletion, lawful basis for processing. Hosting in
  the EU (Hetzner) or Canada (OVH) both work; avoid gratuitous third-party
  trackers and this stays simple.
- Review TOS of Launch Library 2, N2YO, and Twilio for commercial use; NASA data
  itself is public domain.
- Terms of service with a clear "informational only, no liability for missed
  alerts" clause.

### Phase 1 — Closed beta (4–6 weeks, 50–100 users)

- Deploy to a single EU VPS: Caddy + backend + worker + Postgres via docker-compose.
- Recruit from space communities: r/space, r/SpaceX, r/spaceflight, spaceflight
  Discords, Mastodon astronomy instances. Personal invites > open signup.
- **The thing being tested is not load — it is whether notifications fire
  correctly on real launch slips.** That is the core value proposition; a missed
  or wrong alert during beta is the most valuable bug report possible.
- Instrument: signup funnel, notification delivery success rate, which features
  get used, which languages get used.
- Weekly feedback loop (short survey or Discord channel).

### Phase 2 — Public launch (timed to a launch event)

- **Time the launch to a high-profile space event** (Artemis mission, Starship
  flight, major planetary event) when public space interest spikes and journalists
  are looking for angles.
- Channels, in order: Show HN, Product Hunt, the beta communities, space-focused
  newsletters (The Orbital Index, Payload).
- Launch with the free tier only or with Pro at a founding-member discount —
  do not let payments infrastructure delay the launch date.
- Have per-launch SEO pages live before this (see Growth below).

### Phase 3 — Convert & compound (months 2–6)

- Turn on Pro tier (if not already), grandfather beta users with a lifetime
  discount — they are the evangelists.
- Ship the highest-conversion Pro features first: **ISS-pass-over-your-location
  alerts** and **iCal feeds**, then **aurora nowcasting** and **Starlink-train
  alerts** (see `FeatureIdeas/feature-roadmap.md` sequencing).
- Publish **provider reliability scores** as the first slip-dataset product —
  it doubles as a press/SEO asset.
- Release the embeddable countdown widget (growth loop); the replay engine
  and first two missions already exist (pre-Phase-0 step S) — time the
  **Artemis mission content** to the Artemis window for a press moment
  (trigger (a) of the §3.4 cadence rule).
- Run the **museum kiosk pilot**: pitch 5 science centers with a full-screen
  toggle prototype **featuring the mission simulations** before building
  anything more (validates the B2B line in §6). Pilot feedback decides which
  missions get built next (trigger (b)).
- Measure: free→Pro conversion (healthy niche benchmark: 2–5%), monthly churn,
  notification engagement (open/click), pilot conversion.

### Phase 4 — Decide (month 6+)

With 6 months of data, pick a lane:

- **Growing:** invest in mobile PWA/push notifications, community features,
  more languages.
- **Flat but loved:** run it as a low-effort lifestyle product; costs are trivial.
- **Dead:** the sunk cost is a portfolio piece demonstrating full-stack +
  production skills; wind down gracefully (GDPR-compliant data deletion, notify
  users, open-source it for goodwill).

---

## 8. Growth Strategy

1. **SEO on per-launch pages is the #1 free acquisition channel.** Every upcoming
   launch is a recurring search-traffic event ("Falcon 9 Starlink launch time").
   Server-render (or pre-render) a public page per launch with structured data
   (schema.org Event markup) — this requires the SSR/prerender work noted in the
   production doc. Six languages multiplies this: we can rank for launch queries
   in German, French, Spanish, Japanese, and Russian with far less competition.
   **Mission-simulation pages are the evergreen complement**: launch pages
   capture recurring event spikes, mission pages ("Apollo 11 simulation",
   "Mars Pathfinder landing") accumulate rank permanently — same multilingual
   edge, no expiry.
2. **Embeddable widgets** put the brand on other people's sites with backlinks —
   mission-simulation embeds are the most shareable of these (the vignette
   moments are built to be the shareable unit).
3. **Event-driven social content**: automated "launch in 1 hour" posts
   (Mastodon/Bluesky/X) with a link to the tracking page.
4. **Community reciprocity**: be genuinely useful in space communities rather than
   advertising in them; share the tool when it answers someone's question.
5. **Language communities**: the de/fr/es/ja/ru versions deserve their own
   community outreach — these markets have far fewer alternatives.

---

## 9. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Upstream API changes/limits (LL2, N2YO, NASA) | Medium | Caching layer already isolates us; keep sync frequency modest; budget for LL2 paid tier if needed |
| Free competitors add the same alerts | Medium | Compete on multilingual + multi-domain aggregation + UX polish, not any single feature |
| SMS cost abuse | Medium | Pro-only, per-user monthly SMS caps, phone verification (already have OTP) |
| Privacy/anti-spam complaint (CASL, PIPEDA, GDPR) | Low, high impact | Express-consent records (OTP flow), unsubscribe on every message, minimal data collection, deletion endpoint, no third-party trackers |
| Solo-founder burnout | High | Keep infra boring (one VPS, docker-compose); automate backups/monitoring; scope features ruthlessly |
| Mission-library content treadmill (editorial + 6-language cost per mission; no natural stopping point) | Medium | §3.4 cadence rule: new missions only on triggers (press window / paying institution / near-free assets); structured fact panels instead of long-form prose; two-mission timebox before Phase 0 |
| Monetization ceiling too low | Medium | Accept it — cost base is tiny; treat as audience-building with optionality |

---

## 10. KPIs

- **North star:** weekly active *notified* users (users who received ≥1 alert
  that week) — measures the core value, not vanity traffic.
- Signup → verified account rate (OTP funnel health).
- Free → Pro conversion (target 2–5% of engaged users).
- Monthly churn (target <5%).
- Notification delivery success rate (target >99%; alert on failures).
- Organic search sessions to per-launch pages (leading growth indicator).
- **Slip-history dataset size** (launches × recorded NET changes) — the moat
  metric; it should only ever grow.
- **Institutional customers** (kiosk screens + education seats) and their
  annual renewal rate — the B2B engine's health.
- **Mission-simulation engagement** (replay sessions, completion rate,
  embed loads, organic sessions on mission pages) — the education engine's
  leading indicator, and the evidence base for cadence-rule decisions on
  which mission to build next.

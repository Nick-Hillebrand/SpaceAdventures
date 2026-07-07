# Space Adventures — Feature Roadmap & Ideas

*Last updated: 2026-07-06 (v2 — restructured around moat-building; see changelog at bottom)*

Features that would enrich the business and make the app more desirable to the
space community. Organized by leverage: **data-moat foundations first** (they
compound with time — every month of delay is lost data), then conversion
drivers, engagement, growth, community, a B2B track, and long-shot ideas.

Each entry notes what it builds on in the existing codebase and its tier in the
freemium model (see `BusinessPlan/business-plan-and-strategy.md` §4).

**The strategic frame:** alerting is the revenue engine, the simulator is the
brand/education engine, and the slip-history dataset is the thing no competitor
can catch up on. A feature earns a slot here by feeding one of those three.

> **Implementation specs exist** for everything through the "After traction"
> phase: `Architecture/15`–`25`, sequenced as steps P1–T1 in `CLAUDE.md`.
> Spec mapping: Tier 0 + #7/#8 → `18`; #1/#2/#9/#12 → `19`; #3/#6 → `20`;
> #4/#5 → `21`; #10/#11 → `22`; #16–#24 growth surfaces → `23`; #28 → `24`.

---

## Free API inventory (what powers what)

| API (free) | Feeds features |
|---|---|
| Launch Library 2 *(in use)* | #1, #2, launches core |
| NASA APIs *(in use: APOD, NeoWs, DONKI, Mars)* | existing pages |
| N2YO *(in use)* | #3 ISS pass alerts |
| **JPL Horizons** — ephemerides for planets, small bodies, *and spacecraft* | #10 live spacecraft, #11 mission replay |
| **CelesTrak (TLEs)** — every tracked satellite | #4 Starlink trains, #5 transit finder, #24 AMSAT |
| **NOAA SWPC** — real-time space weather + OVATION aurora model | #6 aurora nowcasting |
| **Space-Track** (free account) — authoritative catalog, reentry predictions | #18 reentry alerts |
| **NASA Exoplanet Archive** (TAP) | #17 exoplanet explorer + discovery alerts |
| **NASA GIBS / EPIC** — Earth imagery and map tiles | #16 "Earth today" |
| **NASA Trek WMTS** — Moon/Mars map tiles | #11 landing-site maps, #22 rover traverses |
| **Spaceflight News API** (TheSpaceDevs) | #19 news auto-attach |

---

## Tier 0 — Data-moat foundations ⭐ start immediately, before all other work

### 0a. Permanent launch slip-history recording
The launch sync already detects NET changes (`launches_service.py`) but only
alerts on them. **Store every slip permanently** (launch id, old/new NET,
detected-at, provider, rocket, pad). After 12–18 months this is a dataset nobody
else has bothered to keep. It costs a schema change and an insert.
- **Unlocks:** #7 reliability scores, #8 slip-risk predictions, launch-viewing
  travel planning (#28), media/data licensing (#27).
- **Tier:** n/a (infrastructure). **Effort:** ~1 day. **Do it in Phase 0.**

### 0b. "Store everything" principle for event data
Same logic applies to aurora/space-weather events, pass predictions vs. actual
sightings (#14), and notification outcomes: keep history, don't overwrite.
Storage is free; derived-data products are the moat.

---

## Tier 1 — Conversion drivers (these sell Pro)

### 1. Launch NET-slip & status alerts as a first-class product
Change detection already exists — surface it loudly: "Your launch slipped
2 days", "GO — weather 90% favorable", "Scrub". Launch watchers' single biggest
pain is planning around slips.
- **Builds on:** existing change detection + notification outbox.
- **Tier:** basic reminder Free (3 subscriptions), slip/status stream Pro.

### 2. iCal / calendar feeds
Per-user `webcal://` URL with subscribed launches, auto-updating on slips.
Cheap to build, permanent daily touchpoint, very hard to churn from.
- **Builds on:** launches + subscriptions; signed-token ICS endpoint (same
  pattern as unsubscribe tokens). **Tier:** Pro.

### 3. "ISS visible over your city tonight" alerts
Predicted *visual* ISS passes for the user's location with an alert 30 minutes
before. The moment a space fan physically walks outside because of your app.
- **Builds on:** `n2yo_client.py` (`visualpasses` endpoint), quota guard exists.
- **Needs:** user location (city-level geocode), pass sync in worker.
- **Tier:** Pro (flagship). Free users see tonight's pass on the ISS page.

### 4. Starlink-train visibility alerts *(new in v2)*
"A Starlink train will cross your sky at 22:41 tonight." Currently the #1
"what did I just see" search on the internet after every Starlink launch, and
no mainstream app alerts on it. CelesTrak TLEs + SGP4 propagation + recency
filter (trains are visible days after launch).
- **Builds on:** location from #3; new TLE sync in worker.
- **Tier:** Pro alert; "visible tonight" banner Free.

### 5. ISS lunar/solar transit finder *(new in v2)*
Predict ISS transits across the Moon/Sun for a given location — astrophotographers
plan whole trips around these and currently rely on a single hobbyist site.
Small audience, **very high willingness to pay**, and it feeds the affiliate
gear channel.
- **Builds on:** TLE infrastructure from #4 + ephemerides from #10.
- **Tier:** Pro (consider a separate "Astro" add-on later if demand shows).

### 6. Aurora nowcasting alerts *(upgraded from v1: DONKI → NOAA OVATION)*
v1 planned "Kp threshold + latitude → possible tonight" from DONKI. NOAA SWPC's
OVATION model enables **nowcasting**: "aurora likely visible in the next
30–60 min at your location." That's the difference between an interesting email
and a run-outside push notification.
- **Builds on:** `space_weather_service.py`, location from #3, NOAA polling in
  worker. **Tier:** Pro alert; current-conditions banner Free.

### 7. Provider reliability scores *(new in v2 — consumes Tier 0 data)*
"Falcon 9 launches within 24 h of announced NET 87% of the time." Public
analytics page per provider/rocket: median slip, scrub rate, trend. Press-bait,
SEO gold, and the visible proof of the data moat.
- **Tier:** Free (it's marketing); detailed per-launch history Pro.

### 8. Slip-risk confidence on alerts *(new in v2 — consumes Tier 0 data)*
"This date is 60% likely to hold" on every launch card, derived from historical
slip behavior of that provider/rocket/pad. **Gets better with every month of
operation — a compounding advantage no fast-follower can copy.**
- **Tier:** Pro.

### 9. Web Push notifications (PWA)
Browser push = de-facto mobile app without app stores; reduces SMS cost
pressure. Service worker + push as a third channel in the notification outbox.
- **Tier:** Free for basic reminders (costs nothing, makes free tier sticky);
  advanced alert types remain Pro.

---

## Tier 2 — Engagement, brand & education (make it a daily habit)

### 10. Live spacecraft in the solar system simulator *(new in v2)*
Plot JWST, Voyager 1/2, Parker Solar Probe, and active interplanetary missions
at their real current positions from JPL Horizons. "Where is Voyager right now"
is a perennial search query, and the simulator already computes real Keplerian
orbits (`solar/orbits.ts`) — Horizons state vectors slot into the existing scene.
- **Tier:** Free (brand/SEO feature).

### 11. Mission replay mode ⭐ education centerpiece *(new in v2)*
Guided, scrubable timeline of a mission's real trajectory with milestone
annotations (TLI burn, flyby, entry) — Artemis 1/2, Apollo 11, and live missions
as they happen. Because it uses real Horizons ephemerides it is *true*, not an
animation — the differentiator against YouTube. Embeddable (→ #21) and
classroom-ready (→ #26). Timed right, an Artemis replay is a press moment.
- **Builds on:** simulator engine + Horizons cache from #10; NASA Trek tiles for
  landing-site close-ups.
- **Tier:** current + historical replays Free (growth); replay embeds
  white-label via B2B track.

### 12. Personalized "Today in Space" daily digest
One opt-in email/push per day: APOD, tonight's ISS pass, launches in 48 h, NEO
close approaches, aurora outlook — in the user's language. The aggregation
thesis in one artifact.
- **Tier:** weekly Free, daily + personalized Pro.

### 13. Sky-event calendar beyond launches
Meteor showers, eclipses, conjunctions, supermoons. Mostly computable/static —
an annual curated table gets 90% of the value. Huge SEO surface, fills gaps
between launches.
- **Tier:** browsing Free; alerts Pro.

### 14. Streaks, badges & a personal space log
"You've watched 12 launches", "First ISS spotting logged." A lightweight
"I watched this" button creates personal history — habit mechanics and
**switching costs** (your log lives here), plus sighting data for Tier 0b.
- **Tier:** Free.

### 15. Favorites & followed entities
Follow a rover, agency, launch site, or mission; everything filters to it.
Turns the generic feed into *my* feed.
- **Tier:** a few follows Free, unlimited Pro.

---

## Tier 3 — Growth features (bring new users in)

### 16. "Earth today" shareable content *(new in v2)*
Daily whole-Earth image (NASA EPIC), hurricane/eclipse-shadow visuals from GIBS
tiles. Cheap automated shareable content for the social bot (#20).
- **Tier:** Free.

### 17. Exoplanet explorer + discovery alerts *(new in v2)*
Browse 5,000+ confirmed exoplanets (NASA Exoplanet Archive TAP); "new
potentially habitable planet discovered" alerts extend the alerting DNA beyond
the solar system. Discovery news reliably goes viral.
- **Tier:** browsing Free; discovery alerts Pro.

### 18. Reentry alerts *(new in v2)*
"A large rocket stage reenters over Europe tonight" (Space-Track predictions).
Rare, but each event is massively viral and search-spiking — be the site that
has the map ready.
- **Tier:** Free (growth events, not conversion events).

### 19. News auto-attach *(new in v2)*
Attach relevant Spaceflight News API articles to launches/events already shown,
machine-translated. Explicitly **not** journalism — no editorial treadmill —
just context enrichment on existing pages.
- **Tier:** Free.

### 20. Automated social posting
Worker posts "T-1 hour" alerts, daily APOD, Earth-today images to
Mastodon/Bluesky/X with a link back. The multilingual accounts have far less
competition. Zero-marginal-cost distribution.

### 21. Embeddable widgets
Next-launch countdown / ISS position / APOD / **mission replays (#11)** as
embeds for blogs, YouTube pages, Discords. Free with "Powered by Space
Adventures" backlink; white-label via B2B track (#25). *The* growth loop.

### 22. Per-launch public pages with SEO/OG treatment
Prerendered page per launch (countdown, weather, stream, pad map,
**slip-risk score from #8**) with schema.org Event markup, per-language URLs.
Every launch is a recurring search-traffic event in six languages.
(Prerequisite: prerendering — `ProductionReadiness/production-readiness.md` §14.)

### 23. "Watch party" links
Launch page mode with livestream + synced countdown + presence counter. Shared
into Discords before every big launch — each share is an acquisition event.

### 24. "What does it take" interactives *(new in v2)*
Transfer windows to Mars, why launches scrub, solar-system scale. Evergreen
educational SEO no launch-tracker competitor has; feeds classroom tier (#26).
- **Tier:** Free.

---

## Tier 4 — Community features (defensible once traction exists)

### 25. Sighting reports & photo sharing
"I saw it!" on ISS passes, launches, aurora, Starlink trains — with map of
sightings per event. User-generated content is the only true content moat
available here; sightings also validate prediction accuracy (Tier 0b).
- **Caution:** photos mean moderation + storage; start report-without-photo.

### 26. Comments / discussion threads on launches
Only with an active user base — dead comment sections are worse than none.

### 27. Public API for the community (freemium)
Curated, cached, multilingual aggregation API — the value-add is normalized
data + translations + **slip history**, not raw NASA passthrough. Free keyed
tier; paid tier for apps/bots. Formalizes the widget backend.

---

## B2B Track *(new in v2 — runs parallel to consumer tiers)*

### 28. Museum / planetarium / science-center kiosk mode ⭐ strongest B2B bet
Full-screen display mode: live ISS globe, next-launch countdown, mission
replays, aurora map — auto-cycling, multilingual, auto-updating. Institutions
pay real money (hundreds per screen per year) for exactly this, and the product
is ~90 % built. **Validate before building: pitch 5 science centers with a
full-screen toggle prototype.**
- **Needs (see production doc):** kiosk auth tokens, uptime monitoring
  suitable for institutional customers, offline-tolerant display behavior.

### 29. Education tier (teachers & classrooms)
Classroom mode over the simulator + mission replays (#11) + interactives (#24):
quiz layers, worksheets, teacher dashboard — in six languages (Spanish/French
classroom markets are underserved). Validate with teacher interviews first.
- **Tier:** cheap education plan or free-as-funnel; institutional pricing for
  school boards later.

### 30. Media & data licensing
Normalized, translated event feed + embeddable mission visualizations for
non-English outlets during big missions; reliability-score datasets (#7) for
space media. Inbound-driven — publish the data, let media come.

### 31. Launch-viewing travel layer
Viewing-spot guides per pad (Florida/Texas/Vandenberg/Kourou),
**slip-risk-aware trip planning** (#8 is the differentiator: "book refundable —
this date is shaky"), hotel/tour affiliates.

---

## Tier 5 — Bigger bets (only with clear demand)

### 32. Mars exploration deepening
Rover traverse maps on real Trek tiles, "on this sol" history, 3D rover models
(`RoverViewer.tsx`) as guided walkthroughs. Now largely a consumer of the #10/#11
engine rather than a standalone bet.

### 33. Telescope-night planner
Location + date → what's visible tonight, best window, moon interference.
Pairs with affiliate gear guides. Scope narrowly to "tonight, for normal
people" — don't compete with Stellarium.

### 34. AMSAT / ham-satellite passes
Passionate niche, nearly free to serve once TLE infrastructure (#4) exists.
Community goodwill more than revenue.

### 35. AI mission copilot
Natural-language Q&A over the app's own cached data ("When can I see the ISS
from Vancouver this week?"). Compelling press angle; per-query cost → Pro-only.
Build only after the data foundation exists — it multiplies everything above
but adds nothing alone.

---

## Explicitly not recommended

- **Native mobile apps** — PWA (#9) delivers 90 % of the value at 10 % of the
  maintenance; stores add friction and a 15–30 % revenue cut.
- **Real-time chat** — moderation burden, no differentiation; integrate with
  Discord instead.
- **Space news aggregation/blogging** — crowded and editorially expensive;
  #19 (auto-attach) is the ceiling of news involvement.
- **Cryptocurrency/NFT anything** — poison for this community's trust.

---

## Suggested sequencing

| Phase (aligned with rollout plan) | Features |
|---|---|
| **Phase 0 (with production hardening)** | **Tier 0 slip-history recording** — every month of delay is lost data |
| Beta | #1 slip alerts polished, #9 web push, #22 launch pages, #10 live spacecraft |
| Public launch | #3 ISS pass alerts, #2 iCal, #21 widgets, #7 reliability scores (press angle) |
| Months 2–6 | #6 aurora nowcast, #4 Starlink trains, #11 mission replay (time to Artemis window), #12 digest, #20 social bot, #28 kiosk pilot (5 institutions) |
| After traction | #8 slip-risk scores, #5 transit finder, #13–15 retention pack, #24 interactives, #29 education tier |
| Only with demand | #25–27 community, #30–31, Tier 5 |

---

## Changelog v1 → v2

- **Added Tier 0 (data moat):** permanent slip-history recording — highest-
  conviction item in the roadmap; was entirely absent from v1.
- **New conversion drivers:** Starlink-train alerts (#4), ISS transit finder
  (#5), reliability scores (#7), slip-risk confidence (#8).
- **Aurora alerts upgraded** from DONKI "possible tonight" to NOAA OVATION
  nowcasting (#6).
- **Education became a strategy, not a bet:** live spacecraft (#10) and mission
  replay (#11) promoted into Tier 2 as the brand/education engine, feeding the
  new B2B track; v1's "kids/classroom mode" long-shot became the education tier
  (#29) built on top of them.
- **New B2B track:** museum kiosk mode (#28), education tier (#29), media/data
  licensing (#30), launch-viewing travel (#31) — v1 had no B2B surface at all.
- **New growth items** from free APIs: Earth today (#16), exoplanets (#17),
  reentries (#18), news auto-attach (#19), interactives (#24).
- v1's Mars deepening demoted to a consumer of the simulator engine (#32).

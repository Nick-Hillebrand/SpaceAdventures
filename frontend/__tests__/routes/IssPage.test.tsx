import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";
import type {
  IssPassesResponse,
  IssPositionsResponse,
  IssQuotaResponse,
  IssTleResponse,
  SubscriptionsResponse,
} from "@/types/api";

// P28: vi.mock() hoisting — use vi.hoisted() to create the mock instance
// before it is captured in the mock factory.
//
// Globe.gl usage: `new Globe()(containerRef.current)`
//   1. new Globe()  → returns a callable factory (mockGlobe itself)
//   2. factory(el)  → returns the globe API object (also mockGlobe)
// So mockGlobe must be a callable vi.fn that returns itself.
const { mockGlobe } = vi.hoisted(() => {
  const chainMethods = [
    "width",
    "height",
    "globeImageUrl",
    "bumpImageUrl",
    "backgroundImageUrl",
    "showAtmosphere",
    "atmosphereColor",
    "atmosphereAltitude",
    "pointAltitude",
    "pointRadius",
    "pointColor",
    "pointLabel",
    "pointsData",
    "ringColor",
    "ringMaxRadius",
    "ringPropagationSpeed",
    "ringRepeatPeriod",
    "ringsData",
    "pointOfView",
  ] as const;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fn = vi.fn(() => fn) as any;
  fn._destructor = vi.fn();
  for (const method of chainMethods) {
    fn[method] = vi.fn(() => fn);
  }
  return { mockGlobe: fn };
});

vi.mock("globe.gl", () => ({
  default: vi.fn(() => mockGlobe),
}));

// ── helpers ───────────────────────────────────────────────────────────────────

function makePosition(n: number = 0) {
  return {
    satlatitude: 51.5 + n * 0.001,
    satlongitude: -0.1 + n * 0.001,
    sataltitude: 422.6,
    azimuth: 300.5,
    elevation: 25.3,
    ra: 87.6,
    dec: -10.2,
    timestamp: 1_700_000_000 + n,
    timestamp_ms: (1_700_000_000 + n) * 1000,
    eclipsed: false,
  };
}

// Fetched at far in the past so offset=0 immediately, avoiding future-date issues
const OLD_FETCHED_AT = new Date(Date.now() - 5000).toISOString();

function makePositionsResponse(
  overrides: Partial<IssPositionsResponse> = {},
): IssPositionsResponse {
  return {
    positions: Array.from({ length: 300 }, (_, i) => makePosition(i)),
    fetched_at: OLD_FETCHED_AT,
    cached: false,
    quota_exhausted: false,
    ...overrides,
  };
}

function makeTle(): IssTleResponse {
  return {
    tle_line0: "ISS (ZARYA)",
    tle_line1: "1 25544U 98067A",
    tle_line2: "2 25544  51.6435",
    fetched_at: new Date().toISOString(),
    cached: false,
    quota_exhausted: false,
  };
}

function makePasses(): IssPassesResponse {
  return {
    passes: [
      {
        startUTC: 1_700_001_000,
        maxUTC: 1_700_001_060,
        endUTC: 1_700_001_120,
        startAzCompass: "W",
        endAzCompass: "E",
        maxEl: 45.2,
        duration: 120,
      },
    ],
    fetched_at: new Date().toISOString(),
    cached: false,
    quota_exhausted: false,
  };
}

function makeQuota(overrides: Partial<IssQuotaResponse> = {}): IssQuotaResponse {
  const now = new Date();
  return {
    used: 10,
    cap: 900,
    window_start: now.toISOString(),
    resets_at: new Date(now.getTime() + 3_600_000).toISOString(),
    ...overrides,
  };
}

function mockAll(overrides: {
  positions?: Partial<IssPositionsResponse>;
  quota?: Partial<IssQuotaResponse>;
} = {}) {
  server.use(
    http.get("/api/v1/iss/positions", () =>
      HttpResponse.json(makePositionsResponse(overrides.positions)),
    ),
    http.get("/api/v1/iss/tle", () => HttpResponse.json(makeTle())),
    http.get("/api/v1/iss/passes/visual", () => HttpResponse.json(makePasses())),
    http.get("/api/v1/iss/passes/radio", () => HttpResponse.json(makePasses())),
    http.get("/api/v1/iss/quota", () => HttpResponse.json(makeQuota(overrides.quota))),
  );
}

// ── Globe tests (use real timers — P28) ────────────────────────────────────────
// These tests don't depend on setInterval firing, so real timers are fine.

describe("IssPage — globe / mount (real timers)", () => {
  afterEach(async () => {
    vi.clearAllMocks();
    await act(async () => { await i18n.changeLanguage("en"); });
  });

  it("renders the page heading and globe container", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    renderWithProviders(<IssPage />);
    expect(screen.getByRole("heading", { name: /ISS Tracker/i, level: 1 })).toBeInTheDocument();
    expect(screen.getByTestId("iss-globe")).toBeInTheDocument();
  });

  it("globe.gl _destructor is called on unmount", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    const { unmount } = renderWithProviders(<IssPage />);
    unmount();
    expect(mockGlobe._destructor).toHaveBeenCalled();
  });

  it("renders quota info when data arrives", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll({ quota: { used: 10, cap: 900 } });
    renderWithProviders(<IssPage />);
    await waitFor(() => {
      expect(screen.getByLabelText(/quota-info/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/10 \/ 900/i)).toBeInTheDocument();
  });

  it("shows quota warning when used >= 800", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll({ quota: { used: 850, cap: 900 } });
    renderWithProviders(<IssPage />);
    await waitFor(() => {
      expect(screen.getByText(/quota nearly exhausted/i)).toBeInTheDocument();
    });
  });

  it("shows quota exhausted alert when quota_exhausted=true", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll({ positions: { quota_exhausted: true } });
    renderWithProviders(<IssPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/quota exhausted/i)).toBeInTheDocument();
  });

  it("renders error banner when positions request fails", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    server.use(
      http.get("/api/v1/iss/positions", () =>
        HttpResponse.json(
          { detail: { error: { code: "N2YO_QUOTA_EXHAUSTED", message: "out" } } },
          { status: 429 },
        ),
      ),
      http.get("/api/v1/iss/tle", () => HttpResponse.json(makeTle())),
      http.get("/api/v1/iss/passes/visual", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/passes/radio", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/quota", () => HttpResponse.json(makeQuota())),
    );
    renderWithProviders(<IssPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/ISS data unavailable/i)).toBeInTheDocument();
  });
});

// ── Interpolation tests — probe the component through a helper ─────────────
// These tests verify the data panel, pass sections, and "Updating…" indicator.
// We use fake timers (toFake list from spec) and advance them after data loads.

describe("IssPage — position interpolation (fake timers)", () => {
  beforeEach(() => {
    vi.useFakeTimers({
      toFake: ["Date", "setTimeout", "setInterval", "clearInterval", "clearTimeout"],
    });
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.clearAllMocks();
    await i18n.changeLanguage("en");
  });

  // Helper: render, flush all pending timers (drains fetch + TanStack Query),
  // then advance 1 001 ms so the setInterval fires.
  async function renderAndAdvance(overrides: Parameters<typeof mockAll>[0] = {}) {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll(overrides);
    renderWithProviders(<IssPage />);
    // Drain fetch microtasks and any TanStack Query internal setTimeout(0) calls
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    // Fire the 1 000 ms setInterval callback
    act(() => {
      vi.advanceTimersByTime(1001);
    });
  }

  it("pushes the interpolated ISS position onto the globe as a point and ring, matching the data panel", async () => {
    await renderAndAdvance();
    expect(mockGlobe.pointsData).toHaveBeenCalled();
    expect(mockGlobe.ringsData).toHaveBeenCalled();
    const [marker] = mockGlobe.pointsData.mock.calls.at(-1)![0];

    // The globe marker must reflect exactly what the data panel displays.
    const latTile = screen.getByText(/^Latitude$/i).nextElementSibling;
    expect(latTile?.textContent).toContain(Math.abs(marker.lat).toFixed(4));

    expect(mockGlobe.pointOfView).toHaveBeenCalledWith(
      expect.objectContaining({ lat: marker.lat, lng: marker.lng }),
      expect.any(Number),
    );
  });

  it("renders data panel with position fields after interval fires", async () => {
    await renderAndAdvance();
    expect(screen.getByLabelText(/ISS data/i)).toBeInTheDocument();
    expect(screen.getByText(/Altitude/i)).toBeInTheDocument();
    expect(screen.getByText(/Latitude/i)).toBeInTheDocument();
    expect(screen.getByText(/In Shadow/i)).toBeInTheDocument();
  });

  it("renders TLE details section", async () => {
    await renderAndAdvance();
    expect(screen.getByText("TLE data")).toBeInTheDocument();
    expect(screen.getByText(/ISS \(ZARYA\)/)).toBeInTheDocument();
  });

  it("renders next visible pass heading and duration", async () => {
    await renderAndAdvance();
    expect(screen.getByRole("heading", { name: /Next Visible Pass/i })).toBeInTheDocument();
    // Both passes show duration — use getAllByText since both panels may render
    expect(screen.getAllByText(/120 s/).length).toBeGreaterThan(0);
  });

  it("shows eclipsed=true as 'Yes'", async () => {
    const positions = Array.from({ length: 300 }, (_, i) => ({
      ...makePosition(i),
      eclipsed: true,
    }));
    server.use(
      http.get("/api/v1/iss/positions", () =>
        HttpResponse.json(makePositionsResponse({ positions })),
      ),
      http.get("/api/v1/iss/tle", () => HttpResponse.json(makeTle())),
      http.get("/api/v1/iss/passes/visual", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/passes/radio", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/quota", () => HttpResponse.json(makeQuota())),
    );
    const IssPage = (await import("@/routes/IssPage")).default;
    renderWithProviders(<IssPage />);
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { vi.advanceTimersByTime(1001); });
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("shows 'Updating…' when offset >= 300 (batch expired)", async () => {
    // fetched_at far in the past → offset >> 300 when interval fires
    const farPast = new Date(0).toISOString(); // Unix epoch — always ancient
    server.use(
      http.get("/api/v1/iss/positions", () =>
        HttpResponse.json(makePositionsResponse({ fetched_at: farPast })),
      ),
      http.get("/api/v1/iss/tle", () => HttpResponse.json(makeTle())),
      http.get("/api/v1/iss/passes/visual", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/passes/radio", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/quota", () => HttpResponse.json(makeQuota())),
    );
    const IssPage = (await import("@/routes/IssPage")).default;
    renderWithProviders(<IssPage />);
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { vi.advanceTimersByTime(1001); });
    expect(screen.getByText(/Updating…/i)).toBeInTheDocument();
  });

  it("locale switching — German title appears after changing language to de", async () => {
    server.use(
      http.get("/api/v1/iss/positions", () => HttpResponse.json(makePositionsResponse())),
      http.get("/api/v1/iss/tle", () => HttpResponse.json(makeTle())),
      http.get("/api/v1/iss/passes/visual", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/passes/radio", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/iss/quota", () => HttpResponse.json(makeQuota())),
    );
    const IssPage = (await import("@/routes/IssPage")).default;
    renderWithProviders(<IssPage />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("ISS-Tracker");
  });
});

// ── "Tonight over {city}" / pass-alert tests (real timers) ─────────────────

function makeUser(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    first_name: "Alice",
    last_name: "Liddell",
    email: "alice@example.com",
    phone: null,
    email_verified: true,
    phone_verified: false,
    created_at: "2024-01-01T00:00:00Z",
    consent_notifications_at: "2024-01-01T00:00:00Z",
    is_pro: false,
    location_name: null,
    location_lat: null,
    location_lng: null,
    location_tz: null,
    ...overrides,
  };
}

describe("IssPage — my passes / pass alerts (real timers)", () => {
  afterEach(async () => {
    vi.clearAllMocks();
    await act(async () => { await i18n.changeLanguage("en"); });
  });

  it("prompts to set a location when the user has none saved", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(http.get("/api/v1/auth/me", () => HttpResponse.json(makeUser())));
    renderWithProviders(<IssPage />);

    expect(await screen.findByTestId("iss-set-location-prompt")).toBeInTheDocument();
    expect(screen.queryByTestId("iss-alert-subscribe")).not.toBeInTheDocument();
  });

  it("shows a no-upcoming-passes message when the location has no passes", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({ location_name: "Vancouver, CA", location_lat: 49.28, location_lng: -123.12 }),
        ),
      ),
      http.get("/api/v1/iss/passes", () =>
        HttpResponse.json({
          passes: [],
          fetched_at: new Date().toISOString(),
          cached: false,
          quota_exhausted: false,
        }),
      ),
    );
    renderWithProviders(<IssPage />);

    expect(await screen.findByTestId("iss-no-upcoming-passes")).toBeInTheDocument();
  });

  it("shows the LOCATION_REQUIRED prompt when the server reports no location", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({ location_name: "Vancouver, CA", location_lat: 49.28, location_lng: -123.12 }),
        ),
      ),
      http.get("/api/v1/iss/passes", () =>
        HttpResponse.json(
          { error: { code: "LOCATION_REQUIRED", message: "Set your sky location first" } },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<IssPage />);

    expect(await screen.findByTestId("iss-set-location-prompt")).toBeInTheDocument();
  });

  it("shows an error banner on a generic passes-fetch failure", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({ location_name: "Vancouver, CA", location_lat: 49.28, location_lng: -123.12 }),
        ),
      ),
      http.get("/api/v1/iss/passes", () =>
        HttpResponse.json({ error: { code: "SERVER_ERROR", message: "boom" } }, { status: 500 }),
      ),
    );
    renderWithProviders(<IssPage />);

    await screen.findByText(/Unable to load your upcoming passes/i);
  });

  it("shows passes and a Pro-required message for a non-Pro user", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({ location_name: "Vancouver, CA", location_lat: 49.28, location_lng: -123.12 }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
    );
    renderWithProviders(<IssPage />);

    expect(await screen.findByTestId("iss-pass-0")).toBeInTheDocument();
    expect(screen.getByTestId("iss-alert-pro-required")).toBeInTheDocument();
    expect(screen.queryByTestId("iss-alert-subscribe")).not.toBeInTheDocument();
  });

  it("Pro user with no subscription can subscribe, which then shows unsubscribe", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    let subscribed = false;
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({
            is_pro: true,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
          }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json(
          (subscribed
            ? [
                {
                  id: "sub-iss-1",
                  type: "iss_pass",
                  ll2_id: null,
                  agency_name: null,
                  notify_email: true,
                  notify_sms: false,
                  notify_push: true,
                  created_at: "2026-01-01T00:00:00Z",
                },
              ]
            : []) satisfies SubscriptionsResponse,
        ),
      ),
      http.post("/api/v1/subscriptions", () => {
        subscribed = true;
        return HttpResponse.json(
          {
            id: "sub-iss-1",
            type: "iss_pass",
            ll2_id: null,
            agency_name: null,
            notify_email: true,
            notify_sms: false,
            notify_push: true,
            created_at: "2026-01-01T00:00:00Z",
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<IssPage />);

    const subscribeButton = await screen.findByTestId("iss-alert-subscribe");
    await user.click(subscribeButton);

    await waitFor(() => {
      expect(screen.getByTestId("iss-alert-unsubscribe")).toBeInTheDocument();
    });
  });

  it("subscribed Pro user can unsubscribe", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    let subscribed = true;
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({
            is_pro: true,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
          }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/subscriptions", () =>
        HttpResponse.json(
          (subscribed
            ? [
                {
                  id: "sub-iss-1",
                  type: "iss_pass",
                  ll2_id: null,
                  agency_name: null,
                  notify_email: true,
                  notify_sms: false,
                  notify_push: true,
                  created_at: "2026-01-01T00:00:00Z",
                },
              ]
            : []) satisfies SubscriptionsResponse,
        ),
      ),
      http.delete("/api/v1/subscriptions/:id", () => {
        subscribed = false;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<IssPage />);

    const unsubscribeButton = await screen.findByTestId("iss-alert-unsubscribe");
    await user.click(unsubscribeButton);

    await waitFor(() => {
      expect(screen.getByTestId("iss-alert-subscribe")).toBeInTheDocument();
    });
  });

  it("shows a consent-required error when subscribing without consent", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({
            is_pro: true,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
          }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/subscriptions", () => HttpResponse.json([])),
      http.post("/api/v1/subscriptions", () =>
        HttpResponse.json(
          { error: { code: "CONSENT_REQUIRED", message: "consent first" } },
          { status: 403 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<IssPage />);

    await user.click(await screen.findByTestId("iss-alert-subscribe"));

    expect(await screen.findByTestId("iss-alert-error")).toHaveTextContent(
      /Enable notification consent/i,
    );
  });

  it("shows a Pro-required error when subscribing without Pro (server-side defense)", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({
            is_pro: true,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
          }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/subscriptions", () => HttpResponse.json([])),
      http.post("/api/v1/subscriptions", () =>
        HttpResponse.json({ error: { code: "PRO_REQUIRED", message: "pro only" } }, { status: 403 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<IssPage />);

    await user.click(await screen.findByTestId("iss-alert-subscribe"));

    expect(await screen.findByTestId("iss-alert-error")).toHaveTextContent(
      /ISS pass alerts are a Pro feature/i,
    );
  });

  it("silently no-ops when the subscription already exists (race)", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({
            is_pro: true,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
          }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/subscriptions", () => HttpResponse.json([])),
      http.post("/api/v1/subscriptions", () =>
        HttpResponse.json(
          { error: { code: "ALREADY_SUBSCRIBED", message: "already" } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<IssPage />);

    await user.click(await screen.findByTestId("iss-alert-subscribe"));

    await waitFor(() => {
      expect(screen.queryByTestId("iss-alert-error")).not.toBeInTheDocument();
    });
  });

  it("shows a generic error for other subscribe failures", async () => {
    const IssPage = (await import("@/routes/IssPage")).default;
    mockAll();
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json(
          makeUser({
            is_pro: true,
            location_name: "Vancouver, CA",
            location_lat: 49.28,
            location_lng: -123.12,
          }),
        ),
      ),
      http.get("/api/v1/iss/passes", () => HttpResponse.json(makePasses())),
      http.get("/api/v1/subscriptions", () => HttpResponse.json([])),
      http.post("/api/v1/subscriptions", () =>
        HttpResponse.json({ error: { code: "SERVER_ERROR", message: "boom" } }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<IssPage />);

    await user.click(await screen.findByTestId("iss-alert-subscribe"));

    expect(await screen.findByTestId("iss-alert-error")).toHaveTextContent(
      /Failed to update your pass alert subscription/i,
    );
  });
});

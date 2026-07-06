import {
  screen,
  waitFor,
  within,
  act,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import {
  describe,
  it,
  expect,
  vi,
  afterEach,
  beforeEach,
} from "vitest";
import { server } from "@/msw/server";
import { renderWithProviders } from "@/testUtils";
import type { LaunchData, LaunchesResponse } from "@/types/api";
import i18n from "@/i18n";

// ---------------------------------------------------------------------------
// Mock FullCalendar to avoid CSS/DOM issues in jsdom
// ---------------------------------------------------------------------------

vi.mock("@fullcalendar/react", () => ({
  default: vi.fn(({ events, eventClick }: {
    events?: Array<{ id: string; title: string; extendedProps: LaunchData }>;
    eventClick?: (info: { event: { id: string; extendedProps: LaunchData } }) => void;
  }) => (
    <div data-testid="fullcalendar">
      {events?.map((e) => (
        <div
          key={e.id}
          data-testid="calendar-event"
          onClick={() => eventClick?.({ event: e })}
          role="button"
          aria-label={e.title}
        >
          {e.title}
        </div>
      ))}
    </div>
  )),
}));

vi.mock("@fullcalendar/daygrid", () => ({ default: {} }));

// ---------------------------------------------------------------------------
// Lazy-import page after mocks are set up
// ---------------------------------------------------------------------------

// We import after mocks so that FullCalendar mock is active
import LaunchesPage from "@/routes/LaunchesPage";

// ---------------------------------------------------------------------------
// Test data helpers
// ---------------------------------------------------------------------------

function makeLaunch(overrides: Partial<LaunchData> = {}): LaunchData {
  return {
    ll2_id: "test-001",
    name: "Falcon 9 | Starlink",
    net: new Date(Date.now() + 2 * 3600 * 1000).toISOString(), // 2 hours from now
    status_abbrev: "Go",
    status_name: "Go for Launch",
    agency_name: "SpaceX",
    agency_type: "Commercial",
    rocket_name: "Falcon 9 Block 5",
    rocket_family: "Falcon",
    mission_name: "Starlink Mission",
    mission_description: "A batch of Starlink satellites for LEO constellation.",
    mission_type: "Communications",
    pad_name: "SLC-40",
    pad_location: "Cape Canaveral, FL, USA",
    image_url: null,
    livestream_urls: [],
    fetched_at: new Date().toISOString(),
    ...overrides,
  };
}

function makeResponse(
  launches: LaunchData[] = [makeLaunch()],
  overrides: Partial<LaunchesResponse> = {},
): LaunchesResponse {
  return {
    data: launches,
    last_synced_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(), // 4 min ago
    cached: true,
    ...overrides,
  };
}

const DEFAULT_LAUNCHES = [
  makeLaunch({
    ll2_id: "go-001",
    name: "Falcon 9 | Starlink",
    status_abbrev: "Go",
    status_name: "Go for Launch",
    agency_name: "SpaceX",
    rocket_name: "Falcon 9 Block 5",
  }),
  makeLaunch({
    ll2_id: "tbd-002",
    name: "Soyuz | Crew",
    status_abbrev: "TBD",
    status_name: "To Be Determined",
    agency_name: "Roscosmos",
    rocket_name: "Soyuz 2.1a",
  }),
];

function setupDefaultHandler() {
  server.use(
    http.get("/api/v1/launches/upcoming", () =>
      HttpResponse.json(makeResponse(DEFAULT_LAUNCHES)),
    ),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("LaunchesPage", () => {
  afterEach(async () => {
    vi.useRealTimers();
    localStorage.removeItem("space-adventures-launches-view");
    await act(async () => { await i18n.changeLanguage("en"); });
  });

  it("happy path grid view — renders launch cards with name, agency, countdown", async () => {
    setupDefaultHandler();
    renderWithProviders(<LaunchesPage />);

    // Two launch cards visible
    const cards = await screen.findAllByTestId("launch-card");
    expect(cards.length).toBe(2);

    expect(screen.getByText("Falcon 9 | Starlink")).toBeInTheDocument();
    expect(screen.getByText("Soyuz | Crew")).toBeInTheDocument();

    // Agency names
    expect(screen.getByText("SpaceX")).toBeInTheDocument();
    expect(screen.getByText("Roscosmos")).toBeInTheDocument();

    // Countdowns are present
    const countdowns = screen.getAllByTestId("launch-countdown");
    expect(countdowns.length).toBe(2);
    // Go launch has T− countdown
    expect(countdowns[0].textContent).toMatch(/T[−+]/);
    // TBD launch has NET: date
    expect(countdowns[1].textContent).toMatch(/NET:/);
  });

  it("loading state — shows skeleton/spinner", () => {
    server.use(
      http.get("/api/v1/launches/upcoming", async () => {
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json(makeResponse());
      }),
    );
    renderWithProviders(<LaunchesPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("error state — shows ErrorBanner", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(
          { error: { code: "LL2_UNAVAILABLE", message: "Cannot reach LL2" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<LaunchesPage />);
    const banner = await screen.findByRole("alert");
    expect(banner).toBeInTheDocument();
  });

  it("empty state — shows empty message when no launches", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([])),
      ),
    );
    renderWithProviders(<LaunchesPage />);
    expect(
      await screen.findByTestId("launches-empty"),
    ).toBeInTheDocument();
  });

  it("status filter — filter by Go hides TBD launches", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");

    // Click "Go" filter
    await user.click(screen.getByTestId("filter-status-go"));

    // Only Go launch visible
    const cards = screen.getAllByTestId("launch-card");
    expect(cards.length).toBe(1);
    expect(screen.getByText("Falcon 9 | Starlink")).toBeInTheDocument();
    expect(screen.queryByText("Soyuz | Crew")).not.toBeInTheDocument();
  });

  it("agency search — text filter hides non-matching launches", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");

    const agencyInput = screen.getByTestId("agency-search");
    await user.type(agencyInput, "SpaceX");

    const cards = screen.getAllByTestId("launch-card");
    expect(cards.length).toBe(1);
    expect(screen.getByText("Falcon 9 | Starlink")).toBeInTheDocument();
    expect(screen.queryByText("Soyuz | Crew")).not.toBeInTheDocument();
  });

  it("calendar view toggle — renders FullCalendar with correctly titled events", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    // Wait for data to load
    await screen.findAllByTestId("launch-card");

    // Switch to calendar view
    await user.click(screen.getByTestId("view-calendar"));

    expect(await screen.findByTestId("fullcalendar")).toBeInTheDocument();

    const events = screen.getAllByTestId("calendar-event");
    expect(events.length).toBe(2);

    // Title format: <agency_name>: <rocket_name>
    expect(events[0].textContent).toBe("SpaceX: Falcon 9 Block 5");
    expect(events[1].textContent).toBe("Roscosmos: Soyuz 2.1a");
  });

  it("calendar event click opens drawer with LaunchCard", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");
    await user.click(screen.getByTestId("view-calendar"));

    const events = await screen.findAllByTestId("calendar-event");
    await user.click(events[0]);

    // Drawer opens
    expect(await screen.findByTestId("launch-drawer")).toBeInTheDocument();
    // LaunchCard inside drawer shows launch name
    expect(screen.getAllByText("Falcon 9 | Starlink").length).toBeGreaterThan(0);
  });

  it("countdown timer — Go status shows T− countdown; TBD shows NET date", async () => {
    const fixedNow = new Date("2025-07-10T10:00:00.000Z").getTime();

    const goNet = new Date(fixedNow + 2 * 3600 * 1000).toISOString(); // 2h from now
    const tbdNet = new Date(fixedNow + 48 * 3600 * 1000).toISOString(); // 48h from now

    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(
          makeResponse([
            makeLaunch({ ll2_id: "go-1", status_abbrev: "Go", net: goNet }),
            makeLaunch({ ll2_id: "tbd-1", status_abbrev: "TBD", net: tbdNet }),
          ]),
        ),
      ),
    );

    renderWithProviders(<LaunchesPage />);

    // Wait for data to load with real timers first
    const countdowns = await screen.findAllByTestId("launch-countdown");

    // Now enable fake timers after the data has loaded
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "setInterval", "clearInterval"] });
    vi.setSystemTime(fixedNow);

    // Go: T−
    expect(countdowns[0].textContent).toMatch(/T[−+]/);
    // TBD: NET:
    expect(countdowns[1].textContent).toMatch(/NET:/);

    // Advance time by 1 second
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Countdown should still show T− style
    expect(screen.getAllByTestId("launch-countdown")[0].textContent).toMatch(/T[−+]/);
  });

  it("view persisted in localStorage — switching to calendar persists; re-render reads it", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");

    // Switch to calendar
    await user.click(screen.getByTestId("view-calendar"));
    expect(localStorage.getItem("space-adventures-launches-view")).toBe("calendar");

    // Re-render (new instance)
    unmount();
    setupDefaultHandler();
    renderWithProviders(<LaunchesPage />);

    // Should start in calendar view
    expect(await screen.findByTestId("fullcalendar")).toBeInTheDocument();
  });

  it("livestream button — hidden when no URLs; visible when URLs present", async () => {
    const withStream = makeLaunch({
      ll2_id: "stream-001",
      name: "With Stream",
      livestream_urls: [
        { title: "Main stream", url: "https://youtube.com/live/abc", feature_image: "" },
      ],
    });
    const noStream = makeLaunch({
      ll2_id: "nostream-002",
      name: "No Stream",
      livestream_urls: [],
    });

    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([withStream, noStream])),
      ),
    );

    renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");

    // One livestream button visible
    const buttons = screen.getAllByTestId("livestream-button");
    expect(buttons.length).toBe(1);
    expect(buttons[0]).toHaveAttribute("href", "https://youtube.com/live/abc");
  });

  it("last_synced_at — shows relative time string", async () => {
    const syncTime = new Date(Date.now() - 4 * 60 * 1000).toISOString(); // 4 min ago
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse(DEFAULT_LAUNCHES, { last_synced_at: syncTime })),
      ),
    );

    renderWithProviders(<LaunchesPage />);

    const syncEl = await screen.findByTestId("last-synced");
    expect(syncEl.textContent).toMatch(/Last updated/);
    // Should contain a relative time reference like "4 minutes ago" or similar
    expect(syncEl.textContent!.length).toBeGreaterThan(10);
  });

  it("all status filter shows all launches", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");

    // Filter by Go first
    await user.click(screen.getByTestId("filter-status-go"));
    expect(screen.getAllByTestId("launch-card").length).toBe(1);

    // Back to All
    await user.click(screen.getByTestId("filter-status-all"));
    expect(screen.getAllByTestId("launch-card").length).toBe(2);
  });

  it("drawer can be closed", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    await screen.findAllByTestId("launch-card");
    await user.click(screen.getByTestId("view-calendar"));

    const events = await screen.findAllByTestId("calendar-event");
    await user.click(events[0]);

    expect(await screen.findByTestId("launch-drawer")).toBeInTheDocument();

    // Close the drawer
    await user.click(screen.getByTestId("drawer-close"));
    await waitFor(() => {
      expect(screen.queryByTestId("launch-drawer")).not.toBeInTheDocument();
    });
  });

  it("launch card with image_url renders img", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([
          makeLaunch({ ll2_id: "img-001", name: "With Image", image_url: "https://example.com/rocket.jpg" }),
        ])),
      ),
    );
    renderWithProviders(<LaunchesPage />);
    const img = await screen.findByRole("img", { name: /With Image/i });
    expect(img).toHaveAttribute("src", "https://example.com/rocket.jpg");
  });

  it("launch card description expand/collapse toggle", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([
          makeLaunch({ ll2_id: "desc-001", name: "With Desc", mission_description: "Mission details here" }),
        ])),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    const toggle = await screen.findByTestId("description-toggle");
    expect(toggle).toHaveTextContent(/Show more/i);

    await user.click(toggle);
    expect(toggle).toHaveTextContent(/Show less/i);
  });

  it("launch card extra stream dropdown opens on click", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([
          makeLaunch({
            ll2_id: "multi-stream",
            name: "Multi Stream",
            livestream_urls: [
              { title: "Main", url: "https://yt.com/1", feature_image: "" },
              { title: "Alt", url: "https://yt.com/2", feature_image: "" },
            ],
          }),
        ])),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    const dropdownToggle = await screen.findByTestId("stream-dropdown-toggle");
    expect(screen.queryByTestId("stream-dropdown-menu")).not.toBeInTheDocument();

    await user.click(dropdownToggle);
    expect(screen.getByTestId("stream-dropdown-menu")).toBeInTheDocument();
  });

  it("bell button opens subscribe modal", async () => {
    setupDefaultHandler();
    const user = userEvent.setup();
    renderWithProviders(<LaunchesPage />);

    const bellBtns = await screen.findAllByTestId("bell-button");
    await user.click(bellBtns[0]);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("launch card shows agency type when present", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([
          makeLaunch({ ll2_id: "agency-001", agency_type: "Government" }),
        ])),
      ),
    );
    renderWithProviders(<LaunchesPage />);
    expect(await screen.findByText(/Government/i)).toBeInTheDocument();
  });

  it("launch card shows mission type badge", async () => {
    server.use(
      http.get("/api/v1/launches/upcoming", () =>
        HttpResponse.json(makeResponse([
          makeLaunch({ ll2_id: "mission-001", mission_type: "Science" }),
        ])),
      ),
    );
    renderWithProviders(<LaunchesPage />);
    expect(await screen.findByTestId("launch-mission-type")).toHaveTextContent("Science");
  });

  it("locale switching — German title appears after changing language to de", async () => {
    setupDefaultHandler();
    renderWithProviders(<LaunchesPage />);
    await screen.findAllByTestId("launch-card");

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Bevorstehende Starts");
  });
});

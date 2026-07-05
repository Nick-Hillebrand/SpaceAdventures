import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import SpaceWeatherPage from "@/routes/SpaceWeatherPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { SpaceWeatherResponse } from "@/types/api";

// ── helpers ───────────────────────────────────────────────────────────────────

function makeEvent(
  eventType: string,
  n: number = 1,
  date: string = "2020-01-05",
): object {
  switch (eventType) {
    case "FLR":
      return {
        flrID: `FLR-${date}-${n}`,
        beginTime: `${date}T06:00Z`,
        peakTime: `${date}T07:00Z`,
        classType: "M1.0",
      };
    case "GST":
      return {
        gstID: `GST-${date}-${n}`,
        startTime: `${date}T00:00Z`,
        allKpIndex: [{ kpIndex: 5 }],
      };
    case "CME":
      return { activityID: `CME-${date}-${n}`, startTime: `${date}T12:00Z` };
    case "SEP":
      return { sepID: `SEP-${date}-${n}`, eventTime: `${date}T08:00Z` };
    case "RBE":
      return { rbeID: `RBE-${date}-${n}`, eventTime: `${date}T10:00Z` };
    default:
      return { id: `UNKNOWN-${n}` };
  }
}

function makePayload(
  eventType: string,
  overrides: Partial<SpaceWeatherResponse> = {},
): SpaceWeatherResponse {
  return {
    data: [
      {
        id: `${eventType}:${eventType}-2020-01-05-1`,
        event_type: eventType as SpaceWeatherResponse["data"][0]["event_type"],
        start_date: "2020-01-05",
        raw_json: JSON.stringify(makeEvent(eventType)),
      },
    ],
    cached: false,
    stale: false,
    fetched_at: "2020-01-05T12:00:00Z",
    is_today: false,
    ...overrides,
  };
}

const ROUTES: Record<string, string> = {
  FLR: "/api/v1/space-weather/flares",
  GST: "/api/v1/space-weather/storms",
  CME: "/api/v1/space-weather/cmes",
  SEP: "/api/v1/space-weather/sep",
  RBE: "/api/v1/space-weather/rbe",
};

function mockAllTabs(eventType = "FLR") {
  for (const [type, route] of Object.entries(ROUTES)) {
    server.use(http.get(route, () => HttpResponse.json(makePayload(type === eventType ? eventType : "FLR"))));
  }
}

// ── tests ──────────────────────────────────────────────────────────────────

describe("SpaceWeatherPage", () => {
  it("renders the page heading and 5 tabs", async () => {
    mockAllTabs();
    renderWithProviders(<SpaceWeatherPage />);

    expect(screen.getByRole("heading", { name: /Space Weather/i, level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Solar Flares/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Geomagnetic Storms/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Coronal Mass Ejections/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Solar Energetic Particles/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Radiation Belt Enhancements/i })).toBeInTheDocument();
  });

  it("FLR tab active by default and shows event", async () => {
    server.use(http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))));
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }
    renderWithProviders(<SpaceWeatherPage />);

    const flrTab = screen.getByRole("tab", { name: /Solar Flares/i });
    expect(flrTab).toHaveAttribute("aria-selected", "true");

    // Event card appears
    expect(await screen.findByLabelText(/FLR event/i)).toBeInTheDocument();
  });

  it("switches to GST tab when clicked", async () => {
    server.use(
      http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))),
      http.get(ROUTES.GST, () => HttpResponse.json(makePayload("GST"))),
    );
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR" && type !== "GST") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }

    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await user.click(screen.getByRole("tab", { name: /Geomagnetic Storms/i }));
    expect(screen.getByRole("tab", { name: /Geomagnetic Storms/i })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByLabelText(/GST event/i)).toBeInTheDocument();
  });

  it("switches through all 5 event types", async () => {
    for (const route of Object.values(ROUTES)) {
      server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
    }
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    const tabLabels = [
      "Geomagnetic Storms",
      "Coronal Mass Ejections",
      "Solar Energetic Particles",
      "Radiation Belt Enhancements",
    ];
    for (const label of tabLabels) {
      await user.click(screen.getByRole("tab", { name: new RegExp(label, "i") }));
      expect(
        screen.getByRole("tab", { name: new RegExp(label, "i") }),
      ).toHaveAttribute("aria-selected", "true");
    }
  });

  it("renders loading state", () => {
    server.use(
      http.get(ROUTES.FLR, async () => {
        await new Promise((r) => setTimeout(r, 200));
        return HttpResponse.json(makePayload("FLR"));
      }),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/i);
  });

  it("renders error banner for NASA_AUTH_ERROR", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          { error: { code: "NASA_AUTH_ERROR", message: "Bad key" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Invalid NASA API Key/i)).toBeInTheDocument();
  });

  it("renders error banner for NO_INTERNET", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          { error: { code: "NO_INTERNET", message: "" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByText(/No internet connection/i)).toBeInTheDocument();
  });

  it("renders error with generic fallback for unknown code", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "oops" } },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it("renders empty state when no events returned", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(makePayload("FLR", { data: [] })),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByText(/No events found in this date range/i)).toBeInTheDocument();
  });

  it("shows cached badge", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(makePayload("FLR", { cached: true })),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByLabelText(/cached/i)).toBeInTheDocument();
    expect(screen.getByText(/Served from cache/i)).toBeInTheDocument();
  });

  it("shows stale warning text", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(makePayload("FLR", { cached: true, stale: true })),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByText(/Showing cached data from/i)).toBeInTheDocument();
  });

  it("shows live badge", async () => {
    server.use(http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))));
    renderWithProviders(<SpaceWeatherPage />);
    expect(await screen.findByLabelText(/live/i)).toBeInTheDocument();
    expect(screen.getByText(/^Live/i)).toBeInTheDocument();
  });

  it("event card renders time fields from raw_json", async () => {
    const raw = JSON.stringify({
      flrID: "FLR-TEST-1",
      beginTime: "2020-01-05T06:00Z",
      peakTime: "2020-01-05T07:00Z",
      classType: "X1.5",
    });
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          makePayload("FLR", {
            data: [
              {
                id: "FLR:FLR-TEST-1",
                event_type: "FLR",
                start_date: "2020-01-05",
                raw_json: raw,
              },
            ],
          }),
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    const card = await screen.findByLabelText(/FLR event/i);
    expect(within(card).getByText("beginTime")).toBeInTheDocument();
    expect(within(card).getByText("peakTime")).toBeInTheDocument();
    expect(within(card).getByText("classType")).toBeInTheDocument();
    expect(within(card).getByText("X1.5")).toBeInTheDocument();
  });

  it("event card handles malformed raw_json gracefully", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          makePayload("FLR", {
            data: [
              {
                id: "FLR:FLR-BROKEN",
                event_type: "FLR",
                start_date: "2020-01-05",
                raw_json: "NOT JSON",
              },
            ],
          }),
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    // Should render without crashing
    expect(await screen.findByLabelText(/FLR event/i)).toBeInTheDocument();
  });

  it("date range inputs update correctly", async () => {
    server.use(http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))));
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await screen.findByLabelText(/FLR event/i);

    const startInput = screen.getByLabelText(/^Start/i) as HTMLInputElement;
    await user.clear(startInput);
    await user.type(startInput, "2020-01-01");
    expect(startInput.value).toBe("2020-01-01");

    const endInput = screen.getByLabelText(/^End/i) as HTMLInputElement;
    await user.clear(endInput);
    await user.type(endInput, "2020-01-30");
    expect(endInput.value).toBe("2020-01-30");
  });

  it("CME tab shows event when navigated to", async () => {
    server.use(
      http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))),
      http.get(ROUTES.CME, () => HttpResponse.json(makePayload("CME"))),
    );
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR" && type !== "CME") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await user.click(screen.getByRole("tab", { name: /Coronal Mass Ejections/i }));
    expect(await screen.findByLabelText(/CME event/i)).toBeInTheDocument();
  });

  it("SEP tab shows event when navigated to", async () => {
    server.use(
      http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))),
      http.get(ROUTES.SEP, () => HttpResponse.json(makePayload("SEP"))),
    );
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR" && type !== "SEP") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await user.click(screen.getByRole("tab", { name: /Solar Energetic Particles/i }));
    expect(await screen.findByLabelText(/SEP event/i)).toBeInTheDocument();
  });

  it("RBE tab shows event when navigated to", async () => {
    server.use(
      http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))),
      http.get(ROUTES.RBE, () => HttpResponse.json(makePayload("RBE"))),
    );
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR" && type !== "RBE") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await user.click(screen.getByRole("tab", { name: /Radiation Belt Enhancements/i }));
    expect(await screen.findByLabelText(/RBE event/i)).toBeInTheDocument();
  });
});

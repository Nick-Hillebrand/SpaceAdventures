import { screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach } from "vitest";
import SpaceWeatherPage from "@/routes/SpaceWeatherPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { SpaceWeatherResponse } from "@/types/api";
import i18n from "@/i18n";

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

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

    // Flare row appears in the dashboard
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

  it("FLR dashboard shows class type in event row and peak stat", async () => {
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

    // Flare row contains the class type
    const row = await screen.findByLabelText(/FLR event FLR:FLR-TEST-1/i);
    expect(within(row).getByText("X1.5")).toBeInTheDocument();

    // Stats section
    expect(screen.getByTestId("flare-total")).toHaveTextContent("1");
    expect(screen.getByTestId("flare-peak")).toHaveTextContent("X1.5");
  });

  it("FLR dashboard shows source location when present", async () => {
    const raw = JSON.stringify({
      flrID: "FLR-SRC-1",
      peakTime: "2020-01-05T10:00Z",
      classType: "C2.5",
      sourceLocation: "N15W35",
    });
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          makePayload("FLR", {
            data: [
              {
                id: "FLR:FLR-SRC-1",
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
    expect(await screen.findByText("N15W35")).toBeInTheDocument();
  });

  it("FLR dashboard shows — for peak when classType is absent", async () => {
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          makePayload("FLR", {
            data: [
              {
                id: "FLR:FLR-NOCLASS",
                event_type: "FLR",
                start_date: "2020-01-05",
                raw_json: JSON.stringify({ flrID: "FLR-NOCLASS" }),
              },
            ],
          }),
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    await screen.findByLabelText(/FLR event/i);
    expect(screen.getByTestId("flare-peak")).toHaveTextContent("—");
  });

  it("FLR dashboard shows date when peakTime is absent", async () => {
    const raw = JSON.stringify({ flrID: "FLR-NOTIME", classType: "B1.0" });
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          makePayload("FLR", {
            data: [
              {
                id: "FLR:FLR-NOTIME",
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
    // Row renders without crashing; class badge shows
    const row = await screen.findByLabelText(/FLR event FLR:FLR-NOTIME/i);
    expect(within(row).getByText("B1.0")).toBeInTheDocument();
  });

  it("FLR dashboard handles malformed raw_json gracefully", async () => {
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
    expect(await screen.findByLabelText(/FLR event/i)).toBeInTheDocument();
    expect(screen.getByTestId("flare-peak")).toHaveTextContent("—");
  });

  it("GST event card renders time fields from raw_json", async () => {
    const raw = JSON.stringify({
      gstID: "GST-TEST-1",
      startTime: "2020-01-05T00:00Z",
      allKpIndex: [{ kpIndex: 5 }],
    });
    server.use(
      http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))),
      http.get(ROUTES.GST, () =>
        HttpResponse.json(
          makePayload("GST", {
            data: [
              {
                id: "GST:GST-TEST-1",
                event_type: "GST",
                start_date: "2020-01-05",
                raw_json: raw,
              },
            ],
          }),
        ),
      ),
    );
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR" && type !== "GST") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await user.click(screen.getByRole("tab", { name: /Geomagnetic Storms/i }));
    const card = await screen.findByLabelText(/GST event/i);
    expect(within(card).getByText("startTime")).toBeInTheDocument();
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

  it("FLR dashboard sorts by date when class scores tie", async () => {
    // Two events with the same classType on different dates → hits the date tie-breaker in sort
    server.use(
      http.get(ROUTES.FLR, () =>
        HttpResponse.json(
          makePayload("FLR", {
            data: [
              {
                id: "FLR:FLR-A",
                event_type: "FLR",
                start_date: "2020-01-03",
                raw_json: JSON.stringify({ classType: "C3.0", peakTime: "2020-01-03T08:00Z" }),
              },
              {
                id: "FLR:FLR-B",
                event_type: "FLR",
                start_date: "2020-01-05",
                raw_json: JSON.stringify({ classType: "C3.0", peakTime: "2020-01-05T10:00Z" }),
              },
            ],
          }),
        ),
      ),
    );
    renderWithProviders(<SpaceWeatherPage />);
    const rows = await screen.findAllByRole("listitem");
    // Most recent date first (2020-01-05 before 2020-01-03)
    expect(rows[0]).toHaveAttribute("aria-label", "FLR event FLR:FLR-B");
    expect(rows[1]).toHaveAttribute("aria-label", "FLR event FLR:FLR-A");
    expect(screen.getByTestId("flare-total")).toHaveTextContent("2");
  });

  it("CME event with speed shows speed in card highlight", async () => {
    const raw = JSON.stringify({
      activityID: "CME-SPEED-1",
      startTime: "2020-01-05T12:00Z",
      cmeAnalyses: [{ speed: 850, type: "C" }],
    });
    server.use(
      http.get(ROUTES.FLR, () => HttpResponse.json(makePayload("FLR"))),
      http.get(ROUTES.CME, () =>
        HttpResponse.json(
          makePayload("CME", {
            data: [
              {
                id: "CME:CME-SPEED-1",
                event_type: "CME",
                start_date: "2020-01-05",
                raw_json: raw,
              },
            ],
          }),
        ),
      ),
    );
    for (const [type, route] of Object.entries(ROUTES)) {
      if (type !== "FLR" && type !== "CME") {
        server.use(http.get(route, () => HttpResponse.json(makePayload("FLR"))));
      }
    }
    const user = userEvent.setup();
    renderWithProviders(<SpaceWeatherPage />);

    await user.click(screen.getByRole("tab", { name: /Coronal Mass Ejections/i }));
    expect(await screen.findByText(/850/)).toBeInTheDocument();
    expect(screen.getByText(/km\/s/i)).toBeInTheDocument();
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<SpaceWeatherPage />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Weltraumwetter");
  });
});

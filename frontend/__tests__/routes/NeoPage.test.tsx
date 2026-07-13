import { screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach } from "vitest";
import NeoPage from "@/routes/NeoPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { NeoFeedResponse } from "@/types/api";
import i18n from "@/i18n";

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

function makePayload(overrides: Partial<NeoFeedResponse> = {}): NeoFeedResponse {
  return {
    data: [
      {
        id: "A",
        name: "Asteroid Alpha",
        close_approach_date: "2020-01-01",
        absolute_magnitude_h: 22.5,
        estimated_diameter_min_km: 0.1,
        estimated_diameter_max_km: 0.3,
        is_potentially_hazardous: false,
        relative_velocity_kph: 25000,
        miss_distance_km: 5_000_000,
        orbiting_body: "Earth",
        nasa_jpl_url: "https://jpl.example/A",
      },
      {
        id: "B",
        name: "Bruiser Bravo",
        close_approach_date: "2020-01-02",
        absolute_magnitude_h: 18.1,
        estimated_diameter_min_km: 1.2,
        estimated_diameter_max_km: 2.4,
        is_potentially_hazardous: true,
        relative_velocity_kph: 45000,
        miss_distance_km: 800_000,
        orbiting_body: "Earth",
        nasa_jpl_url: null,
      },
    ],
    cached: false,
    stale: false,
    fetched_at: "2020-01-02T12:00:00Z",
    is_today: false,
    ...overrides,
  };
}

describe("NeoPage", () => {
  it("renders happy path with sortable table and hazardous highlighting", async () => {
    server.use(http.get("/api/v1/neo/feed", () => HttpResponse.json(makePayload())));

    renderWithProviders(<NeoPage />);

    expect(
      await screen.findByRole("heading", { name: /Near-Earth Objects/i, level: 1 }),
    ).toBeInTheDocument();

    // Two rows: A and B (B is hazardous)
    const alphaCell = await screen.findByRole("button", { name: /Asteroid Alpha/i });
    expect(alphaCell).toBeInTheDocument();
    const bravoRow = screen
      .getByRole("button", { name: /Bruiser Bravo/i })
      .closest("tr") as HTMLTableRowElement;
    expect(bravoRow).toHaveAttribute("data-hazardous", "true");

    // Hazardous badge visible
    expect(screen.getByLabelText(/Potentially Hazardous/i)).toBeInTheDocument();

    // Live badge visible
    expect(screen.getByLabelText(/live/i)).toBeInTheDocument();
  });

  it("sorts by column when header button clicked", async () => {
    server.use(http.get("/api/v1/neo/feed", () => HttpResponse.json(makePayload())));
    const user = userEvent.setup();
    renderWithProviders(<NeoPage />);

    // Wait for table
    await screen.findByRole("button", { name: /Asteroid Alpha/i });

    // Default sort is close_approach_date asc → Alpha first, Bravo second
    let rows = screen.getAllByRole("row");
    // rows[0] is header
    expect(within(rows[1]).getByRole("button", { name: /Asteroid Alpha/i })).toBeInTheDocument();

    // Click Name header — asc alphabetical
    await user.click(screen.getByRole("button", { name: /^Name/ }));
    rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByRole("button", { name: /Asteroid Alpha/i })).toBeInTheDocument();

    // Click Name again — desc
    await user.click(screen.getByRole("button", { name: /^Name/ }));
    rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByRole("button", { name: /Bruiser Bravo/i })).toBeInTheDocument();

    // Click Diameter — asc — Alpha (0.3) before Bravo (2.4)
    await user.click(screen.getByRole("button", { name: /^Diameter/ }));
    rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByRole("button", { name: /Asteroid Alpha/i })).toBeInTheDocument();

    // Click Velocity — asc
    await user.click(screen.getByRole("button", { name: /^Velocity/ }));
    rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByRole("button", { name: /Asteroid Alpha/i })).toBeInTheDocument();

    // Click Miss Distance — asc — Bravo (800k) < Alpha (5M)
    await user.click(screen.getByRole("button", { name: /^Miss Distance/ }));
    rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByRole("button", { name: /Bruiser Bravo/i })).toBeInTheDocument();
  });

  it("opens detail drawer when a row is clicked", async () => {
    server.use(http.get("/api/v1/neo/feed", () => HttpResponse.json(makePayload())));
    const user = userEvent.setup();
    renderWithProviders(<NeoPage />);

    const bravo = await screen.findByRole("button", { name: /Bruiser Bravo/i });
    await user.click(bravo);

    const drawer = await screen.findByRole("dialog", { name: /Bruiser Bravo/i });
    expect(within(drawer).getByText(/ID/i)).toBeInTheDocument();
    expect(within(drawer).getByText(/Absolute magnitude/i)).toBeInTheDocument();
    // Bravo has no nasa_jpl_url → drawer must not render a JPL link
    expect(within(drawer).queryByRole("link", { name: /View on JPL/i })).toBeNull();

    // Close drawer
    await user.click(within(drawer).getByRole("button", { name: /Close details/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("shows JPL link in drawer when nasa_jpl_url is set", async () => {
    server.use(http.get("/api/v1/neo/feed", () => HttpResponse.json(makePayload())));
    const user = userEvent.setup();
    renderWithProviders(<NeoPage />);

    const alpha = await screen.findByRole("button", { name: /Asteroid Alpha/i });
    await user.click(alpha);

    const drawer = await screen.findByRole("dialog", { name: /Asteroid Alpha/i });
    const link = within(drawer).getByRole("link", { name: /View on JPL/i });
    expect(link).toHaveAttribute("href", "https://jpl.example/A");
  });

  it("also opens drawer when clicking anywhere on the row", async () => {
    server.use(http.get("/api/v1/neo/feed", () => HttpResponse.json(makePayload())));
    const user = userEvent.setup();
    renderWithProviders(<NeoPage />);

    await screen.findByRole("button", { name: /Asteroid Alpha/i });
    const bravoRow = screen
      .getByRole("button", { name: /Bruiser Bravo/i })
      .closest("tr") as HTMLTableRowElement;

    // Click a non-button cell in the row
    const dateCell = bravoRow.querySelectorAll("td")[1] as HTMLElement;
    await user.click(dateCell);

    expect(await screen.findByRole("dialog", { name: /Bruiser Bravo/i })).toBeInTheDocument();
  });

  it("renders loading state", () => {
    server.use(
      http.get("/api/v1/neo/feed", async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json(makePayload());
      }),
    );
    renderWithProviders(<NeoPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/i);
  });

  it("renders error banner for NASA_AUTH_ERROR", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(
          { error: { code: "NASA_AUTH_ERROR", message: "Bad key" } },
          { status: 502 },
        ),
      ),
    );

    renderWithProviders(<NeoPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Invalid NASA API Key/i)).toBeInTheDocument();
  });

  it("renders error banner for NO_INTERNET", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(
          { error: { code: "NO_INTERNET", message: "" } },
          { status: 502 },
        ),
      ),
    );

    renderWithProviders(<NeoPage />);
    expect(await screen.findByText(/No internet connection/i)).toBeInTheDocument();
  });

  it("renders error banner for INVALID_RANGE", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(
          { detail: { error: { code: "INVALID_RANGE", message: "too long" } } },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(<NeoPage />);
    expect(await screen.findByText(/Invalid date range/i)).toBeInTheDocument();
  });

  it("renders error banner with generic fallback", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "boom" } },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<NeoPage />);
    expect(await screen.findByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it("renders empty state when no NEOs returned", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(makePayload({ data: [] })),
      ),
    );

    renderWithProviders(<NeoPage />);
    expect(
      await screen.findByText(/No near-earth objects found in this range/i),
    ).toBeInTheDocument();
  });

  it("shows cached badge when served from cache", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(makePayload({ cached: true })),
      ),
    );

    renderWithProviders(<NeoPage />);
    expect(await screen.findByLabelText(/Served from cache/i)).toBeInTheDocument();
    expect(screen.getByText(/Served from cache/i)).toBeInTheDocument();
  });

  it("shows stale banner text when data is stale", async () => {
    server.use(
      http.get("/api/v1/neo/feed", () =>
        HttpResponse.json(makePayload({ cached: true, stale: true })),
      ),
    );

    renderWithProviders(<NeoPage />);
    expect(await screen.findByText(/Showing cached data from/i)).toBeInTheDocument();
  });

  it("updates date range inputs when user changes them", async () => {
    server.use(http.get("/api/v1/neo/feed", () => HttpResponse.json(makePayload())));
    const user = userEvent.setup();
    renderWithProviders(<NeoPage />);

    await screen.findByRole("button", { name: /Asteroid Alpha/i });

    const startInput = screen.getByLabelText(/Start/i) as HTMLInputElement;
    const endInput = screen.getByLabelText(/End/i) as HTMLInputElement;

    await user.clear(startInput);
    await user.type(startInput, "2020-01-01");
    await user.clear(endInput);
    await user.type(endInput, "2020-01-05");

    expect(startInput.value).toBe("2020-01-01");
    expect(endInput.value).toBe("2020-01-05");
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<NeoPage />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Erdnahe Objekte");
  });
});

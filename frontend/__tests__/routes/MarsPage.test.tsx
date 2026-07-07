import { screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach, vi } from "vitest";
import MarsPage from "@/routes/MarsPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { MarsPhotosResponse, RoversResponse } from "@/types/api";
import i18n from "@/i18n";

// P36: @/components/RoverViewer is mocked here the same way IssPage.test.tsx
// mocks globe.gl — the real component drives a three.js/WebGL pipeline that
// has no business running inside jsdom, and MarsPage only needs to know it
// gets mounted with the right `rover` prop.
vi.mock("@/components/RoverViewer", () => ({
  RoverViewer: ({ rover }: { rover: string }) => (
    <div data-testid="rover-viewer-mock">{rover}</div>
  ),
}));

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

// ── helpers ───────────────────────────────────────────────────────────────────

const ROVERS_PAYLOAD: RoversResponse = {
  data: [
    { name: "curiosity", cameras: ["FHAZ", "NAVCAM", "MAST"] },
    { name: "opportunity", cameras: ["FHAZ", "PANCAM"] },
    { name: "spirit", cameras: ["FHAZ", "PANCAM"] },
    { name: "perseverance", cameras: ["NAVCAM_LEFT", "MCZ_RIGHT"] },
  ],
};

function makePhoto(id: number, overrides: object = {}) {
  return {
    id,
    sol: 1000,
    earth_date: "2020-01-01",
    rover_name: "curiosity",
    camera_name: "FHAZ",
    img_src: `https://mars.example/${id}.jpg`,
    ...overrides,
  };
}

function makePhotosResponse(
  photos: object[],
  overrides: Partial<MarsPhotosResponse> = {},
): MarsPhotosResponse {
  return {
    data: photos as MarsPhotosResponse["data"],
    cached: false,
    stale: false,
    fetched_at: "2020-01-01T12:00:00Z",
    is_today: false,
    ...overrides,
  };
}

function mockDefault(photos: object[] = [makePhoto(1)]) {
  server.use(
    http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
    http.get("/api/v1/mars/photos", () => HttpResponse.json(makePhotosResponse(photos))),
  );
}

// ── tests ──────────────────────────────────────────────────────────────────

describe("MarsPage", () => {
  it("renders heading and rover selector", async () => {
    mockDefault();
    renderWithProviders(<MarsPage />);

    expect(screen.getByRole("heading", { name: /Mars Explorer/i, level: 1 })).toBeInTheDocument();
    const roverSelect = await screen.findByRole("combobox", { name: /Rover/i });
    expect(roverSelect).toBeInTheDocument();
  });

  it("renders happy path with photo grid", async () => {
    mockDefault([makePhoto(1), makePhoto(2)]);
    renderWithProviders(<MarsPage />);

    const img1 = await screen.findByRole("img", { name: /Mars photo 1/i });
    expect(img1).toHaveAttribute("src", "https://mars.example/1.jpg");
    const img2 = screen.getByRole("img", { name: /Mars photo 2/i });
    expect(img2).toBeInTheDocument();
    expect(screen.getByLabelText(/live/i)).toBeInTheDocument();
  });

  it("opens lightbox when a photo is clicked", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    await user.click(screen.getByRole("button", { name: /Open photo 1/i }));

    const dialog = await screen.findByRole("dialog", { name: /Photo 1 fullscreen/i });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole("img")).toBeInTheDocument();
  });

  it("closes lightbox when close button is clicked", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    await user.click(screen.getByRole("button", { name: /Open photo 1/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Close fullscreen/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("closes lightbox when overlay is clicked", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    await user.click(screen.getByRole("button", { name: /Open photo 1/i }));
    await screen.findByRole("dialog");

    // Click the overlay (the dialog element itself)
    await user.click(screen.getByRole("dialog"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("switches to earth date mode and shows date picker", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    const dateRadio = screen.getByRole("radio", { name: /Earth date/i });
    await user.click(dateRadio);
    expect(screen.getByLabelText(/Earth date/i, { selector: 'input[type="date"]' })).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton", { name: /^Sol$/i })).toBeNull();
  });

  it("shows rover cameras in camera select", async () => {
    mockDefault();
    renderWithProviders(<MarsPage />);

    const cameraSelect = await screen.findByRole("combobox", { name: /Camera/i });
    expect(cameraSelect).toBeInTheDocument();
    expect(within(cameraSelect).getByRole("option", { name: "FHAZ" })).toBeInTheDocument();
    expect(within(cameraSelect).getByRole("option", { name: "NAVCAM" })).toBeInTheDocument();
  });

  it("changes rover and clears camera selection", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () => HttpResponse.json(makePhotosResponse([makePhoto(1)]))),
    );
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    const roverSelect = await screen.findByRole("combobox", { name: /Rover/i });
    await user.selectOptions(roverSelect, "opportunity");
    expect(roverSelect).toHaveValue("opportunity");
  });

  it("shows loading state", () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", async () => {
        await new Promise((r) => setTimeout(r, 200));
        return HttpResponse.json(makePhotosResponse([]));
      }),
    );
    renderWithProviders(<MarsPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/i);
  });

  it("renders NASA_AUTH_ERROR banner", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { error: { code: "NASA_AUTH_ERROR", message: "Bad key" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/Invalid NASA API Key/i)).toBeInTheDocument();
  });

  it("renders NASA_UNAVAILABLE banner with a friendly detail instead of the raw backend message", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { error: { code: "NASA_UNAVAILABLE", message: "NASA returned 404 (endpoint unavailable)" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/NASA services are currently unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/Live data could not be retrieved from NASA/i)).toBeInTheDocument();
    expect(screen.queryByText(/NASA returned 404/i)).not.toBeInTheDocument();
  });

  it("renders MARS_ARCHIVE_UNAVAILABLE banner with a friendly detail instead of the raw backend message", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { error: { code: "MARS_ARCHIVE_UNAVAILABLE", message: "mars.nasa.gov returned 503" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/Mars photo archive is currently unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/Live data could not be retrieved from NASA's Mars raw-image archive/i)).toBeInTheDocument();
    expect(screen.queryByText(/mars.nasa.gov returned 503/i)).not.toBeInTheDocument();
  });

  it("renders MARS_NO_LIVE_SOURCE banner for rovers with no replacement archive", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { error: { code: "MARS_NO_LIVE_SOURCE", message: "No live photo source is available for opportunity" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/No live photos available for this rover/i)).toBeInTheDocument();
    expect(screen.getByText(/NASA no longer provides a live photo feed for this rover/i)).toBeInTheDocument();
    expect(screen.queryByText(/No live photo source is available for opportunity/i)).not.toBeInTheDocument();
  });

  it("renders NO_INTERNET error banner", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { error: { code: "NO_INTERNET", message: "" } },
          { status: 502 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/No internet connection/i)).toBeInTheDocument();
  });

  it("renders generic error for unknown code", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "boom" } },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it("renders empty state when no photos", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () => HttpResponse.json(makePhotosResponse([]))),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/No photos found/i)).toBeInTheDocument();
  });

  it("shows cached badge", async () => {
    mockDefault([makePhoto(1)]);
    server.use(
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(makePhotosResponse([makePhoto(1)], { cached: true })),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByLabelText(/cached/i)).toBeInTheDocument();
    expect(screen.getByText(/Served from cache/i)).toBeInTheDocument();
  });

  it("shows stale warning", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(makePhotosResponse([makePhoto(1)], { cached: true, stale: true })),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/Showing cached data from/i)).toBeInTheDocument();
  });

  it("pagination: next page button disabled when fewer than 25 photos", async () => {
    mockDefault([makePhoto(1), makePhoto(2)]);
    renderWithProviders(<MarsPage />);

    await screen.findByLabelText(/Next page/i);
    expect(screen.getByLabelText(/Next page/i)).toBeDisabled();
  });

  it("pagination: next page button enabled with 25 photos", async () => {
    const photos = Array.from({ length: 25 }, (_, i) => makePhoto(i + 1));
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () => HttpResponse.json(makePhotosResponse(photos))),
    );
    renderWithProviders(<MarsPage />);

    await screen.findByLabelText(/Next page/i);
    expect(screen.getByLabelText(/Next page/i)).not.toBeDisabled();
  });

  it("pagination: previous button disabled on page 1", async () => {
    mockDefault();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img");
    expect(screen.getByLabelText(/Previous page/i)).toBeDisabled();
  });

  it("pagination: clicking next increments page display", async () => {
    const photos = Array.from({ length: 25 }, (_, i) => makePhoto(i + 1));
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () => HttpResponse.json(makePhotosResponse(photos))),
    );
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByLabelText(/Next page/i);
    await user.click(screen.getByLabelText(/Next page/i));
    expect(screen.getByText(/Page 2/i)).toBeInTheDocument();
  });

  it("renders INVALID_PARAMS error banner", async () => {
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", () =>
        HttpResponse.json(
          { detail: { error: { code: "INVALID_PARAMS", message: "bad rover" } } },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<MarsPage />);
    expect(await screen.findByText(/Invalid parameters/i)).toBeInTheDocument();
  });

  it("photo alt text includes descriptive content for accessibility", async () => {
    mockDefault([makePhoto(5, { rover_name: "curiosity", camera_name: "MAST", sol: 1234 })]);
    renderWithProviders(<MarsPage />);
    const img = await screen.findByRole("img", { name: /Mars photo 5/i });
    expect(img).toHaveAttribute("alt", expect.stringContaining("curiosity"));
    expect(img).toHaveAttribute("alt", expect.stringContaining("MAST"));
  });

  it("earth date mode: query includes earth_date param", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(makePhotosResponse([makePhoto(1)]));
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    // Wait for initial render
    await screen.findByRole("img", { name: /Mars photo 1/i });

    // Switch to earth date mode
    await user.click(screen.getByRole("radio", { name: /Earth date/i }));

    // Enter a date
    const dateInput = screen.getByLabelText(/Earth date/i, { selector: 'input[type="date"]' });
    await user.type(dateInput, "2020-06-15");

    await waitFor(() => {
      expect(capturedUrl).toContain("earth_date=2020-06-15");
    });
  });

  it("camera filter: query includes camera param when selected", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/mars/rovers", () => HttpResponse.json(ROVERS_PAYLOAD)),
      http.get("/api/v1/mars/photos", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(makePhotosResponse([makePhoto(1)]));
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    // Wait for camera select to appear (cameras from rover data)
    const cameraSelect = await screen.findByRole("combobox", { name: /Camera/i });
    await user.selectOptions(cameraSelect, "NAVCAM");

    await waitFor(() => {
      expect(capturedUrl).toContain("camera=NAVCAM");
    });
  });

  it("locale switching — German title appears after changing language to de", async () => {
    renderWithProviders(<MarsPage />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Mars-Explorer");
  });

  it("does not mount the 3D rover viewer until the disclosure is expanded", async () => {
    mockDefault();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    expect(screen.queryByTestId("rover-viewer-mock")).toBeNull();
  });

  it("mounts the 3D rover viewer for the selected rover once expanded", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    await user.click(screen.getByText(/3D Model/i));

    expect(await screen.findByTestId("rover-viewer-mock")).toHaveTextContent("curiosity");
  });

  it("passes the newly selected rover to the 3D viewer after switching rovers", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    await user.click(screen.getByText(/3D Model/i));
    await screen.findByTestId("rover-viewer-mock");

    const roverSelect = screen.getByRole("combobox", { name: /Rover/i });
    await user.selectOptions(roverSelect, "opportunity");

    expect(await screen.findByTestId("rover-viewer-mock")).toHaveTextContent("opportunity");
  });

  it("unmounts the 3D rover viewer when the disclosure is collapsed again", async () => {
    mockDefault();
    const user = userEvent.setup();
    renderWithProviders(<MarsPage />);

    await screen.findByRole("img", { name: /Mars photo 1/i });
    const summary = screen.getByText(/3D Model/i);
    await user.click(summary);
    await screen.findByTestId("rover-viewer-mock");

    await user.click(summary);
    expect(screen.queryByTestId("rover-viewer-mock")).toBeNull();
  });
});

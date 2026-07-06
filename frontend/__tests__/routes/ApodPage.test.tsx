import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach } from "vitest";
import ApodPage from "@/routes/ApodPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import i18n from "@/i18n";

afterEach(async () => {
  await act(async () => { await i18n.changeLanguage("en"); });
});

const apodPayload = {
  data: {
    date: "2020-01-01",
    title: "Great APOD",
    explanation: "Cool image.",
    url: "https://example.com/image.jpg",
    hdurl: "https://example.com/hd.jpg",
    media_type: "image",
    copyright: "NASA",
  },
  cached: false,
  stale: false,
  fetched_at: "2020-01-01T12:00:00Z",
  is_today: false,
};

describe("ApodPage", () => {
  it("renders happy path with image", async () => {
    server.use(
      http.get("/api/v1/apod", () => HttpResponse.json(apodPayload)),
    );

    renderWithProviders(<ApodPage />);

    expect(await screen.findByRole("heading", { name: /Great APOD/i })).toBeInTheDocument();
    const img = screen.getByRole("img", { name: /Great APOD/i }) as HTMLImageElement;
    expect(img.src).toContain("hd.jpg");
    expect(screen.getByText(/© NASA/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/live/i)).toBeInTheDocument();
  });

  it("renders loading state", () => {
    server.use(
      http.get("/api/v1/apod", async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json(apodPayload);
      }),
    );

    renderWithProviders(<ApodPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/i);
  });

  it("renders NASA auth error", async () => {
    server.use(
      http.get("/api/v1/apod", () =>
        HttpResponse.json(
          { error: { code: "NASA_AUTH_ERROR", message: "Bad key" } },
          { status: 502 },
        ),
      ),
    );

    renderWithProviders(<ApodPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Invalid NASA API Key/i)).toBeInTheDocument();
  });

  it("renders NO_INTERNET error", async () => {
    server.use(
      http.get("/api/v1/apod", () =>
        HttpResponse.json(
          { error: { code: "NO_INTERNET", message: "" } },
          { status: 502 },
        ),
      ),
    );

    renderWithProviders(<ApodPage />);
    expect(await screen.findByText(/No internet connection/i)).toBeInTheDocument();
  });

  it("renders video APOD as iframe", async () => {
    const videoPayload = {
      ...apodPayload,
      data: { ...apodPayload.data, media_type: "video", url: "https://youtube.com/embed/x" },
    };
    server.use(http.get("/api/v1/apod", () => HttpResponse.json(videoPayload)));

    renderWithProviders(<ApodPage />);
    await waitFor(() => {
      expect(screen.getByTitle("Great APOD")).toBeInTheDocument();
    });
  });

  it("renders empty state when no image URL", async () => {
    const empty = { ...apodPayload, data: { ...apodPayload.data, url: "", media_type: "image" } };
    server.use(http.get("/api/v1/apod", () => HttpResponse.json(empty)));

    renderWithProviders(<ApodPage />);
    expect(await screen.findByText(/No image available/i)).toBeInTheDocument();
  });

  it("shows cached badge when served from cache", async () => {
    server.use(
      http.get("/api/v1/apod", () =>
        HttpResponse.json({ ...apodPayload, cached: true }),
      ),
    );

    renderWithProviders(<ApodPage />);
    expect(await screen.findByLabelText(/cached/i)).toBeInTheDocument();
  });

  it("shows stale banner text when data is stale", async () => {
    server.use(
      http.get("/api/v1/apod", () =>
        HttpResponse.json({ ...apodPayload, cached: true, stale: true }),
      ),
    );

    renderWithProviders(<ApodPage />);
    expect(await screen.findByText(/Showing cached data from/i)).toBeInTheDocument();
  });

  it("renders empty state when query returns null", async () => {
    server.use(
      http.get("/api/v1/apod", () => HttpResponse.json(null)),
    );
    renderWithProviders(<ApodPage />);
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
  });

  it("useApod queryFn appends date param when date is set", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(apodPayload);
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ApodPage />);

    // Wait for initial render then change date
    await screen.findByRole("heading", { name: /Great APOD/i });

    const dateInput = screen.getByLabelText(/date/i);
    await user.type(dateInput, "2020-01-01");

    await waitFor(() => {
      expect(capturedUrl).toContain("date=2020-01-01");
    });
  });

  it("locale switching — German title appears after changing language to de", async () => {
    server.use(
      http.get("/api/v1/apod", () => HttpResponse.json(apodPayload)),
    );

    renderWithProviders(<ApodPage />);
    await screen.findByRole("heading", { level: 1 });

    await act(async () => { await i18n.changeLanguage("de"); });
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Astronomisches Bild des Tages");
  });
});

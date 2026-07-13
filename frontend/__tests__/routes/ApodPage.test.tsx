import { screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach } from "vitest";
import ApodPage, { offsetDate, todayUtc, isDirectVideoFile } from "@/routes/ApodPage";
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

  it("renders video APOD hosted as a direct NASA media file as a native <video>, not an iframe", async () => {
    // apod.nasa.gov sends X-Frame-Options: sameorigin on files like this, so
    // an <iframe> is blocked by the browser (verified against real Firefox).
    const videoPayload = {
      ...apodPayload,
      data: {
        ...apodPayload.data,
        media_type: "video",
        url: "https://apod.nasa.gov/apod/image/2607/Auroras_Esa.mp4",
      },
    };
    server.use(http.get("/api/v1/apod", () => HttpResponse.json(videoPayload)));

    renderWithProviders(<ApodPage />);
    const video = await screen.findByLabelText("Great APOD");
    expect(video.tagName).toBe("VIDEO");
    expect(screen.queryByTitle("Great APOD")).not.toBeInTheDocument();
  });

  it("renders loading state with translated status text", async () => {
    server.use(
      http.get("/api/v1/apod", async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json(apodPayload);
      }),
    );

    renderWithProviders(<ApodPage />);
    await act(async () => { await i18n.changeLanguage("de"); });
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Wird geladen…");
    expect(screen.getByRole("status")).toHaveTextContent("Wird geladen…");
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

  it("date picker is pre-filled with today's date", async () => {
    server.use(
      http.get("/api/v1/apod", () => HttpResponse.json(apodPayload)),
    );

    renderWithProviders(<ApodPage />);
    await screen.findByRole("heading", { name: /Great APOD/i });

    const dateInput = screen.getByLabelText(/date/i) as HTMLInputElement;
    expect(dateInput.value).toBe(todayUtc());
  });

  it("useApod queryFn appends date param when date is set", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(apodPayload);
      }),
    );

    renderWithProviders(<ApodPage />);

    // Wait for initial render then change date via fireEvent to replace (not append) the value
    await screen.findByRole("heading", { name: /Great APOD/i });

    const dateInput = screen.getByLabelText(/date/i);
    fireEvent.change(dateInput, { target: { value: "2020-01-01" } });

    await waitFor(() => {
      expect(capturedUrl).toContain("date=2020-01-01");
    });
  });

  it("prev arrow navigates to the previous day", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(apodPayload);
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ApodPage />);
    await screen.findByRole("heading", { name: /Great APOD/i });

    const today = todayUtc();
    const yesterday = offsetDate(today, -1);

    await user.click(screen.getByRole("button", { name: /previous day/i }));

    await waitFor(() => {
      expect(capturedUrl).toContain(`date=${yesterday}`);
    });
  });

  it("next arrow navigates to the next day from a past date", async () => {
    let capturedUrl = "";
    server.use(
      http.get("/api/v1/apod", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(apodPayload);
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ApodPage />);
    await screen.findByRole("heading", { name: /Great APOD/i });

    // Navigate to a known past date so the next button is enabled
    const dateInput = screen.getByLabelText(/date/i);
    fireEvent.change(dateInput, { target: { value: "2020-01-01" } });
    await screen.findByRole("heading", { name: /Great APOD/i });

    await user.click(screen.getByRole("button", { name: /next day/i }));

    await waitFor(() => {
      expect(capturedUrl).toContain("date=2020-01-02");
    });
  });

  it("next arrow is disabled when viewing today", async () => {
    server.use(
      http.get("/api/v1/apod", () => HttpResponse.json(apodPayload)),
    );

    renderWithProviders(<ApodPage />);
    await screen.findByRole("heading", { name: /Great APOD/i });

    const nextBtn = screen.getByRole("button", { name: /next day/i });
    expect(nextBtn).toBeDisabled();
  });

  it("next arrow is enabled when viewing a past date", async () => {
    server.use(
      http.get("/api/v1/apod", () => HttpResponse.json(apodPayload)),
    );

    renderWithProviders(<ApodPage />);
    await screen.findByRole("heading", { name: /Great APOD/i });

    const dateInput = screen.getByLabelText(/date/i);
    fireEvent.change(dateInput, { target: { value: "2020-01-01" } });
    await screen.findByRole("heading", { name: /Great APOD/i });

    const nextBtn = screen.getByRole("button", { name: /next day/i });
    expect(nextBtn).not.toBeDisabled();
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

describe("isDirectVideoFile helper", () => {
  it("detects a direct NASA-hosted mp4 file", () => {
    expect(isDirectVideoFile("https://apod.nasa.gov/apod/image/2607/Auroras_Esa.mp4")).toBe(true);
  });

  it("detects other direct video extensions", () => {
    expect(isDirectVideoFile("https://example.com/clip.webm")).toBe(true);
    expect(isDirectVideoFile("https://example.com/clip.mov")).toBe(true);
  });

  it("handles a query string after the extension", () => {
    expect(isDirectVideoFile("https://example.com/clip.mp4?token=abc")).toBe(true);
  });

  it("returns false for an embeddable third-party page like YouTube", () => {
    expect(isDirectVideoFile("https://youtube.com/embed/x")).toBe(false);
  });

  it("returns false for a plain image URL", () => {
    expect(isDirectVideoFile("https://example.com/image.jpg")).toBe(false);
  });
});

describe("offsetDate helper", () => {
  it("subtracts one day", () => {
    expect(offsetDate("2020-01-15", -1)).toBe("2020-01-14");
  });

  it("adds one day", () => {
    expect(offsetDate("2020-01-15", 1)).toBe("2020-01-16");
  });

  it("handles month boundary going back", () => {
    expect(offsetDate("2020-03-01", -1)).toBe("2020-02-29"); // 2020 is a leap year
  });

  it("handles month boundary going forward", () => {
    expect(offsetDate("2020-01-31", 1)).toBe("2020-02-01");
  });

  it("handles year boundary going back", () => {
    expect(offsetDate("2020-01-01", -1)).toBe("2019-12-31");
  });

  it("handles year boundary going forward", () => {
    expect(offsetDate("2019-12-31", 1)).toBe("2020-01-01");
  });
});

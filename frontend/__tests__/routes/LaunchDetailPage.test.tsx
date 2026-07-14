import { screen, act, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { describe, it, expect, afterEach } from "vitest";
import LaunchDetailPage from "@/routes/LaunchDetailPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { LaunchData } from "@/types/api";
import i18n from "@/i18n";

function makeLaunch(overrides: Partial<LaunchData> = {}): LaunchData {
  return {
    ll2_id: "l-1",
    name: "Falcon 9 | Starlink",
    net: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
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

// GET /api/v1/launches/:id — the single-launch endpoint LaunchDetailPage
// resolves through (via useLaunch), independent of the /upcoming window so
// past launches remain resolvable. A requested id that doesn't match the
// seeded launch mirrors the backend's 404-on-unknown-or-Gone-id behavior.
function setupLaunchHandler(launch: LaunchData | null = makeLaunch()) {
  server.use(
    http.get("/api/v1/launches/:id", ({ params }) => {
      if (!launch || params.id !== launch.ll2_id) {
        return HttpResponse.json({ detail: "Launch not found" }, { status: 404 });
      }
      return HttpResponse.json(launch);
    }),
  );
}

function setupHistoryHandler(
  history: Array<{ change_type: string; old_value: string | null; new_value: string | null; detected_at: string }> = [],
) {
  server.use(
    http.get("/api/v1/launches/:id/history", () => HttpResponse.json({ data: history })),
  );
}

function renderAtId(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/launches/:id" element={<LaunchDetailPage />} />
      <Route path="/:lang/launches/:id" element={<LaunchDetailPage />} />
    </Routes>,
    undefined,
    { initialEntries: [`/launches/${id}`] },
  );
}

function renderAtLangId(lang: string, id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/launches/:id" element={<LaunchDetailPage />} />
      <Route path="/:lang/launches/:id" element={<LaunchDetailPage />} />
    </Routes>,
    undefined,
    { initialEntries: [`/${lang}/launches/${id}`] },
  );
}

describe("LaunchDetailPage", () => {
  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("renders the matching launch card and back link", async () => {
    setupLaunchHandler(makeLaunch({ ll2_id: "l-1", name: "Falcon 9 | Starlink" }));
    setupHistoryHandler([]);

    renderAtId("l-1");

    expect(await screen.findByText("Falcon 9 | Starlink")).toBeInTheDocument();
    expect(screen.getByTestId("back-to-launches")).toHaveAttribute("href", "/launches");
  });

  it("shows a not-found state for an id the single-launch endpoint 404s on", async () => {
    setupLaunchHandler(makeLaunch({ ll2_id: "l-1" }));
    setupHistoryHandler([]);

    renderAtId("does-not-exist");

    expect(await screen.findByTestId("launch-detail-not-found")).toBeInTheDocument();
  });

  it("renders a past launch outside the /upcoming window via the single-launch endpoint", async () => {
    setupLaunchHandler(
      makeLaunch({
        ll2_id: "l-1",
        name: "Falcon 9 | Starlink",
        net: new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString(),
        status_abbrev: "Success",
        status_name: "Launch Successful",
      }),
    );
    setupHistoryHandler([]);

    renderAtId("l-1");

    expect(await screen.findByText("Falcon 9 | Starlink")).toBeInTheDocument();
    expect(screen.queryByTestId("launch-detail-not-found")).not.toBeInTheDocument();
  });

  it("syncs the client language to the URL's :lang segment", async () => {
    setupLaunchHandler(makeLaunch({ ll2_id: "l-1" }));
    setupHistoryHandler([]);

    renderAtLangId("de", "l-1");

    await screen.findByText("Falcon 9 | Starlink");
    await waitFor(() => expect(i18n.resolvedLanguage).toBe("de"));
  });

  it("shows the empty-history message when there are no recorded changes", async () => {
    setupLaunchHandler(makeLaunch({ ll2_id: "l-1" }));
    setupHistoryHandler([]);

    renderAtId("l-1");

    await screen.findByText("Falcon 9 | Starlink");
    expect(await screen.findByTestId("history-empty")).toBeInTheDocument();
  });

  it("renders history rows with old -> new values and localized type labels", async () => {
    setupLaunchHandler(makeLaunch({ ll2_id: "l-1" }));
    setupHistoryHandler([
      {
        change_type: "net",
        old_value: "2099-01-01T00:00:00+00:00",
        new_value: "2099-01-02T00:00:00+00:00",
        detected_at: "2099-01-01T00:05:00+00:00",
      },
      {
        change_type: "gone",
        old_value: null,
        new_value: "Gone",
        detected_at: "2099-01-03T00:00:00+00:00",
      },
    ]);

    renderAtId("l-1");

    const rows = await screen.findAllByTestId("history-row");
    expect(rows).toHaveLength(2);

    // NET slip row shows both old and new values.
    expect(rows[0]).toHaveTextContent("NET slip");
    expect(screen.getAllByTestId("history-old-value")[0]).toHaveTextContent("2099-01-01T00:00:00+00:00");
    expect(screen.getAllByTestId("history-new-value")[0]).toHaveTextContent("2099-01-02T00:00:00+00:00");

    // Gone row has no old value — only the "→" separator's new-value span.
    expect(screen.queryAllByTestId("history-old-value")).toHaveLength(1);

    // Gone row has no old value, only new.
    expect(rows[1]).toHaveTextContent("Removed from schedule");
  });

  it("falls back to the raw change_type when no translation key matches", async () => {
    setupLaunchHandler(makeLaunch({ ll2_id: "l-1" }));
    setupHistoryHandler([
      { change_type: "mystery", old_value: null, new_value: "x", detected_at: "2099-01-01T00:00:00+00:00" },
    ]);

    renderAtId("l-1");

    const rows = await screen.findAllByTestId("history-row");
    expect(rows[0]).toHaveTextContent("mystery");
  });
});

import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SolarSystemPage from "@/routes/SolarSystemPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";
import type { SolarSceneOptions } from "@/solar/scene";
import i18n from "@/i18n";

// The three.js scene needs WebGL, which jsdom lacks. The page mounts it
// through the @/solar/scene boundary, so mock that module and drive the
// callbacks it receives.
const { mockScene, createSolarScene } = vi.hoisted(() => {
  const mockScene = {
    setSpeed: vi.fn(),
    setScaleMode: vi.fn(),
    setDate: vi.fn(),
    select: vi.fn(),
    refreshLabels: vi.fn(),
    dispose: vi.fn(),
    mission: { load: vi.fn(), clear: vi.fn() },
    spacecraft: { setObjects: vi.fn(), setVisible: vi.fn() },
  };
  const createSolarScene = vi.fn(
    (_container: HTMLElement, _options: unknown) => mockScene,
  );
  return { mockScene, createSolarScene };
});

vi.mock("@/solar/scene", () => ({ createSolarScene }));

const MISSION_INDEX = {
  missions: [{ slug: "apollo-11", name_key: "missions.apollo11.name" }],
};
const APOLLO_SPEC = {
  slug: "apollo-11",
  name_key: "missions.apollo11.name",
  frame: "geocentric",
  t0: "2020-01-01T00:00:00Z",
  t1: "2020-01-02T00:00:00Z",
  trajectory: [
    { t: "2020-01-01T00:00:00Z", x: 0, y: 0, z: 0 },
    { t: "2020-01-02T00:00:00Z", x: 100, y: 0, z: 0 },
  ],
  milestones: [{ t: "2020-01-01T12:00:00Z", key: "missions.apollo11.tli" }],
  bodies: ["earth", "moon"],
};

function sceneOptions(): SolarSceneOptions {
  return createSolarScene.mock.calls.at(-1)![1] as SolarSceneOptions;
}

// Reset in beforeEach, not afterEach: testing-library's automatic cleanup
// (which unmounts and calls dispose) runs after our afterEach hooks would.
// useTrackedSpacecraftEphemerides fires one request per catalog entry on
// every mount, so every test needs a default handler even when it isn't
// exercising the spacecraft feature itself.
beforeEach(() => {
  vi.clearAllMocks();
  server.use(
    http.get("/api/v1/ephemerides/:slug", ({ params }) =>
      HttpResponse.json({ slug: params.slug, name_key: `spacecraft.${params.slug}`, points: [] }),
    ),
  );
});

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
});

describe("SolarSystemPage", () => {
  it("renders the title, canvas and controls, and mounts the scene once", () => {
    renderWithProviders(<SolarSystemPage />);

    expect(screen.getByRole("heading", { name: /Solar System Explorer/i })).toBeInTheDocument();
    expect(screen.getByTestId("solar-canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pause/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /True scale/i })).toBeInTheDocument();
    expect(createSolarScene).toHaveBeenCalledTimes(1);
  });

  it("shows planet facts and moon chips when the scene reports a selection", async () => {
    renderWithProviders(<SolarSystemPage />);

    act(() => sceneOptions().onSelect("earth"));

    const panel = await screen.findByRole("complementary", { name: /Body details/i });
    expect(within(panel).getByRole("heading", { name: "Earth" })).toBeInTheDocument();
    expect(within(panel).getByText(/Rocky planet/i)).toBeInTheDocument();
    expect(within(panel).getByText(/6,371 km/)).toBeInTheDocument();

    await userEvent.click(within(panel).getByRole("button", { name: "Moon" }));
    expect(mockScene.select).toHaveBeenCalledWith("moon");
  });

  it("shows moon facts with a link back to the parent planet", async () => {
    renderWithProviders(<SolarSystemPage />);

    act(() => sceneOptions().onSelect("titan"));

    const panel = await screen.findByRole("complementary", { name: /Body details/i });
    expect(within(panel).getByRole("heading", { name: "Titan" })).toBeInTheDocument();
    expect(within(panel).getByText(/Moon of Saturn/i)).toBeInTheDocument();

    await userEvent.click(within(panel).getByRole("button", { name: /Saturn/ }));
    expect(mockScene.select).toHaveBeenCalledWith("saturn");
  });

  it("closing the info panel deselects in the scene", async () => {
    renderWithProviders(<SolarSystemPage />);
    act(() => sceneOptions().onSelect("jupiter"));

    await userEvent.click(await screen.findByRole("button", { name: /Close/i }));
    expect(mockScene.select).toHaveBeenCalledWith(null);
  });

  it("shows Sun facts (star type, no orbit/moon-count rows) when the Sun is selected", async () => {
    renderWithProviders(<SolarSystemPage />);
    act(() => sceneOptions().onSelect("sun"));

    const panel = await screen.findByRole("complementary", { name: /Body details/i });
    expect(within(panel).getByRole("heading", { name: "Sun" })).toBeInTheDocument();
    expect(panel.querySelector(".solar-info__type")).toHaveTextContent("Star");
    expect(within(panel).queryByText(/Major moons/i)).not.toBeInTheDocument();
  });

  it("shows a planet with a period under a year in days, and retrograde rotation", async () => {
    renderWithProviders(<SolarSystemPage />);
    act(() => sceneOptions().onSelect("venus"));

    const panel = await screen.findByRole("complementary", { name: /Body details/i });
    expect(within(panel).getByText(/224.7 days/i)).toBeInTheDocument();
    expect(within(panel).getByText(/retrograde/i)).toBeInTheDocument();
  });

  it("shows a retrograde moon's orbit period with a retrograde suffix", async () => {
    renderWithProviders(<SolarSystemPage />);
    act(() => sceneOptions().onSelect("triton"));

    const panel = await screen.findByRole("complementary", { name: /Body details/i });
    const orbitDd = panel.querySelectorAll(".solar-facts dd")[2];
    expect(orbitDd).toHaveTextContent("5.9 days (retrograde)");
  });

  it("pause sets the scene speed to zero and play restores it", async () => {
    renderWithProviders(<SolarSystemPage />);

    await userEvent.click(screen.getByRole("button", { name: /Pause/i }));
    expect(mockScene.setSpeed).toHaveBeenLastCalledWith(0);

    await userEvent.click(screen.getByRole("button", { name: /Play/i }));
    const lastSpeed = mockScene.setSpeed.mock.calls.at(-1)![0] as number;
    expect(lastSpeed).toBeGreaterThan(0);
  });

  it("scale buttons switch the scene scale mode", async () => {
    renderWithProviders(<SolarSystemPage />);

    await userEvent.click(screen.getByRole("button", { name: /True scale/i }));
    expect(mockScene.setScaleMode).toHaveBeenCalledWith("true");

    await userEvent.click(screen.getByRole("button", { name: /Didactic scale/i }));
    expect(mockScene.setScaleMode).toHaveBeenCalledWith("visible");
  });

  it("the Now button resets the simulation date", async () => {
    renderWithProviders(<SolarSystemPage />);

    await userEvent.click(screen.getByRole("button", { name: /^Now$/i }));
    expect(mockScene.setDate).toHaveBeenCalledTimes(1);
    const passed = mockScene.setDate.mock.calls[0][0] as Date;
    expect(Math.abs(passed.getTime() - Date.now())).toBeLessThan(5_000);
  });

  it("refreshes scene labels when the language changes", async () => {
    renderWithProviders(<SolarSystemPage />);
    mockScene.refreshLabels.mockClear();

    await act(async () => {
      await i18n.changeLanguage("de");
    });
    expect(mockScene.refreshLabels).toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: /Sonnensystem-Explorer/i })).toBeInTheDocument();
  });

  it("disposes the scene on unmount", () => {
    const { unmount } = renderWithProviders(<SolarSystemPage />);
    unmount();
    expect(mockScene.dispose).toHaveBeenCalledTimes(1);
  });

  describe("missions panel", () => {
    beforeEach(() => {
      server.use(
        http.get("/missions/index.json", () => HttpResponse.json(MISSION_INDEX)),
        http.get("/missions/apollo-11.json", () => HttpResponse.json(APOLLO_SPEC)),
      );
    });

    it("opens the panel, loads a mission into the mounted scene, and shows a canonical link", async () => {
      renderWithProviders(<SolarSystemPage />);

      await userEvent.click(screen.getByRole("button", { name: /Missions/i }));
      const dock = await screen.findByRole("complementary", { name: /Missions/i });
      await userEvent.click(await within(dock).findByRole("button", { name: /Apollo 11/i }));

      await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalledWith(APOLLO_SPEC));
      expect(within(dock).getByRole("link", { name: /Open full page/i })).toHaveAttribute(
        "href",
        "/missions/apollo-11",
      );
    });

    it("locks the scale-mode and main transport controls while a mission is active", async () => {
      renderWithProviders(<SolarSystemPage />);

      await userEvent.click(screen.getByRole("button", { name: /Missions/i }));
      const dock = await screen.findByRole("complementary", { name: /Missions/i });
      await userEvent.click(await within(dock).findByRole("button", { name: /Apollo 11/i }));
      await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalled());

      const mainControls = within(
        document.querySelector(".solar-controls") as HTMLElement,
      );
      expect(mainControls.getByRole("button", { name: /True scale/i })).toBeDisabled();
      expect(mainControls.getByRole("button", { name: /Didactic scale/i })).toBeDisabled();
      expect(mainControls.getByRole("button", { name: /Pause/i })).toBeDisabled();
      expect(mainControls.getByRole("button", { name: /^Now$/i })).toBeDisabled();
    });

    it("exiting the mission clears the scene layer and restores the main controls", async () => {
      renderWithProviders(<SolarSystemPage />);

      await userEvent.click(screen.getByRole("button", { name: /Missions/i }));
      const dock = await screen.findByRole("complementary", { name: /Missions/i });
      await userEvent.click(await within(dock).findByRole("button", { name: /Apollo 11/i }));
      await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalled());

      await userEvent.click(within(dock).getByRole("button", { name: /Exit mission/i }));
      expect(mockScene.mission.clear).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: /Pause/i })).not.toBeDisabled();
    });

    it("shows an error message when the mission index fails to load", async () => {
      server.use(http.get("/missions/index.json", () => new HttpResponse(null, { status: 500 })));
      renderWithProviders(<SolarSystemPage />);

      await userEvent.click(screen.getByRole("button", { name: /Missions/i }));
      const dock = await screen.findByRole("complementary", { name: /Missions/i });
      expect(await within(dock).findByText(/could not be loaded/i)).toBeInTheDocument();
    });

    it("shows an error message when a selected mission's spec fails to load", async () => {
      server.use(
        http.get("/missions/apollo-11.json", () => new HttpResponse(null, { status: 500 })),
      );
      renderWithProviders(<SolarSystemPage />);

      await userEvent.click(screen.getByRole("button", { name: /Missions/i }));
      const dock = await screen.findByRole("complementary", { name: /Missions/i });
      await userEvent.click(await within(dock).findByRole("button", { name: /Apollo 11/i }));

      expect(await within(dock).findByText(/could not be loaded/i)).toBeInTheDocument();
      expect(mockScene.mission.load).not.toHaveBeenCalled();
    });
  });

  describe("live spacecraft", () => {
    // The page's sim clock defaults to `new Date()` (real "now"), and
    // velocityAuPerDay/isWithinCoverage are only non-null/true inside the
    // fetched sample window — so the fixture window must bracket "now",
    // not a fixed past date, or the info card's dimmed/no-data branch fires
    // instead of the in-coverage facts this test wants to exercise.
    const now = Date.now();
    const JWST_RESPONSE = {
      slug: "jwst",
      name_key: "spacecraft.jwst",
      points: [
        { t: new Date(now - 86_400_000).toISOString(), x: 1, y: 0, z: 0 },
        { t: new Date(now + 86_400_000).toISOString(), x: 1.01, y: 0.01, z: 0 },
      ],
    };

    beforeEach(() => {
      server.use(http.get("/api/v1/ephemerides/jwst", () => HttpResponse.json(JWST_RESPONSE)));
    });

    it("toggling Spacecraft opens the dock, lists the catalog, and shows/hides the scene layer", async () => {
      renderWithProviders(<SolarSystemPage />);

      await userEvent.click(screen.getByRole("button", { name: "Spacecraft" }));
      await waitFor(() => expect(mockScene.spacecraft.setVisible).toHaveBeenLastCalledWith(true));

      const dock = await screen.findByRole("complementary", { name: "Spacecraft" });
      expect(
        await within(dock).findByRole("button", { name: "James Webb Space Telescope" }),
      ).toBeInTheDocument();
      expect(within(dock).getByRole("button", { name: "Voyager 1" })).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: "Spacecraft" }));
      expect(mockScene.spacecraft.setVisible).toHaveBeenLastCalledWith(false);
    });

    it("selecting a spacecraft from the dock forwards the slug to the scene", async () => {
      renderWithProviders(<SolarSystemPage />);
      await userEvent.click(screen.getByRole("button", { name: "Spacecraft" }));
      const dock = await screen.findByRole("complementary", { name: "Spacecraft" });

      await userEvent.click(await within(dock).findByRole("button", { name: "James Webb Space Telescope" }));
      expect(mockScene.select).toHaveBeenCalledWith("jwst");
    });

    it("shows distance/velocity facts for a selected spacecraft with cached data", async () => {
      renderWithProviders(<SolarSystemPage />);
      await waitFor(() => expect(mockScene.spacecraft.setObjects).toHaveBeenCalled());
      act(() => sceneOptions().onSelect("jwst"));

      const panel = await screen.findByRole("complementary", { name: /Body details/i });
      expect(within(panel).getByRole("heading", { name: "James Webb Space Telescope" })).toBeInTheDocument();
      expect(within(panel).getByText("Spacecraft")).toBeInTheDocument();
      expect(within(panel).getByText("Distance from Earth")).toBeInTheDocument();
      expect(within(panel).getByText("Velocity")).toBeInTheDocument();
    });

    it("shows a no-data message for a selected spacecraft with an empty cached series", async () => {
      server.use(
        http.get("/api/v1/ephemerides/voyager-1", () =>
          HttpResponse.json({ slug: "voyager-1", name_key: "spacecraft.voyager1", points: [] }),
        ),
      );
      renderWithProviders(<SolarSystemPage />);
      await waitFor(() => expect(mockScene.spacecraft.setObjects).toHaveBeenCalled());
      act(() => sceneOptions().onSelect("voyager-1"));

      const panel = await screen.findByRole("complementary", { name: /Body details/i });
      expect(within(panel).getByText("No tracking data for this date")).toBeInTheDocument();
    });

    it("re-passes the spacecraft layer with translated labels when the language changes", async () => {
      renderWithProviders(<SolarSystemPage />);
      await waitFor(() => expect(mockScene.spacecraft.setObjects).toHaveBeenCalled());
      mockScene.spacecraft.setObjects.mockClear();

      await act(async () => {
        await i18n.changeLanguage("de");
      });

      await waitFor(() => expect(mockScene.spacecraft.setObjects).toHaveBeenCalled());
      const [objects, noDataTooltip] = mockScene.spacecraft.setObjects.mock.calls.at(-1)!;
      const jwst = (objects as Array<{ id: string; label: string }>).find((o) => o.id === "jwst");
      expect(jwst?.label).toBe("James-Webb-Weltraumteleskop");
      expect(noDataTooltip).toBe("Keine Verfolgungsdaten für diesen Termin");
    });
  });
});

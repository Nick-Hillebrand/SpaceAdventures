import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MissionPage from "@/routes/MissionPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";

const { mockScene, createSolarScene } = vi.hoisted(() => {
  const mockScene = {
    setSpeed: vi.fn(),
    setScaleMode: vi.fn(),
    setDate: vi.fn(),
    select: vi.fn(),
    refreshLabels: vi.fn(),
    dispose: vi.fn(),
    mission: { load: vi.fn(), clear: vi.fn() },
  };
  const createSolarScene = vi.fn((_container: HTMLElement, _options: unknown) => mockScene);
  return { mockScene, createSolarScene };
});

vi.mock("@/solar/scene", () => ({ createSolarScene }));

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

beforeEach(() => {
  vi.clearAllMocks();
});

function renderAtSlug(slug: string, embed = false) {
  return renderWithProviders(
    <Routes>
      <Route path="/missions/:slug" element={<MissionPage embed={embed} />} />
    </Routes>,
    undefined,
    { initialEntries: [`/missions/${slug}`] },
  );
}

describe("MissionPage", () => {
  it("shows a loading state, then mounts the scene and loads the mission spec into it", async () => {
    server.use(
      http.get("/missions/apollo-11.json", () => HttpResponse.json(APOLLO_SPEC)),
    );

    renderAtSlug("apollo-11");

    expect(screen.getByText(/Loading missions/i)).toBeInTheDocument();
    expect(createSolarScene).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalledWith(APOLLO_SPEC));
    expect(await screen.findByRole("heading", { name: /Apollo 11/i, level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to missions/i })).toHaveAttribute(
      "href",
      "/missions",
    );
  });

  it("shows an error state when the mission spec fails to load", async () => {
    server.use(
      http.get("/missions/apollo-11.json", () => new HttpResponse(null, { status: 404 })),
    );

    renderAtSlug("apollo-11");

    expect(await screen.findByText(/This mission could not be loaded/i)).toBeInTheDocument();
  });

  it("clears the mission from the scene on unmount", async () => {
    server.use(
      http.get("/missions/apollo-11.json", () => HttpResponse.json(APOLLO_SPEC)),
    );

    const { unmount } = renderAtSlug("apollo-11");
    await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalled());

    unmount();
    expect(mockScene.mission.clear).toHaveBeenCalled();
    expect(mockScene.dispose).toHaveBeenCalled();
  });

  it("fetches and loads the mission matching the current :slug param", async () => {
    const PATHFINDER_SPEC = { ...APOLLO_SPEC, slug: "mars-pathfinder", name_key: "missions.marsPathfinder.name" };
    server.use(
      http.get("/missions/apollo-11.json", () => HttpResponse.json(APOLLO_SPEC)),
      http.get("/missions/mars-pathfinder.json", () => HttpResponse.json(PATHFINDER_SPEC)),
    );

    const { unmount } = renderAtSlug("apollo-11");
    await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalledWith(APOLLO_SPEC));
    unmount();

    vi.clearAllMocks();
    renderAtSlug("mars-pathfinder");
    await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalledWith(PATHFINDER_SPEC));
  });

  it("hides the page heading and back link, and renders an attribution link, in embed mode", async () => {
    server.use(
      http.get("/missions/apollo-11.json", () => HttpResponse.json(APOLLO_SPEC)),
    );

    renderAtSlug("apollo-11", true);

    await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /Back to missions/i })).not.toBeInTheDocument();

    const attribution = screen.getByRole("link", { name: /Space Adventures/i });
    expect(attribution).toHaveAttribute("href", "/missions/apollo-11");
    expect(attribution).toHaveAttribute("target", "_blank");
  });
});

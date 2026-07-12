import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/msw/server";
import App from "@/App";

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

afterEach(() => {
  window.history.pushState({}, "", "/");
});

describe("App", () => {
  it("renders the navbar brand link", () => {
    server.use(http.get("/api/v1/apod", () => HttpResponse.json(null)));
    render(<App />);
    expect(screen.getByRole("link", { name: /Space Adventures/i })).toBeInTheDocument();
  });

  it("hides the navbar on the chrome-less mission embed route", async () => {
    server.use(
      http.get("/missions/apollo-11.json", () =>
        HttpResponse.json({
          slug: "apollo-11",
          name_key: "missions.apollo11.name",
          frame: "geocentric",
          t0: "2020-01-01T00:00:00Z",
          t1: "2020-01-02T00:00:00Z",
          trajectory: [
            { t: "2020-01-01T00:00:00Z", x: 0, y: 0, z: 0 },
            { t: "2020-01-02T00:00:00Z", x: 100, y: 0, z: 0 },
          ],
          milestones: [],
          bodies: ["earth", "moon"],
        }),
      ),
    );
    window.history.pushState({}, "", "/missions/apollo-11/embed");

    render(<App />);

    await waitFor(() => expect(mockScene.mission.load).toHaveBeenCalled());
    expect(document.querySelector("nav")).not.toBeInTheDocument();
    expect(screen.getByTestId("solar-canvas")).toBeInTheDocument();
  });
});

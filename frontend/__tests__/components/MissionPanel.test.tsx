import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import MissionPanel from "@/components/MissionPanel";
import type { MissionSpec } from "@/solar/mission";
import type { SolarSceneHandle } from "@/solar/scene";
import i18n from "@/i18n";

function makeScene(): SolarSceneHandle {
  return {
    setSpeed: vi.fn(),
    setScaleMode: vi.fn(),
    setDate: vi.fn(),
    select: vi.fn(),
    refreshLabels: vi.fn(),
    dispose: vi.fn(),
    mission: { load: vi.fn(), clear: vi.fn() },
  };
}

function makeSpec(overrides: Partial<MissionSpec> = {}): MissionSpec {
  return {
    slug: "apollo-11",
    name_key: "missions.apollo11.name",
    frame: "geocentric",
    t0: "2020-01-01T00:00:00.000Z",
    t1: "2020-01-02T00:00:00.000Z",
    trajectory: [
      { t: "2020-01-01T00:00:00.000Z", x: 0, y: 0, z: 0 },
      { t: "2020-01-02T00:00:00.000Z", x: 100, y: 0, z: 0 },
    ],
    milestones: [
      { t: "2020-01-01T06:00:00.000Z", key: "missions.apollo11.launch" },
      { t: "2020-01-01T18:00:00.000Z", key: "missions.apollo11.tli" },
    ],
    bodies: ["earth", "moon"],
    ...overrides,
  };
}

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
});

describe("MissionPanel", () => {
  it("shows the mission picker when no mission is active", () => {
    render(
      <MissionPanel
        scene={null}
        simDate={new Date("2020-01-01T00:00:00Z")}
        missions={[{ slug: "apollo-11", name_key: "missions.apollo11.name" }]}
        activeSlug={null}
        spec={null}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: /Missions/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Apollo 11/i })).toBeInTheDocument();
  });

  it("selecting a mission from the picker calls onSelectMission with its slug", async () => {
    const onSelectMission = vi.fn();
    render(
      <MissionPanel
        scene={null}
        simDate={new Date()}
        missions={[{ slug: "apollo-11", name_key: "missions.apollo11.name" }]}
        activeSlug={null}
        spec={null}
        onSelectMission={onSelectMission}
        onClearMission={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Apollo 11/i }));
    expect(onSelectMission).toHaveBeenCalledWith("apollo-11");
  });

  it("shows the noMissions message when the catalogue is empty", () => {
    render(
      <MissionPanel
        scene={null}
        simDate={new Date()}
        missions={[]}
        activeSlug={null}
        spec={null}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
      />,
    );
    expect(screen.getByText(/No missions available yet/i)).toBeInTheDocument();
  });

  it("scrubber min/max/value map to the mission's time window and drive scene.setDate", async () => {
    const scene = makeScene();
    const spec = makeSpec();
    render(
      <MissionPanel
        scene={scene}
        simDate={new Date("2020-01-01T12:00:00Z")}
        missions={[]}
        activeSlug="apollo-11"
        spec={spec}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    const scrubber = screen.getByRole("slider", { name: /Mission timeline/i }) as HTMLInputElement;
    expect(Number(scrubber.min)).toBe(Date.parse(spec.t0));
    expect(Number(scrubber.max)).toBe(Date.parse(spec.t1));
    expect(Number(scrubber.value)).toBe(Date.parse("2020-01-01T12:00:00Z"));

    const midMs = Date.parse(spec.t0) + (Date.parse(spec.t1) - Date.parse(spec.t0)) / 4;
    Object.defineProperty(scrubber, "value", { writable: true, value: String(midMs) });
    scrubber.dispatchEvent(new Event("input", { bubbles: true }));
    // React range inputs respond to the "change" event via onChange in jsdom.
    await act(async () => {
      scrubber.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(scene.setDate).toHaveBeenCalledWith(new Date(midMs));
  });

  it("clamps the scrubber's displayed value to the mission window even if simDate is outside it", () => {
    const spec = makeSpec();
    render(
      <MissionPanel
        scene={makeScene()}
        simDate={new Date("2019-01-01T00:00:00Z")}
        missions={[]}
        activeSlug="apollo-11"
        spec={spec}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );
    const scrubber = screen.getByRole("slider", { name: /Mission timeline/i }) as HTMLInputElement;
    expect(Number(scrubber.value)).toBe(Date.parse(spec.t0));
  });

  it("clicking a milestone tick jumps the scene to that time and shows its localized description card", async () => {
    const scene = makeScene();
    const spec = makeSpec();
    render(
      <MissionPanel
        scene={scene}
        simDate={new Date(spec.t0)}
        missions={[]}
        activeSlug="apollo-11"
        spec={spec}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    expect(screen.queryByText(/Launch — the Saturn V lifts off/i)).not.toBeInTheDocument();

    const tick = screen.getByRole("button", { name: /Launch — the Saturn V lifts off/i });
    await userEvent.click(tick);

    expect(scene.setDate).toHaveBeenCalledWith(new Date(spec.milestones[0].t));
    expect(screen.getByText(/Launch — the Saturn V lifts off/i)).toBeInTheDocument();
  });

  it("switches the milestone card's language when the active locale changes", async () => {
    const spec = makeSpec();
    render(
      <MissionPanel
        scene={makeScene()}
        simDate={new Date(spec.t0)}
        missions={[]}
        activeSlug="apollo-11"
        spec={spec}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Launch — the Saturn V lifts off/i }));
    expect(screen.getByText(/Launch — the Saturn V lifts off/i)).toBeInTheDocument();

    await act(async () => {
      await i18n.changeLanguage("de");
    });

    expect(screen.queryByText(/Launch — the Saturn V lifts off/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Apollo 11" })).toBeInTheDocument();
  });

  it("resets transport/milestone state when a new mission spec is loaded", async () => {
    const scene = makeScene();
    const specA = makeSpec();
    const { rerender } = render(
      <MissionPanel
        scene={scene}
        simDate={new Date(specA.t0)}
        missions={[]}
        activeSlug="apollo-11"
        spec={specA}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Launch — the Saturn V lifts off/i }));
    expect(screen.getByText(/Launch — the Saturn V lifts off/i)).toBeInTheDocument();

    const specB = makeSpec({
      slug: "mars-pathfinder",
      name_key: "missions.marsPathfinder.name",
      milestones: [{ t: specA.t0, key: "missions.marsPathfinder.landing" }],
    });
    rerender(
      <MissionPanel
        scene={scene}
        simDate={new Date(specB.t0)}
        missions={[]}
        activeSlug="mars-pathfinder"
        spec={specB}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    expect(screen.queryByText(/Launch — the Saturn V lifts off/i)).not.toBeInTheDocument();
  });

  it("showPicker=false hides the picker list and the exit button", () => {
    render(
      <MissionPanel
        scene={makeScene()}
        simDate={new Date()}
        missions={[{ slug: "apollo-11", name_key: "missions.apollo11.name" }]}
        activeSlug="apollo-11"
        spec={makeSpec()}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    expect(screen.queryByRole("button", { name: /Exit mission/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Missions$/i })).not.toBeInTheDocument();
  });

  it("the exit button calls onClearMission", async () => {
    const onClearMission = vi.fn();
    render(
      <MissionPanel
        scene={makeScene()}
        simDate={new Date()}
        missions={[{ slug: "apollo-11", name_key: "missions.apollo11.name" }]}
        activeSlug="apollo-11"
        spec={makeSpec()}
        onSelectMission={vi.fn()}
        onClearMission={onClearMission}
        showPicker
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Exit mission/i }));
    expect(onClearMission).toHaveBeenCalledTimes(1);
  });

  it("does not render a canonical link when canonicalHref is not provided", () => {
    render(
      <MissionPanel
        scene={makeScene()}
        simDate={new Date()}
        missions={[]}
        activeSlug="apollo-11"
        spec={makeSpec()}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );
    expect(screen.queryByRole("link", { name: /Open full page/i })).not.toBeInTheDocument();
  });

  it("play/pause toggles the scene speed to zero and back to a positive multiplier", async () => {
    const scene = makeScene();
    render(
      <MissionPanel
        scene={scene}
        simDate={new Date()}
        missions={[]}
        activeSlug="apollo-11"
        spec={makeSpec()}
        onSelectMission={vi.fn()}
        onClearMission={vi.fn()}
        showPicker={false}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Pause/i }));
    expect(scene.setSpeed).toHaveBeenLastCalledWith(0);

    await userEvent.click(screen.getByRole("button", { name: /Play/i }));
    const lastSpeed = (scene.setSpeed as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0] as number;
    expect(lastSpeed).toBeGreaterThan(0);
  });
});

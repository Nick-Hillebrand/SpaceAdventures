import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SolarSystemPage from "@/routes/SolarSystemPage";
import { renderWithProviders } from "@/testUtils";
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
  };
  const createSolarScene = vi.fn(
    (_container: HTMLElement, _options: unknown) => mockScene,
  );
  return { mockScene, createSolarScene };
});

vi.mock("@/solar/scene", () => ({ createSolarScene }));

function sceneOptions(): SolarSceneOptions {
  return createSolarScene.mock.calls.at(-1)![1] as SolarSceneOptions;
}

// Reset in beforeEach, not afterEach: testing-library's automatic cleanup
// (which unmounts and calls dispose) runs after our afterEach hooks would.
beforeEach(() => {
  vi.clearAllMocks();
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
});

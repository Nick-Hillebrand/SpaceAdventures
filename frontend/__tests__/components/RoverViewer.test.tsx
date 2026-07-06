import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import "@/i18n";
import { RoverViewer } from "@/components/RoverViewer";

// P28/P36: hoisted mock state for @/lib/roverScene — RoverViewer must never
// touch the real three.js scene factory in a jsdom test environment.
const { state } = vi.hoisted(() => {
  const loadModel = vi.fn();
  const dispose = vi.fn();
  const createRoverScene = vi.fn(() => ({ loadModel, dispose }));
  return { state: { loadModel, dispose, createRoverScene } };
});

vi.mock("@/lib/roverScene", () => ({
  createRoverScene: state.createRoverScene,
}));

beforeEach(() => {
  state.loadModel.mockReset();
  state.dispose.mockReset();
  state.createRoverScene.mockClear();
  state.createRoverScene.mockImplementation(() => ({
    loadModel: state.loadModel,
    dispose: state.dispose,
  }));
});

describe("RoverViewer", () => {
  it("creates the scene once and loads the mapped model for the given rover", async () => {
    state.loadModel.mockResolvedValue(undefined);
    render(<RoverViewer rover="curiosity" />);

    expect(state.createRoverScene).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(state.loadModel).toHaveBeenCalledWith("/models/curiosity.glb"));
  });

  it("loads the shared MER model for both opportunity and spirit", async () => {
    state.loadModel.mockResolvedValue(undefined);
    render(<RoverViewer rover="opportunity" />);
    await waitFor(() => expect(state.loadModel).toHaveBeenCalledWith("/models/mer.glb"));
  });

  it("shows a loading status before the model resolves", () => {
    state.loadModel.mockReturnValue(new Promise(() => {}));
    render(<RoverViewer rover="curiosity" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading 3D model");
  });

  it("shows the NASA credit line once the model has loaded", async () => {
    state.loadModel.mockResolvedValue(undefined);
    render(<RoverViewer rover="perseverance" />);
    expect(await screen.findByText(/NASA\/JPL-Caltech/)).toBeInTheDocument();
  });

  it("shows an error state when loading rejects", async () => {
    state.loadModel.mockRejectedValue(new Error("boom"));
    render(<RoverViewer rover="spirit" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
  });

  it("shows an error state immediately for a rover with no mapped model, without loading", () => {
    render(<RoverViewer rover="not-a-real-rover" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(state.loadModel).not.toHaveBeenCalled();
  });

  it("re-loads the model when the rover prop changes, reusing the same scene", async () => {
    state.loadModel.mockResolvedValue(undefined);
    const { rerender } = render(<RoverViewer rover="curiosity" />);
    await waitFor(() => expect(state.loadModel).toHaveBeenCalledWith("/models/curiosity.glb"));

    rerender(<RoverViewer rover="perseverance" />);
    await waitFor(() => expect(state.loadModel).toHaveBeenCalledWith("/models/perseverance.glb"));

    expect(state.createRoverScene).toHaveBeenCalledTimes(1);
  });

  it("disposes the scene on unmount", async () => {
    state.loadModel.mockResolvedValue(undefined);
    const { unmount } = render(<RoverViewer rover="curiosity" />);
    await waitFor(() => expect(state.loadModel).toHaveBeenCalled());

    unmount();
    expect(state.dispose).toHaveBeenCalledTimes(1);
  });

  it("ignores a late model resolution after unmount", async () => {
    let resolveLoad: () => void = () => {};
    state.loadModel.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveLoad = resolve;
      }),
    );
    const { unmount } = render(<RoverViewer rover="curiosity" />);
    unmount();

    expect(() => resolveLoad()).not.toThrow();
    await Promise.resolve();
  });
});

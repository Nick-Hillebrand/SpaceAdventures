import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createVignette } from "@/solar/missionVignette";
import type { MissionVignette } from "@/solar/mission";

// P36: mock `three` / GLTFLoader / OrbitControls entirely in tests — jsdom
// has no WebGL context and a real THREE.WebGLRenderer would throw trying to
// create one. `src/solar/environments.ts` is *not* mocked — it's a real
// module exercised through this mocked `three`, so environment selection is
// tested end-to-end through createVignette.
const { state } = vi.hoisted(() => {
  const sceneInstance = { add: vi.fn(), remove: vi.fn(), background: undefined, traverse: vi.fn() };
  const cameraInstance = {
    position: { set: vi.fn() },
    aspect: 1,
    updateProjectionMatrix: vi.fn(),
    lookAt: vi.fn(),
  };
  const rendererDomElement = document.createElement("canvas");
  const rendererInstance = {
    domElement: rendererDomElement,
    setPixelRatio: vi.fn(),
    setSize: vi.fn(),
    render: vi.fn(),
    dispose: vi.fn(),
  };
  const controlsInstance = {
    enableDamping: false,
    dampingFactor: 0,
    minDistance: 0,
    maxDistance: 0,
    target: { set: vi.fn() },
    autoRotate: false,
    autoRotateSpeed: 0,
    update: vi.fn(),
    dispose: vi.fn(),
  };

  const textureLoaderInstance = {
    load: vi.fn((_url: string) => ({
      colorSpace: undefined,
      wrapS: undefined,
      wrapT: undefined,
      repeat: { set: vi.fn() },
    })),
  };

  const boxInstance = {
    setFromObject: vi.fn(() => boxInstance),
    getSize: vi.fn((t: { x: number; y: number; z: number }) => {
      t.x = 2;
      t.y = 2;
      t.z = 2;
      return t;
    }),
    getCenter: vi.fn((t: { x: number; y: number; z: number }) => {
      t.x = 0;
      t.y = 0;
      t.z = 0;
      return t;
    }),
  };

  type LoadImpl = (
    url: string,
    onLoad: (gltf: { scene: unknown }) => void,
    onProgress: undefined,
    onError: (err: unknown) => void,
  ) => void;
  let loadImpl: LoadImpl = () => {};

  const gltfLoaderInstance = {
    load: vi.fn((url: string, onLoad: never, onProgress: never, onError: never) =>
      loadImpl(url, onLoad, onProgress, onError),
    ),
  };

  return {
    state: {
      sceneInstance,
      cameraInstance,
      rendererInstance,
      rendererDomElement,
      controlsInstance,
      textureLoaderInstance,
      boxInstance,
      gltfLoaderInstance,
      setLoadImpl: (fn: LoadImpl) => {
        loadImpl = fn;
      },
    },
  };
});

vi.mock("three", () => ({
  Scene: vi.fn(() => state.sceneInstance),
  PerspectiveCamera: vi.fn(() => state.cameraInstance),
  WebGLRenderer: vi.fn(() => state.rendererInstance),
  AmbientLight: vi.fn(() => ({})),
  DirectionalLight: vi.fn(() => ({ position: { set: vi.fn() } })),
  TextureLoader: vi.fn(() => state.textureLoaderInstance),
  Mesh: vi.fn(() => ({ rotation: { x: 0 } })),
  CircleGeometry: vi.fn(() => ({})),
  SphereGeometry: vi.fn(() => ({})),
  MeshStandardMaterial: vi.fn(() => ({})),
  MeshBasicMaterial: vi.fn(() => ({})),
  Color: vi.fn((c: unknown) => ({ c })),
  BackSide: "back",
  SRGBColorSpace: "srgb",
  RepeatWrapping: "repeat",
  MathUtils: { degToRad: (deg: number) => (deg * Math.PI) / 180 },
  Box3: vi.fn(() => state.boxInstance),
  Vector3: vi.fn(() => ({ x: 0, y: 0, z: 0 })),
}));

vi.mock("three/examples/jsm/loaders/GLTFLoader.js", () => ({
  GLTFLoader: vi.fn(() => state.gltfLoaderInstance),
}));

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => ({
  OrbitControls: vi.fn(() => state.controlsInstance),
}));

// jsdom has no IntersectionObserver; capture the callback so tests can
// trigger it, same pattern as the FakeResizeObserver in scene.test.ts.
class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  cb: (entries: Array<{ isIntersecting: boolean }>) => void;
  observe = vi.fn();
  disconnect = vi.fn();
  constructor(cb: (entries: Array<{ isIntersecting: boolean }>) => void) {
    this.cb = cb;
    FakeIntersectionObserver.instances.push(this);
  }
}

function makeContainer(width = 400, height = 300): HTMLDivElement {
  const el = document.createElement("div");
  Object.defineProperty(el, "clientWidth", { value: width, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: height, configurable: true });
  document.body.appendChild(el);
  return el;
}

function makeFakeModel() {
  return {
    scale: { setScalar: vi.fn() },
    position: { set: vi.fn() },
    traverse: vi.fn(),
  };
}

function makeVignette(overrides: Partial<MissionVignette> = {}): MissionVignette {
  return {
    model: "/models/missions/apollo11-lm.glb",
    environment: "moon-surface",
    modelCredit: "missions.credit.nasa",
    cameraOrbit: { distanceM: 18, elevationDeg: 12 },
    narrationKey: "missions.apollo11.landing.narration",
    ...overrides,
  };
}

describe("missionVignette", () => {
  let activeHandles: ReturnType<typeof createVignette>[] = [];
  let rafCallbacks: FrameRequestCallback[] = [];
  function create(container: HTMLElement, spec: MissionVignette, getLabel = (k: string) => k) {
    const handle = createVignette(container, spec, getLabel);
    activeHandles.push(handle);
    return handle;
  }

  beforeEach(() => {
    rafCallbacks = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    state.setLoadImpl(() => {});
    activeHandles = [];
  });

  afterEach(() => {
    for (const handle of activeHandles) {
      try {
        handle.dispose();
      } catch {
        // already disposed in-test
      }
    }
    vi.restoreAllMocks();
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  it("sizes the renderer to the container and appends the canvas", () => {
    const container = makeContainer(400, 300);
    create(container, makeVignette());

    expect(state.rendererInstance.setSize).toHaveBeenCalledWith(400, 300);
    expect(container.contains(state.rendererDomElement)).toBe(true);
  });

  it("falls back to a default size when the container reports zero dimensions", () => {
    const container = makeContainer(0, 0);
    create(container, makeVignette());

    expect(state.rendererInstance.setSize).toHaveBeenCalledWith(480, 480);
  });

  it.each([
    ["moon-surface" as const, "/solar/2k_moon.jpg"],
    ["mars-surface" as const, "/solar/2k_mars.jpg"],
    ["space" as const, "/solar/2k_stars_milky_way.jpg"],
  ])("loads the %s environment's texture", (environment, texturePath) => {
    const container = makeContainer();
    create(container, makeVignette({ environment }));

    expect(state.textureLoaderInstance.load).toHaveBeenCalledWith(texturePath);
  });

  it("looks up and displays the credit line via getLabel", () => {
    const container = makeContainer();
    const getLabel = vi.fn((key: string) => `translated:${key}`);
    create(container, makeVignette({ modelCredit: "missions.credit.nasa" }), getLabel);

    expect(getLabel).toHaveBeenCalledWith("missions.credit.nasa");
    const creditEl = container.querySelector(".mission-vignette__credit");
    expect(creditEl?.textContent).toBe("translated:missions.credit.nasa");
  });

  it("play() loads the model from spec.model and adds it to the scene", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette({ model: "/models/missions/apollo11-lm.glb" }));
    const model = makeFakeModel();
    state.setLoadImpl((url, onLoad) => {
      expect(url).toBe("/models/missions/apollo11-lm.glb");
      onLoad({ scene: model });
    });

    await handle.play();

    expect(state.sceneInstance.add).toHaveBeenCalledWith(model);
    expect(model.scale.setScalar).toHaveBeenCalled();
    expect(window.requestAnimationFrame).toHaveBeenCalled();
  });

  it("the render loop updates controls and renders every frame", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: makeFakeModel() }));

    await handle.play();
    expect(rafCallbacks.length).toBeGreaterThan(0);
    const framesBefore = rafCallbacks.length;
    rafCallbacks[0](0);

    expect(state.controlsInstance.update).toHaveBeenCalled();
    expect(state.rendererInstance.render).toHaveBeenCalledWith(state.sceneInstance, state.cameraInstance);
    expect(rafCallbacks.length).toBeGreaterThan(framesBefore);
  });

  it("play() rejects with the loader's Error on load failure", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    const boom = new Error("boom");
    state.setLoadImpl((_url, _onLoad, _onProgress, onError) => onError(boom));

    await expect(handle.play()).rejects.toThrow("boom");
  });

  it("play() rejects with a generic Error when the loader reports a non-Error value", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    state.setLoadImpl((_url, _onLoad, _onProgress, onError) => onError("network down"));

    await expect(handle.play()).rejects.toThrow("Failed to load vignette model");
  });

  it("dispose tears down the render loop, controls, model, scene, canvas, and credit line", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    const model = makeFakeModel();
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: model }));
    await handle.play();

    handle.dispose();

    expect(window.cancelAnimationFrame).toHaveBeenCalled();
    expect(state.controlsInstance.dispose).toHaveBeenCalled();
    expect(model.traverse).toHaveBeenCalled();
    expect(state.sceneInstance.traverse).toHaveBeenCalled();
    expect(state.rendererInstance.dispose).toHaveBeenCalled();
    expect(container.contains(state.rendererDomElement)).toBe(false);
    expect(container.querySelector(".mission-vignette__credit")).toBeNull();
  });

  it("dispose does not throw when the model never finished loading", () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());

    expect(() => handle.dispose()).not.toThrow();
  });

  it("dispose does not throw when the canvas was already detached from the container", () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    container.removeChild(state.rendererDomElement);

    expect(() => handle.dispose()).not.toThrow();
  });

  it("observes the container for intersection and pauses the loop when it scrolls out of view", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: makeFakeModel() }));
    await handle.play();

    const observer = FakeIntersectionObserver.instances.at(-1)!;
    expect(observer.observe).toHaveBeenCalledWith(container);

    const framesBefore = rafCallbacks.length;
    observer.cb([{ isIntersecting: false }]);
    expect(window.cancelAnimationFrame).toHaveBeenCalled();

    observer.cb([{ isIntersecting: true }]);
    expect(rafCallbacks.length).toBeGreaterThan(framesBefore);
  });

  it("pauses the loop when the tab is hidden and resumes when it becomes visible again", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: makeFakeModel() }));
    await handle.play();

    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(window.cancelAnimationFrame).toHaveBeenCalled();

    const framesBefore = rafCallbacks.length;
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(rafCallbacks.length).toBeGreaterThan(framesBefore);
  });

  it("dispose disconnects the intersection observer and removes the visibilitychange listener", async () => {
    const container = makeContainer();
    const handle = create(container, makeVignette());
    const removeSpy = vi.spyOn(document, "removeEventListener");
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: makeFakeModel() }));
    await handle.play();

    const observer = FakeIntersectionObserver.instances.at(-1)!;
    handle.dispose();

    expect(observer.disconnect).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  });
});

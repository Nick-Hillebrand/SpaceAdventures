import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createRoverScene } from "@/lib/roverScene";

// P28/P36: vi.hoisted() for mock state referenced inside vi.mock() factories.
// `three` is mocked entirely — jsdom has no WebGL context and a real
// THREE.WebGLRenderer would throw trying to create one.
const { state } = vi.hoisted(() => {
  const sceneInstance = { add: vi.fn(), remove: vi.fn() };
  const cameraInstance = {
    position: { set: vi.fn() },
    aspect: 1,
    updateProjectionMatrix: vi.fn(),
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
    autoRotate: false,
    autoRotateSpeed: 0,
    target: { set: vi.fn() },
    update: vi.fn(),
    dispose: vi.fn(),
  };
  const directionalLightInstance = { position: { set: vi.fn() } };

  let boxSize = { x: 2, y: 1, z: 1 };
  let boxCenter = { x: 0.5, y: 0.2, z: 0.1 };

  const boxInstance = {
    setFromObject: vi.fn(() => boxInstance),
    getSize: vi.fn((target: { x: number; y: number; z: number }) => {
      target.x = boxSize.x;
      target.y = boxSize.y;
      target.z = boxSize.z;
      return target;
    }),
    getCenter: vi.fn((target: { x: number; y: number; z: number }) => {
      target.x = boxCenter.x;
      target.y = boxCenter.y;
      target.z = boxCenter.z;
      return target;
    }),
  };

  type LoadImpl = (
    url: string,
    onLoad: (gltf: { scene: unknown }) => void,
    onProgress: undefined,
    onError: (err: unknown) => void,
  ) => void;
  let loadImpl: LoadImpl = () => {};

  const loaderInstance = {
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
      directionalLightInstance,
      boxInstance,
      loaderInstance,
      setBoxSize: (s: { x: number; y: number; z: number }) => { boxSize = s; },
      setBoxCenter: (c: { x: number; y: number; z: number }) => { boxCenter = c; },
      setLoadImpl: (fn: LoadImpl) => { loadImpl = fn; },
    },
  };
});

vi.mock("three", () => ({
  Scene: vi.fn(() => state.sceneInstance),
  PerspectiveCamera: vi.fn(() => state.cameraInstance),
  WebGLRenderer: vi.fn(() => state.rendererInstance),
  HemisphereLight: vi.fn(() => ({})),
  DirectionalLight: vi.fn(() => state.directionalLightInstance),
  Box3: vi.fn(() => state.boxInstance),
  Vector3: vi.fn(() => ({ x: 0, y: 0, z: 0 })),
}));

vi.mock("three/examples/jsm/loaders/GLTFLoader.js", () => ({
  GLTFLoader: vi.fn(() => state.loaderInstance),
}));

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => ({
  OrbitControls: vi.fn(() => state.controlsInstance),
}));

function makeContainer(width: number, height: number): HTMLDivElement {
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

describe("roverScene", () => {
  // Each createRoverScene() adds a real `window` resize listener. Track every
  // instance and dispose it after each test so listeners never leak across tests.
  let activeScenes: ReturnType<typeof createRoverScene>[] = [];
  function create(container: HTMLElement) {
    const scene = createRoverScene(container);
    activeScenes.push(scene);
    return scene;
  }

  beforeEach(() => {
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    state.setBoxSize({ x: 2, y: 1, z: 1 });
    state.setBoxCenter({ x: 0.5, y: 0.2, z: 0.1 });
    state.setLoadImpl(() => {});
    activeScenes = [];
  });

  afterEach(() => {
    for (const scene of activeScenes) {
      try { scene.dispose(); } catch { /* already disposed in-test */ }
    }
    vi.restoreAllMocks();
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  it("sizes the renderer to the container and appends the canvas", () => {
    const container = makeContainer(400, 300);
    create(container);

    expect(state.rendererInstance.setSize).toHaveBeenCalledWith(400, 300);
    expect(container.contains(state.rendererDomElement)).toBe(true);
  });

  it("falls back to a default size when the container reports zero dimensions", () => {
    const container = makeContainer(0, 0);
    create(container);

    expect(state.rendererInstance.setSize).toHaveBeenCalledWith(320, 320);
  });

  it("loadModel centers the model via its bounding box and adds it to the scene", async () => {
    const container = makeContainer(400, 300);
    const scene = create(container);
    const model = makeFakeModel();
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: model }));

    await scene.loadModel("/models/curiosity.glb");

    expect(state.sceneInstance.add).toHaveBeenCalledWith(model);
    // maxDim = 2, TARGET_MODEL_SIZE = 2.2 -> scale = 1.1
    expect(model.scale.setScalar).toHaveBeenCalledWith(1.1);
    const [x, y, z] = model.position.set.mock.calls.at(-1)!;
    expect(x).toBeCloseTo(-0.55, 5);
    expect(y).toBeCloseTo(-0.22, 5);
    expect(z).toBeCloseTo(-0.11, 5);
    expect(state.controlsInstance.target.set).toHaveBeenCalledWith(0, 0, 0);
    expect(state.controlsInstance.update).toHaveBeenCalled();
  });

  it("loadModel rejects with the loader's Error", async () => {
    const container = makeContainer(400, 300);
    const scene = create(container);
    const boom = new Error("boom");
    state.setLoadImpl((_url, _onLoad, _onProgress, onError) => onError(boom));

    await expect(scene.loadModel("/models/bad.glb")).rejects.toThrow("boom");
  });

  it("loadModel rejects with a generic Error when the loader reports a non-Error value", async () => {
    const container = makeContainer(400, 300);
    const scene = create(container);
    state.setLoadImpl((_url, _onLoad, _onProgress, onError) => onError("network down"));

    await expect(scene.loadModel("/models/bad.glb")).rejects.toThrow("Failed to load rover model");
  });

  it("disposes the previous model's geometry/material when switching rovers", async () => {
    const container = makeContainer(400, 300);
    const scene = create(container);

    const geometry = { dispose: vi.fn() };
    const singleMaterial = { dispose: vi.fn() };
    const arrayMaterials = [{ dispose: vi.fn() }, { dispose: vi.fn() }];
    const meshChild = { geometry, material: singleMaterial };
    const multiMaterialChild = { geometry: undefined, material: arrayMaterials };
    const emptyChild = {};

    const model1 = makeFakeModel();
    model1.traverse = vi.fn((cb: (child: unknown) => void) => {
      cb(meshChild);
      cb(multiMaterialChild);
      cb(emptyChild);
    });
    const model2 = makeFakeModel();

    state.setLoadImpl((_url, onLoad) => onLoad({ scene: model1 }));
    await scene.loadModel("/models/curiosity.glb");

    state.setLoadImpl((_url, onLoad) => onLoad({ scene: model2 }));
    await scene.loadModel("/models/perseverance.glb");

    expect(state.sceneInstance.remove).toHaveBeenCalledWith(model1);
    expect(geometry.dispose).toHaveBeenCalled();
    expect(singleMaterial.dispose).toHaveBeenCalled();
    expect(arrayMaterials[0].dispose).toHaveBeenCalled();
    expect(arrayMaterials[1].dispose).toHaveBeenCalled();
  });

  it("updates camera aspect and renderer size on window resize", () => {
    const container = makeContainer(400, 300);
    create(container);

    Object.defineProperty(container, "clientWidth", { value: 800, configurable: true });
    Object.defineProperty(container, "clientHeight", { value: 600, configurable: true });
    window.dispatchEvent(new Event("resize"));

    expect(state.cameraInstance.aspect).toBeCloseTo(800 / 600, 5);
    expect(state.cameraInstance.updateProjectionMatrix).toHaveBeenCalled();
    expect(state.rendererInstance.setSize).toHaveBeenLastCalledWith(800, 600);
  });

  it("dispose tears down listeners, controls, renderer, the model, and the canvas", async () => {
    const container = makeContainer(400, 300);
    const scene = create(container);
    const model = makeFakeModel();
    state.setLoadImpl((_url, onLoad) => onLoad({ scene: model }));
    await scene.loadModel("/models/curiosity.glb");

    scene.dispose();

    expect(window.cancelAnimationFrame).toHaveBeenCalled();
    expect(state.controlsInstance.dispose).toHaveBeenCalled();
    expect(state.rendererInstance.dispose).toHaveBeenCalled();
    expect(model.traverse).toHaveBeenCalled();
    expect(container.contains(state.rendererDomElement)).toBe(false);

    const resizeCallsBefore = state.rendererInstance.setSize.mock.calls.length;
    window.dispatchEvent(new Event("resize"));
    expect(state.rendererInstance.setSize.mock.calls.length).toBe(resizeCallsBefore);
  });

  it("dispose does not throw when the canvas was already detached from the container", () => {
    const container = makeContainer(400, 300);
    const scene = create(container);
    container.removeChild(state.rendererDomElement);

    expect(() => scene.dispose()).not.toThrow();
  });
});

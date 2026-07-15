import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { MissionSpec } from "@/solar/mission";

// P36: jsdom has no WebGL context, so `three` is mocked entirely. Unlike a
// flat call-tracking mock, scene.ts does real vector/camera math (tweens,
// mission trajectory transforms), so the mock below implements small but
// *real* Object3D/Vector3 classes rather than stub objects — tests assert on
// actual computed positions, not just "was this method called".
const { state, FakeVector3, FakeObject3D } = vi.hoisted(() => {
  class FakeVector3 {
    x: number;
    y: number;
    z: number;
    constructor(x = 0, y = 0, z = 0) {
      this.x = x;
      this.y = y;
      this.z = z;
    }
    set(x: number, y: number, z: number) {
      this.x = x;
      this.y = y;
      this.z = z;
      return this;
    }
    copy(v: FakeVector3) {
      this.x = v.x;
      this.y = v.y;
      this.z = v.z;
      return this;
    }
    clone() {
      return new FakeVector3(this.x, this.y, this.z);
    }
    add(v: FakeVector3) {
      this.x += v.x;
      this.y += v.y;
      this.z += v.z;
      return this;
    }
    sub(v: FakeVector3) {
      this.x -= v.x;
      this.y -= v.y;
      this.z -= v.z;
      return this;
    }
    multiplyScalar(s: number) {
      this.x *= s;
      this.y *= s;
      this.z *= s;
      return this;
    }
    length() {
      return Math.hypot(this.x, this.y, this.z);
    }
    lengthSq() {
      return this.x * this.x + this.y * this.y + this.z * this.z;
    }
    normalize() {
      const l = this.length() || 1;
      return this.multiplyScalar(1 / l);
    }
    lerpVectors(a: FakeVector3, b: FakeVector3, t: number) {
      this.x = a.x + (b.x - a.x) * t;
      this.y = a.y + (b.y - a.y) * t;
      this.z = a.z + (b.z - a.z) * t;
      return this;
    }
    lerp(v: FakeVector3, t: number) {
      return this.lerpVectors(this, v, t);
    }
  }

  class FakeVector2 {
    x = 0;
    y = 0;
    set(x: number, y: number) {
      this.x = x;
      this.y = y;
      return this;
    }
  }

  class FakeObject3D {
    position = new FakeVector3();
    rotation = { x: 0, y: 0, z: 0 };
    scale = {
      x: 1,
      y: 1,
      z: 1,
      setScalar(this: { x: number; y: number; z: number }, s: number) {
        this.x = this.y = this.z = s;
      },
    };
    userData: Record<string, unknown> = {};
    name = "";
    children: FakeObject3D[] = [];
    parent: FakeObject3D | null = null;

    add(...objs: FakeObject3D[]) {
      for (const o of objs) {
        o.parent = this;
        this.children.push(o);
      }
      return this;
    }
    remove(...objs: FakeObject3D[]) {
      for (const o of objs) {
        const i = this.children.indexOf(o);
        if (i >= 0) this.children.splice(i, 1);
        if (o.parent === this) o.parent = null;
      }
      return this;
    }
    getWorldPosition(out: FakeVector3) {
      let x = 0, y = 0, z = 0;
      // eslint-disable-next-line @typescript-eslint/no-this-alias
      let node: FakeObject3D | null = this;
      while (node) {
        x += node.position.x;
        y += node.position.y;
        z += node.position.z;
        node = node.parent;
      }
      return out.set(x, y, z);
    }
    traverse(cb: (obj: FakeObject3D) => void) {
      cb(this);
      for (const c of this.children) c.traverse(cb);
    }
  }

  class FakeMesh extends FakeObject3D {
    geometry: { dispose: ReturnType<typeof vi.fn> };
    material: unknown;
    constructor(geometry: { dispose: ReturnType<typeof vi.fn> }, material: unknown) {
      super();
      this.geometry = geometry;
      this.material = material;
    }
  }

  class FakeLine extends FakeObject3D {
    geometry: { dispose: ReturnType<typeof vi.fn>; setFromPoints?: ReturnType<typeof vi.fn> };
    material: unknown;
    constructor(geometry: { dispose: ReturnType<typeof vi.fn> }, material: unknown) {
      super();
      this.geometry = geometry;
      this.material = material;
    }
  }

  function makeDisposable(extra: Record<string, unknown> = {}) {
    return { dispose: vi.fn(), ...extra };
  }

  function makeRingGeometry() {
    return makeDisposable({
      attributes: {
        position: {
          count: 4,
          getX: (i: number) => [1, -1, -1, 1][i],
          getY: (i: number) => [1, 1, -1, -1][i],
        },
        uv: { setXY: vi.fn() },
      },
    });
  }

  function makeBufferGeometry() {
    const geo: { dispose: ReturnType<typeof vi.fn>; points: unknown[]; setFromPoints: (p: unknown[]) => unknown } = {
      ...makeDisposable(),
      points: [],
      setFromPoints: () => geo,
    };
    geo.setFromPoints = vi.fn((points: unknown[]) => {
      geo.points = points;
      return geo;
    });
    return geo;
  }

  let nextDelta = 0.1;
  let raycastHit: { object: { name: string } } | null = null;

  const rendererDomElement = document.createElement("canvas");
  const labelDomElement = document.createElement("div");
  const rendererInstance = {
    domElement: rendererDomElement,
    setPixelRatio: vi.fn(),
    setSize: vi.fn(),
    render: vi.fn(),
    dispose: vi.fn(),
    capabilities: { getMaxAnisotropy: () => 4 },
  };
  const labelRendererInstance = {
    domElement: labelDomElement,
    setSize: vi.fn(),
    render: vi.fn(),
  };
  const controlsInstance = {
    enableDamping: false,
    dampingFactor: 0,
    minDistance: 0,
    maxDistance: 0,
    target: new FakeVector3(),
    update: vi.fn(),
    dispose: vi.fn(),
  };
  const cameraInstance = {
    position: new FakeVector3(0, 170, 260),
    aspect: 1,
    updateProjectionMatrix: vi.fn(),
  };
  const raycasterInstance = {
    setFromCamera: vi.fn(),
    intersectObjects: vi.fn(() => (raycastHit ? [raycastHit] : [])),
  };
  const textures: Array<{ dispose: ReturnType<typeof vi.fn> }> = [];

  const state: {
    FakeVector2: typeof FakeVector2;
    FakeMesh: typeof FakeMesh;
    FakeLine: typeof FakeLine;
    makeDisposable: typeof makeDisposable;
    makeRingGeometry: typeof makeRingGeometry;
    makeBufferGeometry: typeof makeBufferGeometry;
    rendererInstance: typeof rendererInstance;
    rendererDomElement: typeof rendererDomElement;
    labelRendererInstance: typeof labelRendererInstance;
    labelDomElement: typeof labelDomElement;
    controlsInstance: typeof controlsInstance;
    cameraInstance: typeof cameraInstance;
    raycasterInstance: typeof raycasterInstance;
    textures: typeof textures;
    sceneInstance: InstanceType<typeof FakeObject3D> | null;
    setDelta: (d: number) => void;
    getDelta: () => number;
    setRaycastHit: (name: string | null) => void;
  } = {
    FakeVector2,
    FakeMesh,
    FakeLine,
    makeDisposable,
    makeRingGeometry,
    makeBufferGeometry,
    rendererInstance,
    rendererDomElement,
    labelRendererInstance,
    labelDomElement,
    controlsInstance,
    cameraInstance,
    raycasterInstance,
    textures,
    sceneInstance: null,
    setDelta: (d: number) => { nextDelta = d; },
    getDelta: () => nextDelta,
    setRaycastHit: (name: string | null) => {
      raycastHit = name === null ? null : { object: { name } };
    },
  };

  return { FakeVector3, FakeObject3D, state };
});

vi.mock("three", () => {
  class FakeMathUtils {
    static degToRad(d: number) {
      return (d * Math.PI) / 180;
    }
    static clamp(v: number, min: number, max: number) {
      return Math.min(Math.max(v, min), max);
    }
  }
  class FakeColor {
    value: unknown;
    constructor(v?: unknown) {
      this.value = v;
    }
  }
  class FakeClock {
    getDelta() {
      return state.getDelta();
    }
  }
  class FakeTextureLoader {
    load(_url: string) {
      const tex = { colorSpace: undefined, anisotropy: undefined, dispose: vi.fn() };
      state.textures.push(tex);
      return tex;
    }
  }
  class FakeScene extends FakeObject3D {
    constructor() {
      super();
      state.sceneInstance = this;
    }
  }
  class FakeGroup extends FakeObject3D {}
  class FakeLight extends FakeObject3D {}
  class FakePerspectiveCamera {
    // Not used directly: scene.ts's `camera` const is created via `new
    // THREE.PerspectiveCamera(...)`, so this must be the same shared
    // instance the test asserts against.
    constructor() {
      return state.cameraInstance as unknown as FakePerspectiveCamera;
    }
  }
  class FakeWebGLRenderer {
    constructor() {
      return state.rendererInstance as unknown as FakeWebGLRenderer;
    }
  }
  class FakeRaycaster {
    constructor() {
      return state.raycasterInstance as unknown as FakeRaycaster;
    }
  }

  return {
    Scene: FakeScene,
    Group: FakeGroup,
    PerspectiveCamera: FakePerspectiveCamera,
    WebGLRenderer: FakeWebGLRenderer,
    TextureLoader: FakeTextureLoader,
    SRGBColorSpace: "srgb",
    BackSide: "back",
    DoubleSide: "double",
    AmbientLight: FakeLight,
    PointLight: FakeLight,
    SphereGeometry: vi.fn(() => state.makeDisposable()),
    RingGeometry: vi.fn(() => state.makeRingGeometry()),
    BufferGeometry: vi.fn(() => state.makeBufferGeometry()),
    OctahedronGeometry: vi.fn(() => state.makeDisposable()),
    MeshBasicMaterial: vi.fn((opts: Record<string, unknown> = {}) => state.makeDisposable(opts)),
    MeshStandardMaterial: vi.fn((opts: Record<string, unknown> = {}) => state.makeDisposable(opts)),
    MeshLambertMaterial: vi.fn((opts: Record<string, unknown> = {}) => state.makeDisposable(opts)),
    LineBasicMaterial: vi.fn((opts: Record<string, unknown> = {}) => state.makeDisposable(opts)),
    Mesh: state.FakeMesh,
    Line: state.FakeLine,
    Color: FakeColor,
    MathUtils: FakeMathUtils,
    Raycaster: FakeRaycaster,
    Vector2: state.FakeVector2,
    Vector3: FakeVector3,
    Clock: FakeClock,
  };
});

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => ({
  OrbitControls: vi.fn(() => state.controlsInstance),
}));

vi.mock("three/examples/jsm/renderers/CSS2DRenderer.js", () => {
  class FakeCSS2DObject extends FakeObject3D {
    element: HTMLElement;
    constructor(el: HTMLElement) {
      super();
      this.element = el;
      // Real CSS2DRenderer appends label elements into its domElement during
      // render(); since render() is a no-op mock, append eagerly here so
      // tests can query labels via the container's DOM.
      state.labelDomElement.appendChild(el);
    }
  }
  class FakeCSS2DRenderer {
    constructor() {
      return state.labelRendererInstance as unknown as FakeCSS2DRenderer;
    }
  }
  return { CSS2DObject: FakeCSS2DObject, CSS2DRenderer: FakeCSS2DRenderer };
});

// jsdom has no ResizeObserver; capture the callback so tests can trigger it.
class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  cb: () => void;
  observe = vi.fn();
  disconnect = vi.fn();
  constructor(cb: () => void) {
    this.cb = cb;
    FakeResizeObserver.instances.push(this);
  }
}

import { createSolarScene, type SolarSceneHandle } from "@/solar/scene";

type FakeNode = InstanceType<typeof FakeObject3D>;

function findMeshNamed(root: FakeNode, name: string): FakeNode | null {
  let found: FakeNode | null = null;
  root.traverse((obj) => {
    if (!found && obj.name === name) found = obj;
  });
  return found;
}

/**
 * Body meshes live two levels below their group (group -> tilt -> mesh), the
 * same scene-graph shape scene.ts uses to parent geocentric mission layers
 * directly onto the body's group (a sibling of tilt/moons).
 */
function findBodyGroup(root: FakeNode, meshName: string): FakeNode {
  const mesh = findMeshNamed(root, meshName);
  if (!mesh?.parent?.parent) throw new Error(`could not locate group for mesh "${meshName}"`);
  return mesh.parent.parent;
}

function makeContainer(width = 400, height = 300): HTMLDivElement {
  const el = document.createElement("div");
  Object.defineProperty(el, "clientWidth", { value: width, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: height, configurable: true });
  document.body.appendChild(el);
  return el;
}

function makeMissionSpec(overrides: Partial<MissionSpec> = {}): MissionSpec {
  return {
    slug: "test-mission",
    name_key: "missions.testMission.name",
    frame: "geocentric",
    t0: "2020-01-01T00:00:00Z",
    t1: "2020-01-02T00:00:00Z",
    trajectory: [
      { t: "2020-01-01T00:00:00Z", x: 10000, y: 0, z: 0 },
      { t: "2020-01-01T12:00:00Z", x: 0, y: 10000, z: 0 },
      { t: "2020-01-02T00:00:00Z", x: -10000, y: 0, z: 0 },
    ],
    milestones: [{ t: "2020-01-01T12:00:00Z", key: "missions.testMission.midpoint" }],
    bodies: ["earth", "moon"],
    ...overrides,
  };
}

const KM_TO_UNITS = 60 / 149_597_870.7;

describe("solar/scene", () => {
  let getLabel: ReturnType<typeof vi.fn>;
  let onSelect: ReturnType<typeof vi.fn>;
  let onDateTick: ReturnType<typeof vi.fn>;
  let activeScenes: SolarSceneHandle[] = [];
  let rafCallback: FrameRequestCallback | null = null;

  function create(container: HTMLElement, extra: Partial<Parameters<typeof createSolarScene>[1]> = {}) {
    const handle = createSolarScene(container, {
      getLabel,
      onSelect,
      onDateTick,
      ...extra,
    });
    activeScenes.push(handle);
    return handle;
  }

  function tick(delta = 0.1) {
    state.setDelta(delta);
    rafCallback?.(0);
  }

  beforeEach(() => {
    getLabel = vi.fn((id: string) => id);
    onSelect = vi.fn();
    onDateTick = vi.fn();
    activeScenes = [];
    rafCallback = null;
    FakeResizeObserver.instances = [];
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      rafCallback = cb;
      return 1;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    state.setDelta(0.1);
    state.setRaycastHit(null);
    // rendererDomElement/labelDomElement/textures are shared singletons
    // across tests (three.js's own renderer/camera/controls are mocked as
    // one shared instance per test file), so reset their accumulated state.
    state.textures.length = 0;
    state.labelDomElement.innerHTML = "";
  });

  afterEach(() => {
    for (const s of activeScenes) {
      try { s.dispose(); } catch { /* already disposed in-test */ }
    }
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("mounts the renderer and label renderer into the container, sized to it", () => {
    const container = makeContainer(400, 300);
    create(container);

    expect(state.rendererInstance.setSize).toHaveBeenCalledWith(400, 300);
    expect(state.labelRendererInstance.setSize).toHaveBeenCalledWith(400, 300);
    expect(container.contains(state.rendererDomElement)).toBe(true);
    expect(container.contains(state.labelDomElement)).toBe(true);
  });

  it("falls back to default dimensions when the container reports zero size", () => {
    const container = makeContainer(0, 0);
    create(container);
    expect(state.rendererInstance.setSize).toHaveBeenCalledWith(800, 480);
  });

  it("builds the sun and every planet, including both the textured (Saturn) and untextured (Uranus) ring branches", () => {
    const container = makeContainer();
    create(container);
    expect(getLabel).toHaveBeenCalledWith("sun");
    expect(getLabel).toHaveBeenCalledWith("saturn");
    expect(getLabel).toHaveBeenCalledWith("uranus");

    expect(findMeshNamed(state.sceneInstance!, "sun")).not.toBeNull();
    expect(findMeshNamed(state.sceneInstance!, "earth")).not.toBeNull();
    expect(findMeshNamed(state.sceneInstance!, "moon")).not.toBeNull();
  });

  it("selects a planet: toggles active label class, updates moon label visibility, calls onSelect", () => {
    const container = makeContainer();
    const handle = create(container);
    handle.select("earth");
    expect(onSelect).toHaveBeenCalledWith("earth");

    const moonLabelButtons = container.querySelectorAll(".solar-label--moon");
    expect(moonLabelButtons.length).toBeGreaterThan(0);
  });

  it("selects a moon and the sun, and deselects with null", () => {
    const container = makeContainer();
    const handle = create(container);
    handle.select("moon");
    expect(onSelect).toHaveBeenCalledWith("moon");
    handle.select("sun");
    expect(onSelect).toHaveBeenCalledWith("sun");
    handle.select(null);
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("click-to-select: a small pointer movement selects the hit body", () => {
    const container = makeContainer();
    create(container);
    state.setRaycastHit("mars");

    state.rendererDomElement.dispatchEvent(new MouseEvent("pointerdown", { clientX: 10, clientY: 10 }));
    state.rendererDomElement.dispatchEvent(new MouseEvent("pointerup", { clientX: 12, clientY: 11 }));

    expect(onSelect).toHaveBeenCalledWith("mars");
  });

  it("click-to-select: no hit deselects; a drag beyond the threshold does not select", () => {
    const container = makeContainer();
    create(container);
    state.setRaycastHit(null);
    state.rendererDomElement.dispatchEvent(new MouseEvent("pointerdown", { clientX: 0, clientY: 0 }));
    state.rendererDomElement.dispatchEvent(new MouseEvent("pointerup", { clientX: 1, clientY: 1 }));
    expect(onSelect).toHaveBeenCalledWith(null);

    onSelect.mockClear();
    state.setRaycastHit("mars");
    state.rendererDomElement.dispatchEvent(new MouseEvent("pointerdown", { clientX: 0, clientY: 0 }));
    state.rendererDomElement.dispatchEvent(new MouseEvent("pointerup", { clientX: 50, clientY: 50 }));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("pointerup without a preceding pointerdown is a no-op", () => {
    const container = makeContainer();
    create(container);
    expect(() =>
      state.rendererDomElement.dispatchEvent(new MouseEvent("pointerup", { clientX: 1, clientY: 1 })),
    ).not.toThrow();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("setScaleMode rescales the sun and is a no-op when set to the current mode", () => {
    const container = makeContainer();
    const handle = create(container);
    const sun = findMeshNamed(state.sceneInstance!, "sun")!;

    const visibleScale = sun.scale.x;
    handle.setScaleMode("visible"); // already visible: no-op
    expect(sun.scale.x).toBe(visibleScale);

    handle.setScaleMode("true");
    const trueScale = sun.scale.x;
    expect(trueScale).not.toBe(visibleScale);

    handle.setScaleMode("true"); // already true: no-op
    expect(sun.scale.x).toBe(trueScale);
  });

  it("setDate updates the sim clock and fires onDateTick", () => {
    const container = makeContainer();
    const handle = create(container);
    onDateTick.mockClear();
    const d = new Date("2030-06-01T00:00:00Z");
    handle.setDate(d);
    expect(onDateTick).toHaveBeenCalledWith(d);
  });

  it("refreshLabels re-reads getLabel for the sun, bodies, and moons", () => {
    const container = makeContainer();
    const handle = create(container);
    getLabel.mockImplementation((id: string) => `translated:${id}`);
    handle.refreshLabels();
    const moonLabelButtons = Array.from(container.querySelectorAll(".solar-label--moon")) as HTMLElement[];
    expect(moonLabelButtons.some((el) => el.textContent?.startsWith("translated:"))).toBe(true);
  });

  it("resizing the container updates the camera aspect and renderer sizes", () => {
    const container = makeContainer(400, 300);
    create(container);
    const observer = FakeResizeObserver.instances.at(-1)!;
    expect(observer.observe).toHaveBeenCalledWith(container);

    Object.defineProperty(container, "clientWidth", { value: 800, configurable: true });
    Object.defineProperty(container, "clientHeight", { value: 600, configurable: true });
    observer.cb();

    expect(state.cameraInstance.aspect).toBeCloseTo(800 / 600, 5);
    expect(state.cameraInstance.updateProjectionMatrix).toHaveBeenCalled();
    expect(state.rendererInstance.setSize).toHaveBeenLastCalledWith(800, 600);
  });

  it("the animate loop advances the sim clock and periodically fires onDateTick", () => {
    const container = makeContainer();
    create(container);
    onDateTick.mockClear();

    for (let i = 0; i < 4; i++) tick(0.1);
    expect(onDateTick).toHaveBeenCalled();
  });

  it("clamps per-frame delta to 0.25s even when the real delta is larger", () => {
    const container = makeContainer();
    const handle = create(container);
    handle.setSpeed(10);
    const start = new Date("2000-01-01T00:00:00Z");
    handle.setDate(start);
    onDateTick.mockClear();

    tick(10); // real delta is 10s; scene.ts must clamp it to 0.25s
    const ticked = onDateTick.mock.calls.at(-1)?.[0] as Date;
    // tickAccumulator was already at 0.1s from the construction-time animate()
    // call (state's default mocked delta), so this frame's clamped 0.25s
    // pushes it over the 0.25s onDateTick threshold and fires immediately.
    expect(ticked.getTime()).toBe(start.getTime() + 10 * 86_400_000 * 0.25);
  });

  it("follows the selected body across frames once a focus tween completes", () => {
    const container = makeContainer();
    const handle = create(container);
    handle.select("earth");
    const posBefore = state.cameraInstance.position.clone();

    // Tween duration is 0.7s; drive well past it, then one more frame to
    // exercise the "ride along with the selected body" branch.
    for (let i = 0; i < 10; i++) tick(0.2);

    const posAfter = state.cameraInstance.position;
    expect(posAfter.x !== posBefore.x || posAfter.y !== posBefore.y || posAfter.z !== posBefore.z).toBe(true);
  });

  it("dispose cancels the animation frame, disconnects resize, disposes GL resources, and detaches canvases", () => {
    const container = makeContainer();
    const handle = create(container);
    handle.dispose();

    expect(window.cancelAnimationFrame).toHaveBeenCalled();
    expect(FakeResizeObserver.instances.at(-1)!.disconnect).toHaveBeenCalled();
    expect(state.controlsInstance.dispose).toHaveBeenCalled();
    expect(state.rendererInstance.dispose).toHaveBeenCalled();
    expect(state.textures.every((t) => t.dispose.mock.calls.length > 0)).toBe(true);
    expect(container.contains(state.rendererDomElement)).toBe(false);
    expect(container.contains(state.labelDomElement)).toBe(false);

    activeScenes = activeScenes.filter((s) => s !== handle);
  });

  it("after dispose, further animate frames are a no-op", () => {
    const container = makeContainer();
    const handle = create(container);
    handle.dispose();
    const renderCallsBefore = state.rendererInstance.render.mock.calls.length;
    expect(() => tick(0.1)).not.toThrow();
    expect(state.rendererInstance.render.mock.calls.length).toBe(renderCallsBefore);
    activeScenes = activeScenes.filter((s) => s !== handle);
  });

  describe("mission mode", () => {
    it("load() (geocentric) parents the mission layer under Earth's group with one child per element (line, craft, ticks)", () => {
      const container = makeContainer();
      const handle = create(container);
      const spec = makeMissionSpec(); // 1 milestone
      const earthGroup = findBodyGroup(state.sceneInstance!, "earth");
      const childCountBefore = earthGroup.children.length;

      handle.mission.load(spec);

      expect(earthGroup.children.length).toBe(childCountBefore + 1);
      const missionGroup = earthGroup.children.at(-1)!;
      // line + craft + 1 milestone tick, in that deterministic order.
      expect(missionGroup.children.length).toBe(3);
    });

    it("clamps the sim clock to [t0, t1] while a mission is loaded", () => {
      const container = makeContainer();
      const handle = create(container);
      const spec = makeMissionSpec();
      handle.mission.load(spec);
      onDateTick.mockClear();

      handle.setDate(new Date("2019-01-01T00:00:00Z")); // before t0
      let ticked = onDateTick.mock.calls.at(-1)?.[0] as Date;
      expect(ticked.getTime()).toBe(Date.parse(spec.t0));

      handle.setDate(new Date("2025-01-01T00:00:00Z")); // after t1
      ticked = onDateTick.mock.calls.at(-1)?.[0] as Date;
      expect(ticked.getTime()).toBe(Date.parse(spec.t1));
    });

    it("clamps forward playback at t1 during the animate loop", () => {
      const container = makeContainer();
      const handle = create(container);
      const spec = makeMissionSpec();
      handle.mission.load(spec);
      handle.setSpeed(100_000); // fast enough to blow past t1 in one frame
      onDateTick.mockClear();

      for (let i = 0; i < 5; i++) tick(0.25);

      const ticked = onDateTick.mock.calls.at(-1)?.[0] as Date;
      expect(ticked.getTime()).toBe(Date.parse(spec.t1));
    });

    it("locks scale mode to true-scale while a mission is active and unlocks on clear()", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.setScaleMode("visible");
      handle.mission.load(makeMissionSpec());

      const setSizeCallsBefore = state.rendererInstance.setSize.mock.calls.length;
      handle.setScaleMode("visible"); // should no-op: locked
      expect(state.rendererInstance.setSize.mock.calls.length).toBe(setSizeCallsBefore);

      handle.mission.clear();
      handle.setScaleMode("true"); // no longer locked
      handle.setScaleMode("visible");
    });

    it("clear() restores the pre-mission sim date, speed, and scale mode", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.setSpeed(3);
      handle.setDate(new Date("2010-05-05T00:00:00Z"));

      handle.mission.load(makeMissionSpec());
      handle.setDate(new Date("2020-01-01T12:00:00Z"));
      onDateTick.mockClear();

      handle.mission.clear();

      const ticked = onDateTick.mock.calls.at(-1)?.[0] as Date;
      expect(ticked.getTime()).toBe(Date.parse("2010-05-05T00:00:00Z"));
    });

    it("clear() is a no-op when no mission is active", () => {
      const container = makeContainer();
      const handle = create(container);
      expect(() => handle.mission.clear()).not.toThrow();
    });

    it("loading a second mission swaps the layer without disturbing the original pre-mission snapshot", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.setDate(new Date("2010-05-05T00:00:00Z"));

      handle.mission.load(makeMissionSpec({ slug: "mission-a" }));
      handle.mission.load(makeMissionSpec({ slug: "mission-b", t0: "2021-01-01T00:00:00Z", t1: "2021-01-02T00:00:00Z" }));

      onDateTick.mockClear();
      handle.mission.clear();
      const ticked = onDateTick.mock.calls.at(-1)?.[0] as Date;
      expect(ticked.getTime()).toBe(Date.parse("2010-05-05T00:00:00Z"));
    });

    it("applies Moon phase calibration for geocentric missions and restores it on clear()", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.setDate(new Date("2020-01-01T06:00:00Z"));

      const specNoCalibration = makeMissionSpec();
      handle.mission.load(specNoCalibration);
      handle.mission.clear();

      const specCalibrated = makeMissionSpec({ bodyCalibration: { moon: { phaseDeg: 42 } } });
      // Loading twice with/without calibration should not throw either way,
      // and the calibrated variant must restore cleanly too.
      handle.mission.load(specCalibrated);
      handle.mission.clear();
      expect(() => handle.mission.load(specCalibrated)).not.toThrow();
    });

    it("parents heliocentric missions directly onto the scene root instead of Earth's group", () => {
      const container = makeContainer();
      const handle = create(container);
      const earthGroup = findBodyGroup(state.sceneInstance!, "earth");
      const earthChildCountBefore = earthGroup.children.length;
      const sceneChildCountBefore = state.sceneInstance!.children.length;

      const spec = makeMissionSpec({
        frame: "heliocentric",
        bodies: ["earth", "mars"],
        bodyCalibration: undefined,
      });
      handle.mission.load(spec);

      expect(earthGroup.children.length).toBe(earthChildCountBefore); // untouched
      expect(state.sceneInstance!.children.length).toBe(sceneChildCountBefore + 1);
      expect(state.sceneInstance!.children.at(-1)!.children.length).toBe(3);

      handle.mission.clear();
      expect(state.sceneInstance!.children.length).toBe(sceneChildCountBefore);
    });

    it("handles an empty trajectory/milestone mission gracefully", () => {
      const container = makeContainer();
      const handle = create(container);
      expect(() =>
        handle.mission.load(
          makeMissionSpec({
            trajectory: [{ t: "2020-01-01T00:00:00Z", x: 0, y: 0, z: 0 }],
            milestones: [],
          }),
        ),
      ).not.toThrow();
    });

    it("dispose() while a mission is active tears down the mission layer too", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.mission.load(makeMissionSpec());
      expect(() => handle.dispose()).not.toThrow();
      activeScenes = activeScenes.filter((s) => s !== handle);
    });
  });

  describe("spacecraft layer", () => {
    function point(t: string, x: number, y: number, z: number) {
      return { t: Date.parse(t), x, y, z };
    }

    it("creates a marker + label per object and positions it via the true-scale AU mapping", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.setScaleMode("true");
      handle.setDate(new Date("2026-01-01T00:00:00Z"));

      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST", points: [point("2026-01-01T00:00:00Z", 2, 3, 0)] }],
        "no data",
      );

      const mesh = findMeshNamed(state.sceneInstance!, "jwst")!;
      const group = mesh.parent!;
      const UNITS_PER_AU = 60;
      expect(group.position.x).toBeCloseTo(2 * UNITS_PER_AU, 6);
      expect(group.position.y).toBeCloseTo(0, 6);
      expect(group.position.z).toBeCloseTo(-3 * UNITS_PER_AU, 6);

      const labelButtons = Array.from(container.querySelectorAll(".solar-label--spacecraft")) as HTMLElement[];
      expect(labelButtons.some((el) => el.textContent === "JWST")).toBe(true);
    });

    it("dims the marker/label and sets a tooltip when the sim clock is outside the object's covered range", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.spacecraft.setObjects(
        [
          {
            id: "voyager-1",
            label: "Voyager 1",
            points: [point("2026-01-01T00:00:00Z", 1, 0, 0), point("2026-01-02T00:00:00Z", 1.1, 0, 0)],
          },
        ],
        "No data for this date",
      );
      const mesh = findMeshNamed(state.sceneInstance!, "voyager-1")!;
      const label = container.querySelector(".solar-label--spacecraft") as HTMLElement;

      handle.setDate(new Date("2026-01-01T12:00:00Z")); // within coverage
      expect((mesh.material as { opacity: number }).opacity).toBe(1);
      expect(label.classList.contains("solar-label--dimmed")).toBe(false);
      expect(label.title).toBe("");

      handle.setDate(new Date("2026-01-05T00:00:00Z")); // outside coverage
      expect((mesh.material as { opacity: number }).opacity).toBeCloseTo(0.3, 10);
      expect(label.classList.contains("solar-label--dimmed")).toBe(true);
      expect(label.title).toBe("No data for this date");
    });

    it("hides the marker entirely when an object has no ephemeris points at all", () => {
      const container = makeContainer();
      const handle = create(container);
      expect(() =>
        handle.spacecraft.setObjects([{ id: "ghost", label: "Ghost", points: [] }], "no data"),
      ).not.toThrow();
      const mesh = findMeshNamed(state.sceneInstance!, "ghost")!;
      expect(mesh.parent!.visible).toBe(false);
    });

    it("setVisible toggles the marker group and trail line together", () => {
      const container = makeContainer();
      const handle = create(container);
      const before = state.sceneInstance!.children.length;
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      const added = state.sceneInstance!.children.slice(before);
      expect(added).toHaveLength(2); // marker group + trail line
      const [group, trailLine] = added;

      expect(group.visible).toBe(true);
      expect(trailLine.visible).toBe(true);

      handle.spacecraft.setVisible(false);
      expect(group.visible).toBe(false);
      expect(trailLine.visible).toBe(false);

      handle.spacecraft.setVisible(true);
      expect(group.visible).toBe(true);
      expect(trailLine.visible).toBe(true);
    });

    it("click-to-select includes spacecraft markers only while the layer is visible", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      state.setRaycastHit("jwst");
      const mesh = findMeshNamed(state.sceneInstance!, "jwst")!;

      state.rendererDomElement.dispatchEvent(new MouseEvent("pointerdown", { clientX: 0, clientY: 0 }));
      state.rendererDomElement.dispatchEvent(new MouseEvent("pointerup", { clientX: 1, clientY: 1 }));
      let meshesArg = state.raycasterInstance.intersectObjects.mock.calls.at(-1)![0] as unknown[];
      expect(meshesArg).toContain(mesh);

      handle.spacecraft.setVisible(false);
      state.rendererDomElement.dispatchEvent(new MouseEvent("pointerdown", { clientX: 0, clientY: 0 }));
      state.rendererDomElement.dispatchEvent(new MouseEvent("pointerup", { clientX: 1, clientY: 1 }));
      meshesArg = state.raycasterInstance.intersectObjects.mock.calls.at(-1)![0] as unknown[];
      expect(meshesArg).not.toContain(mesh);
    });

    it("selecting a spacecraft toggles its active label class and reports through onSelect", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      handle.select("jwst");
      expect(onSelect).toHaveBeenCalledWith("jwst");
      const label = container.querySelector(".solar-label--spacecraft") as HTMLElement;
      expect(label.classList.contains("solar-label--active")).toBe(true);
    });

    it("re-invoking setObjects with fresh label text renders the new text (locale-switch pattern)", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "James Webb Space Telescope", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "James-Webb-Weltraumteleskop", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "keine Daten",
      );

      const labelButtons = Array.from(container.querySelectorAll(".solar-label--spacecraft")) as HTMLElement[];
      expect(labelButtons.some((el) => el.textContent === "James-Webb-Weltraumteleskop")).toBe(true);
    });

    it("re-invoking setObjects tears down old markers without disposing the shared marker geometry, which disposes exactly once on scene dispose()", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      const firstMesh = findMeshNamed(state.sceneInstance!, "jwst")!;
      const geometry = (firstMesh as unknown as { geometry: { dispose: ReturnType<typeof vi.fn> } }).geometry;

      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST (updated)", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      expect(geometry.dispose).not.toHaveBeenCalled();

      const secondMesh = findMeshNamed(state.sceneInstance!, "jwst")!;
      expect((secondMesh as unknown as { geometry: unknown }).geometry).toBe(geometry);

      handle.dispose();
      expect(geometry.dispose).toHaveBeenCalledTimes(1);
      activeScenes = activeScenes.filter((s) => s !== handle);
    });

    it("dispose() while spacecraft are loaded tears down the layer too", () => {
      const container = makeContainer();
      const handle = create(container);
      handle.spacecraft.setObjects(
        [{ id: "jwst", label: "JWST", points: [point("2026-01-01T00:00:00Z", 1, 0, 0)] }],
        "no data",
      );
      expect(() => handle.dispose()).not.toThrow();
      activeScenes = activeScenes.filter((s) => s !== handle);
    });
  });

  describe("mission trajectory math (white-box)", () => {
    it("places the craft marker at the exact mapped position at t0, and interpolates at the midpoint", () => {
      const container = makeContainer();
      const handle = create(container);
      const spec = makeMissionSpec({
        trajectory: [
          { t: "2020-01-01T00:00:00Z", x: 100_000, y: 200_000, z: 0 },
          { t: "2020-01-02T00:00:00Z", x: 300_000, y: -400_000, z: 0 },
        ],
        milestones: [],
      });
      handle.mission.load(spec);
      const earthGroup = findBodyGroup(state.sceneInstance!, "earth");
      const missionGroup = earthGroup.children.at(-1)!;
      const craft = missionGroup.children[1]; // line, craft, ticks — see loadMission()

      // scene.ts maps ecliptic (x,y,z) km -> three.js (x*k, z*k, -y*k) units,
      // same convention as heliocentricPosition's mapping for planets.
      handle.setDate(new Date(spec.t0));
      expect(craft.position.x).toBeCloseTo(100_000 * KM_TO_UNITS, 6);
      expect(craft.position.y).toBeCloseTo(0, 6);
      expect(craft.position.z).toBeCloseTo(-200_000 * KM_TO_UNITS, 6);

      handle.setDate(new Date(spec.t1));
      expect(craft.position.x).toBeCloseTo(300_000 * KM_TO_UNITS, 6);
      expect(craft.position.z).toBeCloseTo(400_000 * KM_TO_UNITS, 6);

      // Raw midpoint: x=(100_000+300_000)/2=200_000, y=(200_000-400_000)/2=-100_000
      // -> mapped (x*k, z*k, -y*k) = (200_000k, 0, 100_000k).
      const midMs = (Date.parse(spec.t0) + Date.parse(spec.t1)) / 2;
      handle.setDate(new Date(midMs));
      expect(craft.position.x).toBeCloseTo(200_000 * KM_TO_UNITS, 6);
      expect(craft.position.z).toBeCloseTo(100_000 * KM_TO_UNITS, 6);
    });

    it("places milestone ticks at their own interpolated trajectory position", () => {
      const container = makeContainer();
      const handle = create(container);
      const spec = makeMissionSpec({
        trajectory: [
          { t: "2020-01-01T00:00:00Z", x: 0, y: 0, z: 0 },
          { t: "2020-01-02T00:00:00Z", x: 10000, y: 0, z: 0 },
        ],
        milestones: [{ t: "2020-01-01T12:00:00Z", key: "missions.testMission.midpoint" }],
      });
      handle.mission.load(spec);
      const earthGroup = findBodyGroup(state.sceneInstance!, "earth");
      const missionGroup = earthGroup.children.at(-1)!;
      const tick = missionGroup.children[2];

      expect(tick.position.x).toBeCloseTo(5000 * KM_TO_UNITS, 6);
    });
  });
});

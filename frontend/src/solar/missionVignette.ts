// Imperative three.js module for mission "vignettes" — a self-contained,
// close-up staging scene (glTF model + environment + own camera/lighting)
// mounted when a replay milestone with a `vignette` is entered
// (Architecture/27-mission-simulations-3d.md). Same pattern as
// `solar/scene.ts` / `lib/roverScene.ts`: kept free of React, owns its own
// render loop, disposed via an explicit dispose().
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { disposeObject3D, normalizeModelScale } from "@/lib/gltfNormalize";
import { ENVIRONMENTS } from "./environments";
import type { MissionVignette } from "./mission";

const FALLBACK_SIZE = 480;
// Real-meter framing per the "Vignette" scale row in 27-…; models are
// normalized to this so cameraOrbit.distanceM reads as a sensible close-up
// regardless of each source asset's native scale.
const TARGET_MODEL_SIZE_M = 6;

export interface VignetteHandle {
  /**
   * Starts the render loop and loads the model. Resolves once the model is
   * in the scene; rejects with the loader's error on failure (never throws
   * synchronously) so the caller can show `t("missions.vignette.error")`.
   */
  play(): Promise<void>;
  dispose(): void;
}

// P36: mock `three` / GLTFLoader / OrbitControls entirely in tests — jsdom
// has no WebGL context and THREE.WebGLRenderer throws when it can't get one.
export function createVignette(
  container: HTMLElement,
  spec: MissionVignette,
  getLabel: (key: string) => string,
): VignetteHandle {
  const width = container.clientWidth || FALLBACK_SIZE;
  const height = container.clientHeight || FALLBACK_SIZE;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  const env = ENVIRONMENTS[spec.environment];
  const textureLoader = new THREE.TextureLoader();
  env.build(scene, textureLoader);

  scene.add(new THREE.AmbientLight(env.ambientColor, env.ambientIntensity));
  const sunLight = new THREE.DirectionalLight(env.lightColor, env.lightIntensity);
  sunLight.position.set(4, 6, 3);
  scene.add(sunLight);

  const distance = spec.cameraOrbit.distanceM;
  const elevationRad = THREE.MathUtils.degToRad(spec.cameraOrbit.elevationDeg);
  camera.position.set(0, distance * Math.sin(elevationRad), distance * Math.cos(elevationRad));
  camera.lookAt(0, 0, 0);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = Math.max(distance * 0.2, 1);
  controls.maxDistance = distance * 5;
  controls.target.set(0, 0, 0);
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.4;

  const creditEl = document.createElement("div");
  creditEl.className = "mission-vignette__credit";
  creditEl.textContent = getLabel(spec.modelCredit);
  container.appendChild(creditEl);

  // 26-performance.md §2.4: render loops must pause when the tab is hidden
  // or the scene scrolls out of view — the #1 avoidable frame-budget cost.
  let frameId = 0;
  const animate = () => {
    controls.update();
    renderer.render(scene, camera);
    frameId = requestAnimationFrame(animate);
  };

  function startLoop(): void {
    if (frameId === 0) frameId = requestAnimationFrame(animate);
  }

  function stopLoop(): void {
    cancelAnimationFrame(frameId);
    frameId = 0;
  }

  function handleVisibilityChange(): void {
    if (document.hidden) stopLoop();
    else startLoop();
  }
  document.addEventListener("visibilitychange", handleVisibilityChange);

  const intersectionObserver = new IntersectionObserver((entries) => {
    const entry = entries[entries.length - 1];
    if (!entry) return;
    if (entry.isIntersecting) startLoop();
    else stopLoop();
  });
  intersectionObserver.observe(container);

  const loader = new GLTFLoader();
  let model: THREE.Object3D | null = null;

  function play(): Promise<void> {
    startLoop();
    return new Promise((resolve, reject) => {
      loader.load(
        spec.model,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (gltf: { scene: any }) => {
          const loaded: THREE.Object3D = gltf.scene;
          model = loaded;
          normalizeModelScale(loaded, TARGET_MODEL_SIZE_M);
          scene.add(loaded);
          resolve();
        },
        undefined,
        (event: unknown) => {
          reject(event instanceof Error ? event : new Error("Failed to load vignette model"));
        },
      );
    });
  }

  function dispose(): void {
    stopLoop();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    intersectionObserver.disconnect();
    controls.dispose();
    if (model) disposeObject3D(model);
    disposeObject3D(scene);
    renderer.dispose();
    if (renderer.domElement.parentElement === container) {
      container.removeChild(renderer.domElement);
    }
    if (creditEl.parentElement === container) {
      container.removeChild(creditEl);
    }
  }

  return { play, dispose };
}

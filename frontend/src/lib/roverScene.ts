import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { disposeObject3D, normalizeModelScale } from "@/lib/gltfNormalize";

const FALLBACK_SIZE = 320;
const TARGET_MODEL_SIZE = 2.2;
const CAMERA_START = { x: 2.4, y: 1.7, z: 2.4 };

export interface RoverScene {
  loadModel(url: string): Promise<void>;
  dispose(): void;
}

// P36: mock `three` / GLTFLoader / OrbitControls entirely in tests — jsdom
// has no WebGL context and THREE.WebGLRenderer throws when it can't get one.
export function createRoverScene(container: HTMLElement): RoverScene {
  const width = container.clientWidth || FALLBACK_SIZE;
  const height = container.clientHeight || FALLBACK_SIZE;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
  camera.position.set(CAMERA_START.x, CAMERA_START.y, CAMERA_START.z);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xffe8d0, 0x231405, 1.15));
  const keyLight = new THREE.DirectionalLight(0xfff2e0, 2.4);
  keyLight.position.set(4, 6, 3);
  scene.add(keyLight);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 1;
  controls.maxDistance = 10;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;

  let frameId = 0;
  const animate = () => {
    controls.update();
    renderer.render(scene, camera);
    frameId = requestAnimationFrame(animate);
  };
  frameId = requestAnimationFrame(animate);

  const handleResize = () => {
    const w = container.clientWidth || FALLBACK_SIZE;
    const h = container.clientHeight || FALLBACK_SIZE;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  };
  window.addEventListener("resize", handleResize);

  const loader = new GLTFLoader();
  let currentModel: THREE.Object3D | null = null;

  function loadModel(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      loader.load(
        url,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (gltf: { scene: any }) => {
          if (currentModel) {
            scene.remove(currentModel);
            disposeObject3D(currentModel);
          }

          const model = gltf.scene;
          normalizeModelScale(model, TARGET_MODEL_SIZE);
          scene.add(model);
          currentModel = model;

          camera.position.set(CAMERA_START.x, CAMERA_START.y, CAMERA_START.z);
          controls.target.set(0, 0, 0);
          controls.update();
          resolve();
        },
        undefined,
        (event: unknown) => {
          reject(event instanceof Error ? event : new Error("Failed to load rover model"));
        },
      );
    });
  }

  function dispose(): void {
    window.removeEventListener("resize", handleResize);
    cancelAnimationFrame(frameId);
    controls.dispose();
    if (currentModel) disposeObject3D(currentModel);
    renderer.dispose();
    if (renderer.domElement.parentElement === container) {
      container.removeChild(renderer.domElement);
    }
  }

  return { loadModel, dispose };
}

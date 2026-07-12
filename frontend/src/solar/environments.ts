// Reusable vignette staging backdrops (Architecture/27-mission-simulations-
// 3d.md): a small, code-defined set shared by every mission vignette rather
// than per-mission assets. "moon-surface"/"mars-surface" are a textured
// ground plane + matched light/sky color using the same public-domain
// NASA/Solar-System-Scope textures already shipped for the main solar scene
// (`/solar/2k_moon.jpg`, `/solar/2k_mars.jpg`); "space" reuses the same
// starfield texture as `solar/scene.ts`.
import * as THREE from "three";
import type { VignetteEnvironment } from "./mission";

const GROUND_RADIUS_M = 60;

export interface EnvironmentDef {
  lightColor: number;
  lightIntensity: number;
  ambientColor: number;
  ambientIntensity: number;
  /**
   * Adds the environment's geometry to `scene`. Callers dispose it via a
   * whole-scene `disposeObject3D` sweep rather than tracking objects here.
   */
  build(scene: THREE.Scene, textureLoader: THREE.TextureLoader): void;
}

function surfaceEnvironment(
  texturePath: string,
  groundColor: number,
  lightColor: number,
  skyColor: number,
): EnvironmentDef {
  return {
    lightColor,
    lightIntensity: 2.2,
    ambientColor: groundColor,
    ambientIntensity: 0.35,
    build(scene, textureLoader) {
      const texture = textureLoader.load(texturePath);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(8, 8);

      const ground = new THREE.Mesh(
        new THREE.CircleGeometry(GROUND_RADIUS_M, 48),
        new THREE.MeshStandardMaterial({ map: texture, color: groundColor, roughness: 1, metalness: 0 }),
      );
      ground.rotation.x = -Math.PI / 2;
      scene.add(ground);
      scene.background = new THREE.Color(skyColor);
    },
  };
}

const spaceEnvironment: EnvironmentDef = {
  lightColor: 0xffffff,
  lightIntensity: 2.6,
  ambientColor: 0xffffff,
  ambientIntensity: 0.08,
  build(scene, textureLoader) {
    const texture = textureLoader.load("/solar/2k_stars_milky_way.jpg");
    texture.colorSpace = THREE.SRGBColorSpace;
    const sky = new THREE.Mesh(
      new THREE.SphereGeometry(500, 32, 16),
      new THREE.MeshBasicMaterial({ map: texture, side: THREE.BackSide, color: new THREE.Color(0x888888) }),
    );
    scene.add(sky);
  },
};

export const ENVIRONMENTS: Record<VignetteEnvironment, EnvironmentDef> = {
  "moon-surface": surfaceEnvironment("/solar/2k_moon.jpg", 0x8c8c8c, 0xfff2e0, 0x05060a),
  "mars-surface": surfaceEnvironment("/solar/2k_mars.jpg", 0xb3552b, 0xffd8b0, 0x2b1710),
  space: spaceEnvironment,
};

import { describe, it, expect, vi } from "vitest";
import * as THREE from "three";
import { disposeObject3D, normalizeModelScale } from "@/lib/gltfNormalize";

// Pure math (Box3/Vector3) and plain traversal — no WebGLRenderer involved,
// so unlike roverScene.test.ts (P36) this file uses the real `three` module.

describe("normalizeModelScale", () => {
  it("centers the model on the origin and scales its largest dimension to targetSize", () => {
    const geometry = new THREE.BoxGeometry(2, 1, 1);
    geometry.translate(1, 0.5, 0.5); // bbox now [0,2]x[0,1]x[0,1], center (1, 0.5, 0.5)
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
    const group = new THREE.Group();
    group.add(mesh);

    const scale = normalizeModelScale(group, 2.2);

    expect(scale).toBeCloseTo(1.1, 5); // maxDim = 2, target = 2.2 -> scale = 1.1
    expect(group.scale.x).toBeCloseTo(1.1, 5);
    expect(group.scale.y).toBeCloseTo(1.1, 5);
    expect(group.scale.z).toBeCloseTo(1.1, 5);
    expect(group.position.x).toBeCloseTo(-1.1, 5);
    expect(group.position.y).toBeCloseTo(-0.55, 5);
    expect(group.position.z).toBeCloseTo(-0.55, 5);
  });

  it("falls back to a divisor of 1 when the model has no extent (degenerate/empty bbox)", () => {
    const group = new THREE.Group(); // empty — Box3 stays infinite/empty, size collapses to 0

    const scale = normalizeModelScale(group, 5);

    expect(scale).toBe(5); // maxDim guarded to `|| 1` -> scale = targetSize / 1
  });
});

describe("disposeObject3D", () => {
  it("disposes geometry and a single material on every mesh in the hierarchy", () => {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = new THREE.MeshBasicMaterial();
    const geometryDispose = vi.spyOn(geometry, "dispose");
    const materialDispose = vi.spyOn(material, "dispose");
    const mesh = new THREE.Mesh(geometry, material);
    const group = new THREE.Group();
    group.add(mesh);

    disposeObject3D(group);

    expect(geometryDispose).toHaveBeenCalledTimes(1);
    expect(materialDispose).toHaveBeenCalledTimes(1);
  });

  it("disposes every material in a multi-material mesh", () => {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const materials = [new THREE.MeshBasicMaterial(), new THREE.MeshBasicMaterial()];
    const disposals = materials.map((m) => vi.spyOn(m, "dispose"));
    const mesh = new THREE.Mesh(geometry, materials);

    disposeObject3D(mesh);

    for (const spy of disposals) {
      expect(spy).toHaveBeenCalledTimes(1);
    }
  });

  it("skips nodes with neither geometry nor material (e.g. a bare Group/Object3D)", () => {
    const group = new THREE.Group();
    const empty = new THREE.Object3D();
    group.add(empty);

    expect(() => disposeObject3D(group)).not.toThrow();
  });
});

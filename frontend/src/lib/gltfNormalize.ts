import * as THREE from "three";

// Structural view of the mesh members disposeObject3D touches — not every
// Object3D in a glTF scene graph is a mesh.
export interface Disposable {
  dispose(): void;
}
export interface MeshLike {
  geometry?: Disposable;
  material?: Disposable | Disposable[];
}

export function disposeObject3D(object: THREE.Object3D): void {
  object.traverse((node) => {
    const child = node as unknown as MeshLike;
    if (!child.geometry && !child.material) return;
    child.geometry?.dispose();
    const material = child.material;
    if (Array.isArray(material)) {
      material.forEach((m) => m.dispose());
    } else {
      material?.dispose();
    }
  });
}

/**
 * Centers `model` on the origin and scales it so its largest bounding-box
 * dimension equals `targetSize`, mutating `model.scale`/`model.position` in
 * place. Returns the scale factor applied.
 */
export function normalizeModelScale(model: THREE.Object3D, targetSize: number): number {
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const scale = targetSize / maxDim;

  model.scale.setScalar(scale);
  model.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
  return scale;
}

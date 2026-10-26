import { Raycaster, Vector2, type Camera, type Object3D } from "three";
import { PART_ID_KEY } from "../scene/mapping";

/** Walk up from a hit object to the nearest part id. */
export function partIdFor(object: Object3D | null | undefined): string | null {
  let node = object ?? null;
  while (node) {
    const id = node.userData[PART_ID_KEY];
    if (typeof id === "string") return id;
    node = node.parent;
  }
  return null;
}

/** Pick the nearest part under a normalised device coordinate, or null for empty space. */
export function pickPart(
  ndc: Vector2,
  camera: Camera,
  root: Object3D | null,
): string | null {
  if (!root) return null;
  const raycaster = new Raycaster();
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObject(root, true);
  return hits.length > 0 ? partIdFor(hits[0].object) : null;
}

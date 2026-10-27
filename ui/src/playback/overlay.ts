/** Contact overlay: points at each contact plus a normal line scaled by force (visual only). */
import {
  BufferAttribute,
  BufferGeometry,
  Group,
  LineBasicMaterial,
  LineSegments,
  Points,
  PointsMaterial,
} from "three";
import type { ContactPoint } from "./frames";

const CONTACT_COLOR = 0xff5050;
const MIN_NORMAL_MM = 2;
const MAX_NORMAL_MM = 30;

/** Normal-line length in mm: grows with the square root of the force, clamped to [2, 30]. */
export function normalLength(force: number): number {
  if (!Number.isFinite(force) || force <= 0) return MIN_NORMAL_MM;
  return Math.min(Math.max(Math.sqrt(force) * 4, MIN_NORMAL_MM), MAX_NORMAL_MM);
}

/** Largest number of contacts in any one frame, from a `contactIndex` offsets array. */
export function maxContactsPerFrame(index: Uint32Array): number {
  let max = 0;
  for (let f = 0; f + 1 < index.length; f += 1) max = Math.max(max, index[f + 1] - index[f]);
  return max;
}

export interface ContactOverlay {
  group: Group;
  /** Show these contacts; extra contacts beyond the allocated capacity are dropped. */
  update(points: readonly ContactPoint[]): void;
}

/** Preallocated so per-frame updates never reallocate GPU buffers. Not pickable. */
export function createContactOverlay(capacity: number): ContactOverlay {
  const size = Math.max(capacity, 1);
  const pointPositions = new Float32Array(size * 3);
  const linePositions = new Float32Array(size * 6);
  const pointGeometry = new BufferGeometry();
  pointGeometry.setAttribute("position", new BufferAttribute(pointPositions, 3));
  const lineGeometry = new BufferGeometry();
  lineGeometry.setAttribute("position", new BufferAttribute(linePositions, 3));
  const points = new Points(pointGeometry, new PointsMaterial({ color: CONTACT_COLOR, size: 6, sizeAttenuation: false, depthTest: false }));
  const lines = new LineSegments(lineGeometry, new LineBasicMaterial({ color: CONTACT_COLOR, depthTest: false }));
  const group = new Group();
  group.name = "contacts";
  group.renderOrder = 10;
  group.add(points, lines);
  // Buffers are partly used, so their bounds are meaningless: never cull or pick them.
  for (const object of [group, points, lines]) {
    object.raycast = () => {};
    object.frustumCulled = false;
  }

  const update = (contacts: readonly ContactPoint[]): void => {
    const n = Math.min(contacts.length, size);
    for (let k = 0; k < n; k += 1) {
      const { position: p, normal: d, force } = contacts[k];
      const length = normalLength(force);
      pointPositions.set(p, k * 3);
      linePositions.set([p[0], p[1], p[2], p[0] + d[0] * length, p[1] + d[1] * length, p[2] + d[2] * length], k * 6);
    }
    pointGeometry.setDrawRange(0, n);
    lineGeometry.setDrawRange(0, n * 2);
    (pointGeometry.attributes.position as BufferAttribute).needsUpdate = true;
    (lineGeometry.attributes.position as BufferAttribute).needsUpdate = true;
  };
  update([]);
  return { group, update };
}

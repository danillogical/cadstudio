import { Vector3, type Box3 } from "three";

export interface CameraFit {
  position: Vector3;
  target: Vector3;
  near: number;
  far: number;
  distance: number;
}

/** Iso view direction in Z-up space: from +X, -Y and above. */
export const VIEW_DIRECTION = new Vector3(1, -1, 0.8).normalize();

/**
 * A 1/2/5 x 10^n millimetre grid step giving roughly 10-20 cells across `sizeMm`.
 * A non-positive or non-finite size falls back to 1 mm.
 */
export function niceGridStep(sizeMm: number): number {
  if (!Number.isFinite(sizeMm) || sizeMm <= 0) return 1;
  const target = sizeMm / 15;
  const exponent = Math.floor(Math.log10(target));
  const power = 10 ** exponent;
  const fraction = target / power;
  // Round to the nearest 1/2/5 so the cell count stays near 15.
  const nice = fraction < 1.5 ? 1 : fraction < 3.5 ? 2 : fraction < 7.5 ? 5 : 10;
  return nice * power;
}

/** Place a perspective camera so `box` fills the frame from a fixed iso direction. */
export function fitCamera(box: Box3, fovDeg: number, aspect: number): CameraFit {
  const target = box.isEmpty() ? new Vector3() : box.getCenter(new Vector3());
  const size = box.isEmpty() ? new Vector3(1, 1, 1) : box.getSize(new Vector3());
  const radius = Math.max(size.length() / 2, 0.5);

  const vFov = (fovDeg * Math.PI) / 180;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(aspect, 1e-3));
  const limiting = Math.min(vFov, hFov);
  // 1.15 leaves a small margin so the model does not touch the frame edge.
  const distance = (radius / Math.sin(limiting / 2)) * 1.15;
  const position = target.clone().addScaledVector(VIEW_DIRECTION, distance);

  return {
    position,
    target,
    near: Math.max(distance / 1000, 0.01),
    far: distance + radius * 4,
    distance,
  };
}

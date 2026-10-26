import { Box3, PerspectiveCamera, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { fitCamera, niceGridStep } from "./camera";

describe("niceGridStep", () => {
  it("returns 1/2/5 x 10^n", () => {
    for (const size of [1, 3.5, 12, 35, 80, 300, 1234, 0.4]) {
      const step = niceGridStep(size);
      const mantissa = step / 10 ** Math.floor(Math.log10(step));
      expect([1, 2, 5]).toContain(Math.round(mantissa * 10) / 10);
    }
  });

  it("gives roughly 10-20 cells", () => {
    for (const size of [3.5, 12, 35, 80, 300, 1234]) {
      const cells = size / niceGridStep(size);
      expect(cells).toBeGreaterThanOrEqual(7);
      expect(cells).toBeLessThanOrEqual(30);
    }
  });

  it("picks a sane step for 35 mm and 300 mm", () => {
    expect(niceGridStep(35)).toBe(2);
    expect(niceGridStep(300)).toBe(20);
  });

  it("falls back to 1 for a non-positive size", () => {
    expect(niceGridStep(0)).toBe(1);
    expect(niceGridStep(Number.NaN)).toBe(1);
  });
});

describe("fitCamera", () => {
  const box = new Box3(new Vector3(0, 0, 0), new Vector3(40, 20, 35));

  function visibleFraction(position: Vector3, target: Vector3, radius: number, fov: number, aspect: number) {
    const distance = position.distanceTo(target);
    const vFov = (fov * Math.PI) / 180;
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);
    const limiting = Math.min(vFov, hFov);
    return (radius / distance) / Math.sin(limiting / 2);
  }

  it("targets the box centre and looks from above in Z-up", () => {
    const fit = fitCamera(box, 45, 1);
    expect(fit.target.toArray()).toEqual([20, 10, 17.5]);
    expect(fit.position.z).toBeGreaterThan(fit.target.z);
    expect(fit.distance).toBeGreaterThan(0);
  });

  it("keeps the bounding sphere inside the frustum at aspect 0.5 and 2", () => {
    const radius = box.getSize(new Vector3()).length() / 2;
    for (const aspect of [0.5, 1, 2]) {
      const fit = fitCamera(box, 45, aspect);
      expect(visibleFraction(fit.position, fit.target, radius, 45, aspect)).toBeLessThan(1);
      expect(fit.near).toBeLessThan(fit.distance - radius);
      expect(fit.far).toBeGreaterThan(fit.distance + radius);
    }
  });

  it("produces a camera whose matrix looks at the target", () => {
    const fit = fitCamera(box, 45, 1.5);
    const camera = new PerspectiveCamera(45, 1.5, fit.near, fit.far);
    camera.up.set(0, 0, 1);
    camera.position.copy(fit.position);
    camera.lookAt(fit.target);
    camera.updateMatrixWorld(true);
    const forward = new Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
    const expected = fit.target.clone().sub(fit.position).normalize();
    expect(forward.dot(expected)).toBeCloseTo(1, 6);
  });

  it("handles an empty box", () => {
    const fit = fitCamera(new Box3(), 45, 1);
    expect(Number.isFinite(fit.position.x)).toBe(true);
    expect(fit.distance).toBeGreaterThan(0);
  });
});

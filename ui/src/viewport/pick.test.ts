import { readFileSync } from "node:fs";
import { Box3, PerspectiveCamera, Vector2, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { buildSceneGroup } from "../scene/mapping";
import type { SceneDoc } from "../transport/types";
import { fitCamera } from "./camera";
import { pickPart } from "./pick";

const FIXTURES = `${process.cwd()}/test/fixtures/`;

function fixtureBytes(path: string): ArrayBuffer {
  const buffer = readFileSync(`${FIXTURES}${path}`);
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength) as ArrayBuffer;
}

function makeCamera(box: Box3): PerspectiveCamera {
  const fit = fitCamera(box, 45, 1);
  const camera = new PerspectiveCamera(45, 1, fit.near, fit.far);
  camera.up.set(0, 0, 1);
  camera.position.copy(fit.position);
  camera.lookAt(fit.target);
  camera.updateMatrixWorld(true);
  return camera;
}

async function fixtureScene() {
  const doc = JSON.parse(readFileSync(`${FIXTURES}scene.json`, "utf8")) as SceneDoc;
  return { doc, scene: await buildSceneGroup(doc, async (path) => fixtureBytes(path)) };
}

describe("pickPart", () => {
  it("picks each part by its bbox centre projected to NDC", async () => {
    const { doc, scene } = await fixtureScene();
    const camera = makeCamera(scene.bounds);
    for (const part of doc.parts) {
      const centre = new Vector3(
        (part.bbox.min[0] + part.bbox.max[0]) / 2,
        (part.bbox.min[1] + part.bbox.max[1]) / 2,
        (part.bbox.min[2] + part.bbox.max[2]) / 2,
      );
      const ndc = centre.clone().project(camera);
      expect(pickPart(new Vector2(ndc.x, ndc.y), camera, scene.root)).toBe(part.id);
    }
  });

  it("returns null on empty space", async () => {
    const { scene } = await fixtureScene();
    const camera = makeCamera(scene.bounds);
    expect(pickPart(new Vector2(-0.99, 0.99), camera, scene.root)).toBeNull();
  });

  it("returns null without a root", () => {
    const camera = makeCamera(new Box3(new Vector3(), new Vector3(1, 1, 1)));
    expect(pickPart(new Vector2(0, 0), camera, null)).toBeNull();
  });
});

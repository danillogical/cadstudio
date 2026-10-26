import { readFileSync } from "node:fs";
import { Box3, Mesh, Vector3, type Material, type MeshStandardMaterial } from "three";
import { describe, expect, it } from "vitest";
import { buildSceneGroup, matrixFromRowMajor } from "./mapping";
import type { SceneDoc } from "../transport/types";

const FIXTURES = `${process.cwd()}/test/fixtures/`;

function fixtureDoc(): SceneDoc {
  return JSON.parse(readFileSync(`${FIXTURES}scene.json`, "utf8")) as SceneDoc;
}

function fixtureBytes(path: string): ArrayBuffer {
  const buffer = readFileSync(`${FIXTURES}${path}`);
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength) as ArrayBuffer;
}

async function loadFixture(doc = fixtureDoc()) {
  return buildSceneGroup(doc, async (path) => fixtureBytes(path));
}

function meshesUnder(root: import("three").Object3D): Mesh[] {
  const meshes: Mesh[] = [];
  root.traverse((node) => {
    if ((node as Mesh).isMesh) meshes.push(node as Mesh);
  });
  return meshes;
}

describe("buildSceneGroup", () => {
  it("names the root and parts from the document", async () => {
    const scene = await loadFixture();
    expect(scene.root.name).toBe("scene:fixture/two_box");
    expect(scene.root.children.map((child) => child.name)).toEqual(["base", "pin"]);
    expect([...scene.parts.keys()]).toEqual(["base", "pin"]);
  });

  it("tags every mesh with its part id", async () => {
    const scene = await loadFixture();
    for (const [id, part] of scene.parts) {
      const meshes = meshesUnder(part);
      expect(meshes.length).toBeGreaterThan(0);
      for (const mesh of meshes) expect(mesh.userData.partId).toBe(id);
    }
  });

  it("keeps millimetres and Z up: GLB bounds equal the fixture bbox", async () => {
    const scene = await loadFixture();
    const doc = fixtureDoc();
    for (const part of doc.parts) {
      const object = scene.parts.get(part.id);
      expect(object).toBeDefined();
      const box = new Box3().setFromObject(object!);
      for (const axis of [0, 1, 2] as const) {
        expect(box.min.getComponent(axis)).toBeCloseTo(part.bbox.min[axis], 3);
        expect(box.max.getComponent(axis)).toBeCloseTo(part.bbox.max[axis], 3);
      }
    }
    // The pin is 30 mm tall: any Y/Z swap or scale would break this.
    const pin = scene.parts.get("pin")!;
    const size = new Box3().setFromObject(pin).getSize(new Vector3());
    expect(size.z).toBeCloseTo(30, 3);
    expect(size.x).toBeCloseTo(4, 3);
  });

  it("leaves the root and parts at identity and does not apply printPose", async () => {
    const scene = await loadFixture();
    expect(scene.root.matrix.elements).toEqual([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
    const pin = scene.parts.get("pin")!;
    expect(pin.matrix.elements).toEqual([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
    const pose = pin.userData.printPose as import("three").Matrix4;
    expect(pose.elements[14]).toBeCloseTo(2, 9);
    // The geometry is still at z 5..35, so the pose was not baked in.
    expect(new Box3().setFromObject(pin).min.z).toBeCloseTo(5, 3);
  });

  it("maps row-major printPose to a column-major matrix", () => {
    const matrix = matrixFromRowMajor([
      [1, 2, 3, 4],
      [5, 6, 7, 8],
      [9, 10, 11, 12],
      [0, 0, 0, 1],
    ]);
    // Column-major storage: element 4 is row 0, column 1.
    expect(matrix.elements[4]).toBe(2);
    expect(matrix.elements[1]).toBe(5);
    expect(matrix.elements[12]).toBe(4);
    expect(matrix.elements[13]).toBe(8);
  });

  it("uses the fixture colour on every mesh material", async () => {
    const scene = await loadFixture();
    for (const part of fixtureDoc().parts) {
      for (const mesh of meshesUnder(scene.parts.get(part.id)!)) {
        const materials = (Array.isArray(mesh.material) ? mesh.material : [mesh.material]) as Material[];
        const standard = materials[0] as MeshStandardMaterial;
        expect(standard.color.getHexString()).toBe(part.color.replace("#", ""));
      }
    }
  });

  it("computes the assembly bounds", async () => {
    const scene = await loadFixture();
    expect(scene.bounds.min.toArray()).toEqual([0, 0, 0]);
    expect(scene.bounds.max.toArray()).toEqual([40, 20, 35]);
  });

  it("rejects a non-mm document", async () => {
    const doc = fixtureDoc();
    doc.units = "cm";
    await expect(loadFixture(doc)).rejects.toThrow(/units/);
  });

  it("rejects an unsupported schema version", async () => {
    const doc = fixtureDoc();
    doc.schemaVersion = 2;
    await expect(loadFixture(doc)).rejects.toThrow(/schemaVersion/);
  });

  it("is atomic: one failing part rejects the whole load", async () => {
    const doc = fixtureDoc();
    await expect(
      buildSceneGroup(doc, async (path) => {
        if (path.endsWith("pin.glb")) throw new Error("missing pin");
        return fixtureBytes(path);
      }),
    ).rejects.toThrow("missing pin");
  });
});

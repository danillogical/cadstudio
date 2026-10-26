import {
  Box3,
  Color,
  Group,
  Mesh,
  MeshStandardMaterial,
  Matrix4,
  Object3D,
} from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { SceneDoc, ScenePart } from "../transport/types";

/** One loaded scene: the group to add to the viewport plus the parts and their bounds. */
export interface LoadedScene {
  root: Group;
  parts: Map<string, Object3D>;
  bounds: Box3;
}

export const PART_ID_KEY = "partId";

type Matrix16 = [
  number, number, number, number,
  number, number, number, number,
  number, number, number, number,
  number, number, number, number,
];

/** Row-major 4x4 (as `scene.json` stores it) to a Three column-major matrix. */
export function matrixFromRowMajor(rows: number[][]): Matrix4 {
  const flat = rows.flat();
  if (flat.length !== 16) throw new Error(`expected a 4x4 matrix, got ${flat.length} values`);
  return new Matrix4().set(...(flat as Matrix16));
}

/** Every mesh under `root` belongs to `partId`, so a ray hit can walk up to it. */
export function tagMeshes(root: Object3D, partId: string): void {
  root.traverse((node) => {
    node.userData[PART_ID_KEY] = partId;
  });
}

function partMaterial(part: ScenePart): MeshStandardMaterial {
  return new MeshStandardMaterial({
    color: new Color(part.color),
    roughness: 0.7,
    metalness: 0.05,
    flatShading: false,
  });
}

/**
 * Parse one part GLB into a `Group` named by part id.
 *
 * The GLB is already in assembly coordinates in millimetres with Z up, so no axis swap,
 * scale or `printPose` is applied here.
 */
export async function loadPart(part: ScenePart, bytes: ArrayBuffer): Promise<Group> {
  const gltf = await new GLTFLoader().parseAsync(bytes, "");
  const group = new Group();
  group.name = part.id;
  group.userData[PART_ID_KEY] = part.id;
  group.userData.printPose = part.printPose
    ? matrixFromRowMajor(part.printPose)
    : new Matrix4();
  const material = partMaterial(part);
  gltf.scene.traverse((node) => {
    if ((node as Mesh).isMesh) {
      (node as Mesh).material = material;
    }
  });
  group.add(gltf.scene);
  tagMeshes(group, part.id);
  return group;
}

/**
 * Build the scene group from a scene document. Loading is atomic: a failed part rejects
 * the whole call so the caller can keep the previous scene on screen.
 */
export async function buildSceneGroup(
  doc: SceneDoc,
  loadBytes: (meshPath: string) => Promise<ArrayBuffer>,
): Promise<LoadedScene> {
  if (doc.schemaVersion !== 1) {
    throw new Error(`unsupported scene schemaVersion ${doc.schemaVersion}`);
  }
  if (doc.units !== "mm") {
    throw new Error(`unsupported scene units ${doc.units}`);
  }

  const root = new Group();
  root.name = `scene:${doc.project}/${doc.model}`;
  const parts = new Map<string, Object3D>();
  for (const part of doc.parts) {
    const bytes = await loadBytes(part.mesh);
    const group = await loadPart(part, bytes);
    parts.set(part.id, group);
    root.add(group);
  }

  root.updateMatrixWorld(true);
  return { root, parts, bounds: new Box3().setFromObject(root) };
}

/** Release GPU resources for a scene group; safe to call on a partly loaded scene. */
export function disposeScene(scene: LoadedScene | null): void {
  if (!scene) return;
  scene.root.traverse((node) => {
    const mesh = node as Mesh;
    mesh.geometry?.dispose();
    const material = mesh.material;
    if (Array.isArray(material)) material.forEach((m) => m.dispose());
    else material?.dispose();
  });
  scene.root.removeFromParent();
}

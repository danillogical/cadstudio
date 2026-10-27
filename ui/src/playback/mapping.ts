/** Trajectory bodies as Three objects: one group per body, its meshes at their local geom poses. */
import { Box3, Color, Group, Mesh, MeshStandardMaterial, Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PART_ID_KEY, tagMeshes, type LoadedScene } from "../scene/mapping";
import type { TrajectoryDoc } from "../transport/types";
import type { Pose } from "./frames";

/** Body colours, cycled by body index. */
export const BODY_COLORS = ["#6f9a86", "#c98b4f", "#5f86b5", "#b56f8c", "#9a9a5f", "#7f6fb5", "#5fa8a8"];
/** Opacity of a body toggled transparent. */
export const TRANSPARENT_OPACITY = 0.25;

/** A loaded trajectory: `parts` maps body name to its group, `bodies` is in `doc.bodies` order. */
export interface LoadedTrajectory extends LoadedScene {
  bodies: Object3D[];
  /** One material per body, shared by all of its meshes. */
  materials: MeshStandardMaterial[];
}

/** Three quaternions are `(x, y, z, w)`; the trajectory stores `[w, x, y, z]`. */
export function applyPose(object: Object3D, pose: Pose): void {
  object.position.set(pose.position[0], pose.position[1], pose.position[2]);
  const [w, x, y, z] = pose.quaternion;
  object.quaternion.set(x, y, z, w);
}

/** Move every body to its pose; `poses` is index-aligned with `bodies`. */
export function applyPoses(bodies: readonly Object3D[], poses: readonly Pose[]): void {
  const n = Math.min(bodies.length, poses.length);
  for (let k = 0; k < n; k += 1) applyPose(bodies[k], poses[k]);
}

/** Make one body see-through (or opaque again). */
export function setTransparent(material: MeshStandardMaterial, transparent: boolean): void {
  material.transparent = transparent;
  material.opacity = transparent ? TRANSPARENT_OPACITY : 1;
  material.depthWrite = !transparent;
  material.needsUpdate = true;
}

/**
 * Build the body groups from a trajectory. Mesh GLBs are body-local millimetres; each mesh
 * gets its geom pose, and the body group is later posed per frame by `applyPoses`. Loading is
 * atomic: any failed mesh rejects so the caller can keep the previous trajectory.
 */
export async function buildTrajectoryGroup(
  doc: TrajectoryDoc,
  loadBytes: (meshPath: string) => Promise<ArrayBuffer>,
  initial: readonly Pose[] = [],
): Promise<LoadedTrajectory> {
  const root = new Group();
  root.name = `trajectory:${doc.runId}`;
  const parts = new Map<string, Object3D>();
  const bodies: Object3D[] = [];
  const materials: MeshStandardMaterial[] = [];
  const bytes = new Map<string, Promise<ArrayBuffer>>();
  const loader = new GLTFLoader();

  for (const [index, body] of doc.bodies.entries()) {
    const group = new Group();
    group.name = body.name;
    group.userData[PART_ID_KEY] = body.name;
    const material = new MeshStandardMaterial({
      color: new Color(BODY_COLORS[index % BODY_COLORS.length]),
      roughness: 0.7,
      metalness: 0.05,
    });
    for (const mesh of body.meshes) {
      let pending = bytes.get(mesh.mesh);
      if (!pending) {
        pending = loadBytes(mesh.mesh);
        bytes.set(mesh.mesh, pending);
      }
      const gltf = await loader.parseAsync(await pending, "");
      gltf.scene.traverse((node) => {
        if ((node as Mesh).isMesh) (node as Mesh).material = material;
      });
      const local = new Group();
      local.name = mesh.geom;
      applyPose(local, {
        position: [mesh.pose[0], mesh.pose[1], mesh.pose[2]],
        quaternion: [mesh.pose[3], mesh.pose[4], mesh.pose[5], mesh.pose[6]],
      });
      local.add(gltf.scene);
      group.add(local);
    }
    tagMeshes(group, body.name);
    if (initial[index]) applyPose(group, initial[index]);
    parts.set(body.name, group);
    bodies.push(group);
    materials.push(material);
    root.add(group);
  }

  root.updateMatrixWorld(true);
  return { root, parts, bounds: new Box3().setFromObject(root), bodies, materials };
}

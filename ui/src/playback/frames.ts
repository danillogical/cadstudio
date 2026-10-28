/**
 * Pure trajectory maths: validate `trajectory.json`, decode `poses.bin` / `contacts.bin`,
 * look frames and phases up by sim time, and interpolate poses (lerp + shortest-path slerp).
 * No Three.js or DOM here, so every function is unit-testable in plain Node.
 */
import type { ContactsInfo, Phase, TrajectoryBody, TrajectoryDoc } from "../transport/types";

export type Vec3 = [number, number, number];
/** Quaternion in MuJoCo order `[w, x, y, z]`. */
export type Quat = [number, number, number, number];

export interface Pose {
  /** Millimetres. */
  position: Vec3;
  /** Unit quaternion `[w, x, y, z]`. */
  quaternion: Quat;
}

/** Floats per body per frame in `poses.bin`: `x, y, z, qw, qx, qy, qz`. */
export const POSE_STRIDE = 7;
/** Floats per contact in `contacts.bin`: `frame, x, y, z, nx, ny, nz, normalForce`. */
export const CONTACT_STRIDE = 8;
/** Above this |dot|, slerp falls back to a normalised lerp to avoid dividing by sin(~0). */
export const SLERP_LINEAR_THRESHOLD = 0.9995;

/** `trajectory.json`, `poses.bin` or `contacts.bin` does not match the export contract. */
export class TrajectoryFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TrajectoryFormatError";
  }
}

function fail(message: string): never {
  throw new TrajectoryFormatError(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finite(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(`${what} must be a finite number`);
  return value;
}

function count(value: unknown, what: string, min: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < min) {
    fail(`${what} must be an integer >= ${min}`);
  }
  return value;
}

function text(value: unknown, what: string): string {
  if (typeof value !== "string" || !value) fail(`${what} must be a non-empty string`);
  return value;
}

function parseBody(raw: unknown, index: number): TrajectoryBody {
  if (!isRecord(raw)) fail(`bodies[${index}] must be an object`);
  const name = text(raw.name, `bodies[${index}].name`);
  if (typeof raw.fixed !== "boolean") fail(`bodies[${index}].fixed must be a boolean`);
  if (!Array.isArray(raw.meshes)) fail(`bodies[${index}].meshes must be an array`);
  const meshes = raw.meshes.map((mesh, m) => {
    const where = `bodies[${index}].meshes[${m}]`;
    if (!isRecord(mesh)) fail(`${where} must be an object`);
    if (!Array.isArray(mesh.pose) || mesh.pose.length !== POSE_STRIDE) {
      fail(`${where}.pose must have ${POSE_STRIDE} numbers`);
    }
    const pose = mesh.pose.map((v, k) => finite(v, `${where}.pose[${k}]`));
    return {
      geom: text(mesh.geom, `${where}.geom`),
      mesh: text(mesh.mesh, `${where}.mesh`),
      pose: pose as TrajectoryBody["meshes"][number]["pose"],
    };
  });
  let removedAt: number | null = null;
  if (raw.removedAt !== undefined && raw.removedAt !== null) {
    removedAt = finite(raw.removedAt, `bodies[${index}].removedAt`);
  }
  return { name, fixed: raw.fixed, meshes, removedAt };
}

/** A body's `removedAt` as a number or `null`; anything that is not a finite number is `null`. */
export function removedAtOf(body: Pick<TrajectoryBody, "removedAt">): number | null {
  const value = body.removedAt;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Whether a body is shown at sim time `t`: a removed body is hidden from `removedAt` on. */
export function bodyVisibleAt(body: Pick<TrajectoryBody, "removedAt">, t: number): boolean {
  const removedAt = removedAtOf(body);
  return removedAt === null || t < removedAt;
}

function parseContactsInfo(raw: unknown): ContactsInfo | null {
  if (raw === null || raw === undefined) return null;
  if (!isRecord(raw)) fail("contacts must be an object or null");
  if (raw.dtype !== "float32" || raw.byteOrder !== "little") {
    fail("contacts must be little-endian float32");
  }
  return {
    path: text(raw.path, "contacts.path"),
    dtype: "float32",
    byteOrder: "little",
    count: count(raw.count, "contacts.count", 0),
    layout: typeof raw.layout === "string" ? raw.layout : "",
    forceUnits: typeof raw.forceUnits === "string" ? raw.forceUnits : "N",
  };
}

/**
 * Validate a `trajectory.json` document and return it typed.
 *
 * Requires `schemaVersion` 1, `units` "mm", at least one frame and one body, `times` of
 * length `frameCount` that is finite and non-decreasing, phases with finite `t0 <= t1`, and
 * `poses.shape` equal to `[frameCount, bodies.length, 7]` as little-endian float32.
 * Throws `TrajectoryFormatError` on any mismatch.
 */
export function parseTrajectory(raw: unknown): TrajectoryDoc {
  if (!isRecord(raw)) fail("trajectory must be a JSON object");
  if (raw.schemaVersion !== 1) fail(`unsupported trajectory schemaVersion ${String(raw.schemaVersion)}`);
  if (raw.units !== "mm") fail(`unsupported trajectory units ${String(raw.units)}`);
  const frameCount = count(raw.frameCount, "frameCount", 1);
  if (!Array.isArray(raw.times) || raw.times.length !== frameCount) {
    fail(`times must have frameCount (${frameCount}) entries`);
  }
  const times = raw.times.map((t, k) => finite(t, `times[${k}]`));
  for (let k = 1; k < times.length; k += 1) {
    if (times[k] < times[k - 1]) fail(`times must be non-decreasing (times[${k}])`);
  }
  if (!Array.isArray(raw.bodies) || raw.bodies.length === 0) fail("bodies must be a non-empty array");
  const bodies = raw.bodies.map(parseBody);
  if (!Array.isArray(raw.phases)) fail("phases must be an array");
  const phases: Phase[] = raw.phases.map((phase, k) => {
    if (!isRecord(phase)) fail(`phases[${k}] must be an object`);
    const t0 = finite(phase.t0, `phases[${k}].t0`);
    const t1 = finite(phase.t1, `phases[${k}].t1`);
    if (t1 < t0) fail(`phases[${k}] ends before it starts`);
    return { name: text(phase.name, `phases[${k}].name`), t0, t1 };
  });
  const poses = raw.poses;
  if (!isRecord(poses)) fail("poses must be an object");
  if (poses.dtype !== "float32" || poses.byteOrder !== "little") {
    fail("poses must be little-endian float32");
  }
  const shape = poses.shape;
  if (
    !Array.isArray(shape) ||
    shape.length !== 3 ||
    shape[0] !== frameCount ||
    shape[1] !== bodies.length ||
    shape[2] !== POSE_STRIDE
  ) {
    fail(`poses.shape must be [${frameCount}, ${bodies.length}, ${POSE_STRIDE}]`);
  }
  return {
    schemaVersion: 1,
    units: "mm",
    runId: typeof raw.runId === "string" ? raw.runId : "",
    manifestSha256: typeof raw.manifestSha256 === "string" ? raw.manifestSha256 : "",
    fps: typeof raw.fps === "number" ? raw.fps : 0,
    frameCount,
    times,
    bodies,
    phases,
    poses: {
      path: text(poses.path, "poses.path"),
      dtype: "float32",
      byteOrder: "little",
      shape: [frameCount, bodies.length, POSE_STRIDE],
      layout: typeof poses.layout === "string" ? poses.layout : "",
      positionUnits: typeof poses.positionUnits === "string" ? poses.positionUnits : "mm",
    },
    contacts: parseContactsInfo(raw.contacts),
  };
}

/** Decode little-endian float32 regardless of host byte order. */
function readFloat32LE(buffer: ArrayBuffer, floats: number): Float32Array {
  const view = new DataView(buffer);
  const out = new Float32Array(floats);
  for (let k = 0; k < floats; k += 1) out[k] = view.getFloat32(k * 4, true);
  return out;
}

/**
 * Decode `poses.bin` into a flat `[frame][body][x,y,z,qw,qx,qy,qz]` array.
 * Throws `TrajectoryFormatError` when the byte length is not `frames * bodies * 7 * 4` or any
 * value is not finite.
 */
export function parsePoses(buffer: ArrayBuffer, frameCount: number, bodyCount: number): Float32Array {
  const floats = frameCount * bodyCount * POSE_STRIDE;
  if (buffer.byteLength !== floats * 4) {
    fail(`poses.bin has ${buffer.byteLength} bytes, expected ${floats * 4}`);
  }
  const poses = readFloat32LE(buffer, floats);
  for (let k = 0; k < poses.length; k += 1) {
    if (!Number.isFinite(poses[k])) fail(`poses.bin value ${k} is not finite`);
  }
  return poses;
}

/** The stored pose of `body` at integer `frame`; throws `RangeError` outside the data. */
export function readPose(poses: Float32Array, bodyCount: number, frame: number, body: number): Pose {
  const frames = bodyCount > 0 ? poses.length / (bodyCount * POSE_STRIDE) : 0;
  if (!Number.isInteger(frame) || frame < 0 || frame >= frames) {
    throw new RangeError(`frame ${frame} is outside 0..${frames - 1}`);
  }
  if (!Number.isInteger(body) || body < 0 || body >= bodyCount) {
    throw new RangeError(`body ${body} is outside 0..${bodyCount - 1}`);
  }
  const o = (frame * bodyCount + body) * POSE_STRIDE;
  return {
    position: [poses[o], poses[o + 1], poses[o + 2]],
    quaternion: [poses[o + 3], poses[o + 4], poses[o + 5], poses[o + 6]],
  };
}

/** Where a time falls between two stored frames: blend `index` toward `next` by `alpha`. */
export interface FrameSample {
  index: number;
  next: number;
  /** In [0, 1); 0 when clamped to an end or when the two frames share a time. */
  alpha: number;
}

/**
 * Locate sim time `t` in the non-decreasing `times`.
 *
 * `index` is the last frame with `times[index] <= t`. Times before the first frame (or NaN)
 * clamp to frame 0 and times at or after the last clamp to the last frame, both with
 * `index === next` and `alpha === 0`. Throws `RangeError` for an empty `times`.
 */
export function frameAt(times: ArrayLike<number>, t: number): FrameSample {
  const n = times.length;
  if (n === 0) throw new RangeError("a trajectory needs at least one frame");
  if (Number.isNaN(t) || t <= times[0]) return { index: 0, next: 0, alpha: 0 };
  if (t >= times[n - 1]) return { index: n - 1, next: n - 1, alpha: 0 };
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) lo = mid;
    else hi = mid;
  }
  const span = times[hi] - times[lo];
  return { index: lo, next: hi, alpha: span > 0 ? (t - times[lo]) / span : 0 };
}

/** The stored frame closest to a sample (ties round toward `next`); used for display and contacts. */
export function nearestFrame(sample: FrameSample): number {
  return sample.alpha >= 0.5 ? sample.next : sample.index;
}

/**
 * Index of the phase containing `t` (`t0 <= t <= t1`), or -1 for none or NaN.
 * At a shared boundary the later phase wins, so phase spans read as half-open except the last.
 */
export function phaseAt(phases: readonly Phase[], t: number): number {
  if (Number.isNaN(t)) return -1;
  for (let k = phases.length - 1; k >= 0; k -= 1) {
    if (phases[k].t0 <= t && t <= phases[k].t1) return k;
  }
  return -1;
}

/** Unit quaternion; a zero or non-finite input becomes the identity `[1, 0, 0, 0]`. */
export function normalizeQuat(q: readonly number[]): Quat {
  const length = Math.hypot(q[0], q[1], q[2], q[3]);
  if (!Number.isFinite(length) || length === 0) return [1, 0, 0, 0];
  return [q[0] / length, q[1] / length, q[2] / length, q[3] / length];
}

function clamp01(alpha: number): number {
  if (Number.isNaN(alpha)) return 0;
  return Math.min(Math.max(alpha, 0), 1);
}

/**
 * Shortest-path spherical interpolation between `a` and `b` (`[w,x,y,z]`, normalised first).
 * `alpha` is clamped to [0, 1]. When `dot(a, b) < 0` `b` is negated so the blend takes the
 * short arc; near-parallel inputs use a normalised lerp. The result is always unit length.
 */
export function slerp(a: readonly number[], b: readonly number[], alpha: number): Quat {
  const t = clamp01(alpha);
  const qa = normalizeQuat(a);
  let qb = normalizeQuat(b);
  let dot = qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3];
  if (dot < 0) {
    qb = [-qb[0], -qb[1], -qb[2], -qb[3]];
    dot = -dot;
  }
  if (dot > SLERP_LINEAR_THRESHOLD) {
    return normalizeQuat([
      qa[0] + (qb[0] - qa[0]) * t,
      qa[1] + (qb[1] - qa[1]) * t,
      qa[2] + (qb[2] - qa[2]) * t,
      qa[3] + (qb[3] - qa[3]) * t,
    ]);
  }
  const theta = Math.acos(Math.min(dot, 1));
  const sin = Math.sin(theta);
  const wa = Math.sin((1 - t) * theta) / sin;
  const wb = Math.sin(t * theta) / sin;
  return normalizeQuat([
    qa[0] * wa + qb[0] * wb,
    qa[1] * wa + qb[1] * wb,
    qa[2] * wa + qb[2] * wb,
    qa[3] * wa + qb[3] * wb,
  ]);
}

/** Linear blend of two points; `alpha` is clamped to [0, 1]. */
export function lerpVec3(a: readonly number[], b: readonly number[], alpha: number): Vec3 {
  const t = clamp01(alpha);
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/** Lerp the positions and slerp the orientations of two poses. */
export function interpolatePose(a: Pose, b: Pose, alpha: number): Pose {
  return {
    position: lerpVec3(a.position, b.position, alpha),
    quaternion: slerp(a.quaternion, b.quaternion, alpha),
  };
}

/**
 * Every body's pose at sim time `t`, interpolated between the two surrounding frames.
 * `t` is clamped to the recorded range, so the first and last frames are returned exactly.
 * `bodies` (index-aligned, optional) holds each body's `removedAt`: a body whose next frame
 * is at or after its removal keeps the earlier frame's pose instead of blending toward it.
 */
export function posesAt(
  times: ArrayLike<number>,
  poses: Float32Array,
  bodyCount: number,
  t: number,
  bodies: readonly Pick<TrajectoryBody, "removedAt">[] = [],
): Pose[] {
  const sample = frameAt(times, t);
  const out: Pose[] = [];
  for (let body = 0; body < bodyCount; body += 1) {
    const a = readPose(poses, bodyCount, sample.index, body);
    // A removed body's later frames hold its off-scene parking pose: never blend toward it.
    const removedAt = bodies[body] ? removedAtOf(bodies[body]) : null;
    const parkedNext = removedAt !== null && times[sample.next] >= removedAt;
    if (sample.next === sample.index || sample.alpha === 0 || parkedNext) {
      out.push({ position: a.position, quaternion: normalizeQuat(a.quaternion) });
    } else {
      out.push(interpolatePose(a, readPose(poses, bodyCount, sample.next, body), sample.alpha));
    }
  }
  return out;
}

export interface ContactPoint {
  frame: number;
  /** Millimetres. */
  position: Vec3;
  /** Unit contact normal from the MuJoCo contact frame. */
  normal: Vec3;
  /** Normal force in newtons. */
  force: number;
}

/**
 * Decode `contacts.bin` into a flat `[contact][frame,x,y,z,nx,ny,nz,normalForce]` array.
 * Throws `TrajectoryFormatError` for a wrong byte length, non-finite values, a frame
 * column that is not an integer in `[0, frameCount)`, or contacts out of frame order.
 */
export function parseContacts(buffer: ArrayBuffer, contactCount: number, frameCount: number): Float32Array {
  const floats = contactCount * CONTACT_STRIDE;
  if (buffer.byteLength !== floats * 4) {
    fail(`contacts.bin has ${buffer.byteLength} bytes, expected ${floats * 4}`);
  }
  const data = readFloat32LE(buffer, floats);
  let previous = 0;
  for (let c = 0; c < contactCount; c += 1) {
    const o = c * CONTACT_STRIDE;
    for (let k = 0; k < CONTACT_STRIDE; k += 1) {
      if (!Number.isFinite(data[o + k])) fail(`contacts.bin contact ${c} is not finite`);
    }
    const frame = data[o];
    if (!Number.isInteger(frame) || frame < 0 || frame >= frameCount) {
      fail(`contacts.bin contact ${c} has frame ${frame} outside 0..${frameCount - 1}`);
    }
    if (frame < previous) fail(`contacts.bin contact ${c} is out of frame order`);
    previous = frame;
  }
  return data;
}

/** Start offsets per frame: contacts of frame `f` are `[index[f], index[f + 1])`. */
export function contactIndex(contacts: Float32Array, frameCount: number): Uint32Array {
  const index = new Uint32Array(frameCount + 1);
  const total = Math.floor(contacts.length / CONTACT_STRIDE);
  let c = 0;
  for (let f = 0; f <= frameCount; f += 1) {
    while (c < total && contacts[c * CONTACT_STRIDE] < f) c += 1;
    index[f] = c;
  }
  return index;
}

/** The contacts recorded at integer `frame`; empty outside the indexed range. */
export function contactsAtFrame(contacts: Float32Array, index: Uint32Array, frame: number): ContactPoint[] {
  if (!Number.isInteger(frame) || frame < 0 || frame >= index.length - 1) return [];
  const out: ContactPoint[] = [];
  for (let c = index[frame]; c < index[frame + 1]; c += 1) {
    const o = c * CONTACT_STRIDE;
    out.push({
      frame,
      position: [contacts[o + 1], contacts[o + 2], contacts[o + 3]],
      normal: [contacts[o + 4], contacts[o + 5], contacts[o + 6]],
      force: contacts[o + 7],
    });
  }
  return out;
}

/**
 * A growing pose buffer for a live run: `poses.bin` is append-only, so the player reads the
 * bytes past what it holds and appends whole frames, trusting only the `frames` count of
 * `live.json`. No Three.js or DOM here.
 */
import type { LiveDoc, TrajectoryDoc } from "../transport/types";
import { POSE_STRIDE, removedAtOf, TrajectoryFormatError } from "./frames";

const FLOAT_BYTES = 4;
const INITIAL_FRAMES = 256;

/** A live run counts as stalled when its frame count has not moved for this long (ms). */
export const LIVE_STALL_MS = 10_000;
/** How often the tail is polled when no event arrives (ms). */
export const LIVE_POLL_MS = 2_000;
/** A trailing playhead further than this behind the newest frame (sim s) is pulled forward. */
export const LIVE_MAX_LAG = 1.5;
/** Where the playhead is put when it is pulled forward: this far behind the newest frame (sim s). */
export const LIVE_TARGET_LAG = 0.3;

export class LiveBuffer {
  readonly bodyCount: number;
  readonly fps: number;
  readonly t0: number;
  /** Sim seconds per frame; this array is shared with the displayed `TrajectoryDoc.times`. */
  readonly times: number[] = [];
  /** Capacity-sized; only the first `frames * bodyCount * 7` floats are valid. */
  poses: Float32Array;
  frames = 0;

  constructor(bodyCount: number, fps: number, t0: number) {
    this.bodyCount = bodyCount;
    this.fps = fps > 0 ? fps : 30;
    this.t0 = t0;
    this.poses = new Float32Array(INITIAL_FRAMES * bodyCount * POSE_STRIDE);
  }

  get frameBytes(): number {
    return this.bodyCount * POSE_STRIDE * FLOAT_BYTES;
  }

  /** Where the next fetch starts: the end of the last whole frame held. */
  get byteOffset(): number {
    return this.frames * this.frameBytes;
  }

  /**
   * Append the whole frames in `bytes` (which start at `byteOffset`), stopping at `limit`
   * total frames. A trailing partial frame, or frames past `limit`, are ignored and fetched
   * again next time. Returns the frames appended; throws on non-finite poses.
   */
  append(bytes: ArrayBuffer, limit: number): number {
    const available = Math.floor(bytes.byteLength / this.frameBytes);
    const count = Math.max(0, Math.min(available, limit - this.frames));
    if (count === 0) return 0;
    const perFrame = this.bodyCount * POSE_STRIDE;
    const need = (this.frames + count) * perFrame;
    if (need > this.poses.length) {
      const grown = new Float32Array(Math.max(need, this.poses.length * 2));
      grown.set(this.poses.subarray(0, this.frames * perFrame));
      this.poses = grown;
    }
    const view = new DataView(bytes);
    const base = this.frames * perFrame;
    for (let k = 0; k < count * perFrame; k += 1) {
      const value = view.getFloat32(k * FLOAT_BYTES, true);
      if (!Number.isFinite(value)) throw new TrajectoryFormatError(`live poses value ${base + k} is not finite`);
      this.poses[base + k] = value;
    }
    for (let k = 0; k < count; k += 1) this.times.push(this.t0 + (this.frames + k) / this.fps);
    this.frames += count;
    return count;
  }
}

/** The last phase's open end (`t1: null`) is closed at `now` so every phase has finite bounds. */
function closePhases(live: LiveDoc, now: number): TrajectoryDoc["phases"] {
  return live.phases.map((phase) => ({ name: phase.name, t0: phase.t0, t1: phase.t1 ?? Math.max(now, phase.t0) }));
}

/** A `TrajectoryDoc` view of a live run, sharing `buffer.times`, for the regular player code. */
export function liveTrajectoryDoc(live: LiveDoc, liveId: string, buffer: LiveBuffer): TrajectoryDoc {
  const frames = buffer.frames;
  return {
    schemaVersion: 1,
    units: "mm",
    runId: liveId,
    manifestSha256: "",
    fps: buffer.fps,
    frameCount: frames,
    times: buffer.times,
    bodies: live.bodies,
    phases: closePhases(live, buffer.times[frames - 1] ?? buffer.t0),
    poses: {
      path: live.poses.path,
      dtype: "float32",
      byteOrder: "little",
      shape: [frames, live.bodies.length, POSE_STRIDE],
      layout: live.poses.layout,
      positionUnits: live.poses.positionUnits,
    },
    contacts: null,
  };
}

/** Refresh the phases of a live `TrajectoryDoc` from the latest `live.json`. */
export function updateLivePhases(doc: TrajectoryDoc, live: LiveDoc, buffer: LiveBuffer): void {
  doc.phases = closePhases(live, buffer.times[buffer.frames - 1] ?? buffer.t0);
}

/**
 * Copy each body's `removedAt` from the latest `live.json` into a live `TrajectoryDoc`. The
 * writer stamps it the moment a body is removed, before any later frame is published. A body
 * is matched by index and name; a missing or non-numeric value leaves the body shown.
 */
export function updateLiveRemovals(doc: TrajectoryDoc, live: LiveDoc): void {
  doc.bodies = doc.bodies.map((body, k) => {
    const latest = live.bodies[k];
    if (!latest || latest.name !== body.name) return body;
    const removedAt = removedAtOf(latest);
    return removedAt === removedAtOf(body) ? body : { ...body, removedAt };
  });
}

/** Whether a `live.json` has what the player needs to start: bodies and at least one frame. */
export function liveReady(live: LiveDoc): boolean {
  return live.bodies.length > 0 && live.frames >= 1 && live.t0 !== null;
}

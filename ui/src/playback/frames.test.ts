import { describe, expect, it } from "vitest";
import {
  contactIndex,
  contactsAtFrame,
  frameAt,
  interpolatePose,
  nearestFrame,
  parseContacts,
  parsePoses,
  parseTrajectory,
  phaseAt,
  posesAt,
  readPose,
  slerp,
  TrajectoryFormatError,
  type Quat,
} from "./frames";

function buffer(values: number[], littleEndian = true): ArrayBuffer {
  const buf = new ArrayBuffer(values.length * 4);
  const view = new DataView(buf);
  values.forEach((v, k) => view.setFloat32(k * 4, v, littleEndian));
  return buf;
}

const Z90: Quat = [Math.SQRT1_2, 0, 0, Math.SQRT1_2];
const Z45: Quat = [Math.cos(Math.PI / 8), 0, 0, Math.sin(Math.PI / 8)];
const IDENT: Quat = [1, 0, 0, 0];

/** Angle in radians of the rotation taking `a` to `b` (sign-insensitive). */
function angleBetween(a: readonly number[], b: readonly number[]): number {
  const dot = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]);
  return 2 * Math.acos(Math.min(1, dot));
}

function validDoc(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: 1,
    units: "mm",
    runId: "r",
    manifestSha256: "x",
    fps: 2,
    frameCount: 3,
    times: [0, 0.5, 1],
    bodies: [
      { name: "a", fixed: true, meshes: [{ geom: "g", mesh: "m.glb", pose: [0, 0, 0, 1, 0, 0, 0] }] },
      { name: "b", fixed: false, meshes: [] },
    ],
    phases: [{ name: "p", t0: 0, t1: 1 }],
    poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", shape: [3, 2, 7], layout: "l", positionUnits: "mm" },
    contacts: null,
    ...overrides,
  };
}

describe("parsePoses", () => {
  // 2 frames x 2 bodies, each float encodes frame*100 + body*10 + component.
  const values: number[] = [];
  for (let f = 0; f < 2; f += 1) for (let b = 0; b < 2; b += 1) for (let c = 0; c < 7; c += 1) values.push(f * 100 + b * 10 + c);

  it("reads [frame][body][x,y,z,qw,qx,qy,qz] for a multi-frame multi-body fixture", () => {
    const poses = parsePoses(buffer(values), 2, 2);
    expect(poses.length).toBe(28);
    expect(readPose(poses, 2, 0, 0)).toEqual({ position: [0, 1, 2], quaternion: [3, 4, 5, 6] });
    expect(readPose(poses, 2, 0, 1)).toEqual({ position: [10, 11, 12], quaternion: [13, 14, 15, 16] });
    expect(readPose(poses, 2, 1, 0)).toEqual({ position: [100, 101, 102], quaternion: [103, 104, 105, 106] });
    expect(readPose(poses, 2, 1, 1)).toEqual({ position: [110, 111, 112], quaternion: [113, 114, 115, 116] });
  });

  it("requires the exact byte length", () => {
    expect(() => parsePoses(buffer(values.slice(0, 27)), 2, 2)).toThrow(TrajectoryFormatError);
    expect(() => parsePoses(buffer([...values, 0]), 2, 2)).toThrow(TrajectoryFormatError);
    expect(() => parsePoses(new ArrayBuffer(3), 2, 2)).toThrow(TrajectoryFormatError);
  });

  it("decodes little-endian, and big-endian bytes do not give the same values", () => {
    const le = parsePoses(buffer(values, true), 2, 2);
    expect(Array.from(le)).toEqual(values);
    const be = parsePoses(buffer([1, 2, 3, 4, 5, 6, 7], false), 1, 1);
    expect(Array.from(be)).not.toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("rejects non-finite values", () => {
    for (const bad of [NaN, Infinity, -Infinity]) {
      const v = [...values];
      v[9] = bad;
      expect(() => parsePoses(buffer(v), 2, 2)).toThrow(TrajectoryFormatError);
    }
  });

  it("readPose rejects out-of-range indices", () => {
    const poses = parsePoses(buffer(values), 2, 2);
    expect(() => readPose(poses, 2, 2, 0)).toThrow(RangeError);
    expect(() => readPose(poses, 2, -1, 0)).toThrow(RangeError);
    expect(() => readPose(poses, 2, 0, 2)).toThrow(RangeError);
    expect(() => readPose(poses, 2, 0.5, 0)).toThrow(RangeError);
  });
});

describe("parseTrajectory", () => {
  it("accepts a valid document", () => {
    const doc = parseTrajectory(validDoc());
    expect(doc.frameCount).toBe(3);
    expect(doc.bodies).toHaveLength(2);
    expect(doc.poses.shape).toEqual([3, 2, 7]);
    expect(doc.contacts).toBeNull();
  });

  it("accepts equal consecutive times", () => {
    expect(() => parseTrajectory(validDoc({ times: [0, 0, 1] }))).not.toThrow();
  });

  const bad: Array<[string, Record<string, unknown>]> = [
    ["schemaVersion", { schemaVersion: 2 }],
    ["units", { units: "m" }],
    ["frameCount zero", { frameCount: 0, times: [] }],
    ["frameCount fractional", { frameCount: 2.5 }],
    ["times length", { times: [0, 1] }],
    ["times decreasing", { times: [0, 1, 0.5] }],
    ["times non-finite", { times: [0, NaN, 1] }],
    ["times not array", { times: "x" }],
    ["no bodies", { bodies: [], poses: { path: "p", dtype: "float32", byteOrder: "little", shape: [3, 0, 7] } }],
    ["body without name", { bodies: [{ fixed: true, meshes: [] }] }],
    ["body fixed not boolean", { bodies: [{ name: "a", fixed: 1, meshes: [] }] }],
    ["mesh pose length", { bodies: [{ name: "a", fixed: true, meshes: [{ geom: "g", mesh: "m", pose: [0, 0, 0] }] }] }],
    ["phases not array", { phases: {} }],
    ["phase reversed", { phases: [{ name: "p", t0: 1, t1: 0 }] }],
    ["phase non-finite", { phases: [{ name: "p", t0: NaN, t1: 1 }] }],
    ["poses missing", { poses: undefined }],
    ["poses big-endian", { poses: { path: "p", dtype: "float32", byteOrder: "big", shape: [3, 2, 7] } }],
    ["poses dtype", { poses: { path: "p", dtype: "float64", byteOrder: "little", shape: [3, 2, 7] } }],
    ["poses shape frames", { poses: { path: "p", dtype: "float32", byteOrder: "little", shape: [2, 2, 7] } }],
    ["poses shape bodies", { poses: { path: "p", dtype: "float32", byteOrder: "little", shape: [3, 1, 7] } }],
    ["poses shape stride", { poses: { path: "p", dtype: "float32", byteOrder: "little", shape: [3, 2, 6] } }],
    ["contacts big-endian", { contacts: { path: "c", dtype: "float32", byteOrder: "big", count: 1 } }],
  ];
  it.each(bad)("rejects bad %s", (_name, overrides) => {
    expect(() => parseTrajectory(validDoc(overrides))).toThrow(TrajectoryFormatError);
  });

  it("rejects non-objects", () => {
    for (const v of [null, undefined, 3, "x", []]) expect(() => parseTrajectory(v)).toThrow(TrajectoryFormatError);
  });

  it("parses a contacts descriptor", () => {
    const doc = parseTrajectory(
      validDoc({ contacts: { path: "contacts.bin", dtype: "float32", byteOrder: "little", count: 4, layout: "l", forceUnits: "N" } }),
    );
    expect(doc.contacts?.count).toBe(4);
    expect(doc.contacts?.path).toBe("contacts.bin");
  });
});

describe("frameAt", () => {
  const times = [0, 1, 3];
  it("clamps before the first frame", () => {
    expect(frameAt(times, -5)).toEqual({ index: 0, next: 0, alpha: 0 });
  });
  it("clamps after the last frame", () => {
    expect(frameAt(times, 99)).toEqual({ index: 2, next: 2, alpha: 0 });
  });
  it("is exact on a frame time", () => {
    expect(frameAt(times, 0)).toEqual({ index: 0, next: 0, alpha: 0 });
    const s = frameAt(times, 1);
    expect(s.index).toBe(1);
    expect(s.alpha).toBe(0);
    expect(frameAt(times, 3)).toEqual({ index: 2, next: 2, alpha: 0 });
  });
  it("interpolates midway", () => {
    expect(frameAt(times, 0.5)).toEqual({ index: 0, next: 1, alpha: 0.5 });
    expect(frameAt(times, 2)).toEqual({ index: 1, next: 2, alpha: 0.5 });
  });
  it("handles duplicate times without dividing by zero", () => {
    const dup = [0, 1, 1, 2];
    for (const t of [0, 0.5, 1, 1.5, 2]) {
      const s = frameAt(dup, t);
      expect(Number.isFinite(s.alpha)).toBe(true);
      expect(s.alpha).toBeGreaterThanOrEqual(0);
      expect(s.alpha).toBeLessThanOrEqual(1);
      expect(dup[s.index]).toBeLessThanOrEqual(t);
    }
    // At the duplicated time the later of the two frames is the "last frame <= t".
    expect(frameAt(dup, 1).index).toBe(2);
  });
  it("treats NaN as the first frame", () => {
    expect(frameAt(times, NaN)).toEqual({ index: 0, next: 0, alpha: 0 });
  });
  it("handles a single frame", () => {
    expect(frameAt([5], 0)).toEqual({ index: 0, next: 0, alpha: 0 });
    expect(frameAt([5], 5)).toEqual({ index: 0, next: 0, alpha: 0 });
    expect(frameAt([5], 9)).toEqual({ index: 0, next: 0, alpha: 0 });
  });
  it("throws for empty times", () => {
    expect(() => frameAt([], 0)).toThrow(RangeError);
  });
  it("accepts a Float64Array and many frames", () => {
    const big = Float64Array.from({ length: 1000 }, (_, k) => k * 0.01);
    const s = frameAt(big, 5.005);
    expect(s.index).toBe(500);
    expect(s.alpha).toBeCloseTo(0.5, 6);
  });
  it("nearestFrame rounds ties toward next", () => {
    expect(nearestFrame({ index: 3, next: 4, alpha: 0.49 })).toBe(3);
    expect(nearestFrame({ index: 3, next: 4, alpha: 0.5 })).toBe(4);
    expect(nearestFrame({ index: 3, next: 3, alpha: 0 })).toBe(3);
  });
});

describe("phaseAt", () => {
  const phases = [
    { name: "a", t0: 0, t1: 1 },
    { name: "b", t0: 1, t1: 2 },
    { name: "c", t0: 3, t1: 4 },
  ];
  it("finds the containing phase", () => {
    expect(phaseAt(phases, 0.5)).toBe(0);
    expect(phaseAt(phases, 1.5)).toBe(1);
    expect(phaseAt(phases, 3.5)).toBe(2);
  });
  it("lets the later phase win at a shared boundary", () => {
    expect(phaseAt(phases, 1)).toBe(1);
  });
  it("includes both ends of the first and last phases", () => {
    expect(phaseAt(phases, 0)).toBe(0);
    expect(phaseAt(phases, 4)).toBe(2);
  });
  it("returns -1 in gaps and outside", () => {
    expect(phaseAt(phases, 2.5)).toBe(-1);
    expect(phaseAt(phases, -0.1)).toBe(-1);
    expect(phaseAt(phases, 4.1)).toBe(-1);
  });
  it("returns -1 for NaN and for no phases", () => {
    expect(phaseAt(phases, NaN)).toBe(-1);
    expect(phaseAt([], 1)).toBe(-1);
  });
});

describe("slerp", () => {
  it("returns the endpoints at alpha 0 and 1", () => {
    const a = slerp(IDENT, Z90, 0);
    const b = slerp(IDENT, Z90, 1);
    expect(angleBetween(a, IDENT)).toBeCloseTo(0, 6);
    expect(angleBetween(b, Z90)).toBeCloseTo(0, 6);
  });
  it("gives 45 degrees about Z halfway from identity to 90 degrees about Z", () => {
    const q = slerp(IDENT, Z90, 0.5);
    const sign = Math.sign(q[0]) || 1;
    expect(q[0] * sign).toBeCloseTo(Z45[0], 6);
    expect(q[1] * sign).toBeCloseTo(0, 6);
    expect(q[2] * sign).toBeCloseTo(0, 6);
    expect(q[3] * sign).toBeCloseTo(Z45[3], 6);
  });
  it("takes the shortest arc: q and -q are the same rotation", () => {
    const neg: Quat = [-Z90[0], -Z90[1], -Z90[2], -Z90[3]];
    const viaPos = slerp(IDENT, Z90, 0.5);
    const viaNeg = slerp(IDENT, neg, 0.5);
    expect(angleBetween(viaPos, viaNeg)).toBeCloseTo(0, 6);
    // Halfway is 45 degrees, not the 225 degrees of the long way round.
    expect(angleBetween(viaNeg, IDENT)).toBeCloseTo(Math.PI / 4, 6);
  });
  it("does not spin for identical rotations with opposite sign", () => {
    for (const t of [0.1, 0.5, 0.9]) {
      const q = slerp(Z90, [-Z90[0], -Z90[1], -Z90[2], -Z90[3]], t);
      expect(angleBetween(q, Z90)).toBeCloseTo(0, 5);
    }
  });
  it("keeps the angle monotonic along the path", () => {
    let last = -1;
    for (let k = 0; k <= 10; k += 1) {
      const angle = angleBetween(slerp(IDENT, Z90, k / 10), IDENT);
      expect(angle).toBeGreaterThanOrEqual(last - 1e-9);
      last = angle;
    }
    expect(last).toBeCloseTo(Math.PI / 2, 6);
  });
  it("returns unit quaternions", () => {
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      const q = slerp([0.3, 0.1, -0.7, 0.2], [-0.5, 0.4, 0.3, 0.9], t);
      expect(Math.hypot(...q)).toBeCloseTo(1, 9);
    }
  });
  it("handles near-parallel inputs", () => {
    const a: Quat = [1, 0, 0, 0];
    const b: Quat = [Math.cos(1e-4), 0, 0, Math.sin(1e-4)];
    const q = slerp(a, b, 0.5);
    expect(Math.hypot(...q)).toBeCloseTo(1, 9);
    expect(q.every(Number.isFinite)).toBe(true);
    expect(angleBetween(q, a)).toBeCloseTo(1e-4, 6);
    expect(angleBetween(slerp(a, a, 0.5), a)).toBeCloseTo(0, 9);
  });
  it("clamps alpha", () => {
    expect(angleBetween(slerp(IDENT, Z90, -3), IDENT)).toBeCloseTo(0, 6);
    expect(angleBetween(slerp(IDENT, Z90, 7), Z90)).toBeCloseTo(0, 6);
    expect(angleBetween(slerp(IDENT, Z90, NaN), IDENT)).toBeCloseTo(0, 6);
  });
  it("normalises unnormalised inputs", () => {
    const q = slerp([2, 0, 0, 0], [2 * Z90[0], 0, 0, 2 * Z90[3]], 0.5);
    expect(Math.hypot(...q)).toBeCloseTo(1, 9);
    expect(angleBetween(q, Z45)).toBeCloseTo(0, 6);
  });
  it("treats a zero quaternion as identity instead of producing NaN", () => {
    const q = slerp([0, 0, 0, 0], Z90, 0.5);
    expect(q.every(Number.isFinite)).toBe(true);
  });
});

describe("pose interpolation", () => {
  it("lerps positions and slerps orientation", () => {
    const p = interpolatePose(
      { position: [0, 0, 0], quaternion: IDENT },
      { position: [10, -20, 30], quaternion: Z90 },
      0.5,
    );
    expect(p.position).toEqual([5, -10, 15]);
    expect(angleBetween(p.quaternion, Z45)).toBeCloseTo(0, 6);
  });

  // 3 frames x 2 bodies.
  const times = [0, 1, 2];
  const poses = new Float32Array([
    0, 0, 0, 1, 0, 0, 0, 5, 5, 5, 1, 0, 0, 0,
    10, 0, 0, Z90[0], 0, 0, Z90[3], 5, 5, 5, 1, 0, 0, 0,
    20, 0, 0, 1, 0, 0, 0, 7, 8, 9, 1, 0, 0, 0,
  ]);

  it("interpolates every body at its own pair of frames", () => {
    const out = posesAt(times, poses, 2, 0.5);
    expect(out[0].position).toEqual([5, 0, 0]);
    expect(out[1].position).toEqual([5, 5, 5]);
    const second = posesAt(times, poses, 2, 1.5);
    expect(second[0].position).toEqual([15, 0, 0]);
    expect(second[1].position[0]).toBeCloseTo(6, 6);
    expect(second[1].position[2]).toBeCloseTo(7, 6);
  });
  it("returns the exact recorded frames when clamped at both ends", () => {
    const first = posesAt(times, poses, 2, -10);
    const last = posesAt(times, poses, 2, 100);
    expect(first[0]).toEqual({ position: [0, 0, 0], quaternion: [1, 0, 0, 0] });
    expect(first[1].position).toEqual([5, 5, 5]);
    expect(last[0].position).toEqual([20, 0, 0]);
    expect(last[1].position).toEqual([7, 8, 9]);
    expect(posesAt(times, poses, 2, 0)[0].position).toEqual([0, 0, 0]);
    expect(posesAt(times, poses, 2, 2)[1].position).toEqual([7, 8, 9]);
  });
});

describe("contacts", () => {
  // [frame, x, y, z, nx, ny, nz, force]
  const row = (frame: number, x: number) => [frame, x, x + 1, x + 2, 0, 0, 1, x * 10];

  it("parses and indexes per-frame offsets including empty frames", () => {
    const values = [...row(0, 1), ...row(0, 2), ...row(2, 3), ...row(4, 4)];
    const data = parseContacts(buffer(values), 4, 5);
    const index = contactIndex(data, 5);
    expect(Array.from(index)).toEqual([0, 2, 2, 3, 3, 4]);
    expect(contactsAtFrame(data, index, 0)).toHaveLength(2);
    expect(contactsAtFrame(data, index, 1)).toEqual([]);
    expect(contactsAtFrame(data, index, 3)).toEqual([]);
    expect(contactsAtFrame(data, index, 2)).toEqual([
      { frame: 2, position: [3, 4, 5], normal: [0, 0, 1], force: 30 },
    ]);
    expect(contactsAtFrame(data, index, 4)[0].position).toEqual([4, 5, 6]);
  });

  it("returns [] for out-of-range or non-integer frames", () => {
    const data = parseContacts(buffer(row(1, 1)), 1, 2);
    const index = contactIndex(data, 2);
    for (const f of [-1, 2, 99, 0.5, NaN]) expect(contactsAtFrame(data, index, f)).toEqual([]);
  });

  it("handles no contacts at all", () => {
    const data = parseContacts(new ArrayBuffer(0), 0, 3);
    const index = contactIndex(data, 3);
    expect(Array.from(index)).toEqual([0, 0, 0, 0]);
    expect(contactsAtFrame(data, index, 1)).toEqual([]);
  });

  it("rejects out-of-order frames", () => {
    expect(() => parseContacts(buffer([...row(2, 1), ...row(1, 2)]), 2, 5)).toThrow(TrajectoryFormatError);
  });
  it("rejects wrong length, non-finite, bad frame columns", () => {
    expect(() => parseContacts(buffer(row(0, 1)), 2, 5)).toThrow(TrajectoryFormatError);
    expect(() => parseContacts(buffer([...row(0, 1), 0]), 1, 5)).toThrow(TrajectoryFormatError);
    const nan = row(0, 1);
    nan[7] = NaN;
    expect(() => parseContacts(buffer(nan), 1, 5)).toThrow(TrajectoryFormatError);
    expect(() => parseContacts(buffer(row(5, 1)), 1, 5)).toThrow(TrajectoryFormatError);
    expect(() => parseContacts(buffer(row(-1, 1)), 1, 5)).toThrow(TrajectoryFormatError);
    expect(() => parseContacts(buffer(row(1.5, 1)), 1, 5)).toThrow(TrajectoryFormatError);
  });
  it("decodes little-endian only", () => {
    const be = buffer(row(0, 1), false);
    // Big-endian bytes read as LE either fail validation or differ from the intended values.
    let decoded: Float32Array | null = null;
    try {
      decoded = parseContacts(be, 1, 5);
    } catch (error) {
      expect(error).toBeInstanceOf(TrajectoryFormatError);
    }
    if (decoded) expect(Array.from(decoded)).not.toEqual(row(0, 1));
  });
});

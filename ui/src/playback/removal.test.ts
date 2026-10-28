// @vitest-environment happy-dom
/**
 * `removedAt` in playback, from the behaviour spec: a removed body is hidden from `removedAt`
 * on, holds its earlier pose across the removal, and never widens a fit. Final and live
 * playback run through the real controller, `buildTrajectoryGroup` and `Viewport`; only the
 * renderer and the GLB parser are replaced.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class FakeRenderer {
    domElement = document.createElement("canvas");
    setPixelRatio() {}
    setSize() {}
    render() {}
    dispose() {}
  }
  return { ...actual, WebGLRenderer: FakeRenderer };
});

vi.mock("three/examples/jsm/loaders/GLTFLoader.js", async () => {
  const { BoxGeometry, Group, Mesh } = await import("three");
  class GLTFLoader {
    async parseAsync() {
      const scene = new Group();
      scene.add(new Mesh(new BoxGeometry(10, 10, 10)));
      return { scene };
    }
  }
  return { GLTFLoader };
});

import type { ArtifactRange, CadStudioTransport, LiveDoc, TrajectoryBody, TrajectoryResponse } from "../transport/types";
import { Viewport } from "../viewport/viewport";
import { PlaybackController, type PlaybackElements } from "./controller";
import { posesAt } from "./frames";

const FPS = 10;
const PARKED_X = 10_000; // 10 m in mm
const FRAME_BYTES = 2 * 28; // two bodies
const LIVE_ID = "p/runs/r1";
const BASE = `${LIVE_ID}.live`;
const REMOVED_AT = 0.55;

const mesh = (name: string) => ({ geom: `${name}_g`, mesh: `meshes/${name}.glb`, pose: [0, 0, 0, 1, 0, 0, 0] as [number, number, number, number, number, number, number] });
const body = (name: string, removedAt: number | null): TrajectoryBody => ({ name, fixed: false, meshes: [mesh(name)], removedAt });

/** Body 0 ("base") stays at the origin. Body 1 ("pkt") moves +x by 1 per frame, and is parked
 * at 10 m from `parkedFrom` on. */
function poseBytes(frames: number, parkedFrom: number, bodies = 2): ArrayBuffer {
  const floats = new Float32Array(frames * bodies * 7);
  for (let k = 0; k < frames; k += 1) {
    floats.set([0, 0, 0, 1, 0, 0, 0], (k * bodies) * 7);
    if (bodies > 1) floats.set([k >= parkedFrom ? PARKED_X : k, 0, 0, 1, 0, 0, 0], (k * bodies + 1) * 7);
  }
  return floats.buffer;
}

function elements(): PlaybackElements {
  const el = <T extends HTMLElement>(tag: string) => document.createElement(tag) as T;
  return {
    panel: el("section"), banner: el("div"), play: el("button"), restart: el("button"),
    seek: el("input"), speed: el("input"), speedLabel: el("span"), time: el("span"),
    phase: el("span"), frame: el("span"), bodies: el("div"), contacts: el("input"), contactsNote: el("div"),
    liveBadge: el("span"),
  };
}

function trajectory(runId: string, frames: number, bodies: TrajectoryBody[]): TrajectoryResponse {
  return {
    schemaVersion: 1, runId, stale: false, error: null, artifactBase: `${runId}.gui`,
    trajectory: {
      schemaVersion: 1, units: "mm", runId, manifestSha256: "x", fps: FPS, frameCount: frames,
      times: Array.from({ length: frames }, (_, k) => k / FPS),
      bodies,
      phases: [{ name: "all", t0: 0, t1: (frames - 1) / FPS }],
      poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", shape: [frames, bodies.length, 7], layout: "", positionUnits: "mm" },
      contacts: null,
    },
  };
}

interface LiveServer {
  frames: number;
  removedAt: number | null;
  /** First frame at which the pkt is parked. */
  parkedFrom: number;
}

function liveDoc(server: LiveServer): LiveDoc {
  return {
    schemaVersion: 1, units: "mm", liveId: LIVE_ID, fps: FPS, t0: 0, frames: server.frames,
    simTime: (server.frames - 1) / FPS, plannedTime: 5,
    bodies: [body("base", null), body("pkt", server.removedAt)] as never,
    phases: [{ name: "all", t0: 0, t1: null }],
    poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", layout: "", positionUnits: "mm", frameBytes: FRAME_BYTES },
    done: false, status: null, runId: null, error: null,
  };
}

function setup(options: { runs?: Record<string, { frames: number; bodies: TrajectoryBody[] }>; live?: LiveServer } = {}) {
  document.body.replaceChildren();
  const container = document.createElement("div");
  document.body.append(container);
  const viewport = new Viewport(container);
  viewport.setActiveLayer("trajectory");
  const els = elements();
  const runs = options.runs ?? {};
  const live = options.live;
  let now = 0;
  const transport = {
    getTrajectory: async (runId: string) => {
      const run = runs[runId];
      if (!run) throw new Error(`no run ${runId}`);
      return trajectory(runId, run.frames, run.bodies);
    },
    getLive: async () => liveDoc(live!),
  } as unknown as CadStudioTransport;
  const loadBytes = async (path: string, range?: ArtifactRange): Promise<ArrayBuffer> => {
    if (path.endsWith("poses.bin")) {
      if (path === `${BASE}/poses.bin`) {
        const file = poseBytes(live!.frames, live!.parkedFrom);
        return file.slice(range?.offset ?? 0);
      }
      const runId = path.replace(/\.gui\/poses\.bin$/, "");
      const run = runs[runId];
      return poseBytes(run.frames, Math.ceil(REMOVED_AT * FPS), run.bodies.length);
    }
    return new ArrayBuffer(0); // the mocked GLB parser ignores the bytes
  };
  const controller = new PlaybackController({
    transport,
    viewport: viewport.layer("trajectory"),
    elements: els,
    loadBytes,
    now: () => now,
    requestFrame: () => 0,
    cancelFrame: () => {},
  });
  const settle = () => vi.advanceTimersByTimeAsync(0);
  return { controller, viewport, els, settle, live };
}

const bodiesOf = (controller: PlaybackController) => controller.state.artifact!.scene.bodies;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("posesAt holds a body across its removal", () => {
  it("does not blend toward the parking pose between the last frame before and the first after", () => {
    const times = [0, 0.1, 0.2];
    const poses = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, PARKED_X, 0, 0, 1, 0, 0, 0]);
    // Removed at 0.15: frame 2 (t=0.2) is the first one after.
    const removed = [{ removedAt: 0.15 }];
    for (const t of [0.1, 0.12, 0.149]) expect(posesAt(times, poses, 1, t, removed)[0].position[0]).toBe(1);
    // Without removal info the same query slides toward the parking spot.
    expect(posesAt(times, poses, 1, 0.12).at(0)!.position[0]).toBeGreaterThan(1000);
  });
});

describe("final trajectory", () => {
  const bodies = [body("base", null), body("pkt", REMOVED_AT)];

  it("shows a removed body before removedAt and hides it from removedAt on", async () => {
    const { controller } = setup({ runs: { a: { frames: 10, bodies } } });
    await controller.openRun("a");
    const [, pkt] = bodiesOf(controller);
    controller.seek(0.5);
    expect(pkt.visible).toBe(true);
    controller.seek(0.549);
    expect(pkt.visible).toBe(true);
    controller.seek(REMOVED_AT);
    expect(pkt.visible).toBe(false);
    controller.seek(0.9);
    expect(pkt.visible).toBe(false);
    controller.seek(0.2); // scrubbing back shows it again
    expect(pkt.visible).toBe(true);
    expect(bodiesOf(controller)[0].visible).toBe(true);
  });

  it("holds the earlier pose between the last frame before and the first after the removal", async () => {
    const { controller } = setup({ runs: { a: { frames: 10, bodies } } });
    await controller.openRun("a");
    const [, pkt] = bodiesOf(controller);
    // Frame 5 (t=0.5) is at x=5; frame 6 (t=0.6) is parked at 10 m.
    for (const t of [0.5, 0.52, 0.549]) {
      controller.seek(t);
      expect(pkt.visible).toBe(true);
      expect(pkt.position.x).toBe(5);
    }
  });
});

describe("live playback", () => {
  it("hides the body once live.json stamps removedAt and holds its pose across the removal", async () => {
    const server: LiveServer = { frames: 5, removedAt: null, parkedFrom: 6 };
    const { controller, settle } = setup({ live: server });
    await controller.openLive(LIVE_ID);
    await settle();
    const [, pkt] = bodiesOf(controller);
    controller.seek(0.3);
    expect(pkt.visible).toBe(true);

    // The run advances past the removal; live.json now carries removedAt.
    server.frames = 9;
    server.removedAt = REMOVED_AT;
    controller.handleLive({ liveId: LIVE_ID, frames: 9, done: false });
    await settle();
    await settle();

    controller.seek(0.5);
    expect(pkt.visible).toBe(true);
    controller.seek(0.54);
    expect(pkt.visible).toBe(true);
    expect(pkt.position.x).toBe(5); // held, not sliding toward 10 m
    controller.seek(REMOVED_AT);
    expect(pkt.visible).toBe(false);
    controller.seek(0.8);
    expect(pkt.visible).toBe(false);
  });

  it("opens with the body hidden when live.json already has removedAt", async () => {
    const server: LiveServer = { frames: 9, removedAt: REMOVED_AT, parkedFrom: 6 };
    const { controller, settle } = setup({ live: server });
    await controller.openLive(LIVE_ID);
    await settle();
    const [, pkt] = bodiesOf(controller);
    controller.seek(0.8);
    expect(pkt.visible).toBe(false);
    controller.seek(0.1);
    expect(pkt.visible).toBe(true);
  });
});

describe("fit ignores removed bodies", () => {
  const withRemoved = [body("base", null), body("pkt", REMOVED_AT)];
  const withoutBody = [body("base", null)];
  const camera = (viewport: Viewport) => ({ position: viewport.camera.position.toArray(), target: viewport.controls.target.toArray() });

  async function referenceFit() {
    const ref = setup({ runs: { r: { frames: 10, bodies: withoutBody } } });
    await ref.controller.openRun("r");
    ref.viewport.fit();
    return camera(ref.viewport);
  }

  it("the Fit button / F key path (viewport.fit) at a time after removal matches a scene without the body", async () => {
    const expected = await referenceFit();
    const { controller, viewport } = setup({ runs: { a: { frames: 10, bodies: withRemoved } } });
    await controller.openRun("a");
    controller.seek(0.8);
    expect(bodiesOf(controller)[1].position.x).toBe(PARKED_X);
    viewport.fit();
    expect(camera(viewport)).toEqual(expected);
  });

  it("the same fit before removal does include the body, so the comparison is meaningful", async () => {
    const expected = await referenceFit();
    const { controller, viewport } = setup({ runs: { a: { frames: 10, bodies: withRemoved } } });
    await controller.openRun("a");
    controller.seek(0.5);
    viewport.fit();
    expect(camera(viewport)).not.toEqual(expected);
  });

  it("auto-fit on opening a run whose body is already removed excludes it", async () => {
    const expected = await referenceFit();
    const gone = [body("base", null), body("pkt", 0)];
    const { controller, viewport } = setup({ runs: { a: { frames: 10, bodies: gone } } });
    await controller.openRun("a");
    expect(bodiesOf(controller)[1].visible).toBe(false);
    expect(camera(viewport)).toEqual(expected);
  });

  it("a live run fits without the removed body too", async () => {
    const expected = await referenceFit();
    const server: LiveServer = { frames: 9, removedAt: REMOVED_AT, parkedFrom: 6 };
    const { controller, viewport, settle } = setup({ live: server });
    await controller.openLive(LIVE_ID);
    await settle();
    controller.seek(0.8);
    viewport.fit();
    expect(camera(viewport)).toEqual(expected);
  });
});

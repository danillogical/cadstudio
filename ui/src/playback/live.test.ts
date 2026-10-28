// @vitest-environment happy-dom
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { Box3, Group, MeshStandardMaterial, Object3D } from "three";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactRange, CadStudioTransport, LiveDoc, TrajectoryResponse } from "../transport/types";
import { PlaybackController, type PlaybackElements } from "./controller";
import { LiveBuffer, LIVE_STALL_MS } from "./live";
import type { LoadedTrajectory } from "./mapping";

const FPS = 10;
const FRAME_BYTES = 28; // one body: 7 float32
const LIVE_ID = "p/runs/r1";
const BASE = `${LIVE_ID}.live`;

/** Frame `k` of a body that moves along +x: pose `[k, 0, 0, 1, 0, 0, 0]`. */
function poseBytes(from: number, to: number, partialBytes = 0): ArrayBuffer {
  const floats = new Float32Array((to - from) * 7 + partialBytes / 4);
  for (let k = from; k < to; k += 1) floats.set([k, 0, 0, 1, 0, 0, 0], (k - from) * 7);
  return floats.buffer.slice(0, (to - from) * FRAME_BYTES + partialBytes);
}

const BODY = { name: "box", fixed: false, meshes: [{ geom: "g", mesh: "meshes/box.glb", pose: [0, 0, 0, 1, 0, 0, 0] as const }] };

/** What the service has on disk: `poses.bin` may be ahead of what `live.json` announces. */
class FakeLiveServer {
  frames = 5;
  written = 5;
  extraPartialBytes = 0;
  done = false;
  runId: string | null = null;
  fetches: Array<{ path: string; offset: number | undefined }> = [];
  liveReads = 0;

  doc(): LiveDoc {
    return {
      schemaVersion: 1,
      units: "mm",
      liveId: LIVE_ID,
      fps: FPS,
      t0: 0,
      frames: this.frames,
      simTime: (this.frames - 1) / FPS,
      plannedTime: 5,
      bodies: this.frames > 0 ? [{ ...BODY, meshes: [{ ...BODY.meshes[0], pose: [...BODY.meshes[0].pose] }] }] : [],
      phases: [{ name: "fall", t0: 0, t1: null }],
      poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", layout: "", positionUnits: "mm", frameBytes: FRAME_BYTES },
      done: this.done,
      status: this.done ? "pass" : null,
      runId: this.runId,
      error: null,
    };
  }

  file(): ArrayBuffer {
    return poseBytes(0, this.written, this.extraPartialBytes);
  }
}

function finalTrajectory(runId: string, frames: number): TrajectoryResponse {
  return {
    schemaVersion: 1,
    runId,
    stale: false,
    error: null,
    artifactBase: `${runId}.gui`,
    trajectory: {
      schemaVersion: 1,
      units: "mm",
      runId,
      manifestSha256: "x",
      fps: FPS,
      frameCount: frames,
      times: Array.from({ length: frames }, (_, k) => k / FPS),
      bodies: [BODY],
      phases: [{ name: "fall", t0: 0, t1: (frames - 1) / FPS }],
      poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", shape: [frames, 1, 7], layout: "", positionUnits: "mm" },
      contacts: null,
    },
  };
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

interface Options {
  /** Frames in the finished trajectory of run `runId`. */
  finalFrames?: number;
  /** Frames for plain `openRun` runs, by run id. */
  runs?: Record<string, number>;
  /** Run `requestFrame` normally (a test drives frames by hand through `frames`). */
}

function setup(options: Options = {}) {
  const server = new FakeLiveServer();
  const els = elements();
  let now = 0;
  const frames: Array<() => void> = [];
  const runFrames = new Map<string, number>(Object.entries(options.runs ?? {}));
  if (options.finalFrames) runFrames.set(LIVE_ID, options.finalFrames);
  const transport = {
    getLive: async (id: string) => {
      server.liveReads += 1;
      expect(id).toBe(LIVE_ID);
      return server.doc();
    },
    getTrajectory: async (runId: string) => {
      const count = runFrames.get(runId);
      if (count === undefined) throw new Error(`no run ${runId}`);
      return finalTrajectory(runId, count);
    },
  } as unknown as CadStudioTransport;
  const loadBytes = async (path: string, range?: ArtifactRange): Promise<ArrayBuffer> => {
    if (path === `${BASE}/poses.bin`) {
      server.fetches.push({ path, offset: range?.offset });
      const file = server.file();
      const offset = range?.offset ?? 0;
      return offset >= file.byteLength ? new ArrayBuffer(0) : file.slice(offset);
    }
    const match = /^(.*)\.gui\/poses\.bin$/.exec(path);
    if (match) return poseBytes(0, runFrames.get(match[1]) ?? 0);
    throw new Error(`unexpected artifact ${path}`);
  };
  const scenes: unknown[] = [];
  const controller = new PlaybackController({
    transport,
    viewport: { setScene: (s) => scenes.push(s), setHighlight: () => {}, requestRender: () => {} },
    elements: els,
    loadBytes,
    buildTrajectory: async (): Promise<LoadedTrajectory> => {
      const body = new Object3D();
      return { root: new Group(), parts: new Map([["box", body]]), bounds: new Box3(), bodies: [body], materials: [new MeshStandardMaterial()] };
    },
    now: () => now,
    // Throttled rAF: the callback is queued and only a test ever runs it.
    requestFrame: (cb) => frames.push(cb),
    cancelFrame: () => {},
  });
  /** Move wall time and the fake timers together, in small steps so interval ticks see the right `now`. */
  const advance = async (ms: number) => {
    for (let left = ms; left > 0; left -= 50) {
      const step = Math.min(50, left);
      now += step;
      await vi.advanceTimersByTimeAsync(step);
    }
  };
  const settle = () => vi.advanceTimersByTimeAsync(0);
  return { controller, els, server, frames, advance, settle, scenes, runFrames, wall: () => now };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

type Harness = ReturnType<typeof setup>;

function live(h: Harness) {
  const run = h.controller.state.artifact;
  if (!run?.live) throw new Error("no live run on screen");
  return { run, live: run.live };
}

async function openLive(h: Harness) {
  await h.controller.openLive(LIVE_ID);
  await h.settle();
}

describe("live: opening", () => {
  it("opens a live run, loads the poses so far, and autoplays at 1x", async () => {
    const h = setup();
    await openLive(h);
    const { run, live: state } = live(h);
    expect(h.controller.liveId).toBe(LIVE_ID);
    expect(state.buffer.frames).toBe(5);
    expect(run.doc.frameCount).toBe(5);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.speed).toBe(1);
    expect(h.controller.autoplaying).toBe(true);
    expect(h.els.panel.hidden).toBe(false);
    expect(h.els.liveBadge!.hidden).toBe(false);
    expect(h.els.liveBadge!.dataset.state).toBe("live");
    // The first read is the whole file; no Range yet.
    expect(h.server.fetches[0]).toEqual({ path: `${BASE}/poses.bin`, offset: undefined });
    for (let k = 0; k < 5; k += 1) expect(run.poses[k * 7]).toBe(k);
  });

  it("plays at 1x even when the previous run was at another speed", async () => {
    const h = setup({ runs: { a: 3 } });
    await h.controller.openRun("a", { autoplay: true });
    h.controller.setSpeed(3);
    await openLive(h);
    expect(h.controller.speed).toBe(1);
    expect(h.controller.playing).toBe(true);
  });

  it("waits for the first frames, then opens when a live event arrives", async () => {
    const h = setup();
    h.server.frames = 0;
    h.server.written = 0;
    await h.controller.openLive(LIVE_ID);
    expect(h.controller.state.artifact).toBeNull();
    expect(h.controller.liveId).toBe(LIVE_ID);
    h.server.frames = 3;
    h.server.written = 3;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 3, done: false });
    await h.settle();
    expect(live(h).live.buffer.frames).toBe(3);
    expect(h.controller.playing).toBe(true);
  });
});

describe("live: growing", () => {
  it("fetches new bytes from frames_loaded x frameBytes and appends them", async () => {
    const h = setup();
    await openLive(h);
    h.server.fetches.length = 0;

    h.server.frames = 8;
    h.server.written = 8;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 8, done: false });
    await h.settle();
    expect(h.server.fetches).toEqual([{ path: `${BASE}/poses.bin`, offset: 5 * FRAME_BYTES }]);
    expect(live(h).live.buffer.frames).toBe(8);

    h.server.frames = 12;
    h.server.written = 12;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 12, done: false });
    await h.settle();
    expect(h.server.fetches.at(-1)).toEqual({ path: `${BASE}/poses.bin`, offset: 8 * FRAME_BYTES });

    const { run } = live(h);
    expect(run.doc.frameCount).toBe(12);
    expect(run.doc.times).toHaveLength(12);
    for (let k = 0; k < 12; k += 1) {
      expect(run.poses[k * 7], `frame ${k}`).toBe(k);
      expect(run.doc.times[k]).toBeCloseTo(k / FPS, 6);
    }
  });

  it("uses only whole frames up to live.json's frame count, even if extra bytes arrive", async () => {
    const h = setup();
    h.server.frames = 5;
    h.server.written = 8; // poses.bin is ahead of live.json ...
    h.server.extraPartialBytes = 10; // ... and ends in a torn frame
    await openLive(h);
    expect(live(h).live.buffer.frames).toBe(5);
    expect(live(h).run.doc.frameCount).toBe(5);
    expect(live(h).run.doc.times).toHaveLength(5);

    h.server.frames = 7;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 7, done: false });
    await h.settle();
    // The tail came back with frames 5..8 and a torn one; only up to 7 are kept.
    expect(h.server.fetches.at(-1)?.offset).toBe(5 * FRAME_BYTES);
    expect(live(h).live.buffer.frames).toBe(7);
    expect(live(h).run.doc.times).toHaveLength(7);
    expect(live(h).live.buffer.byteOffset).toBe(7 * FRAME_BYTES);
  });

  it("never exposes a frame past the announced count to the clock", async () => {
    const h = setup();
    h.server.written = 9;
    await openLive(h);
    await h.advance(5000);
    expect(h.controller.time).toBeCloseTo(4 / FPS, 6);
  });

  it("does not fetch when no new frames are announced", async () => {
    const h = setup();
    await openLive(h);
    h.server.fetches.length = 0;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 5, done: false });
    await h.settle();
    expect(h.server.fetches).toEqual([]);
  });

  it("ignores a live event for another run", async () => {
    const h = setup();
    await openLive(h);
    h.server.fetches.length = 0;
    h.server.frames = 9;
    h.server.written = 9;
    h.controller.handleLive({ liveId: "p/runs/other", frames: 9, done: false });
    await h.settle();
    expect(h.server.fetches).toEqual([]);
    expect(live(h).live.buffer.frames).toBe(5);
  });

  it("LiveBuffer keeps a torn trailing frame out and stops at the limit", () => {
    const buffer = new LiveBuffer(1, FPS, 0);
    expect(buffer.append(poseBytes(0, 4, 12), 3)).toBe(3);
    expect(buffer.frames).toBe(3);
    expect(buffer.byteOffset).toBe(3 * FRAME_BYTES);
    expect(buffer.append(poseBytes(3, 4, 12), 10)).toBe(1);
    expect(buffer.times.map((t) => Math.round(t * FPS))).toEqual([0, 1, 2, 3]);
    expect(buffer.append(new ArrayBuffer(0), 10)).toBe(0);
  });
});

describe("live: playhead", () => {
  it("holds at the newest frame instead of stopping, and resumes when more frames arrive", async () => {
    const h = setup();
    await openLive(h);
    await h.advance(3000);
    // Caught up: still playing, parked on the newest frame.
    expect(h.controller.playing).toBe(true);
    expect(h.controller.time).toBeCloseTo(4 / FPS, 6);
    expect(h.els.play.textContent).toBe("Pause");
    expect(h.els.frame.textContent).toBe("frame 4 / 4");
    await h.advance(2000);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.time).toBeCloseTo(4 / FPS, 6);

    h.server.frames = 12;
    h.server.written = 12;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 12, done: false });
    await h.settle();
    await h.advance(300);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.time).toBeCloseTo(4 / FPS + 0.3, 1);
    await h.advance(300);
    expect(h.controller.time).toBeCloseTo(4 / FPS + 0.6, 1);
    await h.advance(2000);
    expect(h.controller.time).toBeCloseTo(11 / FPS, 6);
    expect(h.controller.playing).toBe(true);
  });

  it("does not loop a live run while it is still being written", async () => {
    const h = setup();
    await openLive(h);
    await h.advance(10_000);
    expect(h.controller.time).toBeCloseTo(4 / FPS, 6);
  });
});

describe("live: stalled", () => {
  it("shows a stalled state after 10 s without frame growth", async () => {
    expect(LIVE_STALL_MS).toBe(10_000);
    const h = setup();
    await openLive(h);
    await h.advance(9000);
    expect(live(h).live.stalled).toBe(false);
    expect(h.els.liveBadge!.dataset.state).toBe("live");
    await h.advance(2000);
    expect(live(h).live.stalled).toBe(true);
    expect(h.els.liveBadge!.dataset.state).toBe("stalled");
    expect(h.els.liveBadge!.textContent).toContain("STALLED");
  });

  it("is not stalled while frames keep growing", async () => {
    const h = setup();
    await openLive(h);
    for (let i = 0; i < 5; i += 1) {
      await h.advance(4000);
      h.server.frames += 2;
      h.server.written += 2;
      h.controller.handleLive({ liveId: LIVE_ID, frames: h.server.frames, done: false });
      await h.settle();
    }
    expect(live(h).live.stalled).toBe(false);
    expect(h.els.liveBadge!.dataset.state).toBe("live");
  });

  it("leaves the stalled state when frames arrive again", async () => {
    const h = setup();
    await openLive(h);
    await h.advance(12_000);
    expect(live(h).live.stalled).toBe(true);
    h.server.frames = 8;
    h.server.written = 8;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 8, done: false });
    await h.settle();
    expect(live(h).live.stalled).toBe(false);
    expect(h.els.liveBadge!.dataset.state).toBe("live");
  });
});

describe("live: done", () => {
  async function finish(h: Harness, frames: number) {
    h.server.frames = frames;
    h.server.written = frames;
    h.server.done = true;
    h.server.runId = LIVE_ID;
    h.controller.handleLive({ liveId: LIVE_ID, frames, done: true });
    await h.settle();
  }

  it("swaps to the final trajectory without losing play state, then loops", async () => {
    const h = setup({ finalFrames: 8 });
    await openLive(h);
    await h.advance(500);
    const before = h.controller.time!;
    await finish(h, 8);
    expect(h.controller.state.artifact?.live).toBeNull();
    expect(h.controller.displayedRunId).toBe(LIVE_ID);
    expect(h.controller.state.artifact?.doc.frameCount).toBe(8);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.speed).toBe(1);
    expect(h.controller.autoplaying).toBe(true);
    expect(h.controller.time!).toBeGreaterThanOrEqual(before - 1e-6);
    expect(h.els.liveBadge!.hidden).toBe(true);

    // It now loops: after the 0.7 s run ends it restarts instead of stopping.
    await h.advance(600);
    const wrapped: number[] = [];
    for (let i = 0; i < 40; i += 1) {
      await h.advance(100);
      wrapped.push(h.controller.time!);
      expect(h.controller.playing).toBe(true);
    }
    expect(Math.max(...wrapped)).toBeLessThanOrEqual(7 / FPS + 1e-6);
    expect(wrapped.some((t, i) => i > 0 && t < wrapped[i - 1])).toBe(true);
  });

  it("swaps to the final trajectory when the run id differs from the live id", async () => {
    const h = setup({ runs: { "p/runs/final": 8 } });
    await openLive(h);
    h.server.frames = 8;
    h.server.written = 8;
    h.server.done = true;
    h.server.runId = "p/runs/final";
    h.controller.handleLive({ liveId: LIVE_ID, frames: 8, done: true });
    await h.settle();
    expect(h.controller.displayedRunId).toBe("p/runs/final");
    expect(h.controller.state.artifact?.live).toBeNull();
    expect(h.controller.playing).toBe(true);
  });

  it("stays paused across the swap if the user had paused", async () => {
    const h = setup({ finalFrames: 8 });
    await openLive(h);
    h.controller.toggle();
    expect(h.controller.playing).toBe(false);
    await finish(h, 8);
    expect(h.controller.state.artifact?.live).toBeNull();
    expect(h.controller.playing).toBe(false);
    expect(h.controller.autoplaying).toBe(false);
  });

  it("appends the last frames before swapping, so the final run is complete", async () => {
    const h = setup({ finalFrames: 12 });
    await openLive(h);
    await finish(h, 12);
    expect(h.controller.state.artifact?.doc.frameCount).toBe(12);
    expect(h.server.fetches.at(-1)?.offset).toBe(5 * FRAME_BYTES);
  });

  it("opens an already-finished live run as a normal looping trajectory", async () => {
    const h = setup({ finalFrames: 8 });
    h.server.frames = 8;
    h.server.written = 8;
    h.server.done = true;
    h.server.runId = LIVE_ID;
    await openLive(h);
    expect(h.controller.state.artifact?.live).toBeNull();
    expect(h.controller.displayedRunId).toBe(LIVE_ID);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.autoplaying).toBe(true);
  });
});

describe("autoplay and loop on a run", () => {
  const A = "p/runs/a";
  const B = "p/runs/b";

  it("plays at once and loops when opened with autoplay", async () => {
    const h = setup({ runs: { [A]: 11 } }); // 1.0 s
    await h.controller.openRun(A, { autoplay: true });
    expect(h.controller.playing).toBe(true);
    expect(h.controller.autoplaying).toBe(true);
    expect(h.controller.speed).toBe(1);
    await h.advance(500);
    expect(h.controller.time).toBeCloseTo(0.5, 1);
    await h.advance(700);
    // 1.2 s of wall time on a 1.0 s run: it wrapped and is playing again.
    expect(h.controller.playing).toBe(true);
    expect(h.controller.time!).toBeLessThan(0.5);
    await h.advance(2000);
    expect(h.controller.playing).toBe(true);
  });

  it("does not play, or loop, when opened without autoplay", async () => {
    const h = setup({ runs: { [A]: 11 } });
    await h.controller.openRun(A);
    expect(h.controller.playing).toBe(false);
    expect(h.controller.autoplaying).toBe(false);
    h.controller.toggle();
    await h.advance(1500);
    expect(h.controller.playing).toBe(false);
    expect(h.controller.time).toBeCloseTo(1.0, 6);
  });

  it("a manual pause disables autoplay, and play turns it back on", async () => {
    const h = setup({ runs: { [A]: 11 } });
    await h.controller.openRun(A, { autoplay: true });
    await h.advance(300);
    h.controller.toggle();
    expect(h.controller.playing).toBe(false);
    expect(h.controller.autoplaying).toBe(false);
    const paused = h.controller.time!;
    await h.advance(3000);
    expect(h.controller.playing).toBe(false);
    expect(h.controller.time).toBe(paused);

    h.controller.toggle();
    expect(h.controller.playing).toBe(true);
    expect(h.controller.autoplaying).toBe(true);
    await h.advance(2500);
    expect(h.controller.playing).toBe(true); // it loops again
  });

  it("a manual pause stops a run from looping once it ends", async () => {
    const h = setup({ runs: { [A]: 11 } });
    await h.controller.openRun(A, { autoplay: true });
    await h.advance(200);
    h.controller.toggle(); // pause
    h.controller.seek(0.95);
    h.controller.toggle(); // play
    h.controller.toggle(); // pause again
    await h.advance(2000);
    expect(h.controller.playing).toBe(false);
  });

  it("opening a new run with autoplay resumes playback after a pause", async () => {
    const h = setup({ runs: { [A]: 11, [B]: 21 } });
    await h.controller.openRun(A, { autoplay: true });
    h.controller.toggle();
    expect(h.controller.autoplaying).toBe(false);
    await h.controller.openRun(B, { autoplay: true });
    expect(h.controller.displayedRunId).toBe(B);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.autoplaying).toBe(true);
    await h.advance(2500);
    expect(h.controller.playing).toBe(true); // 2.0 s run looped
  });

  it("opening a new run without autoplay clears the autoplay of the old one", async () => {
    const h = setup({ runs: { [A]: 11, [B]: 21 } });
    await h.controller.openRun(A, { autoplay: true });
    await h.controller.openRun(B);
    expect(h.controller.playing).toBe(false);
    expect(h.controller.autoplaying).toBe(false);
  });
});

describe("focus independence", () => {
  const RUN = "p/runs/long";

  it("advances time at wall-clock rate when requestFrame never calls back", async () => {
    const h = setup({ runs: { [RUN]: 301 } }); // 30 s
    await h.controller.openRun(RUN, { autoplay: true });
    expect(h.frames.length).toBeGreaterThan(0); // a frame was requested and will never run
    await h.advance(1000);
    expect(h.controller.time!).toBeGreaterThan(0.9);
    expect(h.controller.time!).toBeLessThanOrEqual(1.0 + 1e-6);
    await h.advance(4000);
    expect(h.controller.time!).toBeGreaterThan(4.9);
    expect(h.controller.time!).toBeLessThanOrEqual(5.0 + 1e-6);
    expect(h.els.time.textContent).toMatch(/^[45]\.\d{3} \/ 30\.000 s$/);
  });

  it("keeps the speed multiplier under the interval fallback", async () => {
    const h = setup({ runs: { [RUN]: 301 } });
    await h.controller.openRun(RUN, { autoplay: true });
    h.controller.setSpeed(2);
    await h.advance(2000);
    expect(h.controller.time!).toBeGreaterThan(3.8);
    expect(h.controller.time!).toBeLessThanOrEqual(4.0 + 1e-6);
  });

  it("does not run the interval while paused", async () => {
    const h = setup({ runs: { [RUN]: 301 } });
    await h.controller.openRun(RUN, { autoplay: true });
    await h.advance(500);
    h.controller.toggle();
    const t = h.controller.time;
    await h.advance(2000);
    expect(h.controller.time).toBe(t);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps advancing through visibilitychange and blur", async () => {
    const h = setup({ runs: { [RUN]: 301 } });
    await h.controller.openRun(RUN, { autoplay: true });
    await h.advance(500);
    const hidden = Object.getOwnPropertyDescriptor(Document.prototype, "hidden");
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    try {
      document.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("blur"));
      document.dispatchEvent(new Event("blur"));
      document.body.dispatchEvent(new Event("blur"));
      expect(h.controller.playing).toBe(true);
      await h.advance(1500);
      expect(h.controller.playing).toBe(true);
      expect(h.controller.time!).toBeGreaterThan(1.9);
      expect(h.controller.time!).toBeLessThanOrEqual(2.0 + 1e-6);
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
      await h.advance(1000);
      expect(h.controller.time!).toBeGreaterThan(2.9);
      expect(h.controller.time!).toBeLessThanOrEqual(3.0 + 1e-6);
    } finally {
      delete (document as unknown as Record<string, unknown>).hidden;
      delete (document as unknown as Record<string, unknown>).visibilityState;
      if (hidden) Object.defineProperty(Document.prototype, "hidden", hidden);
    }
  });

  it("keeps a live run playing through visibilitychange and blur with rAF throttled", async () => {
    const h = setup();
    await openLive(h);
    window.dispatchEvent(new Event("blur"));
    document.dispatchEvent(new Event("visibilitychange"));
    await h.advance(200);
    expect(h.controller.playing).toBe(true);
    h.server.frames = 15;
    h.server.written = 15;
    h.controller.handleLive({ liveId: LIVE_ID, frames: 15, done: false });
    await h.settle();
    const t = h.controller.time!;
    window.dispatchEvent(new Event("blur"));
    await h.advance(1000);
    expect(h.controller.playing).toBe(true);
    expect(h.controller.time!).toBeGreaterThan(t + 0.9);
  });

  it("no UI source listens for visibilitychange or blur", () => {
    const root = join(process.cwd(), "src");
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.ts$/.test(name) && !/\.test\.ts$/.test(name)) files.push(path);
      }
    };
    walk(root);
    expect(files.length).toBeGreaterThan(5);
    for (const file of files) {
      const source = readFileSync(file, "utf8");
      expect(source, file).not.toMatch(/visibilitychange|visibilityState|document\.hidden|["']blur["']|\bonblur\b/);
    }
  });
});

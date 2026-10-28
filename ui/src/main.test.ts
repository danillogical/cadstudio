// @vitest-environment happy-dom
/**
 * The page wiring in `main.ts` against a fake transport: follow on by default, a live run that
 * opens and autoplays, and `navigate` to a run that autoplays and loops. Three.js and the GLB
 * mapping are replaced; everything else (controllers, follow manager, DOM) is real.
 */
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveDoc, ServiceEvent, TrajectoryResponse } from "./transport/types";

const hoisted = vi.hoisted(() => ({
  transport: null as unknown,
}));

vi.mock("./viewport/viewport", () => {
  class Viewport {
    activeLayer = "scene";
    onPick = () => {};
    layer(_name: string) {
      return { setScene: () => {}, setHighlight: () => {}, requestRender: () => {} };
    }
    setActiveLayer(layer: string) {
      this.activeLayer = layer;
    }
    setLayerHighlight() {}
    fit() {}
    dispose() {}
  }
  return { Viewport };
});

vi.mock("./playback/mapping", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./playback/mapping")>();
  const { Box3, Group, MeshStandardMaterial, Object3D } = await import("three");
  return {
    ...actual,
    applyPoses: () => {},
    setTransparent: () => {},
    buildTrajectoryGroup: async (doc: { bodies: unknown[] }) => ({
      root: new Group(),
      parts: new Map(),
      bounds: new Box3(),
      bodies: doc.bodies.map(() => new Object3D()),
      materials: doc.bodies.map(() => new MeshStandardMaterial()),
    }),
  };
});

vi.mock("./scene/mapping", () => ({
  buildSceneGroup: async () => {
    const { Box3, Group } = await import("three");
    return { root: new Group(), parts: new Map(), bounds: new Box3() };
  },
  disposeScene: () => {},
}));

vi.mock("./transport/browser", () => ({
  BrowserTransport: { fromLocation: () => hoisted.transport },
}));

vi.mock("./transport/vscode", () => ({
  hasVsCodeApi: () => true,
  VsCodeTransport: { fromWebview: () => hoisted.transport },
}));

const FPS = 10;
const LIVE_ID = "p/runs/live1";
const BODY = { name: "box", fixed: false, meshes: [{ geom: "g", mesh: "meshes/box.glb", pose: [0, 0, 0, 1, 0, 0, 0] }] };

function poseBytes(frames: number): ArrayBuffer {
  const floats = new Float32Array(frames * 7);
  for (let k = 0; k < frames; k += 1) floats.set([k, 0, 0, 1, 0, 0, 0], k * 7);
  return floats.buffer;
}

function trajectory(runId: string, frames: number): TrajectoryResponse {
  return {
    schemaVersion: 1,
    runId,
    stale: false,
    error: null,
    artifactBase: `${runId}.gui`,
    trajectory: {
      schemaVersion: 1, units: "mm", runId, manifestSha256: "x", fps: FPS, frameCount: frames,
      times: Array.from({ length: frames }, (_, k) => k / FPS),
      bodies: [BODY],
      phases: [{ name: "fall", t0: 0, t1: (frames - 1) / FPS }],
      poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", shape: [frames, 1, 7], layout: "", positionUnits: "mm" },
      contacts: null,
    },
  };
}

function liveDoc(frames: number): LiveDoc {
  return {
    schemaVersion: 1, units: "mm", liveId: LIVE_ID, fps: FPS, t0: 0, frames, simTime: (frames - 1) / FPS, plannedTime: 5,
    bodies: [BODY as never],
    phases: [{ name: "fall", t0: 0, t1: null }],
    poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", layout: "", positionUnits: "mm", frameBytes: 28 },
    done: false, status: null, runId: null, error: null,
  };
}

function makeTransport() {
  let listener: (event: ServiceEvent) => void = () => {};
  let navigate: (target: { model: string } | { run: string }) => void = () => {};
  const t = {
    liveFrames: 5,
    follow: vi.fn(async (model: string) => ({ model, expiresAt: 0, leaseSeconds: 60, following: [] })),
    unfollow: vi.fn(async (_model: string) => {}),
    health: vi.fn(async () => ({ schemaVersion: 1, service: "cadstudio", protocolVersion: 1, repoRoot: "/r", pid: 1 })),
    listModels: vi.fn(async () => ({ schemaVersion: 1, projects: [], models: ["p/m", "p/n"] })),
    listRuns: vi.fn(async () => ({
      schemaVersion: 1,
      runs: [
        { runId: "p/runs/a", path: "out/p/runs/a", status: "pass", modified: 1 },
        { runId: "p/runs/b", path: "out/p/runs/b", status: "pass", modified: 2 },
      ],
    })),
    listLive: vi.fn(async () => ({ lives: [] })),
    getLive: vi.fn(async () => liveDoc(t.liveFrames)),
    getTrajectory: vi.fn(async (runId: string) => trajectory(runId, 21)), // 2.0 s
    getScene: vi.fn(async () => {
      throw new Error("no scene in this test");
    }),
    getArtifact: vi.fn(async (path: string, range?: { offset: number }) => {
      if (path.endsWith(".live/poses.bin")) return poseBytes(t.liveFrames).slice(range?.offset ?? 0);
      return poseBytes(21);
    }),
    listPhysicsInputs: vi.fn(async () => ({ schemaVersion: 1, project: "p", model: "m", scenarios: [], acceptance: [], options: [] })),
    startBuild: vi.fn(),
    startRun: vi.fn(),
    getJob: vi.fn(),
    cancelJob: vi.fn(),
    subscribe: vi.fn((l: (event: ServiceEvent) => void) => {
      listener = l;
      return () => {};
    }),
    onNavigate: vi.fn((l: typeof navigate) => {
      navigate = l;
      return () => {};
    }),
    ready: vi.fn(),
    emit: (event: ServiceEvent) => listener(event),
    navigate: (target: { model: string } | { run: string }) => navigate(target),
  };
  return t;
}

type Fake = ReturnType<typeof makeTransport>;

const INDEX_BODY = (() => {
  const html = readFileSync(`${process.cwd()}/index.html`, "utf8");
  const body = /<body[^>]*>([\s\S]*)<\/body>/.exec(html)![1];
  return body.replace(/<script[\s\S]*?<\/script>/g, "");
})();

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const flush = () => vi.advanceTimersByTimeAsync(0);
const advance = (ms: number) => vi.advanceTimersByTimeAsync(ms);

async function boot(prepare: (t: Fake) => void = () => {}): Promise<Fake> {
  vi.resetModules();
  document.body.innerHTML = INDEX_BODY;
  const t = makeTransport();
  prepare(t);
  hoisted.transport = t;
  await import("./main");
  await advance(50);
  return t;
}

async function pickModel(model: string) {
  const picker = $<HTMLSelectElement>("model-picker");
  picker.value = model;
  picker.dispatchEvent(new Event("change"));
  await flush();
}

beforeEach(() => {
  vi.useFakeTimers();
  sessionStorage.clear();
});

afterEach(() => {
  window.dispatchEvent(new Event("pagehide"));
  vi.useRealTimers();
});

describe("main: follow", () => {
  it("is on by default and follows the selected model", async () => {
    const t = await boot();
    expect($<HTMLInputElement>("follow").checked).toBe(true);
    expect(t.follow).not.toHaveBeenCalled(); // two models and none picked
    await pickModel("p/m");
    expect(t.follow.mock.calls).toEqual([["p/m"]]);
  });

  it("renews every 20 s, switches on model change, and unfollows when toggled off", async () => {
    const t = await boot();
    await pickModel("p/m");
    await advance(20_000);
    expect(t.follow.mock.calls).toEqual([["p/m"], ["p/m"]]);

    await pickModel("p/n");
    expect(t.unfollow.mock.calls).toEqual([["p/m"]]);
    expect(t.follow.mock.calls.at(-1)).toEqual(["p/n"]);

    const box = $<HTMLInputElement>("follow");
    box.checked = false;
    box.dispatchEvent(new Event("change"));
    await flush();
    expect(t.unfollow.mock.calls.at(-1)).toEqual(["p/n"]);
    const calls = t.follow.mock.calls.length;
    await advance(60_000);
    expect(t.follow.mock.calls.length).toBe(calls);
  });

  it("remembers an off choice across a reload of the page (sessionStorage)", async () => {
    await boot();
    const box = $<HTMLInputElement>("follow");
    box.checked = false;
    box.dispatchEvent(new Event("change"));
    const t = await boot();
    expect($<HTMLInputElement>("follow").checked).toBe(false);
    await pickModel("p/m");
    expect(t.follow).not.toHaveBeenCalled();
  });

  it("follows a lone model right away", async () => {
    const t = await boot((fake) => {
      fake.listModels.mockResolvedValue({ schemaVersion: 1, projects: [], models: ["p/m"] });
    });
    expect(t.follow.mock.calls).toEqual([["p/m"]]);
  });
});

describe("main: live runs", () => {
  const liveEvent = (frames: number, done = false): ServiceEvent => ({ type: "artifact", kind: "live", liveId: LIVE_ID, frames, done });

  it("a live event for a new liveId opens it, loads poses and autoplays at 1x", async () => {
    const t = await boot();
    t.emit(liveEvent(5));
    await advance(100);
    expect(t.getLive).toHaveBeenCalledWith(LIVE_ID);
    expect(t.getArtifact.mock.calls.some(([path]) => path === `${LIVE_ID}.live/poses.bin`)).toBe(true);
    expect($("playback").hidden).toBe(false);
    expect($("play").textContent).toBe("Pause");
    expect($<HTMLInputElement>("speed").value).toBe("1");
    expect($("live-badge").hidden).toBe(false);
    expect($("stage").dataset.layer).toBe("trajectory");
  });

  it("tails new bytes from frames x frameBytes as later events arrive", async () => {
    const t = await boot();
    t.emit(liveEvent(5));
    await advance(100);
    t.getArtifact.mockClear();
    t.liveFrames = 9;
    t.emit(liveEvent(9));
    await advance(100);
    expect(t.getArtifact.mock.calls).toEqual([[`${LIVE_ID}.live/poses.bin`, { offset: 5 * 28 }]]);
    expect($("play-frame").textContent).toContain("/ 8");
  });

  it("ignores live events while follow is off", async () => {
    const t = await boot();
    const box = $<HTMLInputElement>("follow");
    box.checked = false;
    box.dispatchEvent(new Event("change"));
    t.emit(liveEvent(5));
    await advance(100);
    expect(t.getLive).not.toHaveBeenCalled();
    expect($("playback").hidden).toBe(true);
  });

  it("does not open a run that is already done", async () => {
    const t = await boot();
    t.emit(liveEvent(5, true));
    await advance(100);
    expect(t.getLive).not.toHaveBeenCalled();
  });

  it("keeps playing while the window is blurred or hidden", async () => {
    const t = await boot();
    t.emit(liveEvent(5));
    await advance(100);
    t.liveFrames = 15;
    t.emit(liveEvent(15));
    await advance(100);
    window.dispatchEvent(new Event("blur"));
    document.dispatchEvent(new Event("visibilitychange"));
    const before = $("play-time").textContent;
    await advance(1000);
    expect($("play").textContent).toBe("Pause");
    expect($("play-time").textContent).not.toBe(before);
  });
});

describe("main: navigate to a run", () => {
  it("opens the run, autoplays at 1x and loops", async () => {
    const t = await boot();
    expect(t.ready).toHaveBeenCalledTimes(1);
    t.navigate({ run: "p/runs/a" });
    await advance(100);
    expect(t.getTrajectory).toHaveBeenCalledWith("p/runs/a");
    expect($("stage").dataset.layer).toBe("trajectory");
    expect($("play").textContent).toBe("Pause");
    await advance(1000);
    const midway = Number($("play-time").textContent!.split(" ")[0]);
    expect(midway).toBeGreaterThan(0.8);
    // 2.0 s long; after 2.6 s more it has wrapped and still plays.
    await advance(2600);
    expect($("play").textContent).toBe("Pause");
    const wrapped = Number($("play-time").textContent!.split(" ")[0]);
    expect(wrapped).toBeLessThan(2.0);
  });

  it("a manual pause stops it for good until play is pressed", async () => {
    const t = await boot();
    t.navigate({ run: "p/runs/a" });
    await advance(300);
    $("play").click();
    expect($("play").textContent).toBe("Play");
    const paused = $("play-time").textContent;
    await advance(5000);
    expect($("play-time").textContent).toBe(paused);
    expect($("play").textContent).toBe("Play");
    $("play").click();
    expect($("play").textContent).toBe("Pause");
    await advance(5000);
    expect($("play").textContent).toBe("Pause");
  });

  it("navigating to another run after a pause plays again", async () => {
    const t = await boot();
    t.navigate({ run: "p/runs/a" });
    await advance(300);
    $("play").click();
    t.navigate({ run: "p/runs/b" });
    await advance(300);
    expect(t.getTrajectory).toHaveBeenLastCalledWith("p/runs/b");
    expect($("play").textContent).toBe("Pause");
  });

  it("navigating to a model selects it and follows it", async () => {
    const t = await boot();
    t.navigate({ model: "p/n" });
    await advance(100);
    expect($<HTMLSelectElement>("model-picker").value).toBe("p/n");
    expect(t.follow.mock.calls).toEqual([["p/n"]]);
  });
});

describe("main: model list refresh", () => {
  const MORE = { schemaVersion: 1, projects: [], models: ["p/m", "p/n", "p/new"] };
  const pickerValues = () => [...$<HTMLSelectElement>("model-picker").options].map((o) => o.value);

  it("navigate to an unlisted model lists the models again, then selects it", async () => {
    const t = await boot();
    expect(t.listModels).toHaveBeenCalledTimes(1);
    expect(pickerValues()).not.toContain("p/new");
    t.listModels.mockResolvedValue(MORE);
    t.navigate({ model: "p/new" });
    await advance(100);
    expect(t.listModels).toHaveBeenCalledTimes(2);
    expect($<HTMLSelectElement>("model-picker").value).toBe("p/new");
    expect(t.follow.mock.calls).toEqual([["p/new"]]);
    // The fake getScene rejects, so the banner may show that error, but never "Unknown model".
    expect($("banner").textContent ?? "").not.toContain("Unknown model");
  });

  it("navigate to a listed model does not list again", async () => {
    const t = await boot();
    t.navigate({ model: "p/n" });
    await advance(100);
    expect(t.listModels).toHaveBeenCalledTimes(1);
    expect($<HTMLSelectElement>("model-picker").value).toBe("p/n");
  });

  it("navigate to a model still missing after the refresh shows the unknown-model banner", async () => {
    const t = await boot();
    t.navigate({ model: "p/zzz" });
    await advance(100);
    expect(t.listModels).toHaveBeenCalledTimes(2);
    expect($("banner").hidden).toBe(false);
    expect($("banner").textContent).toContain("Unknown model p/zzz");
    expect($<HTMLSelectElement>("model-picker").value).not.toBe("p/zzz");
  });

  it("a scene artifact for an unlisted model refreshes the picker without switching model", async () => {
    const t = await boot();
    await pickModel("p/m");
    t.follow.mockClear();
    t.listModels.mockResolvedValue(MORE);
    t.emit({ type: "artifact", kind: "scene", model: "p/new" });
    await advance(100);
    expect(t.listModels).toHaveBeenCalledTimes(2);
    expect(pickerValues()).toContain("p/new");
    expect($<HTMLSelectElement>("model-picker").value).toBe("p/m");
    expect(t.follow).not.toHaveBeenCalled();
    expect(t.getScene).not.toHaveBeenCalledWith("p/new");
  });

  it("a scene artifact for a listed model does not refresh the list", async () => {
    const t = await boot();
    await pickModel("p/m");
    t.emit({ type: "artifact", kind: "scene", model: "p/n" });
    await advance(100);
    expect(t.listModels).toHaveBeenCalledTimes(1);
  });
});

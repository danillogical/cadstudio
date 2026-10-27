// @vitest-environment happy-dom
import { Box3, Group, MeshStandardMaterial, Object3D } from "three";
import { describe, expect, it } from "vitest";
import { JobPanel } from "../app/jobs-panel";
import type { CadStudioTransport, Job, TrajectoryResponse } from "../transport/types";
import { PlaybackController, type PlaybackElements } from "./controller";
import type { LoadedTrajectory } from "./mapping";

function trajectory(runId: string): TrajectoryResponse {
  return {
    schemaVersion: 1,
    runId,
    stale: false,
    error: null,
    artifactBase: `${runId}.gui`,
    trajectory: {
      schemaVersion: 1, units: "mm", runId, manifestSha256: "x", fps: 1, frameCount: 2,
      times: [0, 1],
      bodies: [{ name: "box", fixed: false, meshes: [{ geom: "g", mesh: "meshes/box.glb", pose: [0, 0, 0, 1, 0, 0, 0] }] }],
      phases: [{ name: "settle", t0: 0, t1: 1 }],
      poses: { path: "poses.bin", dtype: "float32", byteOrder: "little", shape: [2, 1, 7], layout: "", positionUnits: "mm" },
      contacts: null,
    },
  };
}

const job = (overrides: Partial<Job> = {}): Job => ({
  id: "j1", kind: "run", key: "p/m", model: "p/m", status: "queued", createdAt: 0, startedAt: null,
  finishedAt: null, error: null, exitCode: null, log: [], artifacts: {}, ...overrides,
});

function elements(): PlaybackElements {
  const el = <T extends HTMLElement>(tag: string) => document.createElement(tag) as T;
  return {
    panel: el("section"), banner: el("div"), play: el("button"), restart: el("button"),
    seek: el("input"), speed: el("input"), speedLabel: el("span"), time: el("span"),
    phase: el("span"), frame: el("span"), bodies: el("div"), contacts: el("input"), contactsNote: el("div"),
  };
}

function fakeTransport(responses: Array<TrajectoryResponse | Error>): CadStudioTransport {
  return {
    getTrajectory: async () => {
      const next = responses.shift();
      if (!next || next instanceof Error) throw next ?? new Error("none");
      return next;
    },
    artifactUrl: (p: string) => p,
  } as unknown as CadStudioTransport;
}

function setup(responses: Array<TrajectoryResponse | Error>) {
  const scenes: unknown[] = [];
  let clock = 0;
  const frames: Array<() => void> = [];
  const els = elements();
  const controller = new PlaybackController({
    transport: fakeTransport(responses),
    viewport: { setScene: (s) => scenes.push(s), setHighlight: () => {}, requestRender: () => {} },
    elements: els,
    loadBytes: async () => new Float32Array([0, 0, 0, 1, 0, 0, 0, 10, 0, 0, 1, 0, 0, 0]).buffer,
    buildTrajectory: async (doc): Promise<LoadedTrajectory> => {
      const body = new Object3D();
      return { root: new Group(), parts: new Map([["box", body]]), bounds: new Box3(), bodies: [body], materials: [new MeshStandardMaterial()] };
    },
    now: () => clock,
    requestFrame: (cb) => frames.push(cb),
    cancelFrame: () => {},
  });
  return { controller, els, scenes, frames, advance: (ms: number) => { clock += ms; } };
}

describe("PlaybackController wiring", () => {
  it("plays real frames and keeps the trajectory stale after a failed run", async () => {
    const { controller, els, frames, advance } = setup([trajectory("a")]);
    await controller.openRun("a");
    expect(controller.displayedRunId).toBe("a");
    expect(els.panel.hidden).toBe(false);
    expect(els.frame.textContent).toBe("frame 0 / 1");
    controller.toggle();
    advance(600);
    frames.shift()?.();
    expect(controller.time).toBeCloseTo(0.6);
    expect(els.frame.textContent).toBe("frame 1 / 1");
    controller.handleJobFinished(job({ status: "failed", error: "boom" }));
    expect(controller.displayedRunId).toBe("a");
    expect(els.banner.textContent).toContain("last good trajectory");
  });

  it("clears a failed switch to another run", async () => {
    const { controller, els } = setup([trajectory("a"), new Error("gone")]);
    await controller.openRun("a");
    await controller.openRun("b");
    expect(controller.displayedRunId).toBeNull();
    expect(els.banner.textContent).toContain("Could not load the trajectory");
  });
});

describe("PlaybackController stale and ordering", () => {
  it("keeps the last good trajectory, marked stale, when a reload of the same run fails", async () => {
    const { controller, els } = setup([trajectory("a"), new Error("reload failed")]);
    await controller.openRun("a");
    await controller.openRun("a");
    expect(controller.displayedRunId).toBe("a");
    expect(els.panel.hidden).toBe(false);
    expect(controller.state.artifact).not.toBeNull();
    expect(controller.state.stale).toBe(true);
    expect(els.banner.textContent).toContain("reload failed");
  });

  it("keeps the trajectory displayed with the error after a failed run job", async () => {
    const { controller, els } = setup([trajectory("a")]);
    await controller.openRun("a");
    controller.handleJobFinished(job({ status: "failed", error: "solver diverged" }));
    expect(controller.displayedRunId).toBe("a");
    expect(controller.state.stale).toBe(true);
    expect(controller.state.error).toBe("solver diverged");
    expect(els.panel.hidden).toBe(false);
    expect(els.banner.textContent).toContain("solver diverged");
  });

  it("ignores build jobs and non-failures", async () => {
    const { controller } = setup([trajectory("a")]);
    await controller.openRun("a");
    controller.handleJobFinished(job({ kind: "build", status: "failed", error: "x" }));
    expect(controller.state.stale).toBe(false);
    controller.handleJobFinished(job({ status: "succeeded" }));
    controller.handleJobFinished(job({ status: "cancelled" }));
    expect(controller.state.stale).toBe(false);
    expect(controller.state.error).toBeNull();
  });

  it("ignores a superseded (older) load response", async () => {
    const resolvers: Array<(r: TrajectoryResponse) => void> = [];
    const transport = {
      getTrajectory: () => new Promise<TrajectoryResponse>((resolve) => resolvers.push(resolve)),
      artifactUrl: (p: string) => p,
    } as unknown as CadStudioTransport;
    const els = elements();
    const controller = new PlaybackController({
      transport,
      viewport: { setScene: () => {}, setHighlight: () => {}, requestRender: () => {} },
      elements: els,
      loadBytes: async () => new Float32Array([0, 0, 0, 1, 0, 0, 0, 10, 0, 0, 1, 0, 0, 0]).buffer,
      buildTrajectory: async (): Promise<LoadedTrajectory> => {
        const body = new Object3D();
        return { root: new Group(), parts: new Map([["box", body]]), bounds: new Box3(), bodies: [body], materials: [new MeshStandardMaterial()] };
      },
      now: () => 0,
      requestFrame: () => 1,
      cancelFrame: () => {},
    });
    const first = controller.openRun("old");
    const second = controller.openRun("new");
    // The newer request answers first, then the stale one arrives late.
    resolvers[1](trajectory("new"));
    await second;
    resolvers[0](trajectory("old"));
    await first;
    expect(controller.displayedRunId).toBe("new");
    expect(controller.runId).toBe("new");
  });

  it("ignores a superseded load failure", async () => {
    const rejecters: Array<{ resolve: (r: TrajectoryResponse) => void; reject: (e: Error) => void }> = [];
    const transport = {
      getTrajectory: () => new Promise<TrajectoryResponse>((resolve, reject) => rejecters.push({ resolve, reject })),
      artifactUrl: (p: string) => p,
    } as unknown as CadStudioTransport;
    const els = elements();
    const controller = new PlaybackController({
      transport,
      viewport: { setScene: () => {}, setHighlight: () => {}, requestRender: () => {} },
      elements: els,
      loadBytes: async () => new Float32Array([0, 0, 0, 1, 0, 0, 0, 10, 0, 0, 1, 0, 0, 0]).buffer,
      buildTrajectory: async (): Promise<LoadedTrajectory> => {
        const body = new Object3D();
        return { root: new Group(), parts: new Map([["box", body]]), bounds: new Box3(), bodies: [body], materials: [new MeshStandardMaterial()] };
      },
      now: () => 0,
      requestFrame: () => 1,
      cancelFrame: () => {},
    });
    const first = controller.openRun("old");
    const second = controller.openRun("new");
    rejecters[1].resolve(trajectory("new"));
    await second;
    rejecters[0].reject(new Error("late failure"));
    await first;
    expect(controller.displayedRunId).toBe("new");
    expect(els.banner.textContent ?? "").not.toContain("late failure");
  });
});

describe("JobPanel wiring", () => {
  it("reports a finished job once across SSE and polling", async () => {
    const button = () => document.createElement("button");
    const select = () => document.createElement("select");
    const finished: Job[] = [];
    let tick: (() => void) | null = null;
    const transport = {
      listPhysicsInputs: async () => ({
        schemaVersion: 1, project: "p", model: "m",
        scenarios: [{ name: "s.json", path: "projects/p/physics/scenarios/s.json" }],
        acceptance: [{ name: "a_acceptance.json", path: "projects/p/physics/a_acceptance.json" }],
        options: [],
      }),
      startRun: async () => job(),
      getJob: async () => job({ status: "failed", error: "exit 1" }),
    } as unknown as CadStudioTransport;
    const panel = new JobPanel({
      transport,
      elements: {
        build: button(), run: button(), scenario: select(), acceptance: select(), options: select(),
        status: document.createElement("div"), log: document.createElement("pre"), cancel: button(),
      },
      onFinished: (j) => finished.push(j),
      setInterval: (cb) => { tick = cb; return 1; },
      clearInterval: () => { tick = null; },
    });
    await panel.setModel("p/m");
    await panel.startRun();
    expect(panel.tracker.job?.id).toBe("j1");
    panel.handleEvent({ type: "job", job: job({ status: "running" }) });
    panel.handleEvent({ type: "job", job: job({ status: "failed", error: "exit 1" }) });
    expect(finished.map((j) => j.status)).toEqual(["failed"]);
    expect(tick).toBeNull();
    panel.handleEvent({ type: "job", job: job({ status: "failed", error: "exit 1" }) });
    expect(finished).toHaveLength(1);
  });
});

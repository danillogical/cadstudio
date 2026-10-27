// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { Box3, Group } from "three";
import { describe, expect, it } from "vitest";
import type { LoadedScene } from "../scene/mapping";
import type {
  CadStudioTransport,
  Job,
  ModelList,
  PhysicsInputs,
  RunList,
  SceneDoc,
  SceneResponse,
  ServiceEvent,
  StartRunRequest,
  TrajectoryResponse,
  HealthInfo,
} from "../transport/types";
import { TransportError } from "../transport/types";
import type { SceneViewport } from "../viewport/viewport";
import { bannerFor, renderBanner } from "./banner";
import { AppController } from "./controller";
import { Selection } from "./selection";

const FIXTURES = `${process.cwd()}/test/fixtures/`;

function fixtureDoc(): SceneDoc {
  return JSON.parse(readFileSync(`${FIXTURES}scene.json`, "utf8")) as SceneDoc;
}

function response(overrides: Partial<SceneResponse> = {}): SceneResponse {
  const doc = fixtureDoc();
  return {
    schemaVersion: 1,
    project: doc.project,
    model: doc.model,
    stale: false,
    error: null,
    job: null,
    artifactBase: `${doc.project}/${doc.model}/scene`,
    scene: doc,
    ...overrides,
  };
}

function loadedScene(): LoadedScene {
  return { root: new Group(), parts: new Map(), bounds: new Box3() };
}

class FakeViewport implements SceneViewport {
  scenes: Array<LoadedScene | null> = [];
  highlights: Array<string | null> = [];

  setScene(scene: LoadedScene | null): void {
    this.scenes.push(scene);
  }

  setHighlight(partId: string | null): void {
    this.highlights.push(partId);
  }
}

const job = (overrides: Partial<Job> = {}): Job => ({
  id: "j1",
  kind: "build",
  key: "fixture/two_box",
  model: "fixture/two_box",
  status: "running",
  createdAt: 0,
  startedAt: 0,
  finishedAt: null,
  error: null,
  exitCode: null,
  log: [],
  artifacts: {},
  ...overrides,
});

class FakeTransport implements CadStudioTransport {
  scenes: Array<SceneResponse | Error> = [];
  requests: string[] = [];
  sceneCalls = 0;

  async health(): Promise<HealthInfo> {
    return { schemaVersion: 1, service: "cadstudio", protocolVersion: 1, repoRoot: "/r", pid: 1 };
  }

  async listModels(): Promise<ModelList> {
    return { schemaVersion: 1, projects: [], models: [] };
  }

  async getScene(model: string): Promise<SceneResponse> {
    this.sceneCalls += 1;
    this.requests.push(model);
    const next = this.scenes.shift();
    if (!next) throw new Error(`no scripted scene for ${model}`);
    if (next instanceof Error) throw next;
    return next;
  }

  async startBuild(): Promise<Job> {
    return job();
  }

  async listPhysicsInputs(): Promise<PhysicsInputs> {
    return { schemaVersion: 1, project: "", model: "", scenarios: [], acceptance: [], options: [] };
  }

  async listRuns(): Promise<RunList> {
    return { schemaVersion: 1, runs: [] };
  }

  async getTrajectory(): Promise<TrajectoryResponse> {
    throw new Error("not used");
  }

  async startRun(_req: StartRunRequest): Promise<Job> {
    return job({ kind: "run" });
  }

  async getJob(): Promise<Job> {
    return job();
  }

  async cancelJob(): Promise<Job> {
    return job({ status: "cancelled" });
  }

  subscribe(): () => void {
    return () => {};
  }

  artifactUrl(path: string): string {
    return `http://test/v1/artifacts/${path}`;
  }
}

function mount() {
  document.body.replaceChildren();
  const banner = document.createElement("div");
  const tree = document.createElement("div");
  const props = document.createElement("div");
  document.body.append(banner, tree, props);
  const transport = new FakeTransport();
  const viewport = new FakeViewport();
  const selection = new Selection();
  const controller = new AppController({
    transport,
    viewport,
    elements: { banner, tree, props },
    selection,
    buildScene: async () => loadedScene(),
  });
  return { banner, tree, props, transport, viewport, selection, controller };
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("bannerFor", () => {
  it("is quiet for a fresh scene", () => {
    expect(bannerFor({ stale: false, sceneError: null, loadError: null })).toBeNull();
  });

  it("reports a stale scene with the build error", () => {
    expect(bannerFor({ stale: true, sceneError: "checks failed", loadError: null })).toEqual({
      kind: "stale",
      text: "Showing the last good scene; the latest build failed: checks failed",
    });
  });

  it("explains a 401", () => {
    const state = bannerFor({
      stale: false,
      sceneError: null,
      loadError: new TransportError(401, "missing or invalid token"),
    });
    expect(state?.kind).toBe("error");
    expect(state?.text).toContain("cad gui serve");
  });

  it("shows the command for a 404 with one", () => {
    const state = bannerFor({
      stale: false,
      sceneError: null,
      loadError: new TransportError(404, "no scene", { command: "cad gui scene fixture/two_box" }),
    });
    expect(state).toEqual({
      kind: "info",
      text: "No scene yet. Run `cad gui scene fixture/two_box`.",
    });
  });

  it("shows any other error message", () => {
    const state = bannerFor({ stale: false, sceneError: null, loadError: new Error("boom") });
    expect(state).toEqual({ kind: "error", text: "Could not load the scene: boom" });
  });

  it("renders and hides the banner element", () => {
    const element = document.createElement("div");
    renderBanner(element, { kind: "stale", text: "old" });
    expect(element.hidden).toBe(false);
    expect(element.dataset.kind).toBe("stale");
    expect(element.textContent).toBe("old");
    renderBanner(element, null);
    expect(element.hidden).toBe(true);
    expect(element.textContent).toBe("");
  });
});

describe("AppController stale and error handling", () => {
  it("loads a fresh scene without a banner", async () => {
    const { banner, tree, props, transport, viewport, controller } = mount();
    transport.scenes.push(response());
    await controller.loadModel("fixture/two_box");
    expect(viewport.scenes).toHaveLength(1);
    expect(banner.hidden).toBe(true);
    expect(tree.querySelectorAll("li[role='treeitem']").length).toBe(2);
    expect(props.textContent).toContain("none selected");
  });

  it("shows the stale banner while keeping the scene on screen", async () => {
    const { banner, transport, viewport, controller } = mount();
    transport.scenes.push(response());
    await controller.loadModel("fixture/two_box");
    transport.scenes.push(response({ stale: true, error: "checks failed" }));
    await controller.loadModel("fixture/two_box");

    expect(banner.hidden).toBe(false);
    expect(banner.dataset.kind).toBe("stale");
    expect(banner.textContent).toContain("checks failed");
    expect(viewport.scenes).toHaveLength(2);
  });

  it("keeps the previous scene when a reload fails", async () => {
    const { banner, transport, viewport, controller } = mount();
    transport.scenes.push(response());
    await controller.loadModel("fixture/two_box");
    transport.scenes.push(new TransportError(500, "scene.json is unreadable"));
    await controller.loadModel("fixture/two_box");

    expect(viewport.scenes).toHaveLength(1);
    expect(banner.dataset.kind).toBe("error");
    expect(banner.textContent).toContain("scene.json is unreadable");
  });

  it("re-fetches on a scene artifact for the current model only", async () => {
    const { transport, controller } = mount();
    transport.scenes.push(response(), response());
    await controller.loadModel("fixture/two_box");
    const callsAfterLoad = transport.sceneCalls;

    controller.handleEvent({ type: "artifact", kind: "scene", model: "other/model" });
    await flush();
    expect(transport.sceneCalls).toBe(callsAfterLoad);

    controller.handleEvent({ type: "artifact", kind: "scene", model: "fixture/two_box" });
    await flush();
    expect(transport.sceneCalls).toBe(callsAfterLoad + 1);
  });

  it("re-fetches when the current model's build job finishes", async () => {
    const { transport, controller } = mount();
    transport.scenes.push(response(), response());
    await controller.loadModel("fixture/two_box");
    const callsAfterLoad = transport.sceneCalls;

    controller.handleEvent({ type: "job", job: job({ status: "succeeded" }) });
    await flush();
    expect(transport.sceneCalls).toBe(callsAfterLoad + 1);
  });

  it("clears the old model's panels when a switch to another model fails", async () => {
    const { banner, tree, props, transport, viewport, selection, controller } = mount();
    transport.scenes.push(response());
    await controller.loadModel("fixture/two_box");
    selection.set("pin");
    expect(tree.children.length).toBeGreaterThan(0);

    transport.scenes.push(
      new TransportError(404, "no scene", { command: "cad gui scene fixture/other" }),
    );
    await controller.loadModel("fixture/other");

    // The picker now shows B, so nothing may still describe A.
    expect(viewport.scenes.at(-1)).toBeNull();
    expect(viewport.scenes).toHaveLength(2);
    expect(tree.children).toHaveLength(0);
    expect(props.children).toHaveLength(0);
    expect(selection.get()).toBeNull();
    expect(controller.sceneResponse).toBeNull();
    expect(banner.dataset.kind).toBe("info");
    expect(banner.textContent).toContain("cad gui scene fixture/other");
  });

  it("clears the panels on a first load that fails", async () => {
    const { banner, tree, props, transport, viewport, controller } = mount();
    transport.scenes.push(new TransportError(404, "no scene", { command: "cad gui scene a/b" }));
    await controller.loadModel("a/b");
    expect(viewport.scenes.at(-1)).toBeNull();
    expect(tree.children).toHaveLength(0);
    expect(props.children).toHaveLength(0);
    expect(banner.hidden).toBe(false);
  });

  it("discards a slow first load that resolves after a newer one", async () => {
    const { transport, viewport, controller } = mount();
    const first = response();
    const second = response({ model: "other" });
    transport.scenes.push(first, second);
    const slow = controller.loadModel("fixture/two_box");
    const fast = controller.loadModel("fixture/other");
    await Promise.all([slow, fast]);
    // Only the second load may reach the viewport.
    expect(viewport.scenes).toHaveLength(1);
    expect(controller.model).toBe("fixture/other");
  });

  it("clears a selection that no longer exists", async () => {
    const { transport, selection, controller } = mount();
    transport.scenes.push(response(), response({ scene: { ...fixtureDoc(), parts: [] } }));
    await controller.loadModel("fixture/two_box");
    selection.set("pin");
    await controller.loadModel("fixture/empty");
    expect(selection.get()).toBeNull();
  });

  it("exposes the loaded response", async () => {
    const { transport, controller } = mount();
    const doc = response();
    transport.scenes.push(doc);
    await controller.loadModel("fixture/two_box");
    expect(controller.sceneResponse).toBe(doc);
    expect(controller.model).toBe("fixture/two_box");
  });
});

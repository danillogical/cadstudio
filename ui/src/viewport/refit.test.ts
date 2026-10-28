// @vitest-environment happy-dom
import { Box3, Group, Vector3 } from "three";
import { describe, expect, it, vi } from "vitest";

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

import { AppController } from "../app/controller";
import type { LoadedScene } from "../scene/mapping";
import type { CadStudioTransport, SceneResponse } from "../transport/types";
import { Viewport } from "./viewport";

function sceneFor(project: string, model: string, size: number): LoadedScene {
  const root = new Group();
  root.name = `scene:${project}/${model}`;
  return { root, parts: new Map(), bounds: new Box3(new Vector3(0, 0, 0), new Vector3(size, size, size)) };
}

function response(project: string, model: string): SceneResponse {
  return {
    schemaVersion: 1,
    project,
    model,
    stale: false,
    error: null,
    job: null,
    artifactBase: `${project}/${model}/scene`,
    scene: { schemaVersion: 1, project, model, units: "mm", provenance: {} as never, parts: [] },
  };
}

function mount() {
  document.body.replaceChildren();
  const container = document.createElement("div");
  const banner = document.createElement("div");
  const tree = document.createElement("div");
  const props = document.createElement("div");
  document.body.append(container, banner, tree, props);
  const viewport = new Viewport(container);
  const transport = {
    getScene: async (spec: string) => {
      const [project, model] = spec.split("/");
      return response(project, model);
    },
  } as unknown as CadStudioTransport;
  const sizes = new Map<string, number>([["p/a", 100], ["p/b", 400]]);
  const controller = new AppController({
    transport,
    viewport,
    elements: { banner, tree, props },
    buildScene: async (doc) => sceneFor(doc.project, doc.model, sizes.get(`${doc.project}/${doc.model}`) ?? 100),
  });
  return { viewport, controller };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("scene reload keeps the user's camera", () => {
  it("a scene artifact for the current model reloads without refitting", async () => {
    const { viewport, controller } = mount();
    await controller.loadModel("p/a");
    // The user orbits somewhere.
    viewport.camera.position.set(7, 8, 9);
    viewport.controls.target.set(1, 2, 3);
    const setScene = vi.spyOn(viewport, "setScene");

    controller.handleEvent({ type: "artifact", kind: "scene", model: "p/a" });
    await flush();

    expect(viewport.camera.position.toArray()).toEqual([7, 8, 9]);
    expect(viewport.controls.target.toArray()).toEqual([1, 2, 3]);
    // It did reload: a new scene was swapped in.
    expect(setScene).toHaveBeenCalledTimes(1);
    expect(viewport.hasLayer("scene")).toBe(true);
  });

  it("repeated reloads never move the camera either", async () => {
    const { viewport, controller } = mount();
    await controller.loadModel("p/a");
    viewport.camera.position.set(-40, 5, 60);
    for (let i = 0; i < 3; i += 1) {
      controller.handleEvent({ type: "artifact", kind: "scene", model: "p/a" });
      await flush();
    }
    expect(viewport.camera.position.toArray()).toEqual([-40, 5, 60]);
  });

  it("a different model still refits", async () => {
    const { viewport, controller } = mount();
    await controller.loadModel("p/a");
    viewport.camera.position.set(7, 8, 9);
    await controller.loadModel("p/b");
    expect(viewport.camera.position.toArray()).not.toEqual([7, 8, 9]);
  });

  it("a scene artifact for another model does not touch the camera or reload", async () => {
    const { viewport, controller } = mount();
    await controller.loadModel("p/a");
    viewport.camera.position.set(7, 8, 9);
    controller.handleEvent({ type: "artifact", kind: "scene", model: "p/b" });
    await flush();
    expect(viewport.camera.position.toArray()).toEqual([7, 8, 9]);
    expect(controller.model).toBe("p/a");
  });
});

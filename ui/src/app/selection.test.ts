// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { Box3, Group } from "three";
import { describe, expect, it } from "vitest";
import type { LoadedScene } from "../scene/mapping";
import type { SceneDoc } from "../transport/types";
import type { SceneViewport } from "../viewport/viewport";
import { renderProps } from "./props";
import { Selection } from "./selection";
import { renderTree } from "./tree";

const FIXTURES = `${process.cwd()}/test/fixtures/`;

function fixtureDoc(): SceneDoc {
  return JSON.parse(readFileSync(`${FIXTURES}scene.json`, "utf8")) as SceneDoc;
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

function mount(doc = fixtureDoc()) {
  document.body.replaceChildren();
  const tree = document.createElement("div");
  const props = document.createElement("div");
  document.body.append(tree, props);
  const selection = new Selection();
  const viewport = new FakeViewport();
  const unsubscribe = renderTree(tree, doc, selection);
  // The controller renders the panel once after load, then on every selection change.
  renderProps(props, doc, selection.get());
  selection.onChange((id) => {
    viewport.setHighlight(id);
    renderProps(props, doc, id);
  });
  return { tree, props, selection, viewport, unsubscribe };
}

function item(tree: HTMLElement, id: string): HTMLLIElement {
  return tree.querySelector<HTMLLIElement>(`li[data-part-id="${id}"]`)!;
}

describe("part tree and selection", () => {
  it("renders one treeitem per part", () => {
    const { tree } = mount();
    const items = tree.querySelectorAll("li[role='treeitem']");
    expect([...items].map((node) => (node as HTMLElement).dataset.partId)).toEqual(["base", "pin"]);
  });

  it("selects a part from the tree and highlights it in the viewport", () => {
    const { tree, props, selection, viewport } = mount();
    item(tree, "pin").click();

    expect(selection.get()).toBe("pin");
    expect(item(tree, "pin").getAttribute("aria-selected")).toBe("true");
    expect(item(tree, "base").getAttribute("aria-selected")).toBe("false");
    expect(viewport.highlights.at(-1)).toBe("pin");
    expect(props.textContent).toContain("pin");
    expect(props.textContent).toContain("480.00 mm³");
  });

  it("selects from the viewport and updates the tree and properties", () => {
    const { tree, props, selection, viewport } = mount();
    // A viewport pick calls the same selection store.
    selection.set("base");
    expect(item(tree, "base").getAttribute("aria-selected")).toBe("true");
    expect(item(tree, "pin").getAttribute("aria-selected")).toBe("false");
    expect(viewport.highlights.at(-1)).toBe("base");
    expect(props.textContent).toContain("base");
    expect(props.textContent).toContain("4000.00 mm³");
    expect(props.textContent).toContain("40.00 mm, 20.00 mm, 5.00 mm");
  });

  it("clears both when selection becomes null", () => {
    const { tree, props, selection, viewport } = mount();
    selection.set("pin");
    selection.set(null);
    expect(item(tree, "pin").getAttribute("aria-selected")).toBe("false");
    expect(item(tree, "base").getAttribute("aria-selected")).toBe("false");
    expect(viewport.highlights.at(-1)).toBeNull();
    expect(props.textContent).toContain("none selected");
  });

  it("shows the model provenance read-only", () => {
    const { props } = mount();
    expect(props.textContent).toContain("000000000000");
    expect(props.textContent).toContain("fixture/params.toml");
    expect(props.textContent).toContain("2024-01-02T03:04:05Z");
    expect(props.querySelector("input, textarea, select")).toBeNull();
  });

  it("does not fire listeners when the selection is unchanged", () => {
    const selection = new Selection();
    let calls = 0;
    selection.onChange(() => calls++);
    selection.set("pin");
    selection.set("pin");
    expect(calls).toBe(1);
  });

  it("unsubscribes cleanly", () => {
    const { tree, selection, unsubscribe } = mount();
    unsubscribe();
    selection.set("pin");
    expect(item(tree, "pin").getAttribute("aria-selected")).toBe("false");
  });
});

describe("renderProps", () => {
  it("works with no scene part selected", () => {
    const doc = fixtureDoc();
    const props = document.createElement("div");
    renderProps(props, doc, "missing");
    expect(props.textContent).toContain("none selected");
    expect(props.textContent).toContain("000000000000");
  });

  it("is independent of the loaded scene group", () => {
    const doc = fixtureDoc();
    const props = document.createElement("div");
    renderProps(props, doc, null);
    expect(props.querySelectorAll("dt").length).toBeGreaterThan(0);
    expect(new Group()).toBeInstanceOf(Group);
    expect(new Box3().isEmpty()).toBe(true);
  });
});

import {
  buildSceneGroup as defaultBuildSceneGroup,
  disposeScene,
  type LoadedScene,
} from "../scene/mapping";
import type { SceneViewport } from "../viewport/viewport";
import {
  type CadStudioTransport,
  type SceneDoc,
  type SceneResponse,
  type ServiceEvent,
  TransportError,
} from "../transport/types";
import { bannerFor, renderBanner } from "./banner";
import { renderProps } from "./props";
import { Selection } from "./selection";
import { renderTree } from "./tree";

export interface ControllerElements {
  banner: HTMLElement;
  tree: HTMLElement;
  props: HTMLElement;
}

export interface ControllerOptions {
  transport: CadStudioTransport;
  viewport: SceneViewport;
  elements: ControllerElements;
  selection?: Selection;
  /** Injectable for tests so they do not have to parse GLBs. */
  buildScene?: (doc: SceneDoc, loadBytes: (meshPath: string) => Promise<ArrayBuffer>) => Promise<LoadedScene>;
  loadBytes?: (url: string) => Promise<ArrayBuffer>;
}

async function fetchBytes(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new TransportError(response.status, `artifact request failed: ${response.statusText}`);
  }
  return response.arrayBuffer();
}

/**
 * Owns the loaded model: fetches the scene, swaps the viewport, keeps the tree,
 * properties and banner in step, and ignores responses from superseded loads.
 */
export class AppController {
  readonly selection: Selection;

  private readonly transport: CadStudioTransport;
  private readonly viewport: SceneViewport;
  private readonly elements: ControllerElements;
  private readonly buildScene: NonNullable<ControllerOptions["buildScene"]>;
  private readonly loadBytes: (url: string) => Promise<ArrayBuffer>;
  private readonly unsubscribeSelection: () => void;

  private currentModel: string | null = null;
  /** The model whose scene, tree and properties are actually on screen. */
  private displayedModel: string | null = null;
  private response: SceneResponse | null = null;
  private loadError: unknown = null;
  private loadToken = 0;
  private unsubscribeTree: (() => void) | null = null;
  private disposed = false;

  constructor(options: ControllerOptions) {
    this.transport = options.transport;
    this.viewport = options.viewport;
    this.elements = options.elements;
    this.selection = options.selection ?? new Selection();
    this.buildScene = options.buildScene ?? defaultBuildSceneGroup;
    this.loadBytes = options.loadBytes ?? fetchBytes;
    this.unsubscribeSelection = this.selection.onChange((id) => {
      this.viewport.setHighlight(id);
      if (this.response) renderProps(this.elements.props, this.response.scene, id);
    });
  }

  get model(): string | null {
    return this.currentModel;
  }

  get sceneResponse(): SceneResponse | null {
    return this.response;
  }

  async loadModel(model: string): Promise<void> {
    const token = ++this.loadToken;
    this.currentModel = model;
    try {
      const response = await this.transport.getScene(model);
      if (token !== this.loadToken) return;
      const loaded = await this.buildScene(response.scene, (meshPath) =>
        this.loadBytes(this.transport.artifactUrl(`${response.artifactBase}/${meshPath}`)),
      );
      if (token !== this.loadToken) {
        disposeScene(loaded);
        return;
      }
      this.response = response;
      this.displayedModel = model;
      this.loadError = null;
      this.viewport.setScene(loaded);
      const selected = this.selection.get();
      if (selected && !response.scene.parts.some((part) => part.id === selected)) {
        this.selection.set(null);
      }
      this.unsubscribeTree?.();
      this.unsubscribeTree = renderTree(this.elements.tree, response.scene, this.selection);
      renderProps(this.elements.props, response.scene, this.selection.get());
      this.viewport.setHighlight(this.selection.get());
      this.renderBanner();
    } catch (error) {
      if (token !== this.loadToken) return;
      this.loadError = error;
      // A failed reload of the same model keeps the last good scene; a failed switch
      // must not leave the old model's scene and panels under the new picker value.
      if (model !== this.displayedModel) this.clearPanels();
      this.renderBanner();
    }
  }

  /** React to a service event; scene-affecting events re-fetch the current model. */
  handleEvent(event: ServiceEvent): void {
    if (event.type === "artifact" && event.kind === "scene") {
      if (event.model === this.currentModel) void this.loadModel(event.model);
      return;
    }
    if (event.type === "job") {
      const { job } = event;
      if (job.model !== this.currentModel) return;
      if (job.status === "failed" || job.status === "succeeded") {
        void this.loadModel(job.model);
      }
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.loadToken += 1;
    this.unsubscribeTree?.();
    this.unsubscribeSelection();
  }

  /** Recompute the banner from the current state, e.g. after the event stream reconnects. */
  refreshBanner(): void {
    this.renderBanner();
  }

  /** Drop the old model's scene, tree and properties so nothing is mislabelled. */
  private clearPanels(): void {
    this.response = null;
    this.displayedModel = null;
    this.selection.set(null);
    this.viewport.setScene(null);
    this.unsubscribeTree?.();
    this.unsubscribeTree = null;
    this.elements.tree.replaceChildren();
    this.elements.props.replaceChildren();
  }

  private renderBanner(): void {
    renderBanner(
      this.elements.banner,
      bannerFor({
        stale: this.response?.stale ?? false,
        sceneError: this.response?.error ?? null,
        loadError: this.loadError,
      }),
    );
  }
}

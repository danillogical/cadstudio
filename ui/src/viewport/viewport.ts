import {
  AmbientLight,
  AxesHelper,
  Box3,
  Color,
  DirectionalLight,
  GridHelper,
  Group,
  PerspectiveCamera,
  Scene,
  Sphere,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { disposeScene, type LoadedScene } from "../scene/mapping";
import { fitCamera, niceGridStep } from "./camera";
import { pickPart } from "./pick";

export const FOV_DEG = 45;
const CLICK_SLOP_PX = 4;
const BACKGROUND = new Color("#1e1e1e");
const HIGHLIGHT = new Color("#ffb347");

/** The viewport surface the controller drives; kept small so tests can fake it. */
export interface SceneViewport {
  setScene(scene: LoadedScene | null): void;
  setHighlight(partId: string | null): void;
}

/** A viewport the playback controller drives: it moves bodies itself, then asks for a frame. */
export interface TrajectoryViewport extends SceneViewport {
  requestRender(): void;
}

/** The model scene and the run trajectory each own a layer; only the active one is drawn. */
export type LayerName = "scene" | "trajectory";

interface Layer {
  loaded: LoadedScene | null;
  highlighted: string | null;
}

/**
 * Three.js assembly viewport: Z up, millimetres, orbit/pan/zoom, a mm grid, axes and
 * click-to-select. Geometry arrives already in assembly coordinates, so nothing is scaled.
 */
export class Viewport implements SceneViewport {
  readonly renderer: WebGLRenderer;
  readonly camera: PerspectiveCamera;
  readonly scene = new Scene();
  readonly controls: OrbitControls;

  private readonly container: HTMLElement;
  private readonly modelRoot = new Group();
  private readonly overlay: HTMLElement;
  private readonly resizeObserver: ResizeObserver;
  private readonly layers: Record<LayerName, Layer> = {
    scene: { loaded: null, highlighted: null },
    trajectory: { loaded: null, highlighted: null },
  };
  private active: LayerName = "scene";
  private grid: GridHelper | null = null;
  private axes: AxesHelper | null = null;
  private pointerStart: { x: number; y: number; id: number } | null = null;
  private disposed = false;

  onPick: (partId: string | null) => void = () => {};

  constructor(container: HTMLElement) {
    this.container = container;
    this.renderer = new WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2));
    this.renderer.domElement.className = "viewport-canvas";
    container.appendChild(this.renderer.domElement);

    this.overlay = document.createElement("div");
    this.overlay.className = "viewport-overlay";
    container.appendChild(this.overlay);

    this.camera = new PerspectiveCamera(FOV_DEG, 1, 0.1, 10000);
    // Z up must be set before OrbitControls captures the camera basis.
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(120, -120, 100);

    this.scene.background = BACKGROUND;
    this.scene.add(this.modelRoot);
    this.scene.add(new AmbientLight(0xffffff, 0.75));
    const key = new DirectionalLight(0xffffff, 1.4);
    key.position.set(1, -1.4, 2);
    const fill = new DirectionalLight(0xffffff, 0.6);
    fill.position.set(-1.2, 1, 0.4);
    this.scene.add(key, fill);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.screenSpacePanning = true;
    this.controls.addEventListener("change", () => this.render());

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();

    this.renderer.domElement.addEventListener("pointerdown", this.onPointerDown);
    this.renderer.domElement.addEventListener("pointerup", this.onPointerUp);
    globalThis.addEventListener("keydown", this.onKeyDown);
    this.render();
  }

  private get loaded(): LoadedScene | null {
    return this.layers[this.active].loaded;
  }

  /** The layer currently drawn. */
  get activeLayer(): LayerName {
    return this.active;
  }

  /** Whether `layer` holds something to draw. */
  hasLayer(layer: LayerName): boolean {
    return this.layers[layer].loaded !== null;
  }

  /** Replace the model scene layer; the previous one is disposed after the swap. */
  setScene(loaded: LoadedScene | null): void {
    this.setLayerScene("scene", loaded);
  }

  /** Replace one layer's content; a hidden layer is swapped without touching the camera. */
  setLayerScene(layer: LayerName, loaded: LoadedScene | null): void {
    const state = this.layers[layer];
    const previous = state.loaded;
    // A rebuild of the same model keeps the user's viewpoint; a different model refits.
    const sameModel = loaded !== null && previous !== null && loaded.root.name === previous.root.name;
    state.loaded = loaded;
    state.highlighted = null;
    if (layer !== this.active) {
      disposeScene(previous);
      return;
    }
    this.modelRoot.clear();
    disposeScene(previous);
    if (loaded) {
      this.modelRoot.add(loaded.root);
      this.rebuildHelpers(shownBounds(loaded));
      if (sameModel) this.updateClipping(shownBounds(loaded));
      else this.fit();
    } else {
      this.rebuildHelpers(null);
    }
    this.render();
  }

  /** Draw `layer` instead of the current one and fit the camera to it. */
  setActiveLayer(layer: LayerName): void {
    if (layer === this.active) return;
    this.active = layer;
    this.modelRoot.clear();
    const loaded = this.layers[layer].loaded;
    if (loaded) this.modelRoot.add(loaded.root);
    this.rebuildHelpers(loaded ? shownBounds(loaded) : null);
    this.fit();
  }

  /** A `TrajectoryViewport` bound to one layer, for a controller that owns that layer. */
  layer(layer: LayerName): TrajectoryViewport {
    return {
      setScene: (loaded) => this.setLayerScene(layer, loaded),
      setHighlight: (partId) => this.setLayerHighlight(layer, partId),
      requestRender: () => {
        if (layer === this.active) this.render();
      },
    };
  }

  /** Draw a frame now, e.g. after moving bodies. */
  requestRender(): void {
    this.render();
  }

  /** Keep the camera where it is but make sure the new bounds are not clipped. */
  private updateClipping(bounds: Box3): void {
    const distance = this.camera.position.distanceTo(this.controls.target);
    const radius = bounds.isEmpty() ? 1 : bounds.getBoundingSphere(new Sphere()).radius;
    this.camera.near = Math.max(distance / 1000, 0.01);
    this.camera.far = Math.max(distance + radius * 4, this.camera.near * 2);
    this.camera.updateProjectionMatrix();
  }

  /**
   * Fit the camera to the current model, or to a default box when empty. Every fit (the Fit
   * button, the F key, opening a scene or run, switching layers) comes through here and uses
   * `shownBounds`, so a hidden (removed) trajectory body never widens it.
   */
  fit(): void {
    const shown = this.loaded ? shownBounds(this.loaded) : null;
    const bounds =
      shown && !shown.isEmpty() ? shown.clone() : new Box3(new Vector3(-50, -50, -50), new Vector3(50, 50, 50));
    const aspect = this.camera.aspect || 1;
    const fit = fitCamera(bounds, FOV_DEG, aspect);
    this.camera.position.copy(fit.position);
    this.camera.near = fit.near;
    this.camera.far = fit.far;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(fit.target);
    this.controls.update();
    this.render();
  }

  setHighlight(partId: string | null): void {
    this.setLayerHighlight("scene", partId);
  }

  setLayerHighlight(layer: LayerName, partId: string | null): void {
    const state = this.layers[layer];
    if (state.highlighted === partId) return;
    state.highlighted = partId;
    for (const [id, object] of state.loaded?.parts ?? []) {
      object.traverse((node) => {
        const material = (node as { material?: unknown }).material;
        const materials = Array.isArray(material) ? material : [material];
        for (const entry of materials) {
          const standard = entry as { emissive?: Color } | undefined;
          if (!standard?.emissive) continue;
          standard.emissive.copy(id === partId ? HIGHLIGHT : new Color(0x000000));
        }
      });
    }
    this.render();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.resizeObserver.disconnect();
    this.renderer.domElement.removeEventListener("pointerdown", this.onPointerDown);
    this.renderer.domElement.removeEventListener("pointerup", this.onPointerUp);
    globalThis.removeEventListener("keydown", this.onKeyDown);
    this.controls.dispose();
    this.modelRoot.clear();
    for (const state of Object.values(this.layers)) {
      disposeScene(state.loaded);
      state.loaded = null;
    }
    this.renderer.dispose();
    this.overlay.remove();
    this.renderer.domElement.remove();
  }

  private rebuildHelpers(bounds: Box3 | null): void {
    for (const helper of [this.grid, this.axes]) {
      if (helper) {
        helper.removeFromParent();
        helper.geometry.dispose();
        (helper.material as { dispose(): void }).dispose();
      }
    }
    this.grid = null;
    this.axes = null;

    const size = bounds && !bounds.isEmpty() ? bounds.getSize(new Vector3()) : new Vector3(100, 100, 100);
    const span = Math.max(size.x, size.y, size.z, 1);
    const step = niceGridStep(span);
    const cells = Math.max(Math.ceil(span / step) * 2, 10);
    const gridSize = cells * step;
    this.grid = new GridHelper(gridSize, cells, 0x6b6b6b, 0x3c3c3c);
    // GridHelper lies in XZ (Y up); the model is Z up, so rotate it into XY.
    this.grid.rotation.x = Math.PI / 2;
    this.scene.add(this.grid);

    const axesSize = Math.max(step * 5, span * 0.4);
    this.axes = new AxesHelper(axesSize);
    this.scene.add(this.axes);

    this.overlay.textContent = `grid ${formatStep(step)} mm · X red · Y green · Z blue`;
  }

  private resize(): void {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.render();
  }

  private render(): void {
    if (this.disposed) return;
    this.renderer.render(this.scene, this.camera);
  }

  private readonly onPointerDown = (event: PointerEvent): void => {
    if (event.button !== 0) return;
    this.pointerStart = { x: event.clientX, y: event.clientY, id: event.pointerId };
  };

  private readonly onPointerUp = (event: PointerEvent): void => {
    const start = this.pointerStart;
    this.pointerStart = null;
    if (!start || start.id !== event.pointerId) return;
    if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > CLICK_SLOP_PX) return;

    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.onPick(pickPart(ndc, this.camera, this.modelRoot));
  };

  private readonly onKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== "f" && event.key !== "F") return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable)
    ) {
      return;
    }
    this.fit();
  };
}

/** What a fit should frame: the scene's live shown bounds when it has them, else its fixed bounds. */
function shownBounds(loaded: LoadedScene): Box3 {
  return loaded.fitBounds ? loaded.fitBounds() : loaded.bounds;
}

function formatStep(step: number): string {
  return step >= 1 ? String(step) : step.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

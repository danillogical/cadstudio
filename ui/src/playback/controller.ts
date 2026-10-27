/**
 * Owns the displayed run: loads the trajectory, its poses and meshes, drives the clock and
 * the playback controls, and keeps the last good trajectory (marked stale) when a run fails.
 */
import { bannerFor, renderBanner } from "../app/banner";
import { afterJob, afterLoad, emptyDisplay, type DisplayState } from "../app/jobs";
import { disposeScene } from "../scene/mapping";
import {
  TransportError,
  type CadStudioTransport,
  type Job,
  type TrajectoryDoc,
} from "../transport/types";
import type { TrajectoryViewport } from "../viewport/viewport";
import { clampSpeed, MAX_SPEED, MIN_SPEED, PlaybackClock } from "./clock";
import {
  contactIndex,
  contactsAtFrame,
  frameAt,
  nearestFrame,
  parseContacts,
  parsePoses,
  parseTrajectory,
  phaseAt,
  posesAt,
  type Pose,
} from "./frames";
import {
  applyPoses,
  buildTrajectoryGroup,
  setTransparent,
  type LoadedTrajectory,
} from "./mapping";
import { createContactOverlay, maxContactsPerFrame, type ContactOverlay } from "./overlay";

export interface PlaybackElements {
  /** Shown only while a trajectory is displayed. */
  panel: HTMLElement;
  banner: HTMLElement;
  play: HTMLButtonElement;
  restart: HTMLButtonElement;
  /** Range input whose value is sim seconds. */
  seek: HTMLInputElement;
  /** Range input from 0.1 to 4. */
  speed: HTMLInputElement;
  speedLabel: HTMLElement;
  time: HTMLElement;
  phase: HTMLElement;
  frame: HTMLElement;
  bodies: HTMLElement;
  contacts: HTMLInputElement;
  contactsNote: HTMLElement;
}

/** Everything one displayed run needs. */
export interface LoadedRun {
  runId: string;
  doc: TrajectoryDoc;
  poses: Float32Array;
  contacts: { data: Float32Array; index: Uint32Array } | null;
  scene: LoadedTrajectory;
  overlay: ContactOverlay | null;
}

export interface PlaybackOptions {
  transport: CadStudioTransport;
  viewport: TrajectoryViewport;
  elements: PlaybackElements;
  /** Injectable for tests so they do not have to parse GLBs. */
  buildTrajectory?: (
    doc: TrajectoryDoc,
    loadBytes: (meshPath: string) => Promise<ArrayBuffer>,
    initial: readonly Pose[],
  ) => Promise<LoadedTrajectory>;
  loadBytes?: (url: string) => Promise<ArrayBuffer>;
  /** Milliseconds, monotonic. */
  now?: () => number;
  requestFrame?: (callback: () => void) => number;
  cancelFrame?: (handle: number) => void;
}

async function fetchBytes(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new TransportError(response.status, `artifact request failed: ${response.statusText}`);
  }
  return response.arrayBuffer();
}

function seconds(value: number): string {
  return value.toFixed(3);
}

export class PlaybackController {
  private readonly transport: CadStudioTransport;
  private readonly viewport: TrajectoryViewport;
  private readonly elements: PlaybackElements;
  private readonly buildTrajectory: NonNullable<PlaybackOptions["buildTrajectory"]>;
  private readonly loadBytes: (url: string) => Promise<ArrayBuffer>;
  private readonly now: () => number;
  private readonly requestFrame: (callback: () => void) => number;
  private readonly cancelFrame: (handle: number) => void;

  private display: DisplayState<LoadedRun> = emptyDisplay();
  private clock: PlaybackClock | null = null;
  private requested: string | null = null;
  private loadError: unknown = null;
  private loadToken = 0;
  private frameHandle: number | null = null;
  private readonly transparent = new Set<string>();
  private disposed = false;

  constructor(options: PlaybackOptions) {
    this.transport = options.transport;
    this.viewport = options.viewport;
    this.elements = options.elements;
    this.buildTrajectory = options.buildTrajectory ?? buildTrajectoryGroup;
    this.loadBytes = options.loadBytes ?? fetchBytes;
    this.now = options.now ?? (() => performance.now());
    this.requestFrame = options.requestFrame ?? ((cb) => requestAnimationFrame(cb));
    this.cancelFrame = options.cancelFrame ?? ((handle) => cancelAnimationFrame(handle));

    const { play, restart, seek, speed, contacts } = this.elements;
    speed.min = String(MIN_SPEED);
    speed.max = String(MAX_SPEED);
    speed.step = "0.1";
    speed.value = "1";
    play.addEventListener("click", () => this.toggle());
    restart.addEventListener("click", () => this.restart());
    seek.addEventListener("input", () => this.seek(Number(seek.value)));
    speed.addEventListener("input", () => this.setSpeed(Number(speed.value)));
    contacts.addEventListener("change", () => this.showContacts(contacts.checked));
    this.renderControls();
  }

  /** The run most recently asked for. */
  get runId(): string | null {
    return this.requested;
  }

  /** The run actually on screen. */
  get displayedRunId(): string | null {
    return this.display.artifact?.runId ?? null;
  }

  get state(): DisplayState<LoadedRun> {
    return this.display;
  }

  get time(): number | null {
    return this.clock?.time ?? null;
  }

  get playing(): boolean {
    return this.clock?.playing ?? false;
  }

  get speed(): number {
    return this.clock?.speed ?? 1;
  }

  /** Load and display a run; a failed reload of the same run keeps it on screen. */
  async openRun(runId: string): Promise<void> {
    const token = ++this.loadToken;
    this.requested = runId;
    try {
      const response = await this.transport.getTrajectory(runId);
      if (token !== this.loadToken) return;
      const doc = parseTrajectory(response.trajectory);
      const url = (rel: string) => this.transport.artifactUrl(`${response.artifactBase}/${rel}`);
      const poses = parsePoses(await this.loadBytes(url(doc.poses.path)), doc.frameCount, doc.bodies.length);
      let contacts: LoadedRun["contacts"] = null;
      if (doc.contacts) {
        const data = parseContacts(await this.loadBytes(url(doc.contacts.path)), doc.contacts.count, doc.frameCount);
        contacts = { data, index: contactIndex(data, doc.frameCount) };
      }
      if (token !== this.loadToken) return;
      const initial = posesAt(doc.times, poses, doc.bodies.length, doc.times[0]);
      const scene = await this.buildTrajectory(doc, (mesh) => this.loadBytes(url(mesh)), initial);
      if (token !== this.loadToken) {
        disposeScene(scene);
        return;
      }
      const overlay = contacts ? createContactOverlay(maxContactsPerFrame(contacts.index)) : null;
      if (overlay) {
        overlay.group.visible = this.elements.contacts.checked;
        scene.root.add(overlay.group);
      }
      const previous = this.display.artifact;
      const keepTime = previous?.runId === runId ? this.clock?.time : undefined;
      const keepSpeed = this.clock?.speed ?? 1;
      this.stopLoop();
      this.display = afterLoad<LoadedRun>({ runId, doc, poses, contacts, scene, overlay }, response.stale, response.error);
      this.loadError = null;
      const now = this.now();
      this.clock = new PlaybackClock(doc.times[0], doc.times[doc.times.length - 1]);
      this.clock.setSpeed(keepSpeed, now);
      if (keepTime !== undefined) this.clock.seek(keepTime, now);
      for (const name of [...this.transparent]) {
        if (!doc.bodies.some((body) => body.name === name)) this.transparent.delete(name);
      }
      doc.bodies.forEach((body, k) => setTransparent(scene.materials[k], this.transparent.has(body.name)));
      this.viewport.setScene(scene);
      this.renderBodies();
      this.renderControls();
      this.applyTime();
      this.renderBanner();
    } catch (error) {
      if (token !== this.loadToken) return;
      this.loadError = error;
      // A failed reload keeps the last good trajectory marked stale; a failed switch to
      // another run must not leave the old one labelled as it.
      if (runId === this.displayedRunId) {
        const message = error instanceof Error ? error.message : String(error);
        this.display = { ...this.display, stale: true, error: message };
      } else {
        this.clear();
      }
      this.renderBanner();
    }
  }

  /**
   * Fold a finished run job into the display: a failure keeps the trajectory on screen and
   * marks it stale; success and cancellation change nothing here (the caller opens the new run).
   */
  handleJobFinished(job: Job): void {
    if (job.kind !== "run") return;
    this.display = afterJob(this.display, job);
    this.renderBanner();
  }

  toggle(): void {
    if (!this.clock) return;
    if (this.clock.playing) {
      this.clock.pause(this.now());
      this.stopLoop();
    } else {
      this.clock.play(this.now());
      this.startLoop();
    }
    this.applyTime();
  }

  restart(): void {
    if (!this.clock) return;
    this.clock.restart(this.now());
    this.applyTime();
  }

  seek(t: number): void {
    if (!this.clock) return;
    this.clock.seek(t, this.now());
    this.applyTime();
  }

  setSpeed(speed: number): void {
    const value = this.clock ? this.clock.setSpeed(speed, this.now()) : clampSpeed(speed);
    this.elements.speed.value = String(value);
    this.elements.speedLabel.textContent = `${value.toFixed(1)}×`;
  }

  setBodyTransparent(name: string, transparent: boolean): void {
    if (transparent) this.transparent.add(name);
    else this.transparent.delete(name);
    const run = this.display.artifact;
    if (!run) return;
    const index = run.doc.bodies.findIndex((body) => body.name === name);
    if (index >= 0) setTransparent(run.scene.materials[index], transparent);
    this.viewport.requestRender();
  }

  showContacts(visible: boolean): void {
    this.elements.contacts.checked = visible;
    const overlay = this.display.artifact?.overlay;
    if (!overlay) return;
    overlay.group.visible = visible;
    this.applyTime();
  }

  refreshBanner(): void {
    this.renderBanner();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.loadToken += 1;
    this.stopLoop();
  }

  private clear(): void {
    this.stopLoop();
    this.display = { ...emptyDisplay<LoadedRun>(), error: this.display.error };
    this.clock = null;
    this.viewport.setScene(null);
    this.elements.bodies.replaceChildren();
    this.renderControls();
  }

  private startLoop(): void {
    if (this.frameHandle !== null || this.disposed) return;
    const step = () => {
      this.frameHandle = null;
      if (!this.clock || this.disposed) return;
      this.clock.tick(this.now());
      this.applyTime();
      if (this.clock.playing) this.frameHandle = this.requestFrame(step);
    };
    this.frameHandle = this.requestFrame(step);
  }

  private stopLoop(): void {
    if (this.frameHandle !== null) this.cancelFrame(this.frameHandle);
    this.frameHandle = null;
  }

  /** Pose the bodies for the clock's time and refresh the time/phase/frame read-outs. */
  private applyTime(): void {
    const run = this.display.artifact;
    const clock = this.clock;
    if (!run || !clock) return;
    const { doc } = run;
    const t = clock.time;
    applyPoses(run.scene.bodies, posesAt(doc.times, run.poses, doc.bodies.length, t));
    const frame = nearestFrame(frameAt(doc.times, t));
    const phase = phaseAt(doc.phases, t);
    if (run.overlay && run.contacts && run.overlay.group.visible) {
      run.overlay.update(contactsAtFrame(run.contacts.data, run.contacts.index, frame));
    }
    const { seek, time, phase: phaseLabel, frame: frameLabel, play } = this.elements;
    seek.value = String(t);
    time.textContent = `${seconds(t)} / ${seconds(clock.end)} s`;
    phaseLabel.textContent = phase >= 0 ? doc.phases[phase].name : "—";
    frameLabel.textContent = `frame ${frame} / ${doc.frameCount - 1}`;
    play.textContent = clock.playing ? "Pause" : "Play";
    play.setAttribute("aria-pressed", String(clock.playing));
    this.viewport.requestRender();
  }

  private renderControls(): void {
    const run = this.display.artifact;
    const clock = this.clock;
    const { panel, play, restart, seek, speed, contacts, contactsNote } = this.elements;
    panel.hidden = !run;
    for (const control of [play, restart, seek, speed]) control.disabled = !run;
    if (run && clock) {
      seek.min = String(clock.start);
      seek.max = String(clock.end);
      seek.step = "any";
      this.setSpeed(clock.speed);
    }
    contacts.disabled = !run?.overlay;
    contactsNote.textContent = run && !run.overlay
      ? "No contacts in this export; run `cad gui trajectory RUN_DIR --contacts`."
      : "";
  }

  private renderBodies(): void {
    const run = this.display.artifact;
    const container = this.elements.bodies;
    container.replaceChildren();
    if (!run) return;
    const list = document.createElement("ul");
    list.className = "body-list";
    for (const body of run.doc.bodies) {
      const item = document.createElement("li");
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = this.transparent.has(body.name);
      box.dataset.body = body.name;
      box.addEventListener("change", () => this.setBodyTransparent(body.name, box.checked));
      const name = document.createElement("span");
      name.textContent = body.fixed ? `${body.name} (fixed)` : body.name;
      label.append(box, name);
      label.title = "Transparent";
      item.appendChild(label);
      list.appendChild(item);
    }
    container.appendChild(list);
  }

  private renderBanner(): void {
    renderBanner(
      this.elements.banner,
      bannerFor({
        subject: "trajectory",
        stale: this.display.stale,
        sceneError: this.display.error,
        loadError: this.loadError,
      }),
    );
  }
}

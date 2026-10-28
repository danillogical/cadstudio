/**
 * Owns the displayed run: loads the trajectory, its poses and meshes, drives the clock and
 * the playback controls, and keeps the last good trajectory (marked stale) when a run fails.
 */
import { bannerFor, renderBanner } from "../app/banner";
import { afterJob, afterLoad, emptyDisplay, type DisplayState } from "../app/jobs";
import { disposeScene } from "../scene/mapping";
import {
  type ArtifactRange,
  type CadStudioTransport,
  type Job,
  type LiveDoc,
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
  applyVisibility,
  buildTrajectoryGroup,
  setTransparent,
  type LoadedTrajectory,
} from "./mapping";
import {
  LIVE_MAX_LAG,
  LIVE_POLL_MS,
  LIVE_STALL_MS,
  LIVE_TARGET_LAG,
  LiveBuffer,
  liveReady,
  liveTrajectoryDoc,
  updateLivePhases,
  updateLiveRemovals,
} from "./live";
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
  /** Shows "LIVE sim / planned" while a live run is displayed. */
  liveBadge?: HTMLElement;
}

/** Where a displayed live run stands; `null` on a `LoadedRun` that is a finished trajectory. */
export interface LiveRunState {
  id: string;
  buffer: LiveBuffer;
  /** The latest `live.json`. */
  info: LiveDoc;
  /** Frames the service has announced; the buffer catches up to it. */
  target: number;
  /** `now()` when the frame count last grew. */
  lastChange: number;
  lastPoll: number;
  stalled: boolean;
  /** No more frames are coming (finished, or the writer stopped). */
  ended: boolean;
  /** The playhead is kept just behind the newest frame; a manual seek lets go. */
  trailing: boolean;
  fetching: boolean;
  syncing: boolean;
  resync: boolean;
}

/** Everything one displayed run needs. */
export interface LoadedRun {
  runId: string;
  doc: TrajectoryDoc;
  poses: Float32Array;
  contacts: { data: Float32Array; index: Uint32Array } | null;
  scene: LoadedTrajectory;
  overlay: ContactOverlay | null;
  live: LiveRunState | null;
}

export interface OpenOptions {
  /** Play at 1x and loop; manual pause turns it off. */
  autoplay?: boolean;
}

/** If no animation frame has fired for this long (ms) while playing, a timer drives the clock. */
export const RAF_STALL_MS = 250;
const FALLBACK_INTERVAL_MS = 33;

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
  /** Bytes of an `out/`-relative artifact (from `range.offset` on); defaults to `transport.getArtifact`. */
  loadBytes?: (path: string, range?: ArtifactRange) => Promise<ArrayBuffer>;
  /** Milliseconds, monotonic. */
  now?: () => number;
  requestFrame?: (callback: () => void) => number;
  cancelFrame?: (handle: number) => void;
  /** Timers for the rAF-stall fallback and the live tail; injectable for tests. */
  setInterval?: (callback: () => void, ms: number) => unknown;
  clearInterval?: (handle: unknown) => void;
  /** Called once a run or live run is on screen; `live` is true for a run still streaming. */
  onOpened?: (runId: string, live: boolean) => void;
}

function seconds(value: number): string {
  return value.toFixed(3);
}

/** Pose every body for sim time `t` and hide the ones removed by then. */
function poseScene(scene: LoadedTrajectory, doc: TrajectoryDoc, poses: Float32Array, t: number): void {
  applyPoses(scene.bodies, posesAt(doc.times, poses, doc.bodies.length, t, doc.bodies));
  applyVisibility(scene.bodies, doc.bodies, t);
}

export class PlaybackController {
  private readonly transport: CadStudioTransport;
  private readonly viewport: TrajectoryViewport;
  private readonly elements: PlaybackElements;
  private readonly buildTrajectory: NonNullable<PlaybackOptions["buildTrajectory"]>;
  private readonly loadBytes: (path: string, range?: ArtifactRange) => Promise<ArrayBuffer>;
  private readonly setTimer: (callback: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;
  private readonly onOpened: (runId: string, live: boolean) => void;
  private readonly now: () => number;
  private readonly requestFrame: (callback: () => void) => number;
  private readonly cancelFrame: (handle: number) => void;

  private display: DisplayState<LoadedRun> = emptyDisplay();
  private clock: PlaybackClock | null = null;
  private requested: string | null = null;
  private loadError: unknown = null;
  private loadToken = 0;
  private frameHandle: number | null = null;
  private fallbackHandle: unknown = null;
  private tailHandle: unknown = null;
  private lastFrameAt = 0;
  /** The run was opened to autoplay (and loop) ... */
  private autoplayRun = false;
  /** ... until the user pauses it. */
  private userPaused = false;
  /** A live run that was asked for before it had bodies and frames. */
  private pendingLive: string | null = null;
  private readonly transparent = new Set<string>();
  private disposed = false;

  constructor(options: PlaybackOptions) {
    this.transport = options.transport;
    this.viewport = options.viewport;
    this.elements = options.elements;
    this.buildTrajectory = options.buildTrajectory ?? buildTrajectoryGroup;
    this.onOpened = options.onOpened ?? (() => {});
    this.loadBytes = options.loadBytes ?? ((path, range) => this.transport.getArtifact(path, range));
    this.setTimer = options.setInterval ?? ((cb, ms) => globalThis.setInterval(cb, ms));
    this.clearTimer =
      options.clearInterval ?? ((handle) => globalThis.clearInterval(handle as ReturnType<typeof setInterval>));
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

  /** The live run on screen or waiting for its first frames. */
  get liveId(): string | null {
    return this.display.artifact?.live?.id ?? this.pendingLive;
  }

  /** Whether the user's pause has turned autoplay off. */
  get autoplaying(): boolean {
    return this.autoplayRun && !this.userPaused;
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
  async openRun(runId: string, options: OpenOptions = {}): Promise<void> {
    const token = ++this.loadToken;
    this.requested = runId;
    this.pendingLive = null;
    try {
      const response = await this.transport.getTrajectory(runId);
      if (token !== this.loadToken) return;
      const doc = parseTrajectory(response.trajectory);
      const artifact = (rel: string) => `${response.artifactBase}/${rel}`;
      const poses = parsePoses(await this.loadBytes(artifact(doc.poses.path)), doc.frameCount, doc.bodies.length);
      let contacts: LoadedRun["contacts"] = null;
      if (doc.contacts) {
        const data = parseContacts(await this.loadBytes(artifact(doc.contacts.path)), doc.contacts.count, doc.frameCount);
        contacts = { data, index: contactIndex(data, doc.frameCount) };
      }
      if (token !== this.loadToken) return;
      const initial = posesAt(doc.times, poses, doc.bodies.length, doc.times[0], doc.bodies);
      const scene = await this.buildTrajectory(doc, (mesh) => this.loadBytes(artifact(mesh)), initial);
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
      // The finished trajectory of the live run on screen takes over its place and play state.
      const swap = previous?.live?.id === runId;
      const resume = swap ? this.autoplaying : options.autoplay === true;
      this.stopLoop();
      this.stopLive();
      this.display = afterLoad<LoadedRun>({ runId, doc, poses, contacts, scene, overlay, live: null }, response.stale, response.error);
      this.loadError = null;
      const now = this.now();
      this.clock = new PlaybackClock(doc.times[0], doc.times[doc.times.length - 1]);
      this.clock.setSpeed(keepSpeed, now);
      if (keepTime !== undefined) this.clock.seek(keepTime, now);
      for (const name of [...this.transparent]) {
        if (!doc.bodies.some((body) => body.name === name)) this.transparent.delete(name);
      }
      doc.bodies.forEach((body, k) => setTransparent(scene.materials[k], this.transparent.has(body.name)));
      if (!swap) {
        this.autoplayRun = options.autoplay === true;
        this.userPaused = false;
      }
      // Pose and hide bodies for the clock's time first, so the fit below frames what is shown.
      poseScene(scene, doc, poses, this.clock.time);
      this.viewport.setScene(scene);
      this.renderBodies();
      this.renderControls();
      if (resume) {
        this.clock.play(now);
        this.startLoop();
      }
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
      this.userPaused = true;
      this.stopLoop();
    } else {
      this.clock.play(this.now());
      this.userPaused = false;
      this.startLoop();
    }
    this.applyTime();
  }

  restart(): void {
    if (!this.clock) return;
    this.letGoOfLive();
    this.clock.restart(this.now());
    this.applyTime();
  }

  seek(t: number): void {
    if (!this.clock) return;
    this.letGoOfLive();
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

  /**
   * Show a running run as it is written: load the meshes and the poses so far, autoplay at 1x
   * and keep tailing `poses.bin`. A run with no bodies or frames yet is remembered and opened
   * by the next `handleLive` that finds it ready. A run that already finished opens as a
   * normal trajectory.
   */
  async openLive(liveId: string): Promise<void> {
    const token = ++this.loadToken;
    this.requested = liveId;
    this.pendingLive = liveId;
    try {
      const info = await this.transport.getLive(liveId);
      if (token !== this.loadToken) return;
      if (info.done && info.runId) {
        await this.openRun(info.runId, { autoplay: true });
        return;
      }
      if (!liveReady(info)) return;
      const base = `${liveId}.live`;
      const buffer = new LiveBuffer(info.bodies.length, info.fps, info.t0 as number);
      const bytes = await this.loadBytes(`${base}/${info.poses.path}`);
      if (token !== this.loadToken) return;
      buffer.append(bytes, info.frames);
      if (buffer.frames < 1) return;
      const doc = liveTrajectoryDoc(info, liveId, buffer);
      const initial = posesAt(doc.times, buffer.poses, doc.bodies.length, doc.times[0], doc.bodies);
      const scene = await this.buildTrajectory(doc, (mesh) => this.loadBytes(`${base}/${mesh}`), initial);
      if (token !== this.loadToken) {
        disposeScene(scene);
        return;
      }
      const now = this.now();
      const live: LiveRunState = {
        id: liveId,
        buffer,
        info,
        target: info.frames,
        lastChange: now,
        lastPoll: now,
        stalled: false,
        ended: false,
        trailing: true,
        fetching: false,
        syncing: false,
        resync: false,
      };
      this.stopLoop();
      this.stopLive();
      this.pendingLive = null;
      this.display = afterLoad<LoadedRun>({ runId: liveId, doc, poses: buffer.poses, contacts: null, scene, overlay: null, live }, false, null);
      this.loadError = null;
      this.autoplayRun = true;
      this.userPaused = false;
      const end = doc.times[doc.times.length - 1];
      this.clock = new PlaybackClock(doc.times[0], end);
      this.clock.setHold(true, now);
      this.clock.setSpeed(1, now);
      this.clock.seek(Math.max(doc.times[0], end - LIVE_TARGET_LAG), now);
      for (const name of [...this.transparent]) {
        if (!doc.bodies.some((body) => body.name === name)) this.transparent.delete(name);
      }
      doc.bodies.forEach((body, k) => setTransparent(scene.materials[k], this.transparent.has(body.name)));
      poseScene(scene, doc, buffer.poses, this.clock.time);
      this.viewport.setScene(scene);
      this.renderBodies();
      this.renderControls();
      this.clock.play(now);
      this.startLoop();
      this.tailHandle = this.setTimer(() => this.tailTick(live), 1000);
      this.applyTime();
      this.renderBanner();
      this.onOpened(liveId, true);
      // Catch up with whatever arrived while the meshes loaded.
      void this.syncLive(live);
    } catch (error) {
      if (token !== this.loadToken) return;
      this.loadError = error;
      this.renderBanner();
    }
  }

  /** A `live` artifact event: wake the tail of the run on screen, or open one that was waiting. */
  handleLive(event: { liveId: string; frames: number; done: boolean }): void {
    const live = this.display.artifact?.live;
    if (live && live.id === event.liveId) {
      live.target = Math.max(live.target, event.frames);
      void this.syncLive(live);
    } else if (this.pendingLive === event.liveId) {
      void this.openLive(event.liveId);
    }
  }

  /** Re-read `live.json`, fetch the new pose bytes, and finish the run when it is done. */
  private async syncLive(live: LiveRunState): Promise<void> {
    if (live.syncing) {
      live.resync = true;
      return;
    }
    live.syncing = true;
    try {
      do {
        live.resync = false;
        const info = await this.transport.getLive(live.id);
        if (this.display.artifact?.live !== live) return;
        live.info = info;
        live.lastPoll = this.now();
        live.target = Math.max(live.target, info.frames);
        // Before any new frame is shown: frames past a removal hold the off-scene parking pose.
        const shown = this.display.artifact;
        if (shown?.live === live) updateLiveRemovals(shown.doc, info);
        await this.pump(live);
        const run = this.display.artifact;
        if (!run || run.live !== live) return;
        updateLivePhases(run.doc, info, live.buffer);
        if (info.done && live.buffer.frames >= live.target) {
          await this.finishLive(live);
          return;
        }
      } while (live.resync);
    } catch (error) {
      // A failed poll is retried by the next event or tick; the frames already shown stay.
      if (this.display.artifact?.live === live) {
        this.loadError = error;
        this.renderBanner();
      }
    } finally {
      live.syncing = false;
    }
    this.applyTime();
  }

  /** Fetch pose bytes past the buffer's end until it holds `live.target` frames or the bytes run out. */
  private async pump(live: LiveRunState): Promise<void> {
    if (live.fetching) return;
    live.fetching = true;
    try {
      while (live.buffer.frames < live.target) {
        const path = `${live.id}.live/${live.info.poses.path}`;
        const bytes = await this.loadBytes(path, { offset: live.buffer.byteOffset });
        const run = this.display.artifact;
        if (!run || run.live !== live) return;
        const added = live.buffer.append(bytes, live.target);
        if (added === 0) return;
        this.framesAppended(run, live);
      }
    } finally {
      live.fetching = false;
    }
  }

  private framesAppended(run: LoadedRun, live: LiveRunState): void {
    const { buffer } = live;
    const now = this.now();
    run.poses = buffer.poses;
    run.doc.frameCount = buffer.frames;
    run.doc.poses.shape = [buffer.frames, run.doc.bodies.length, run.doc.poses.shape[2]];
    live.lastChange = now;
    live.stalled = false;
    const clock = this.clock;
    if (!clock) return;
    const end = buffer.times[buffer.frames - 1];
    clock.extend(end, now);
    // Keep the playhead just behind the newest frame when it has fallen well back.
    if (live.trailing && clock.playing && end - clock.time > LIVE_MAX_LAG) {
      clock.seek(end - LIVE_TARGET_LAG, now);
    }
    this.applyTime();
  }

  /** Once a second: poll if no event has come lately, and flag a run whose frames stopped coming. */
  private tailTick(live: LiveRunState): void {
    if (this.display.artifact?.live !== live || live.ended) return;
    const now = this.now();
    if (!live.stalled && now - live.lastChange > LIVE_STALL_MS) {
      live.stalled = true;
      this.applyTime();
    }
    if (!live.stalled && now - live.lastPoll >= LIVE_POLL_MS) void this.syncLive(live);
  }

  /** The run is done: swap to its finished trajectory (same bodies), or keep the buffer and loop it. */
  private async finishLive(live: LiveRunState): Promise<void> {
    const { info } = live;
    live.ended = true;
    if (this.tailHandle !== null) this.clearTimer(this.tailHandle);
    this.tailHandle = null;
    if (info.runId) {
      await this.openRun(info.runId, { autoplay: this.autoplaying });
      // openRun keeps the live buffer on screen if the trajectory could not be loaded.
      if (this.display.artifact?.live !== live) return;
    }
    this.clock?.setHold(false, this.now());
    live.trailing = false;
    this.applyTime();
  }

  private stopLive(): void {
    if (this.tailHandle !== null) this.clearTimer(this.tailHandle);
    this.tailHandle = null;
  }

  refreshBanner(): void {
    this.renderBanner();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.loadToken += 1;
    this.stopLoop();
    this.stopLive();
  }

  private clear(): void {
    this.stopLoop();
    this.stopLive();
    this.display = { ...emptyDisplay<LoadedRun>(), error: this.display.error };
    this.clock = null;
    this.viewport.setScene(null);
    this.elements.bodies.replaceChildren();
    this.renderControls();
  }

  /**
   * Drive the clock from animation frames. The clock is wall-clock based, so a missed frame
   * costs smoothness, never sim time. If frames stop (an unfocused window throttling rAF), a
   * 33 ms timer drives the clock until rAF resumes.
   */
  private startLoop(): void {
    if (this.frameHandle !== null || this.disposed) return;
    const step = () => {
      this.frameHandle = null;
      if (!this.clock || this.disposed) return;
      this.lastFrameAt = this.now();
      this.advance();
      if (this.clock.playing) this.frameHandle = this.requestFrame(step);
      else this.stopLoop();
    };
    this.lastFrameAt = this.now();
    this.frameHandle = this.requestFrame(step);
    if (this.fallbackHandle === null) {
      this.fallbackHandle = this.setTimer(() => {
        if (!this.clock || this.disposed) return;
        if (!this.clock.playing) {
          this.stopLoop();
          return;
        }
        if (this.now() - this.lastFrameAt <= RAF_STALL_MS) return;
        this.advance();
        if (!this.clock.playing) this.stopLoop();
      }, FALLBACK_INTERVAL_MS);
    }
  }

  private stopLoop(): void {
    if (this.frameHandle !== null) this.cancelFrame(this.frameHandle);
    this.frameHandle = null;
    if (this.fallbackHandle !== null) this.clearTimer(this.fallbackHandle);
    this.fallbackHandle = null;
  }

  /** One clock step: advance, loop an autoplayed run that ended, and redraw. */
  private advance(): void {
    const clock = this.clock;
    if (!clock) return;
    const now = this.now();
    clock.tick(now);
    if (!clock.playing && clock.ended && this.shouldLoop()) {
      clock.seek(clock.start, now);
      clock.play(now);
    }
    this.applyTime();
  }

  private shouldLoop(): boolean {
    const live = this.display.artifact?.live;
    return this.autoplaying && (!live || live.ended);
  }

  /** The user took the playhead somewhere; stop pulling it toward the newest frame. */
  private letGoOfLive(): void {
    const live = this.display.artifact?.live;
    if (live) live.trailing = false;
  }

  /** Pose the bodies for the clock's time and refresh the time/phase/frame read-outs. */
  private applyTime(): void {
    const run = this.display.artifact;
    const clock = this.clock;
    if (!run || !clock) return;
    const { doc } = run;
    const t = clock.time;
    poseScene(run.scene, doc, run.poses, t);
    const frame = nearestFrame(frameAt(doc.times, t));
    const phase = phaseAt(doc.phases, t);
    if (run.overlay && run.contacts && run.overlay.group.visible) {
      run.overlay.update(contactsAtFrame(run.contacts.data, run.contacts.index, frame));
    }
    const { seek, time, phase: phaseLabel, frame: frameLabel, play } = this.elements;
    if (run.live) seek.max = String(clock.end);
    seek.value = String(t);
    time.textContent = `${seconds(t)} / ${seconds(clock.end)} s`;
    phaseLabel.textContent = phase >= 0 ? doc.phases[phase].name : "—";
    frameLabel.textContent = `frame ${frame} / ${doc.frameCount - 1}`;
    play.textContent = clock.playing ? "Pause" : "Play";
    play.setAttribute("aria-pressed", String(clock.playing));
    this.renderLive(run);
    this.viewport.requestRender();
  }

  private renderLive(run: LoadedRun): void {
    const badge = this.elements.liveBadge;
    if (!badge) return;
    const live = run.live;
    badge.hidden = !live;
    if (!live) return;
    const state = live.ended ? "ended" : live.stalled ? "stalled" : "live";
    const newest = live.buffer.times[live.buffer.frames - 1] ?? live.buffer.t0;
    const sim = live.info.simTime ?? newest;
    const planned = live.info.plannedTime;
    const span = planned !== null ? `${sim.toFixed(2)} / ${planned.toFixed(2)} s` : `${sim.toFixed(2)} s`;
    const why = live.info.error ?? live.info.status;
    badge.dataset.state = state;
    badge.textContent =
      state === "live" ? `LIVE ${span}` : state === "stalled" ? `STALLED ${span}` : `ENDED${why ? ` (${why})` : ""} ${span}`;
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
    contactsNote.textContent = run?.live
      ? "Contacts are not shown while a run is live."
      : run && !run.overlay
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

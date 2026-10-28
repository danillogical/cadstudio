import "./style.css";
import { AppController } from "./app/controller";
import { FollowManager } from "./app/follow";
import { renderBanner } from "./app/banner";
import { JobPanel } from "./app/jobs-panel";
import { targetFromSearch } from "./app/navigate";
import { PlaybackController } from "./playback/controller";
import { BrowserTransport } from "./transport/browser";
import type { NavigateTarget } from "./transport/messages";
import { TransportError, type CadStudioTransport, type Job, type RunEntry } from "./transport/types";
import { hasVsCodeApi, VsCodeTransport } from "./transport/vscode";
import { Viewport, type LayerName } from "./viewport/viewport";

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
}

function describe(error: unknown): string {
  return error instanceof TransportError && error.status === 401
    ? "Missing or invalid token; open the URL printed by `cad gui serve`."
    : error instanceof Error
      ? error.message
      : String(error);
}

async function main(): Promise<void> {
  const banner = element("banner");
  const runBanner = element("run-banner");
  const picker = element<HTMLSelectElement>("model-picker");
  const runPicker = element<HTMLSelectElement>("run-picker");
  const stage = element("stage");
  const showModel = element<HTMLButtonElement>("show-model");
  const showRun = element<HTMLButtonElement>("show-run");

  // Same UI in both hosts; only the transport differs. A browser opened by `cad gui open`
  // carries its target as `?model=` or `?run=`; the webview gets it as a `navigate` message.
  const vscodeTransport = hasVsCodeApi() ? VsCodeTransport.fromWebview() : null;
  const urlTarget = vscodeTransport ? null : targetFromSearch(globalThis.location.search);
  const transport: CadStudioTransport = vscodeTransport ?? BrowserTransport.fromLocation();
  const viewport = new Viewport(element("viewport"));
  const controller = new AppController({
    transport,
    viewport: viewport.layer("scene"),
    elements: {
      banner,
      tree: element("tree"),
      props: element("props"),
    },
  });
  const follow = new FollowManager({
    transport,
    onStatus: (text) => {
      element("follow-status").textContent = text;
    },
  });
  const followBox = element<HTMLInputElement>("follow");
  followBox.checked = follow.enabled;
  followBox.addEventListener("change", () => follow.setEnabled(followBox.checked));
  // A run that streams in is shown as soon as it has frames, wherever the user was looking.
  const showLiveRun = () => {
    showLayer("trajectory");
    showRun.disabled = false;
  };
  const playback = new PlaybackController({
    transport,
    onOpened: (_id, live) => {
      if (live) showLiveRun();
    },
    viewport: viewport.layer("trajectory"),
    elements: {
      panel: element("playback"),
      banner: runBanner,
      play: element("play"),
      restart: element("restart"),
      seek: element("seek"),
      speed: element("speed"),
      speedLabel: element("speed-label"),
      time: element("play-time"),
      phase: element("play-phase"),
      frame: element("play-frame"),
      bodies: element("bodies"),
      contacts: element("contacts"),
      contactsNote: element("contacts-note"),
      liveBadge: element("live-badge"),
    },
  });

  const showLayer = (layer: LayerName) => {
    viewport.setActiveLayer(layer);
    stage.dataset.layer = layer;
    showModel.setAttribute("aria-pressed", String(layer === "scene"));
    showRun.setAttribute("aria-pressed", String(layer === "trajectory"));
    showRun.disabled = playback.displayedRunId === null && layer !== "trajectory";
  };
  showModel.addEventListener("click", () => showLayer("scene"));
  showRun.addEventListener("click", () => showLayer("trajectory"));

  const openRun = async (runId: string, autoplay = false) => {
    showLayer("trajectory");
    await playback.openRun(runId, { autoplay });
    showRun.disabled = playback.displayedRunId === null;
  };

  const runPlaceholder = document.createElement("option");
  runPlaceholder.value = "";
  runPlaceholder.textContent = "Select a run…";
  const refreshRuns = async (select?: string): Promise<RunEntry[]> => {
    try {
      const { runs } = await transport.listRuns();
      const current = select ?? runPicker.value;
      runPicker.replaceChildren(runPlaceholder);
      for (const run of runs) {
        const option = document.createElement("option");
        option.value = run.runId;
        option.textContent = run.status ? `${run.runId} (${run.status})` : run.runId;
        runPicker.appendChild(option);
      }
      if (runs.some((run) => run.runId === current)) runPicker.value = current;
      runPicker.disabled = runs.length === 0;
      return runs;
    } catch (error) {
      renderBanner(runBanner, { kind: "error", text: `Could not list runs: ${describe(error)}` });
      return [];
    }
  };

  const onJobFinished = (job: Job) => {
    if (job.kind === "build") {
      controller.handleEvent({ type: "job", job });
      return;
    }
    playback.handleJobFinished(job);
    const runId = job.artifacts.runId;
    const alreadyShown = follow.enabled && (playback.liveId === runId || playback.displayedRunId === runId);
    if (job.status === "succeeded" && runId && !alreadyShown) {
      void refreshRuns(runId).then(() => openRun(runId, follow.enabled));
    } else {
      void refreshRuns();
    }
  };
  const jobs = new JobPanel({
    transport,
    onFinished: onJobFinished,
    elements: {
      build: element("build"),
      run: element("run"),
      scenario: element("run-scenario"),
      acceptance: element("run-acceptance"),
      options: element("run-options"),
      status: element("job-status"),
      log: element("job-log"),
      cancel: element("job-cancel"),
    },
  });

  viewport.onPick = (partId) => {
    if (viewport.activeLayer === "scene") controller.selection.set(partId);
    else viewport.setLayerHighlight("trajectory", partId);
  };

  element("fit").addEventListener("click", () => viewport.fit());
  element("runs-refresh").addEventListener("click", () => void refreshRuns());

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select a model…";
  picker.appendChild(placeholder);
  picker.disabled = true;
  runPicker.appendChild(runPlaceholder);
  runPicker.disabled = true;

  let modelsLoaded = false;
  const hasModel = (model: string) => [...picker.options].some((option) => option.value === model);
  // Fill the picker from the service's list, keeping the current selection when it is listed.
  const fillPicker = (models: string[]) => {
    const current = picker.value;
    picker.replaceChildren(placeholder);
    for (const model of models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      picker.appendChild(option);
    }
    picker.disabled = models.length === 0;
    picker.value = models.includes(current) ? current : "";
  };
  // Re-read the model list, since a model created after startup is not in the picker yet.
  const refreshModels = async () => {
    try {
      fillPicker((await transport.listModels()).models);
    } catch {
      // Keep the list we have; a navigate that still misses reports the unknown model.
    }
  };

  const selectModel = (model: string) => {
    picker.value = model;
    follow.setModel(model);
    showLayer("scene");
    void controller.loadModel(model);
    void jobs.setModel(model);
  };
  picker.addEventListener("change", () => {
    if (picker.value) selectModel(picker.value);
  });
  runPicker.addEventListener("change", () => {
    if (runPicker.value) void openRun(runPicker.value);
  });

  // Live ids already opened or offered, so a late event of an old run never reopens it.
  const seenLive = new Set<string>();
  const openLive = (liveId: string) => {
    seenLive.add(liveId);
    void playback.openLive(liveId);
  };
  const onLiveEvent = (event: { liveId: string; frames: number; done: boolean }) => {
    if (!follow.enabled) return;
    if (playback.liveId === event.liveId) playback.handleLive(event);
    else if (!event.done && !seenLive.has(event.liveId)) openLive(event.liveId);
  };
  // A finished run in follow mode plays by itself; a run being streamed is swapped in place.
  const onRunEvent = (runId: string) => {
    if (!follow.enabled) {
      void refreshRuns();
      return;
    }
    void refreshRuns().then((runs) => {
      if (playback.runId === runId || playback.liveId === runId) return;
      if (runs.some((run) => run.runId === runId && run.status)) void openRun(runId, true);
    });
  };
  const unsubscribe = transport.subscribe((event) => {
    if (event.type === "connection") {
      if (event.state === "error") {
        renderBanner(banner, { kind: "error", text: "Live updates disconnected; retrying…" });
      } else {
        controller.refreshBanner();
        playback.refreshBanner();
      }
      return;
    }
    if (event.type === "artifact" && event.kind === "live") {
      onLiveEvent(event);
      return;
    }
    if (event.type === "artifact" && event.kind === "run") onRunEvent(event.runId);
    // A scene built for a model the picker has not seen means a new model: list it, do not switch.
    if (event.type === "artifact" && event.kind === "scene" && modelsLoaded && !hasModel(event.model)) {
      void refreshModels();
    }
    // The job panel reports its own job's finish once; everything else goes to the scene.
    if (jobs.owns(event)) jobs.handleEvent(event);
    else controller.handleEvent(event);
  });
  globalThis.addEventListener("pagehide", () => {
    unsubscribe();
    follow.dispose();
    jobs.dispose();
    playback.dispose();
    controller.dispose();
    viewport.dispose();
  });

  // At startup, join a run that is still being written (and began within the last 30 s).
  const openRecentLive = async () => {
    try {
      const { lives } = await transport.listLive();
      const now = Date.now() / 1000;
      const recent = lives.find((live) => !live.done && live.mtime !== null && now - live.mtime < 30);
      if (recent && playback.liveId === null && playback.runId === null) openLive(recent.liveId);
    } catch {
      // A service without live runs just has nothing to join.
    }
  };

  let markInitialised: () => void = () => {};
  const initialised = new Promise<void>((resolve) => {
    markInitialised = resolve;
  });
  // Show a `cad gui open` target as if it had been picked, once the model list is in.
  const navigate = async (target: NavigateTarget) => {
    await initialised;
    if (!modelsLoaded) return; // The service error is already on the banner.
    if ("model" in target) {
      if (!hasModel(target.model)) await refreshModels();
      if (hasModel(target.model)) selectModel(target.model);
      else renderBanner(banner, { kind: "error", text: `Unknown model ${target.model}.` });
      return;
    }
    await refreshRuns(target.run);
    await openRun(target.run, true);
  };
  if (vscodeTransport) {
    vscodeTransport.onNavigate((target) => void navigate(target));
    vscodeTransport.ready();
  }

  try {
    const health = await transport.health();
    if (health.protocolVersion !== 1) {
      renderBanner(banner, {
        kind: "error",
        text: `Service protocol ${health.protocolVersion} does not match this UI (1).`,
      });
    }
    const models = await transport.listModels();
    fillPicker(models.models);
    modelsLoaded = true;
    void refreshRuns();
    if (models.models.length === 1 && !urlTarget) {
      picker.value = models.models[0];
      follow.setModel(models.models[0]);
      void jobs.setModel(models.models[0]);
      await controller.loadModel(models.models[0]);
    }
  } catch (error) {
    renderBanner(banner, { kind: "error", text: `Could not reach the GUI service: ${describe(error)}` });
  }
  markInitialised();
  if (follow.enabled && !urlTarget) void openRecentLive();
  if (urlTarget) await navigate(urlTarget);
}

void main();

import "./style.css";
import { AppController } from "./app/controller";
import { renderBanner } from "./app/banner";
import { JobPanel } from "./app/jobs-panel";
import { PlaybackController } from "./playback/controller";
import { BrowserTransport } from "./transport/browser";
import { TransportError, type Job } from "./transport/types";
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

  const transport = BrowserTransport.fromLocation();
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
  const playback = new PlaybackController({
    transport,
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

  const openRun = async (runId: string) => {
    showLayer("trajectory");
    await playback.openRun(runId);
    showRun.disabled = playback.displayedRunId === null;
  };

  const runPlaceholder = document.createElement("option");
  runPlaceholder.value = "";
  runPlaceholder.textContent = "Select a run…";
  const refreshRuns = async (select?: string) => {
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
    } catch (error) {
      renderBanner(runBanner, { kind: "error", text: `Could not list runs: ${describe(error)}` });
    }
  };

  const onJobFinished = (job: Job) => {
    if (job.kind === "build") {
      controller.handleEvent({ type: "job", job });
      return;
    }
    playback.handleJobFinished(job);
    const runId = job.artifacts.runId;
    if (job.status === "succeeded" && runId) {
      void refreshRuns(runId).then(() => openRun(runId));
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

  picker.addEventListener("change", () => {
    const model = picker.value;
    if (!model) return;
    showLayer("scene");
    void controller.loadModel(model);
    void jobs.setModel(model);
  });
  runPicker.addEventListener("change", () => {
    if (runPicker.value) void openRun(runPicker.value);
  });

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
    // The job panel reports its own job's finish once; everything else goes to the scene.
    if (jobs.owns(event)) jobs.handleEvent(event);
    else controller.handleEvent(event);
    if (event.type === "artifact" && event.kind === "run") void refreshRuns();
  });
  globalThis.addEventListener("pagehide", () => {
    unsubscribe();
    jobs.dispose();
    playback.dispose();
    controller.dispose();
    viewport.dispose();
  });

  try {
    const health = await transport.health();
    if (health.protocolVersion !== 1) {
      renderBanner(banner, {
        kind: "error",
        text: `Service protocol ${health.protocolVersion} does not match this UI (1).`,
      });
    }
    const models = await transport.listModels();
    picker.replaceChildren(placeholder);
    for (const model of models.models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      picker.appendChild(option);
    }
    picker.disabled = models.models.length === 0;
    void refreshRuns();
    if (models.models.length === 1) {
      picker.value = models.models[0];
      void jobs.setModel(models.models[0]);
      await controller.loadModel(models.models[0]);
    }
  } catch (error) {
    renderBanner(banner, { kind: "error", text: `Could not reach the GUI service: ${describe(error)}` });
  }
}

void main();

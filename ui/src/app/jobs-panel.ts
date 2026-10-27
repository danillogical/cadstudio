/**
 * Build and Run controls: start jobs, follow the one started here (SSE plus a polling
 * fallback), show progress and the log tail, and cancel. Runs only offer the files the
 * service lists for the model.
 */
import type { CadStudioTransport, Job, PhysicsInputFile, ServiceEvent } from "../transport/types";
import { canCancel, JobTracker, jobProgress, logTail, type JobTransition } from "./jobs";

export interface JobPanelElements {
  build: HTMLButtonElement;
  run: HTMLButtonElement;
  scenario: HTMLSelectElement;
  acceptance: HTMLSelectElement;
  options: HTMLSelectElement;
  status: HTMLElement;
  log: HTMLElement;
  cancel: HTMLButtonElement;
}

export interface JobPanelOptions {
  transport: CadStudioTransport;
  elements: JobPanelElements;
  /** Called once when the tracked job first reaches a terminal state. */
  onFinished?: (job: Job) => void;
  /** Epoch seconds, matching the server's job timestamps. */
  now?: () => number;
  pollMs?: number;
  setInterval?: (callback: () => void, ms: number) => unknown;
  clearInterval?: (handle: unknown) => void;
}

export const LOG_LINES = 20;
const NO_OPTIONS = "";

function fill(select: HTMLSelectElement, files: PhysicsInputFile[], none?: string): void {
  const previous = select.value;
  select.replaceChildren();
  if (none !== undefined) {
    const option = document.createElement("option");
    option.value = NO_OPTIONS;
    option.textContent = none;
    select.appendChild(option);
  }
  for (const file of files) {
    const option = document.createElement("option");
    option.value = file.path;
    option.textContent = file.name;
    option.title = file.path;
    select.appendChild(option);
  }
  // Keep the user's choice across refreshes; otherwise select the first entry explicitly.
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
  else if (select.options.length > 0) select.selectedIndex = 0;
}

export class JobPanel {
  readonly tracker = new JobTracker();

  private readonly transport: CadStudioTransport;
  private readonly elements: JobPanelElements;
  private readonly onFinished: (job: Job) => void;
  private readonly now: () => number;
  private readonly pollMs: number;
  private readonly setTimer: (callback: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;
  private model: string | null = null;
  private inputsToken = 0;
  private timer: unknown = null;
  private message: string | null = null;

  constructor(options: JobPanelOptions) {
    this.transport = options.transport;
    this.elements = options.elements;
    this.onFinished = options.onFinished ?? (() => {});
    this.now = options.now ?? (() => Date.now() / 1000);
    this.pollMs = options.pollMs ?? 1000;
    this.setTimer = options.setInterval ?? ((cb, ms) => globalThis.setInterval(cb, ms));
    this.clearTimer =
      options.clearInterval ?? ((handle) => globalThis.clearInterval(handle as ReturnType<typeof setInterval>));
    const { build, run, cancel, scenario, acceptance } = this.elements;
    build.addEventListener("click", () => void this.startBuild());
    run.addEventListener("click", () => void this.startRun());
    cancel.addEventListener("click", () => void this.cancel());
    scenario.addEventListener("change", () => this.render());
    acceptance.addEventListener("change", () => this.render());
    this.render();
  }

  /** Point the controls at a model and fetch its run inputs. */
  async setModel(model: string | null): Promise<void> {
    const token = ++this.inputsToken;
    this.model = model;
    const { scenario, acceptance, options } = this.elements;
    for (const select of [scenario, acceptance, options]) select.replaceChildren();
    this.render();
    if (!model) return;
    try {
      const inputs = await this.transport.listPhysicsInputs(model);
      if (token !== this.inputsToken) return;
      fill(scenario, inputs.scenarios);
      fill(acceptance, inputs.acceptance);
      fill(options, inputs.options, "(none)");
      this.message = null;
    } catch (error) {
      if (token !== this.inputsToken) return;
      this.message = `Could not list run inputs: ${error instanceof Error ? error.message : String(error)}`;
    }
    this.render();
  }

  async startBuild(): Promise<void> {
    if (!this.model || this.tracker.active) return;
    await this.start(() => this.transport.startBuild(this.model as string));
  }

  async startRun(): Promise<void> {
    const { scenario, acceptance, options } = this.elements;
    if (!this.model || this.tracker.active || !scenario.value || !acceptance.value) return;
    const request = {
      model: this.model,
      scenario: scenario.value,
      acceptance: acceptance.value,
      ...(options.value ? { options: options.value } : {}),
    };
    await this.start(() => this.transport.startRun(request));
  }

  async cancel(): Promise<void> {
    const job = this.tracker.job;
    if (!job || !canCancel(job)) return;
    try {
      this.update(await this.transport.cancelJob(job.id));
    } catch (error) {
      this.message = `Cancel failed: ${error instanceof Error ? error.message : String(error)}`;
      this.render();
    }
  }

  /** True when `event` is about the job this panel is following. */
  owns(event: ServiceEvent): boolean {
    return event.type === "job" && event.job.id === this.tracker.job?.id;
  }

  handleEvent(event: ServiceEvent): void {
    if (event.type === "job") this.update(event.job);
  }

  dispose(): void {
    this.stopPolling();
    this.inputsToken += 1;
  }

  private async start(request: () => Promise<Job>): Promise<void> {
    this.message = null;
    this.elements.build.disabled = true;
    this.elements.run.disabled = true;
    try {
      this.settle(this.tracker.track(await request()));
      if (this.tracker.active) this.startPolling();
    } catch (error) {
      this.message = `Could not start the job: ${error instanceof Error ? error.message : String(error)}`;
    }
    this.render();
  }

  private update(job: Job): void {
    const transition = this.tracker.apply(job);
    if (transition) this.settle(transition);
    this.render();
  }

  private settle(transition: JobTransition): void {
    if (!transition.finished) return;
    this.stopPolling();
    this.onFinished(transition.job);
  }

  private startPolling(): void {
    if (this.timer !== null) return;
    this.timer = this.setTimer(() => {
      const job = this.tracker.job;
      if (!job || !this.tracker.active) {
        this.stopPolling();
        return;
      }
      this.transport.getJob(job.id).then(
        (latest) => this.update(latest),
        () => {},
      );
      // Re-render so the elapsed time ticks even when nothing else changed.
      this.render();
    }, this.pollMs);
  }

  private stopPolling(): void {
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
  }

  private render(): void {
    const { build, run, scenario, acceptance, options, status, log, cancel } = this.elements;
    const busy = this.tracker.active;
    build.disabled = !this.model || busy;
    run.disabled = !this.model || busy || !scenario.value || !acceptance.value;
    for (const select of [scenario, acceptance, options]) select.disabled = !this.model;
    const job = this.tracker.job;
    const lines: string[] = [];
    if (job) lines.push(jobProgress(job, this.now()));
    if (this.message) lines.push(this.message);
    status.textContent = lines.join("\n");
    status.dataset.state = this.message ? "error" : job?.status ?? "";
    log.textContent = job ? logTail(job, LOG_LINES).join("\n") : "";
    log.hidden = !job || job.log.length === 0;
    cancel.hidden = !job || !busy;
    cancel.disabled = !job || !canCancel(job);
  }
}

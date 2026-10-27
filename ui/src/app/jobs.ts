/** Pure job-state handling for the Build/Run controls; no DOM. */
import type { Job } from "../transport/types";

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

const TERMINAL: ReadonlySet<string> = new Set(["succeeded", "failed", "cancelled"]);

/** A job that will not change again. Unknown statuses count as not terminal. */
export function isTerminal(status: string): boolean {
  return TERMINAL.has(status);
}

/**
 * Whether the server will accept a cancel: any queued job, or a running physics run.
 * Running builds are in-process OCCT work and cannot be interrupted.
 */
export function canCancel(job: Job): boolean {
  if (job.status === "queued") return true;
  return job.status === "running" && job.kind === "run";
}

/**
 * Merge an update into the job on display. A different id replaces it; for the same id a
 * terminal state is never overwritten by a non-terminal one (SSE and polling can race).
 */
export function mergeJob(current: Job | null, incoming: Job): Job {
  if (!current || current.id !== incoming.id) return incoming;
  if (isTerminal(current.status) && !isTerminal(incoming.status)) return current;
  return incoming;
}

/** The last `lines` log lines (all of them when `lines` is not positive). */
export function logTail(job: Job, lines = 20): string[] {
  return lines > 0 ? job.log.slice(-lines) : [...job.log];
}

function seconds(value: number): string {
  return value < 10 ? `${value.toFixed(1)} s` : `${Math.round(value)} s`;
}

/**
 * One-line progress text. `nowSeconds` is epoch seconds, matching the server's timestamps.
 * The service reports no percentage, so progress is status plus elapsed time.
 */
export function jobProgress(job: Job, nowSeconds: number): string {
  const label = `${job.kind} ${job.model}`;
  switch (job.status) {
    case "queued":
      return `${label}: queued`;
    case "running": {
      const started = job.startedAt ?? nowSeconds;
      return `${label}: running for ${seconds(Math.max(0, nowSeconds - started))}`;
    }
    case "succeeded": {
      const took =
        job.startedAt !== null && job.finishedAt !== null
          ? ` in ${seconds(Math.max(0, job.finishedAt - job.startedAt))}`
          : "";
      return `${label}: succeeded${took}`;
    }
    case "failed":
      return `${label}: failed${job.error ? `: ${job.error}` : ""}`;
    case "cancelled":
      return `${label}: cancelled`;
    default:
      return `${label}: ${job.status}`;
  }
}

/** An update to the tracked job; `finished` is true exactly once, when it first turns terminal. */
export interface JobTransition {
  job: Job;
  finished: boolean;
}

/** Follows the one job the UI started, deduplicating updates that arrive by SSE and by polling. */
export class JobTracker {
  private current: Job | null = null;
  private done = false;

  get job(): Job | null {
    return this.current;
  }

  /** True while the tracked job may still change. */
  get active(): boolean {
    return this.current !== null && !this.done;
  }

  /** Start following `job`, replacing any previous one. */
  track(job: Job): JobTransition {
    this.current = job;
    this.done = isTerminal(job.status);
    return { job, finished: this.done };
  }

  /** Apply an update; null when it is for another job or changes nothing. */
  apply(incoming: Job): JobTransition | null {
    if (!this.current || incoming.id !== this.current.id) return null;
    const merged = mergeJob(this.current, incoming);
    if (merged === this.current) return null;
    this.current = merged;
    const finished = !this.done && isTerminal(merged.status);
    if (finished) this.done = true;
    return { job: merged, finished };
  }

  clear(): void {
    this.current = null;
    this.done = false;
  }
}

/** What is on screen for one artifact kind (scene or trajectory) and whether it is stale. */
export interface DisplayState<T> {
  artifact: T | null;
  stale: boolean;
  error: string | null;
}

export function emptyDisplay<T>(): DisplayState<T> {
  return { artifact: null, stale: false, error: null };
}

/**
 * Fold a finished job into the display. A failed job never replaces the artifact: it keeps
 * it and marks it stale (or, with nothing displayed, just records the error). Succeeded and
 * cancelled jobs leave the display unchanged; the caller loads the new artifact itself.
 */
export function afterJob<T>(state: DisplayState<T>, job: Job): DisplayState<T> {
  if (job.status !== "failed") return state;
  return {
    artifact: state.artifact,
    stale: state.artifact !== null,
    error: job.error ?? `${job.kind} job failed`,
  };
}

/** A freshly loaded artifact replaces the display, carrying the server's stale flag. */
export function afterLoad<T>(artifact: T, stale = false, error: string | null = null): DisplayState<T> {
  return { artifact, stale, error };
}

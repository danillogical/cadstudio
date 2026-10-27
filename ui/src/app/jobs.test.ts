import { describe, expect, it } from "vitest";
import type { Job } from "../transport/types";
import {
  afterJob,
  afterLoad,
  canCancel,
  emptyDisplay,
  isTerminal,
  JobTracker,
  jobProgress,
  logTail,
  mergeJob,
  type DisplayState,
} from "./jobs";

const job = (overrides: Partial<Job> = {}): Job => ({
  id: "j1", kind: "build", key: "p/m", model: "p/m", status: "queued", createdAt: 0, startedAt: null,
  finishedAt: null, error: null, exitCode: null, log: [], artifacts: {}, ...overrides,
});

describe("isTerminal / canCancel", () => {
  it("classifies statuses", () => {
    for (const s of ["succeeded", "failed", "cancelled"]) expect(isTerminal(s)).toBe(true);
    for (const s of ["queued", "running", "", "weird"]) expect(isTerminal(s)).toBe(false);
  });
  it("allows cancel for queued jobs and running runs only", () => {
    expect(canCancel(job({ status: "queued", kind: "build" }))).toBe(true);
    expect(canCancel(job({ status: "queued", kind: "run" }))).toBe(true);
    expect(canCancel(job({ status: "running", kind: "run" }))).toBe(true);
    expect(canCancel(job({ status: "running", kind: "build" }))).toBe(false);
    for (const status of ["succeeded", "failed", "cancelled"]) {
      expect(canCancel(job({ status, kind: "run" }))).toBe(false);
    }
  });
});

describe("mergeJob", () => {
  it("takes the incoming job when nothing or another job is displayed", () => {
    const next = job({ id: "j2" });
    expect(mergeJob(null, next)).toBe(next);
    expect(mergeJob(job({ id: "j1", status: "failed" }), next)).toBe(next);
  });
  it("never lets a non-terminal update overwrite a terminal state of the same id", () => {
    for (const terminal of ["succeeded", "failed", "cancelled"]) {
      const done = job({ status: terminal });
      for (const live of ["queued", "running"]) {
        expect(mergeJob(done, job({ status: live }))).toBe(done);
      }
    }
  });
  it("lets forward progress and terminal updates through", () => {
    const running = job({ status: "running" });
    const failed = job({ status: "failed" });
    expect(mergeJob(job(), running)).toBe(running);
    expect(mergeJob(running, failed)).toBe(failed);
  });
});

describe("logTail / jobProgress", () => {
  it("returns the last N lines", () => {
    const j = job({ log: ["a", "b", "c", "d"] });
    expect(logTail(j, 2)).toEqual(["c", "d"]);
    expect(logTail(j, 10)).toEqual(["a", "b", "c", "d"]);
    expect(logTail(j, 0)).toEqual(["a", "b", "c", "d"]);
  });
  it("describes progress", () => {
    expect(jobProgress(job(), 0)).toContain("queued");
    expect(jobProgress(job({ status: "running", startedAt: 10 }), 15)).toContain("5.0 s");
    expect(jobProgress(job({ status: "failed", error: "boom" }), 0)).toContain("boom");
    expect(jobProgress(job({ status: "cancelled" }), 0)).toContain("cancelled");
    expect(jobProgress(job({ status: "succeeded", startedAt: 1, finishedAt: 4 }), 0)).toContain("3.0 s");
  });
});

describe("JobTracker", () => {
  it("reports finished exactly once", () => {
    const t = new JobTracker();
    expect(t.track(job()).finished).toBe(false);
    expect(t.active).toBe(true);
    expect(t.apply(job({ status: "running" }))?.finished).toBe(false);
    const done = t.apply(job({ status: "failed", error: "x" }));
    expect(done?.finished).toBe(true);
    expect(t.active).toBe(false);
    expect(t.apply(job({ status: "failed", error: "x" }))?.finished ?? false).toBe(false);
    expect(t.apply(job({ status: "succeeded" }))?.finished ?? false).toBe(false);
  });
  it("ignores late non-terminal updates after finishing", () => {
    const t = new JobTracker();
    t.track(job());
    t.apply(job({ status: "succeeded" }));
    expect(t.apply(job({ status: "running" }))).toBeNull();
    expect(t.job?.status).toBe("succeeded");
  });
  it("ignores updates for other jobs", () => {
    const t = new JobTracker();
    t.track(job());
    expect(t.apply(job({ id: "other", status: "failed" }))).toBeNull();
    expect(t.job?.id).toBe("j1");
  });
  it("tracking an already-terminal job is finished immediately, and a new track resets", () => {
    const t = new JobTracker();
    expect(t.track(job({ status: "failed" })).finished).toBe(true);
    expect(t.active).toBe(false);
    t.track(job({ id: "j2" }));
    expect(t.active).toBe(true);
    expect(t.apply(job({ id: "j2", status: "succeeded" }))?.finished).toBe(true);
  });
  it("clear drops the job", () => {
    const t = new JobTracker();
    t.track(job());
    t.clear();
    expect(t.job).toBeNull();
    expect(t.active).toBe(false);
    expect(t.apply(job())).toBeNull();
  });
});

describe("afterJob", () => {
  const shown: DisplayState<string> = afterLoad("scene-v1");
  it("keeps the previous artifact and marks it stale with the error on failure", () => {
    const next = afterJob(shown, job({ status: "failed", error: "boom" }));
    expect(next.artifact).toBe("scene-v1");
    expect(next.stale).toBe(true);
    expect(next.error).toBe("boom");
  });
  it("is not stale when nothing was displayed, but records the error", () => {
    const next = afterJob(emptyDisplay<string>(), job({ status: "failed", error: "boom" }));
    expect(next.artifact).toBeNull();
    expect(next.stale).toBe(false);
    expect(next.error).toBe("boom");
  });
  it("supplies a message when the failed job has no error text", () => {
    const next = afterJob(shown, job({ status: "failed", error: null }));
    expect(next.error).toBeTruthy();
  });
  it("leaves the display unchanged for succeeded and cancelled jobs", () => {
    for (const status of ["succeeded", "cancelled"]) {
      expect(afterJob(shown, job({ status }))).toEqual(shown);
    }
  });
  it("leaves the display unchanged for non-terminal jobs", () => {
    expect(afterJob(shown, job({ status: "running" }))).toEqual(shown);
  });
  it("afterLoad replaces the artifact with the server stale flag", () => {
    expect(afterLoad("x")).toEqual({ artifact: "x", stale: false, error: null });
    expect(afterLoad("x", true, "e")).toEqual({ artifact: "x", stale: true, error: "e" });
  });
});

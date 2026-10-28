import { TransportError, type Job, type ServiceEvent } from "./types";

/** The SSE event names the service sends; both transports forward only these. */
export const SERVICE_EVENT_NAMES = ["job", "artifact"] as const;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The `job` of a job route's answer; both transports reject an answer without one the same way. */
export function jobOf(doc: unknown): Job {
  if (!isRecord(doc) || !isRecord(doc.job)) {
    throw new TransportError(0, "response has no job");
  }
  return doc.job as unknown as Job;
}

/** Map a parsed SSE `job` or `artifact` payload; anything else is ignored (null). */
export function mapEvent(parsed: unknown): ServiceEvent | null {
  if (!isRecord(parsed)) return null;
  if (isRecord(parsed.job)) {
    return { type: "job", job: parsed.job as unknown as Job };
  }
  if (parsed.kind === "scene" && typeof parsed.model === "string") {
    return { type: "artifact", kind: "scene", model: parsed.model };
  }
  if (parsed.kind === "run" && typeof parsed.runId === "string") {
    return { type: "artifact", kind: "run", runId: parsed.runId };
  }
  if (parsed.kind === "live" && typeof parsed.liveId === "string") {
    return {
      type: "artifact",
      kind: "live",
      liveId: parsed.liveId,
      frames: typeof parsed.frames === "number" ? parsed.frames : 0,
      done: parsed.done === true,
    };
  }
  return null;
}

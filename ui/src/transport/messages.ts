/**
 * The postMessage protocol between the webview (`VsCodeTransport`) and the extension host
 * bridge (`editor/vscode/src/protocol.ts`, which validates every message). Keep both in step.
 */

/** Transport calls the host forwards; `subscribe` travels as its own message kind. */
export const TRANSPORT_METHODS = [
  "health",
  "listModels",
  "getScene",
  "startBuild",
  "listPhysicsInputs",
  "listRuns",
  "getTrajectory",
  "startRun",
  "getJob",
  "cancelJob",
  "getArtifact",
] as const;

export type TransportMethod = (typeof TRANSPORT_METHODS)[number];

export type WebviewToHost =
  | { kind: "request"; id: number; method: TransportMethod; args: unknown[] }
  | { kind: "subscribe" }
  | { kind: "unsubscribe" }
  /** The page can take `navigate` messages; the host holds them back until it says so. */
  | { kind: "ready" };

/** Same fields as `TransportError`; `status` 0 means the request never got an HTTP answer. */
export interface WireError {
  status: number;
  message: string;
  body?: Record<string, unknown>;
}

export type HostToWebview =
  /** `result` is the service's JSON body, or an ArrayBuffer for `getArtifact`. */
  | { kind: "response"; id: number; ok: true; result: unknown }
  | { kind: "response"; id: number; ok: false; error: WireError }
  /** One SSE frame; `data` is the parsed JSON payload. */
  | { kind: "event"; event: string; data: unknown }
  | { kind: "connection"; state: "open" | "error" }
  /** `cad gui open`: select this model, or open this run, as if the user had picked it. */
  | { kind: "navigate"; model: string }
  | { kind: "navigate"; run: string };

/** What to show on open: a `<project>/<model>` spec or an `out/`-relative run id. */
export type NavigateTarget = { model: string } | { run: string };

/** One name segment, as `_SEGMENT` in `cadkit/gui/server.py` and `SEGMENT` in the host protocol. */
const SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;
const MAX_PATH_LENGTH = 1024;

/** A `<project>/<model>` spec: exactly two name segments. */
export function isModelSpec(value: unknown): value is string {
  if (typeof value !== "string" || value.length > MAX_PATH_LENGTH) return false;
  const parts = value.split("/");
  return parts.length === 2 && parts.every((part) => SEGMENT.test(part));
}

/** A relative run id: no leading `/`, backslash, control character, or empty, `.` or `..` segment. */
export function isRunId(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_PATH_LENGTH) return false;
  if (value.startsWith("/") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return false;
  return value.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}

/** A host `navigate` message, exactly `{kind, model}` or `{kind, run}`; null for anything else. */
export function parseNavigate(data: unknown): NavigateTarget | null {
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const message = data as Record<string, unknown>;
  const keys = Object.keys(message);
  if (message.kind !== "navigate" || keys.length !== 2) return null;
  if (keys.includes("model")) return isModelSpec(message.model) ? { model: message.model } : null;
  if (keys.includes("run")) return isRunId(message.run) ? { run: message.run } : null;
  return null;
}

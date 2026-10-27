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
  | { kind: "unsubscribe" };

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
  | { kind: "connection"; state: "open" | "error" };

/**
 * The webview <-> extension host message protocol, and the host's validation of it. The webview
 * side lives in `ui/src/transport/messages.ts` and `vscode.ts`; keep the method list in step.
 *
 * Everything here is pure: `parseWebviewMessage` turns an untrusted message into a typed call,
 * `routeFor` maps a call onto exactly one documented service endpoint, and `mapHttpResponse`
 * turns the service's answer into the same error shape `BrowserTransport` produces.
 */

/** Transport calls the host forwards; anything else is refused. */
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
  "follow",
  "unfollow",
  "listLive",
  "getLive",
] as const;

export type TransportMethod = (typeof TRANSPORT_METHODS)[number];

/** One name segment, the same rule as `_SEGMENT` in `cadkit/gui/server.py`. */
export const SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;

/** Upper bounds that keep a hostile message cheap to reject. */
export const MAX_PATH_LENGTH = 1024;
export const MAX_SETS = 256;
export const MAX_SET_STRING = 1024;

export interface StartRunBody {
  model: string;
  scenario: string;
  acceptance: string;
  options?: string;
}

/** A validated call; models are split into their two segments. */
export type ValidCall =
  | { method: "health" | "listModels" | "listRuns" | "listLive" }
  | { method: "getScene" | "listPhysicsInputs"; project: string; model: string }
  | { method: "startBuild"; project: string; model: string; sets?: Record<string, number | string> }
  | { method: "getTrajectory"; runId: string }
  | { method: "startRun"; body: StartRunBody }
  | { method: "getJob" | "cancelJob"; id: string }
  | { method: "getArtifact"; path: string; offset?: number }
  | { method: "follow" | "unfollow"; project: string; model: string }
  | { method: "getLive"; liveId: string };

export type WebviewMessage =
  | { kind: "request"; id: number; call: ValidCall }
  | { kind: "subscribe" }
  | { kind: "unsubscribe" }
  /** The page has wired its navigate handler; queued navigation can be delivered. */
  | { kind: "ready" };

/** What `cad gui open` asks the panel to show. */
export type NavigateTarget = { model: string } | { run: string };

/** Host -> webview: select this model or run, as if the user had picked it. */
export type NavigateMessage = { kind: "navigate"; model: string } | { kind: "navigate"; run: string };

/**
 * `ok: false` carries the request id when the envelope had a usable one, so the host can
 * reply and the webview can reject that call; `id: null` means the message is dropped.
 */
export type ParseResult =
  | { ok: true; message: WebviewMessage }
  | { ok: false; id: number | null; error: string };

/** Same fields as the UI's `TransportError`; `status` 0 means no HTTP answer was received. */
export interface WireError {
  status: number;
  message: string;
  body?: Record<string, unknown>;
}

export type Reply = { ok: true; result: unknown } | { ok: false; error: WireError };

/** One service request: a fixed path built only from validated, percent-encoded segments. */
export interface HttpRoute {
  method: "GET" | "POST" | "DELETE";
  path: string;
  body?: Record<string, unknown>;
  /** The answer is raw bytes (an artifact), not a JSON document. */
  binary: boolean;
  /** Extra request headers; the host adds the bearer token itself. */
  headers?: Record<string, string>;
}

/** Status the host uses for a message it refused to forward. */
export const REJECTED_STATUS = 400;

class Invalid extends Error {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: readonly string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}

/** A `<project>/<model>` spec: exactly two segments. */
export function parseModelSpec(value: unknown): { project: string; model: string } | null {
  if (typeof value !== "string" || value.length > MAX_PATH_LENGTH) return null;
  const parts = value.split("/");
  if (parts.length !== 2 || !parts.every((part) => SEGMENT.test(part))) return null;
  return { project: parts[0], model: parts[1] };
}

/**
 * A relative `out/` (or repo) path: the server's artifact and run-id rule (no leading `/`, no
 * backslash, no empty, `.` or `..` segment), plus no control characters.
 */
export function isRelativePath(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_PATH_LENGTH) return false;
  if (value.startsWith("/") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return false;
  return value.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}

function requireArity(args: unknown[], min: number, max = min): void {
  if (args.length < min || args.length > max) {
    throw new Invalid(min === max ? `expects ${min} argument(s)` : `expects ${min}-${max} arguments`);
  }
}

function modelArg(value: unknown): { project: string; model: string } {
  const spec = parseModelSpec(value);
  if (!spec) throw new Invalid("model must be <project>/<model> with name segments");
  return spec;
}

function pathArg(value: unknown, what: string): string {
  if (!isRelativePath(value)) throw new Invalid(`${what} must be a relative path without . or .. segments`);
  return value;
}

/** Build overrides: string keys to finite numbers or strings, as the server's `_coerce_sets` accepts. */
function setsArg(value: unknown): Record<string, number | string> {
  if (!isRecord(value)) throw new Invalid("sets must be an object");
  const entries = Object.entries(value);
  if (entries.length > MAX_SETS) throw new Invalid(`at most ${MAX_SETS} sets`);
  const out: Record<string, number | string> = {};
  for (const [key, item] of entries) {
    if (key.length === 0 || key.length > MAX_SET_STRING) throw new Invalid("set keys must be non-empty strings");
    if (typeof item === "number") {
      if (!Number.isFinite(item)) throw new Invalid(`set ${key} must be finite`);
    } else if (typeof item !== "string" || item.length > MAX_SET_STRING) {
      throw new Invalid(`set ${key} must be a number or string`);
    }
    out[key] = item;
  }
  return out;
}

function startRunArg(value: unknown): StartRunBody {
  if (!isRecord(value)) throw new Invalid("run request must be an object");
  if (!hasOnlyKeys(value, ["model", "scenario", "acceptance", "options"])) {
    throw new Invalid("run request has unexpected keys");
  }
  modelArg(value.model);
  const body: StartRunBody = {
    model: value.model as string,
    scenario: pathArg(value.scenario, "scenario"),
    acceptance: pathArg(value.acceptance, "acceptance"),
  };
  if (value.options !== undefined) body.options = pathArg(value.options, "options");
  return body;
}

function jobIdArg(value: unknown): string {
  if (typeof value !== "string" || value.length > 128 || !SEGMENT.test(value)) {
    throw new Invalid("job id must be a name segment");
  }
  return value;
}

/** `{model}` for follow and unfollow: one `<project>/<model>` spec. */
function followArg(value: unknown): { project: string; model: string } {
  if (!isRecord(value) || !hasOnlyKeys(value, ["model"])) throw new Invalid("request must be {model}");
  return modelArg(value.model);
}

/** `{liveId}` for getLive: a relative path under `out/`, the same rule as a run id. */
function liveIdArg(value: unknown): string {
  if (!isRecord(value) || !hasOnlyKeys(value, ["liveId"])) throw new Invalid("request must be {liveId}");
  return pathArg(value.liveId, "liveId");
}

/** `{offset}` for getArtifact: a byte offset to resume from, sent as `Range: bytes=<offset>-`. */
function offsetArg(value: unknown): number {
  if (!isRecord(value) || !hasOnlyKeys(value, ["offset"])) throw new Invalid("range must be {offset}");
  const offset = value.offset;
  if (typeof offset !== "number" || !Number.isSafeInteger(offset) || offset < 0) {
    throw new Invalid("offset must be a non-negative integer");
  }
  return offset;
}

/** Check one call's arguments against its method; throws `Invalid` with the reason. */
function validateCall(method: TransportMethod, args: unknown[]): ValidCall {
  switch (method) {
    case "health":
    case "listModels":
    case "listRuns":
    case "listLive":
      requireArity(args, 0);
      return { method };
    case "getScene":
    case "listPhysicsInputs":
      requireArity(args, 1);
      return { method, ...modelArg(args[0]) };
    case "startBuild": {
      requireArity(args, 1, 2);
      const call: Extract<ValidCall, { method: "startBuild" }> = { method, ...modelArg(args[0]) };
      if (args.length === 2) call.sets = setsArg(args[1]);
      return call;
    }
    case "getTrajectory":
      requireArity(args, 1);
      return { method, runId: pathArg(args[0], "runId") };
    case "startRun":
      requireArity(args, 1);
      return { method, body: startRunArg(args[0]) };
    case "getJob":
    case "cancelJob":
      requireArity(args, 1);
      return { method, id: jobIdArg(args[0]) };
    case "getArtifact": {
      requireArity(args, 1, 2);
      const call: Extract<ValidCall, { method: "getArtifact" }> = { method, path: pathArg(args[0], "artifact path") };
      if (args.length === 2) call.offset = offsetArg(args[1]);
      return call;
    }
    case "follow":
    case "unfollow":
      requireArity(args, 1);
      return { method, ...followArg(args[0]) };
    case "getLive":
      requireArity(args, 1);
      return { method, liveId: liveIdArg(args[0]) };
  }
}

/**
 * Validate an untrusted webview message. Requests must be exactly
 * `{kind: "request", id, method, args}` with a known method and well-typed arguments;
 * `{kind: "subscribe"}`, `{kind: "unsubscribe"}` and `{kind: "ready"}` take no other keys.
 */
export function parseWebviewMessage(raw: unknown): ParseResult {
  if (!isRecord(raw)) return { ok: false, id: null, error: "message must be an object" };
  if (raw.kind === "subscribe" || raw.kind === "unsubscribe" || raw.kind === "ready") {
    if (!hasOnlyKeys(raw, ["kind"])) return { ok: false, id: null, error: `${raw.kind} takes no fields` };
    return { ok: true, message: { kind: raw.kind } };
  }
  if (raw.kind !== "request") return { ok: false, id: null, error: "unknown message kind" };
  const id = Number.isSafeInteger(raw.id) && (raw.id as number) >= 0 ? (raw.id as number) : null;
  if (id === null) return { ok: false, id: null, error: "request id must be a non-negative integer" };
  if (!hasOnlyKeys(raw, ["kind", "id", "method", "args"])) {
    return { ok: false, id, error: "request has unexpected keys" };
  }
  const method = raw.method;
  if (typeof method !== "string" || !(TRANSPORT_METHODS as readonly string[]).includes(method)) {
    return { ok: false, id, error: `unknown method ${JSON.stringify(String(method)).slice(0, 80)}` };
  }
  if (!Array.isArray(raw.args)) return { ok: false, id, error: `${method}: args must be an array` };
  try {
    return { ok: true, message: { kind: "request", id, call: validateCall(method as TransportMethod, raw.args) } };
  } catch (error) {
    if (error instanceof Invalid) return { ok: false, id, error: `${method}: ${error.message}` };
    throw error;
  }
}

/** An open-request id as the service issues it (`secrets.token_urlsafe`); `_OPEN_ID` in server.py. */
export const OPEN_REQUEST_ID = /^[A-Za-z0-9_-]{16,128}$/;

/**
 * A claimed request's `target`: null (just open the GUI), `{model}` with a `<project>/<model>`
 * spec, or `{run}` with a relative run id. `undefined` means the value is malformed.
 */
export function parseNavigateTarget(value: unknown): NavigateTarget | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const keys = Object.keys(value);
  if (keys.length !== 1) return undefined;
  if (keys[0] === "model" && parseModelSpec(value.model)) return { model: value.model as string };
  if (keys[0] === "run" && isRelativePath(value.run)) return { run: value.run };
  return undefined;
}

export function navigateMessage(target: NavigateTarget): NavigateMessage {
  return "model" in target ? { kind: "navigate", model: target.model } : { kind: "navigate", run: target.run };
}

/** `GET /v1/open/{id}`: claim the request (single use). */
export function openClaimRoute(id: string): HttpRoute {
  return { method: "GET", path: `/v1/open/${encodeURIComponent(id)}`, binary: false };
}

export function openAckRoute(id: string): HttpRoute {
  return { method: "POST", path: `/v1/open/${encodeURIComponent(id)}/ack`, body: {}, binary: false };
}

export function openNackRoute(id: string, reason: string): HttpRoute {
  return { method: "POST", path: `/v1/open/${encodeURIComponent(id)}/nack`, body: { reason }, binary: false };
}

/** Percent-encode each slash-separated segment, leaving the separators intact. */
export function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

/** The single documented endpoint for a validated call. */
export function routeFor(call: ValidCall): HttpRoute {
  const json = (method: HttpRoute["method"], path: string, body?: Record<string, unknown>): HttpRoute =>
    body === undefined ? { method, path, binary: false } : { method, path, body, binary: false };
  switch (call.method) {
    case "health":
      return json("GET", "/v1/health");
    case "listModels":
      return json("GET", "/v1/models");
    case "listRuns":
      return json("GET", "/v1/runs");
    case "getScene":
      return json("GET", `/v1/models/${encodePath(call.project)}/${encodePath(call.model)}/scene`);
    case "listPhysicsInputs":
      return json("GET", `/v1/models/${encodePath(call.project)}/${encodePath(call.model)}/physics-inputs`);
    case "startBuild":
      return json(
        "POST",
        `/v1/models/${encodePath(call.project)}/${encodePath(call.model)}/build`,
        call.sets ? { set: call.sets } : {},
      );
    case "getTrajectory":
      return json("GET", `/v1/runs/${encodePath(call.runId)}/trajectory`);
    case "startRun":
      return json("POST", "/v1/runs", { ...call.body });
    case "getJob":
      return json("GET", `/v1/jobs/${encodeURIComponent(call.id)}`);
    case "cancelJob":
      return json("POST", `/v1/jobs/${encodeURIComponent(call.id)}/cancel`);
    case "getArtifact": {
      const path = `/v1/artifacts/${encodePath(call.path)}`;
      if (call.offset === undefined) return { method: "GET", path, binary: true };
      return { method: "GET", path, binary: true, headers: { Range: `bytes=${call.offset}-` } };
    }
    case "follow":
      return json("POST", "/v1/follow", { model: `${call.project}/${call.model}` });
    case "unfollow":
      return json("DELETE", "/v1/follow", { model: `${call.project}/${call.model}` });
    case "listLive":
      return json("GET", "/v1/live");
    case "getLive":
      return json("GET", `/v1/live/${encodePath(call.liveId)}`);
  }
}

function parseJson(text: string): unknown {
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** Copy into a fresh, exactly-sized ArrayBuffer; VS Code transfers those to the webview as-is. */
export function exactArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

/**
 * Map a service answer the way `BrowserTransport` does: a non-2xx status becomes
 * `{status, message: body.error ?? statusText ?? "HTTP <status>", body}`; a JSON route must
 * answer with a JSON object; a binary route answers with an ArrayBuffer. `ranged` marks a
 * request with a `Range` header, for which a 416 means "nothing past that offset": empty bytes.
 */
export function mapHttpResponse(
  status: number,
  statusText: string,
  bytes: Uint8Array,
  binary: boolean,
  ranged = false,
): Reply {
  const ok = status >= 200 && status < 300;
  if (ok && binary) return { ok: true, result: exactArrayBuffer(bytes) };
  if (status === 416 && binary && ranged) return { ok: true, result: new ArrayBuffer(0) };
  const body = parseJson(new TextDecoder().decode(bytes));
  if (!ok) {
    const detail = isRecord(body) && typeof body.error === "string" ? body.error : null;
    const error: WireError = { status, message: detail ?? (statusText || `HTTP ${status}`) };
    if (isRecord(body)) error.body = body;
    return { ok: false, error };
  }
  if (!isRecord(body)) return { ok: false, error: { status, message: "response is not a JSON object" } };
  return { ok: true, result: body };
}

/** A request that got no HTTP answer, worded like `BrowserTransport`'s fetch failure. */
export function networkError(error: unknown): WireError {
  return { status: 0, message: `network error: ${error instanceof Error ? error.message : String(error)}` };
}

/** A message the host refused to forward. */
export function rejectedError(reason: string): WireError {
  return { status: REJECTED_STATUS, message: `rejected by the CADStudio extension: ${reason}` };
}

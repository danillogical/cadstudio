"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/extension.ts
var extension_exports = {};
__export(extension_exports, {
  COMMAND_ID: () => COMMAND_ID,
  GuiPanels: () => GuiPanels,
  MEDIA_DIR: () => MEDIA_DIR,
  NO_FOLDER_MESSAGE: () => NO_FOLDER_MESSAGE,
  UNTRUSTED_MESSAGE: () => UNTRUSTED_MESSAGE,
  VIEW_TYPE: () => VIEW_TYPE,
  activate: () => activate,
  deactivate: () => deactivate,
  defaultDeps: () => defaultDeps,
  panelOptions: () => panelOptions
});
module.exports = __toCommonJS(extension_exports);
var vscode2 = __toESM(require("vscode"));
var import_node_fs = require("node:fs");
var import_promises = require("node:fs/promises");
var import_node_path2 = require("node:path");

// src/http.ts
var http = __toESM(require("node:http"));

// src/sse.ts
var SseParser = class {
  buffer = "";
  event = "";
  data = [];
  push(chunk) {
    this.buffer += chunk;
    const out = [];
    for (; ; ) {
      const match = /\r\n|\r|\n/.exec(this.buffer);
      if (!match) break;
      if (match[0] === "\r" && match.index === this.buffer.length - 1) break;
      const line = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const dispatched = this.line(line);
      if (dispatched) out.push(dispatched);
    }
    return out;
  }
  line(line) {
    if (line === "") {
      const ready = this.data.length > 0 ? { event: this.event || "message", data: this.data.join("\n") } : null;
      this.event = "";
      this.data = [];
      return ready;
    }
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }
};

// src/http.ts
var HEALTH_TIMEOUT_MS = 2e3;
var EVENTS_IDLE_TIMEOUT_MS = 45e3;
var MAX_HEALTH_BYTES = 64 * 1024;
var HttpFailure = class extends Error {
  constructor(message, refused) {
    super(message);
    this.refused = refused;
    this.name = "HttpFailure";
  }
  refused;
};
function failure(error) {
  if (error instanceof HttpFailure) return error;
  const code = error?.code;
  const message = error instanceof Error ? error.message : String(error);
  return new HttpFailure(message, code === "ECONNREFUSED");
}
function serviceRequest(endpoint, route, signal) {
  return new Promise((resolve, reject) => {
    const body = route.body === void 0 ? void 0 : Buffer.from(JSON.stringify(route.body), "utf8");
    const headers = {
      Authorization: `Bearer ${endpoint.token}`,
      Accept: route.binary ? "*/*" : "application/json"
    };
    if (body) {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = String(body.length);
    }
    const request2 = http.request(
      { host: "127.0.0.1", port: endpoint.port, method: route.method, path: route.path, headers, signal },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          if (!response.complete) {
            reject(new HttpFailure("connection closed before the response ended", false));
            return;
          }
          resolve({
            status: response.statusCode ?? 0,
            statusText: response.statusMessage ?? "",
            bytes: Buffer.concat(chunks)
          });
        });
        response.on("error", (error) => reject(failure(error)));
      }
    );
    request2.on("error", (error) => reject(failure(error)));
    request2.on("close", () => reject(new HttpFailure("connection closed before the response ended", false)));
    request2.end(body);
  });
}
function fetchHealth(port, timeoutMs = HEALTH_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const request2 = http.get(
      { host: "127.0.0.1", port, path: "/v1/health", headers: { Accept: "application/json" }, timeout: timeoutMs },
      (response) => {
        const chunks = [];
        let size = 0;
        response.on("data", (chunk) => {
          size += chunk.length;
          if (size > MAX_HEALTH_BYTES) request2.destroy(new Error("health answer too large"));
          else chunks.push(chunk);
        });
        response.on("end", () => {
          if (response.statusCode !== 200 || !response.complete) return resolve(null);
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
          } catch {
            resolve(null);
          }
        });
        response.on("error", () => resolve(null));
      }
    );
    request2.on("timeout", () => request2.destroy(new Error("health check timed out")));
    request2.on("error", () => resolve(null));
    request2.on("close", () => resolve(null));
  });
}
function openEventStream(endpoint, handlers) {
  let closed = false;
  const finish = (reason) => {
    if (closed) return;
    closed = true;
    handlers.onClose(reason);
  };
  const request2 = http.get(
    {
      host: "127.0.0.1",
      port: endpoint.port,
      path: "/v1/events",
      headers: { Authorization: `Bearer ${endpoint.token}`, Accept: "text/event-stream" }
    },
    (response) => {
      if (response.statusCode !== 200) {
        response.resume();
        finish({ message: `event stream answered HTTP ${response.statusCode}`, status: response.statusCode });
        request2.destroy();
        return;
      }
      handlers.onOpen();
      const parser = new SseParser();
      const decoder = new TextDecoder();
      response.on("data", (chunk) => {
        if (closed) return;
        for (const event of parser.push(decoder.decode(chunk, { stream: true }))) handlers.onEvent(event);
      });
      response.on("end", () => finish({ message: "event stream ended" }));
      response.on("error", (error) => finish({ message: error.message }));
    }
  );
  request2.setTimeout(EVENTS_IDLE_TIMEOUT_MS, () => request2.destroy(new Error("event stream went quiet")));
  request2.on("error", (error) => finish({ message: error.message }));
  request2.on("close", () => finish({ message: "event stream closed" }));
  return {
    close() {
      closed = true;
      request2.destroy();
    }
  };
}

// src/protocol.ts
var TRANSPORT_METHODS = [
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
  "getArtifact"
];
var SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;
var MAX_PATH_LENGTH = 1024;
var MAX_SETS = 256;
var MAX_SET_STRING = 1024;
var REJECTED_STATUS = 400;
var Invalid = class extends Error {
};
function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function hasOnlyKeys(value, allowed) {
  return Object.keys(value).every((key) => allowed.includes(key));
}
function parseModelSpec(value) {
  if (typeof value !== "string" || value.length > MAX_PATH_LENGTH) return null;
  const parts = value.split("/");
  if (parts.length !== 2 || !parts.every((part) => SEGMENT.test(part))) return null;
  return { project: parts[0], model: parts[1] };
}
function isRelativePath(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_PATH_LENGTH) return false;
  if (value.startsWith("/") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return false;
  return value.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}
function requireArity(args, min, max = min) {
  if (args.length < min || args.length > max) {
    throw new Invalid(min === max ? `expects ${min} argument(s)` : `expects ${min}-${max} arguments`);
  }
}
function modelArg(value) {
  const spec = parseModelSpec(value);
  if (!spec) throw new Invalid("model must be <project>/<model> with name segments");
  return spec;
}
function pathArg(value, what) {
  if (!isRelativePath(value)) throw new Invalid(`${what} must be a relative path without . or .. segments`);
  return value;
}
function setsArg(value) {
  if (!isRecord(value)) throw new Invalid("sets must be an object");
  const entries = Object.entries(value);
  if (entries.length > MAX_SETS) throw new Invalid(`at most ${MAX_SETS} sets`);
  const out = {};
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
function startRunArg(value) {
  if (!isRecord(value)) throw new Invalid("run request must be an object");
  if (!hasOnlyKeys(value, ["model", "scenario", "acceptance", "options"])) {
    throw new Invalid("run request has unexpected keys");
  }
  modelArg(value.model);
  const body = {
    model: value.model,
    scenario: pathArg(value.scenario, "scenario"),
    acceptance: pathArg(value.acceptance, "acceptance")
  };
  if (value.options !== void 0) body.options = pathArg(value.options, "options");
  return body;
}
function jobIdArg(value) {
  if (typeof value !== "string" || value.length > 128 || !SEGMENT.test(value)) {
    throw new Invalid("job id must be a name segment");
  }
  return value;
}
function validateCall(method, args) {
  switch (method) {
    case "health":
    case "listModels":
    case "listRuns":
      requireArity(args, 0);
      return { method };
    case "getScene":
    case "listPhysicsInputs":
      requireArity(args, 1);
      return { method, ...modelArg(args[0]) };
    case "startBuild": {
      requireArity(args, 1, 2);
      const call = { method, ...modelArg(args[0]) };
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
    case "getArtifact":
      requireArity(args, 1);
      return { method, path: pathArg(args[0], "artifact path") };
  }
}
function parseWebviewMessage(raw) {
  if (!isRecord(raw)) return { ok: false, id: null, error: "message must be an object" };
  if (raw.kind === "subscribe" || raw.kind === "unsubscribe") {
    if (!hasOnlyKeys(raw, ["kind"])) return { ok: false, id: null, error: `${raw.kind} takes no fields` };
    return { ok: true, message: { kind: raw.kind } };
  }
  if (raw.kind !== "request") return { ok: false, id: null, error: "unknown message kind" };
  const id = Number.isSafeInteger(raw.id) && raw.id >= 0 ? raw.id : null;
  if (id === null) return { ok: false, id: null, error: "request id must be a non-negative integer" };
  if (!hasOnlyKeys(raw, ["kind", "id", "method", "args"])) {
    return { ok: false, id, error: "request has unexpected keys" };
  }
  const method = raw.method;
  if (typeof method !== "string" || !TRANSPORT_METHODS.includes(method)) {
    return { ok: false, id, error: `unknown method ${JSON.stringify(String(method)).slice(0, 80)}` };
  }
  if (!Array.isArray(raw.args)) return { ok: false, id, error: `${method}: args must be an array` };
  try {
    return { ok: true, message: { kind: "request", id, call: validateCall(method, raw.args) } };
  } catch (error) {
    if (error instanceof Invalid) return { ok: false, id, error: `${method}: ${error.message}` };
    throw error;
  }
}
function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}
function routeFor(call) {
  const json = (method, path, body) => body === void 0 ? { method, path, binary: false } : { method, path, body, binary: false };
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
        call.sets ? { set: call.sets } : {}
      );
    case "getTrajectory":
      return json("GET", `/v1/runs/${encodePath(call.runId)}/trajectory`);
    case "startRun":
      return json("POST", "/v1/runs", { ...call.body });
    case "getJob":
      return json("GET", `/v1/jobs/${encodeURIComponent(call.id)}`);
    case "cancelJob":
      return json("POST", `/v1/jobs/${encodeURIComponent(call.id)}/cancel`);
    case "getArtifact":
      return { method: "GET", path: `/v1/artifacts/${encodePath(call.path)}`, binary: true };
  }
}
function parseJson(text) {
  if (!text) return void 0;
  try {
    return JSON.parse(text);
  } catch {
    return void 0;
  }
}
function exactArrayBuffer(bytes) {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}
function mapHttpResponse(status, statusText, bytes, binary) {
  const ok = status >= 200 && status < 300;
  if (ok && binary) return { ok: true, result: exactArrayBuffer(bytes) };
  const body = parseJson(new TextDecoder().decode(bytes));
  if (!ok) {
    const detail = isRecord(body) && typeof body.error === "string" ? body.error : null;
    const error = { status, message: detail ?? (statusText || `HTTP ${status}`) };
    if (isRecord(body)) error.body = body;
    return { ok: false, error };
  }
  if (!isRecord(body)) return { ok: false, error: { status, message: "response is not a JSON object" } };
  return { ok: true, result: body };
}
function networkError(error) {
  return { status: 0, message: `network error: ${error instanceof Error ? error.message : String(error)}` };
}
function rejectedError(reason) {
  return { status: REJECTED_STATUS, message: `rejected by the CADStudio extension: ${reason}` };
}

// src/service.ts
var import_node_path = require("node:path");
var PROTOCOL_VERSION = 1;
var START_TIMEOUT_MS = 18e4;
var POLL_INTERVAL_MS = 500;
function discoveryPath(workspaceRoot) {
  return (0, import_node_path.join)(workspaceRoot, "out", ".gui", "service.json");
}
function isPositiveInt(value) {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}
function parseDiscovery(text) {
  let doc;
  try {
    doc = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) return null;
  const record = doc;
  const { pid, port, token, repoRoot, protocolVersion } = record;
  if (!isPositiveInt(pid) || !isPositiveInt(port) || port > 65535) return null;
  if (typeof token !== "string" || token.length === 0) return null;
  if (typeof repoRoot !== "string" || repoRoot.length === 0) return null;
  if (protocolVersion !== PROTOCOL_VERSION) return null;
  return { pid, port, token, repoRoot, protocolVersion };
}
function isHealthy(health, record, workspaceRoot) {
  if (typeof health !== "object" || health === null) return false;
  const body = health;
  return body.service === "cadstudio" && body.protocolVersion === PROTOCOL_VERSION && body.repoRoot === workspaceRoot && body.pid === record.pid;
}
var ServiceUnavailableError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "ServiceUnavailableError";
  }
};
async function findService(deps) {
  const text = await deps.readFile(discoveryPath(deps.workspaceRoot));
  if (text === null) return null;
  const record = parseDiscovery(text);
  if (!record || record.repoRoot !== deps.workspaceRoot) return null;
  const health = await deps.health(record.port);
  return isHealthy(health, record, deps.workspaceRoot) ? record : null;
}
async function waitForService(deps, task, timeoutMs = START_TIMEOUT_MS, pollMs = POLL_INTERVAL_MS) {
  const ended = { done: false };
  void task.exited.then((code) => {
    ended.done = true;
    ended.code = code;
  });
  const deadline = deps.now() + timeoutMs;
  for (; ; ) {
    const found = await findService(deps);
    if (found) return found;
    if (ended.done) {
      const again = await findService(deps);
      if (again) return again;
      throw new ServiceUnavailableError(
        `\`cad gui serve\` exited (code ${ended.code ?? "unknown"}) without registering a healthy service; see the CADStudio GUI service terminal`
      );
    }
    if (deps.now() >= deadline) {
      throw new ServiceUnavailableError(
        `the GUI service did not become healthy within ${Math.round(timeoutMs / 1e3)} s; see the CADStudio GUI service terminal`
      );
    }
    await deps.sleep(pollMs);
  }
}
var ServiceLocator = class {
  constructor(deps, timeoutMs = START_TIMEOUT_MS, pollMs = POLL_INTERVAL_MS) {
    this.deps = deps;
    this.timeoutMs = timeoutMs;
    this.pollMs = pollMs;
  }
  deps;
  timeoutMs;
  pollMs;
  cached = null;
  inflight = null;
  get workspaceRoot() {
    return this.deps.workspaceRoot;
  }
  /** A healthy service, started if necessary; rejects with `ServiceUnavailableError`. */
  get() {
    if (this.cached) return Promise.resolve(this.cached);
    if (!this.inflight) {
      this.inflight = this.locate().finally(() => {
        this.inflight = null;
      });
    }
    return this.inflight;
  }
  /** The cached or registered healthy service, without starting one; null when there is none. */
  async find() {
    if (this.cached) return this.cached;
    if (this.inflight) return this.inflight.catch(() => null);
    const found = await findService(this.deps);
    if (found) this.cached = found;
    return found;
  }
  invalidate(record) {
    if (!record || this.cached === record) this.cached = null;
  }
  async locate() {
    const found = await findService(this.deps);
    if (found) {
      this.cached = found;
      return found;
    }
    let task;
    try {
      task = await this.deps.startService();
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new ServiceUnavailableError(`could not start \`cad gui serve\`: ${reason}`);
    }
    try {
      const started = await waitForService(this.deps, task, this.timeoutMs, this.pollMs);
      this.cached = started;
      return started;
    } finally {
      task.dispose?.();
    }
  }
};

// src/bridge.ts
var FORWARDED_EVENTS = ["job", "artifact"];
var RECONNECT_MS = 3e3;
var NODE_IO = { request: serviceRequest, openEventStream };
function messageOf(error) {
  return error instanceof Error ? error.message : String(error);
}
var HttpServiceClient = class {
  constructor(locator, io = NODE_IO) {
    this.locator = locator;
    this.io = io;
  }
  locator;
  io;
  async request(route, signal) {
    for (let attempt = 0; ; attempt += 1) {
      let record;
      try {
        record = await this.locator.get();
      } catch (error) {
        return { ok: false, error: { status: 0, message: messageOf(error) } };
      }
      if (signal.aborted) return { ok: false, error: networkError(new Error("request cancelled")) };
      let answer;
      try {
        answer = await this.io.request(record, route, signal);
      } catch (error) {
        if (attempt === 0 && error instanceof HttpFailure && error.refused && !signal.aborted) {
          this.locator.invalidate(record);
          continue;
        }
        return { ok: false, error: networkError(error) };
      }
      if (answer.status === 401 && attempt === 0) {
        this.locator.invalidate(record);
        continue;
      }
      return mapHttpResponse(answer.status, answer.statusText, answer.bytes, route.binary);
    }
  }
  async openEvents(handlers, options) {
    const record = options.startService ? await this.locator.get() : await this.locator.find();
    if (!record) throw new ServiceUnavailableError("no healthy GUI service is registered");
    return this.io.openEventStream(record, {
      onOpen: handlers.onOpen,
      onEvent: handlers.onEvent,
      onClose: (reason) => {
        this.locator.invalidate(record);
        handlers.onClose(reason);
      }
    });
  }
};
var PanelBridge = class {
  constructor(webview, client, options = {}) {
    this.webview = webview;
    this.client = client;
    this.reconnectMs = options.reconnectMs ?? RECONNECT_MS;
    this.setTimer = options.setTimer ?? ((callback, ms) => setTimeout(callback, ms));
    this.clearTimer = options.clearTimer ?? ((handle) => clearTimeout(handle));
    this.listener = webview.onDidReceiveMessage((message) => void this.handle(message));
  }
  webview;
  client;
  listener;
  inflight = /* @__PURE__ */ new Set();
  reconnectMs;
  setTimer;
  clearTimer;
  stream = null;
  timer = null;
  subscribed = false;
  /** Bumped on every (un)subscribe so a late stream from an old attempt is closed, not used. */
  generation = 0;
  attempts = 0;
  disposed = false;
  /** Requests currently being forwarded. */
  get pendingRequests() {
    return this.inflight.size;
  }
  get isSubscribed() {
    return this.subscribed;
  }
  /** Validate and act on one webview message; resolves once any reply has been posted. */
  async handle(raw) {
    if (this.disposed) return;
    const parsed = parseWebviewMessage(raw);
    if (!parsed.ok) {
      if (parsed.id !== null) this.post({ kind: "response", id: parsed.id, ok: false, error: rejectedError(parsed.error) });
      return;
    }
    const { message } = parsed;
    if (message.kind === "subscribe") return this.subscribe();
    if (message.kind === "unsubscribe") return this.unsubscribe();
    const controller = new AbortController();
    this.inflight.add(controller);
    try {
      const reply = await this.client.request(routeFor(message.call), controller.signal);
      if (!controller.signal.aborted) this.post({ kind: "response", id: message.id, ...reply });
    } finally {
      this.inflight.delete(controller);
    }
  }
  /** Abort in-flight requests, close the event stream and stop listening to the webview. */
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.listener.dispose();
    for (const controller of this.inflight) controller.abort();
    this.inflight.clear();
    this.stopEvents();
  }
  post(message) {
    if (this.disposed) return;
    Promise.resolve(this.webview.postMessage(message)).then(void 0, () => {
    });
  }
  subscribe() {
    if (this.subscribed) return;
    this.subscribed = true;
    this.attempts = 0;
    void this.connect(++this.generation);
  }
  unsubscribe() {
    this.stopEvents();
  }
  stopEvents() {
    this.subscribed = false;
    this.generation += 1;
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
    this.stream?.close();
    this.stream = null;
  }
  async connect(generation) {
    const current = () => !this.disposed && this.subscribed && generation === this.generation;
    const startService = this.attempts === 0;
    this.attempts += 1;
    let stream;
    try {
      stream = await this.client.openEvents(
        {
          onOpen: () => {
            if (current()) this.post({ kind: "connection", state: "open" });
          },
          onEvent: (event) => {
            if (!current() || !FORWARDED_EVENTS.includes(event.event)) return;
            let data;
            try {
              data = JSON.parse(event.data);
            } catch {
              return;
            }
            this.post({ kind: "event", event: event.event, data });
          },
          onClose: () => {
            if (!current()) return;
            this.stream = null;
            this.post({ kind: "connection", state: "error" });
            this.scheduleReconnect(generation);
          }
        },
        { startService }
      );
    } catch {
      if (!current()) return;
      this.post({ kind: "connection", state: "error" });
      this.scheduleReconnect(generation);
      return;
    }
    if (!current()) {
      stream.close();
      return;
    }
    this.stream = stream;
  }
  scheduleReconnect(generation) {
    if (this.timer !== null) return;
    this.timer = this.setTimer(() => {
      this.timer = null;
      if (!this.disposed && this.subscribed && generation === this.generation) void this.connect(generation);
    }, this.reconnectMs);
  }
};

// src/html.ts
var import_node_crypto = require("node:crypto");
function makeNonce() {
  return (0, import_node_crypto.randomBytes)(16).toString("base64");
}
var ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
};
function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ESCAPES[char]);
}
function buildCsp(nonce) {
  return [
    "default-src 'none'",
    `script-src 'nonce-${nonce}'`,
    `style-src 'nonce-${nonce}'`,
    "connect-src 'none'",
    "base-uri 'none'",
    "form-action 'none'"
  ].join("; ");
}
var ATTRIBUTE = /([^\s"'<>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
function parseAttributes(source) {
  const attributes = [];
  for (const match of source.matchAll(ATTRIBUTE)) {
    attributes.push([match[1].toLowerCase(), match[2] ?? match[3] ?? match[4] ?? null]);
  }
  return attributes;
}
function renderTag(name, attributes) {
  const rendered = attributes.map(([key, value]) => value === null ? key : `${key}="${escapeHtml(value)}"`);
  return `<${name}${rendered.length ? " " + rendered.join(" ") : ""}>`;
}
function bundlePath(value) {
  const path = value.startsWith("./") ? value.slice(2) : value;
  if (path === "" || /^[a-z][a-z0-9+.-]*:/i.test(path) || path.startsWith("/") || /[\\?#]/.test(path) || path.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(`ui/dist/index.html references ${JSON.stringify(value)}, which is not a bundle asset`);
  }
  return path;
}
function renderPanelHtml(indexHtml, options) {
  const { nonce, assetUri } = options;
  if (!/^[A-Za-z0-9+/=]+$/.test(nonce)) throw new Error("nonce must be base64");
  const scripts = (indexHtml.match(/<script\b/gi) ?? []).length;
  let rewritten = 0;
  let html = indexHtml.replace(/<meta\b[^>]*http-equiv\s*=\s*["']?content-security-policy["']?[^>]*>/gi, "");
  if (/<base\b/i.test(html)) throw new Error("ui/dist/index.html must not contain <base>");
  html = html.replace(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi, (_tag, source, body) => {
    const attributes = parseAttributes(source).filter(([key]) => key !== "nonce");
    const src = attributes.find(([key]) => key === "src");
    if (!src || src[1] === null || body.trim() !== "") {
      throw new Error("ui/dist/index.html has an inline script; the webview runs bundle files only");
    }
    src[1] = assetUri(bundlePath(src[1]));
    attributes.push(["nonce", nonce]);
    rewritten += 1;
    return `${renderTag("script", attributes)}</script>`;
  });
  if (rewritten !== scripts) throw new Error("ui/dist/index.html has a <script> without a closing tag");
  html = html.replace(/<link\b([^>]*?)\/?>/gi, (_tag, source) => {
    const attributes = parseAttributes(source).filter(([key]) => key !== "nonce");
    const href = attributes.find(([key]) => key === "href");
    if (href && href[1] !== null) href[1] = assetUri(bundlePath(href[1]));
    const rel = (attributes.find(([key]) => key === "rel")?.[1] ?? "").toLowerCase().split(/\s+/);
    if (rel.includes("stylesheet") || rel.includes("modulepreload")) attributes.push(["nonce", nonce]);
    return renderTag("link", attributes);
  });
  if (/<style\b/i.test(html)) throw new Error("ui/dist/index.html has an inline <style>; use the bundled stylesheet");
  const head = /<head\b[^>]*>/i.exec(html);
  if (!head) throw new Error("ui/dist/index.html has no <head>");
  const meta = `
<meta http-equiv="Content-Security-Policy" content="${buildCsp(nonce)}">`;
  const at = head.index + head[0].length;
  return html.slice(0, at) + meta + html.slice(at);
}

// src/tasks.ts
var vscode = __toESM(require("vscode"));
var TASK_TYPE = "cadstudio";
var SERVE_TASK = "serve";
var SERVE_TASK_NAME = "GUI service";
var SERVE_COMMAND = "uv";
var SERVE_ARGS = ["run", "--frozen", "--extra", "physics", "cad", "gui", "serve", "--no-browser", "--json"];
function isServeTask(task) {
  return task.definition.type === TASK_TYPE && task.definition.task === SERVE_TASK;
}
function makeServeTask(folder) {
  const task = new vscode.Task(
    { type: TASK_TYPE, task: SERVE_TASK },
    folder,
    SERVE_TASK_NAME,
    "CADStudio",
    new vscode.ShellExecution(SERVE_COMMAND, SERVE_ARGS, { cwd: folder.uri.fsPath })
  );
  task.isBackground = true;
  task.presentationOptions = {
    reveal: vscode.TaskRevealKind.Silent,
    panel: vscode.TaskPanelKind.Dedicated,
    focus: false,
    clear: false,
    echo: true
  };
  return task;
}
function watchExit() {
  const listeners = [];
  const dispose = () => listeners.splice(0).forEach((listener) => listener.dispose());
  let settle = () => {
  };
  const exited = new Promise((resolve) => {
    settle = resolve;
  });
  try {
    listeners.push(
      vscode.tasks.onDidEndTaskProcess((event) => {
        if (isServeTask(event.execution.task)) settle(event.exitCode);
      })
    );
    listeners.push(
      vscode.tasks.onDidEndTask((event) => {
        if (isServeTask(event.execution.task)) settle(void 0);
      })
    );
  } catch (error) {
    dispose();
    throw error;
  }
  void exited.then(dispose);
  return { exited, dispose };
}
async function startServeTask(folder) {
  const started = watchExit();
  if (vscode.tasks.taskExecutions.some((execution) => isServeTask(execution.task))) return started;
  try {
    await vscode.tasks.executeTask(makeServeTask(folder));
  } catch (error) {
    started.dispose?.();
    throw error;
  }
  return started;
}

// src/uri.ts
var OPEN_PATH = "/open";
function parseOpenUri(uri) {
  const path = uri.path.endsWith("/") ? uri.path.slice(0, -1) : uri.path;
  if (path !== OPEN_PATH) return void 0;
  return { query: uri.query };
}

// src/extension.ts
var COMMAND_ID = "cadstudio.openGui";
var VIEW_TYPE = "cadstudio.gui";
var MEDIA_DIR = "media";
var UNTRUSTED_MESSAGE = "CADStudio is disabled in untrusted workspaces. Trust this workspace to open the GUI.";
var NO_FOLDER_MESSAGE = "CADStudio: open the cadstudio repository folder to use the GUI.";
function canonicalPath(path) {
  try {
    return (0, import_node_fs.realpathSync)(path);
  } catch {
    return path;
  }
}
var defaultDeps = {
  readIndexHtml: (extensionUri) => (0, import_node_fs.readFileSync)((0, import_node_path2.join)(extensionUri.fsPath, MEDIA_DIR, "index.html"), "utf8"),
  createClient: (folder) => new HttpServiceClient(
    new ServiceLocator({
      workspaceRoot: canonicalPath(folder.uri.fsPath),
      readFile: (path) => (0, import_promises.readFile)(path, "utf8").catch(() => null),
      health: (port) => fetchHealth(port),
      startService: () => startServeTask(folder),
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      now: () => Date.now()
    })
  )
};
function panelOptions(extensionUri) {
  return {
    enableScripts: true,
    localResourceRoots: [vscode2.Uri.joinPath(extensionUri, MEDIA_DIR)],
    retainContextWhenHidden: true
  };
}
var GuiPanels = class {
  constructor(context, deps) {
    this.context = context;
    this.deps = deps;
  }
  context;
  deps;
  panel;
  bridge;
  client;
  get current() {
    return this.panel;
  }
  /** Reveal the open panel, or create one; refuses in an untrusted or folderless window. */
  open() {
    if (this.refused()) return void 0;
    if (this.panel) {
      this.panel.reveal();
      return this.panel;
    }
    const index = this.readIndex();
    if (index === void 0) return void 0;
    const panel = vscode2.window.createWebviewPanel(
      VIEW_TYPE,
      "CADStudio",
      vscode2.ViewColumn.Active,
      panelOptions(this.context.extensionUri)
    );
    this.attach(panel, index);
    return panel;
  }
  /** Take over a panel VS Code revived after a reload; a refused one is closed. */
  restore(panel) {
    if (this.refused()) {
      panel.dispose();
      return;
    }
    if (this.panel && this.panel !== panel) {
      panel.dispose();
      this.panel.reveal();
      return;
    }
    const index = this.readIndex();
    if (index === void 0) {
      panel.dispose();
      return;
    }
    panel.webview.options = panelOptions(this.context.extensionUri);
    this.attach(panel, index);
  }
  dispose() {
    this.bridge?.dispose();
    this.bridge = void 0;
    this.panel = void 0;
  }
  refused() {
    if (!vscode2.workspace.isTrusted) {
      void vscode2.window.showErrorMessage(UNTRUSTED_MESSAGE);
      return true;
    }
    if (!vscode2.workspace.workspaceFolders?.[0]) {
      void vscode2.window.showErrorMessage(NO_FOLDER_MESSAGE);
      return true;
    }
    return false;
  }
  readIndex() {
    try {
      return this.deps.readIndexHtml(this.context.extensionUri);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      void vscode2.window.showErrorMessage(`CADStudio: the GUI bundle is missing (${reason}). Rebuild editor/vscode.`);
      return void 0;
    }
  }
  clientFor(folder) {
    const key = folder.uri.toString();
    if (this.client?.key !== key) this.client = { key, client: this.deps.createClient(folder) };
    return this.client.client;
  }
  attach(panel, index) {
    const folder = vscode2.workspace.workspaceFolders[0];
    const webview = panel.webview;
    const media = vscode2.Uri.joinPath(this.context.extensionUri, MEDIA_DIR);
    let html;
    try {
      html = renderPanelHtml(index, {
        nonce: makeNonce(),
        assetUri: (path) => webview.asWebviewUri(vscode2.Uri.joinPath(media, ...path.split("/"))).toString()
      });
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      void vscode2.window.showErrorMessage(`CADStudio: could not load the GUI bundle: ${reason}`);
      panel.dispose();
      return;
    }
    const bridge = new PanelBridge(webview, this.clientFor(folder));
    this.panel = panel;
    this.bridge = bridge;
    panel.onDidDispose(() => {
      bridge.dispose();
      if (this.panel === panel) {
        this.panel = void 0;
        this.bridge = void 0;
      }
    });
    webview.html = html;
  }
};
function activate(context, deps = defaultDeps) {
  const panels = new GuiPanels(context, deps);
  context.subscriptions.push({ dispose: () => panels.dispose() });
  context.subscriptions.push(
    vscode2.commands.registerCommand(COMMAND_ID, () => {
      panels.open();
    })
  );
  context.subscriptions.push(
    vscode2.window.registerWebviewPanelSerializer(VIEW_TYPE, {
      async deserializeWebviewPanel(panel) {
        panels.restore(panel);
      }
    })
  );
  context.subscriptions.push(
    vscode2.window.registerUriHandler({
      handleUri(uri) {
        const open = parseOpenUri(uri);
        if (!open) {
          void vscode2.window.showWarningMessage(
            `CADStudio: unsupported URI path "${uri.path}"`
          );
          return;
        }
        void vscode2.commands.executeCommand(COMMAND_ID, open.query);
      }
    })
  );
}
function deactivate() {
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  COMMAND_ID,
  GuiPanels,
  MEDIA_DIR,
  NO_FOLDER_MESSAGE,
  UNTRUSTED_MESSAGE,
  VIEW_TYPE,
  activate,
  deactivate,
  defaultDeps,
  panelOptions
});

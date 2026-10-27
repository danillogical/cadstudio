import { isRecord, jobOf, mapEvent } from "./events";
import type { HostToWebview, TransportMethod, WebviewToHost } from "./messages";
import {
  type CadStudioTransport,
  type HealthInfo,
  type Job,
  type ModelList,
  type PhysicsInputs,
  type RunList,
  type SceneResponse,
  type ServiceEvent,
  type StartRunRequest,
  type TrajectoryResponse,
  TransportError,
} from "./types";

/** Long enough for a first trajectory export of a big run; the browser path has no limit at all. */
export const REQUEST_TIMEOUT_MS = 10 * 60_000;

/** The slice of the webview API (`acquireVsCodeApi()`) the transport uses. */
export interface VsCodeApi {
  postMessage(message: unknown): void;
}

export interface VsCodeTransportOptions {
  api: VsCodeApi;
  /** Register a listener for messages from the extension host; returns its remover. */
  listen: (listener: (data: unknown) => void) => () => void;
  timeoutMs?: number;
}

interface Pending {
  method: TransportMethod;
  resolve: (value: unknown) => void;
  reject: (error: TransportError) => void;
  timer: ReturnType<typeof setTimeout>;
}

type VsCodeGlobal = { acquireVsCodeApi?: () => VsCodeApi };

/** True inside a VS Code webview, where `acquireVsCodeApi` is defined. */
export function hasVsCodeApi(scope: unknown = globalThis): boolean {
  return typeof (scope as VsCodeGlobal).acquireVsCodeApi === "function";
}

/** Copy bytes out of whatever the host's structured message delivered into an exact ArrayBuffer. */
export function toArrayBuffer(value: unknown): ArrayBuffer | null {
  if (value instanceof ArrayBuffer) return value;
  if (ArrayBuffer.isView(value)) {
    const view = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    return view.slice().buffer;
  }
  return null;
}

/**
 * The transport inside a VS Code webview. Every call is a postMessage to the extension host,
 * which validates it and talks to the service; the webview never opens a connection itself
 * and never sees the service token.
 */
export class VsCodeTransport implements CadStudioTransport {
  private readonly api: VsCodeApi;
  private readonly timeoutMs: number;
  private readonly pending = new Map<number, Pending>();
  private readonly listeners = new Set<(event: ServiceEvent) => void>();
  private readonly stopListening: () => void;
  private nextId = 1;

  constructor(options: VsCodeTransportOptions) {
    this.api = options.api;
    this.timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
    this.stopListening = options.listen((data) => this.receive(data));
  }

  /** Build from the webview globals; `acquireVsCodeApi` may be called only once per page. */
  static fromWebview(scope: Window & typeof globalThis = window): VsCodeTransport {
    const acquire = (scope as unknown as VsCodeGlobal).acquireVsCodeApi;
    if (!acquire) throw new Error("not running in a VS Code webview");
    const api = acquire();
    return new VsCodeTransport({
      api,
      listen: (listener) => {
        const onMessage = (event: MessageEvent) => listener(event.data);
        scope.addEventListener("message", onMessage);
        return () => scope.removeEventListener("message", onMessage);
      },
    });
  }

  private post(message: WebviewToHost): void {
    this.api.postMessage(message);
  }

  private call(method: TransportMethod, args: unknown[]): Promise<unknown> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!this.pending.delete(id)) return;
        reject(new TransportError(0, `${method} timed out after ${Math.round(this.timeoutMs / 1000)} s`));
      }, this.timeoutMs);
      this.pending.set(id, { method, resolve, reject, timer });
      try {
        this.post({ kind: "request", id, method, args });
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(new TransportError(0, `network error: ${error instanceof Error ? error.message : String(error)}`));
      }
    });
  }

  /** A JSON-object result, mirroring BrowserTransport's "response is not a JSON object" check. */
  private async callJson<T>(method: TransportMethod, args: unknown[]): Promise<T> {
    const result = await this.call(method, args);
    if (!isRecord(result)) throw new TransportError(0, "response is not a JSON object");
    return result as T;
  }

  private receive(data: unknown): void {
    if (!isRecord(data)) return;
    const message = data as unknown as HostToWebview;
    if (message.kind === "response") {
      const entry = typeof message.id === "number" ? this.pending.get(message.id) : undefined;
      if (!entry) return;
      this.pending.delete(message.id);
      clearTimeout(entry.timer);
      if (message.ok === true) {
        entry.resolve(message.result);
      } else {
        const error: Record<string, unknown> = isRecord(message.error) ? message.error : {};
        const status = typeof error.status === "number" ? error.status : 0;
        const text = typeof error.message === "string" ? error.message : "request failed";
        entry.reject(new TransportError(status, text, isRecord(error.body) ? error.body : undefined));
      }
      return;
    }
    if (message.kind === "event") {
      const mapped = mapEvent(message.data);
      if (mapped) this.emit(mapped);
      return;
    }
    if (message.kind === "connection" && (message.state === "open" || message.state === "error")) {
      this.emit({ type: "connection", state: message.state });
    }
  }

  private emit(event: ServiceEvent): void {
    for (const listener of [...this.listeners]) listener(event);
  }

  async health(): Promise<HealthInfo> {
    return this.callJson<HealthInfo>("health", []);
  }

  async listModels(): Promise<ModelList> {
    return this.callJson<ModelList>("listModels", []);
  }

  async getScene(model: string): Promise<SceneResponse> {
    return this.callJson<SceneResponse>("getScene", [model]);
  }

  async startBuild(model: string, sets?: Record<string, number | string>): Promise<Job> {
    return jobOf(await this.callJson("startBuild", sets ? [model, sets] : [model]));
  }

  async listPhysicsInputs(model: string): Promise<PhysicsInputs> {
    return this.callJson<PhysicsInputs>("listPhysicsInputs", [model]);
  }

  async listRuns(): Promise<RunList> {
    return this.callJson<RunList>("listRuns", []);
  }

  async getTrajectory(runId: string): Promise<TrajectoryResponse> {
    return this.callJson<TrajectoryResponse>("getTrajectory", [runId]);
  }

  async startRun(req: StartRunRequest): Promise<Job> {
    const body: Record<string, string> = {
      model: req.model,
      scenario: req.scenario,
      acceptance: req.acceptance,
    };
    if (req.options !== undefined) body.options = req.options;
    return jobOf(await this.callJson("startRun", [body]));
  }

  async getJob(id: string): Promise<Job> {
    return jobOf(await this.callJson("getJob", [id]));
  }

  async cancelJob(id: string): Promise<Job> {
    return jobOf(await this.callJson("cancelJob", [id]));
  }

  async getArtifact(path: string): Promise<ArrayBuffer> {
    const bytes = toArrayBuffer(await this.call("getArtifact", [path]));
    if (!bytes) throw new TransportError(0, "artifact response is not binary");
    return bytes;
  }

  /** The host holds one event stream per panel; it opens with the first listener, closes with the last. */
  subscribe(listener: (event: ServiceEvent) => void): () => void {
    const first = this.listeners.size === 0;
    this.listeners.add(listener);
    if (first) this.post({ kind: "subscribe" });
    let active = true;
    return () => {
      if (!active) return;
      active = false;
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.post({ kind: "unsubscribe" });
    };
  }

  /** Reject outstanding calls and stop listening, e.g. when the page goes away. */
  dispose(): void {
    this.stopListening();
    for (const [id, entry] of this.pending) {
      clearTimeout(entry.timer);
      entry.reject(new TransportError(0, `${entry.method} cancelled: the transport was disposed`));
      this.pending.delete(id);
    }
    if (this.listeners.size > 0) {
      this.listeners.clear();
      this.post({ kind: "unsubscribe" });
    }
  }
}

import {
  type CadStudioTransport,
  type HealthInfo,
  type Job,
  type ModelList,
  type RunList,
  type SceneResponse,
  type ServiceEvent,
  type StartRunRequest,
  type TrajectoryResponse,
  TransportError,
} from "./types";

export const TOKEN_STORAGE_KEY = "cadstudio.token";

/** The slice of `window` the transport needs; kept structural so tests can fake it. */
export interface TransportWindow {
  location: { origin: string; pathname: string; search: string; hash: string };
  history: {
    state: unknown;
    replaceState(state: unknown, title: string, url?: string | null): void;
  };
  sessionStorage: Storage;
}

export interface BrowserTransportOptions {
  baseUrl: string;
  token?: string | null;
  fetch?: typeof fetch;
  EventSource?: typeof EventSource;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Percent-encode each slash-separated segment, leaving the separators intact. */
export function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

/** Remove `token` from a query string while keeping every other parameter and its order. */
export function stripToken(search: string): string {
  const params = new URLSearchParams(search);
  params.delete("token");
  const rest = params.toString();
  return rest ? `?${rest}` : "";
}

export class BrowserTransport implements CadStudioTransport {
  readonly baseUrl: string;
  readonly token: string | null;
  private readonly fetchImpl: typeof fetch;
  private readonly EventSourceImpl: typeof EventSource | undefined;

  constructor(options: BrowserTransportOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.token = options.token ?? null;
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.EventSourceImpl = options.EventSource ?? globalThis.EventSource;
  }

  /**
   * Build from the page URL: a `?token=` is stored in sessionStorage and stripped from the
   * address bar, so a reload keeps working without leaving the token in history.
   */
  static fromLocation(win: TransportWindow = window): BrowserTransport {
    const stored = win.sessionStorage.getItem(TOKEN_STORAGE_KEY);
    const params = new URLSearchParams(win.location.search);
    const fromUrl = params.get("token");
    let token = stored;
    if (fromUrl) {
      token = fromUrl;
      win.sessionStorage.setItem(TOKEN_STORAGE_KEY, fromUrl);
      const search = stripToken(win.location.search);
      const url = `${win.location.pathname}${search}${win.location.hash}`;
      win.history.replaceState(win.history.state, "", url);
    }
    return new BrowserTransport({ baseUrl: win.location.origin, token });
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");

    let response: Response;
    try {
      response = await this.fetchImpl(this.url(path), { ...init, headers });
    } catch (error) {
      throw new TransportError(0, `network error: ${errorMessage(error)}`);
    }

    let body: unknown;
    const text = await response.text();
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined;
      }
    }
    if (!response.ok) {
      const detail = isRecord(body) && typeof body.error === "string" ? body.error : null;
      throw new TransportError(
        response.status,
        detail ?? (response.statusText || `HTTP ${response.status}`),
        isRecord(body) ? body : undefined,
      );
    }
    if (!isRecord(body)) {
      throw new TransportError(response.status, "response is not a JSON object");
    }
    return body as T;
  }

  async health(): Promise<HealthInfo> {
    return this.request<HealthInfo>("/v1/health");
  }

  async listModels(): Promise<ModelList> {
    return this.request<ModelList>("/v1/models");
  }

  async getScene(model: string): Promise<SceneResponse> {
    return this.request<SceneResponse>(`/v1/models/${encodePath(model)}/scene`);
  }

  async startBuild(model: string, sets?: Record<string, number | string>): Promise<Job> {
    const body = sets ? { set: sets } : {};
    const doc = await this.request<{ job: Job }>(`/v1/models/${encodePath(model)}/build`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    return doc.job;
  }

  async listRuns(): Promise<RunList> {
    return this.request<RunList>("/v1/runs");
  }

  async getTrajectory(runId: string): Promise<TrajectoryResponse> {
    return this.request<TrajectoryResponse>(`/v1/runs/${encodePath(runId)}/trajectory`);
  }

  async startRun(req: StartRunRequest): Promise<Job> {
    const body: Record<string, unknown> = {
      model: req.model,
      scenario: req.scenario,
      acceptance: req.acceptance,
    };
    if (req.options !== undefined) body.options = req.options;
    const doc = await this.request<{ job: Job }>("/v1/runs", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return doc.job;
  }

  async getJob(id: string): Promise<Job> {
    const doc = await this.request<{ job: Job }>(`/v1/jobs/${encodeURIComponent(id)}`);
    return doc.job;
  }

  async cancelJob(id: string): Promise<Job> {
    const doc = await this.request<{ job: Job }>(
      `/v1/jobs/${encodeURIComponent(id)}/cancel`,
      { method: "POST" },
    );
    return doc.job;
  }

  /** EventSource cannot send headers, so the token rides in the query string. */
  subscribe(listener: (event: ServiceEvent) => void): () => void {
    if (!this.EventSourceImpl) {
      listener({ type: "connection", state: "error" });
      return () => {};
    }
    const query = this.token ? `?token=${encodeURIComponent(this.token)}` : "";
    const source = new this.EventSourceImpl(`${this.url("/v1/events")}${query}`);

    const onMessage = (event: Event) => {
      try {
        const mapped = mapEvent(JSON.parse((event as MessageEvent<string>).data));
        if (mapped) listener(mapped);
      } catch {
        // A malformed frame is not worth tearing the stream down for.
      }
    };

    source.addEventListener("job", onMessage);
    source.addEventListener("artifact", onMessage);
    source.onopen = () => listener({ type: "connection", state: "open" });
    source.onerror = () => listener({ type: "connection", state: "error" });

    return () => source.close();
  }

  artifactUrl(path: string): string {
    const base = `${this.url("/v1/artifacts")}/${encodePath(path)}`;
    return this.token ? `${base}?token=${encodeURIComponent(this.token)}` : base;
  }
}

/** Map an SSE `job` or `artifact` payload; anything else is ignored. */
function mapEvent(parsed: unknown): ServiceEvent | null {
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
  return null;
}

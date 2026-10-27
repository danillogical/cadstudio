/**
 * One suite, two transports: `BrowserTransport` over a fake fetch/EventSource, and
 * `VsCodeTransport` wired through the real extension-host `PanelBridge` and `HttpServiceClient`
 * (validation, routing, error mapping) to the same fake service. Both must behave identically.
 */
import { afterEach, describe, expect, it } from "vitest";
import { HttpServiceClient, PanelBridge, type HttpIo } from "../../../editor/vscode/src/bridge";
import type { EventStream, EventStreamHandlers } from "../../../editor/vscode/src/http";
import type { HttpRoute } from "../../../editor/vscode/src/protocol";
import type { ServiceLocator, ServiceRecord } from "../../../editor/vscode/src/service";
import { BrowserTransport } from "./browser";
import { TransportError, type CadStudioTransport, type ServiceEvent } from "./types";
import { VsCodeTransport } from "./vscode";

const TOKEN = "contract-token";
const JOB = {
  id: "j1",
  kind: "build",
  key: "pocky/syringe",
  model: "pocky/syringe",
  status: "queued",
  createdAt: 1,
  startedAt: null,
  finishedAt: null,
  error: null,
  exitCode: null,
  log: [],
  artifacts: {},
};
const BYTES = Uint8Array.from([0, 1, 2, 3, 250, 251, 252, 253, 254, 255]);

interface ServiceRequest {
  method: string;
  path: string;
  body: unknown;
  authorized: boolean;
}

interface ServiceAnswer {
  status: number;
  statusText?: string;
  json?: unknown;
  bytes?: Uint8Array;
  /** Make the "network" fail instead of answering. */
  networkError?: string;
}

/** The fake GUI service both transports talk to; records what reached it. */
class FakeService {
  requests: ServiceRequest[] = [];
  respond: (request: ServiceRequest) => ServiceAnswer = () => ({ status: 200, json: {} });
  /** Event-stream subscribers (browser sources and host streams alike). */
  private emitters = new Set<(event: string, data: string) => void>();
  private openers = new Set<() => void>();
  closedStreams = 0;

  handle(method: string, path: string, rawBody: string | undefined, token: string | null): ServiceAnswer {
    const request: ServiceRequest = {
      method,
      path,
      body: rawBody ? JSON.parse(rawBody) : undefined,
      authorized: token === TOKEN,
    };
    this.requests.push(request);
    if (!request.authorized) return { status: 401, statusText: "Unauthorized", json: { error: "bad token" } };
    return this.respond(request);
  }

  attach(emit: (event: string, data: string) => void, onOpen: () => void): () => void {
    this.emitters.add(emit);
    this.openers.add(onOpen);
    onOpen();
    return () => {
      this.emitters.delete(emit);
      this.openers.delete(onOpen);
      this.closedStreams += 1;
    };
  }

  emit(event: string, data: unknown): void {
    for (const emitter of [...this.emitters]) emitter(event, typeof data === "string" ? data : JSON.stringify(data));
  }

  get subscribers(): number {
    return this.emitters.size;
  }
}

function toResponse(answer: ServiceAnswer): Response {
  const body = answer.bytes ?? (answer.json === undefined ? "" : JSON.stringify(answer.json));
  return new Response(body as BodyInit, { status: answer.status, statusText: answer.statusText ?? "" });
}

function makeBrowser(service: FakeService): { transport: CadStudioTransport; dispose(): void } {
  const fetchImpl = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input));
    const headers = new Headers(init.headers);
    const auth = headers.get("Authorization");
    const answer = service.handle(
      init.method ?? "GET",
      url.pathname + url.search,
      init.body as string | undefined,
      auth?.startsWith("Bearer ") ? auth.slice(7) : null,
    );
    if (answer.networkError) throw new TypeError(answer.networkError);
    return toResponse(answer);
  }) as typeof fetch;

  class FakeEventSource {
    onopen: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private listeners = new Map<string, Array<(event: { data: string }) => void>>();
    private detach: () => void;
    constructor(readonly url: string) {
      this.detach = service.attach(
        (event, data) => this.listeners.get(event)?.forEach((listener) => listener({ data })),
        () => queueMicrotask(() => this.onopen?.()),
      );
    }
    addEventListener(name: string, listener: (event: { data: string }) => void) {
      this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
    }
    close() {
      this.detach();
    }
  }

  return {
    transport: new BrowserTransport({
      baseUrl: "http://127.0.0.1:4321",
      token: TOKEN,
      fetch: fetchImpl,
      EventSource: FakeEventSource as unknown as typeof EventSource,
    }),
    dispose() {},
  };
}

const RECORD: ServiceRecord = { pid: 1, port: 4321, token: TOKEN, repoRoot: "/r", protocolVersion: 1 };

function makeVsCode(service: FakeService): { transport: CadStudioTransport; dispose(): void } {
  const locator = {
    get: async () => RECORD,
    find: async () => RECORD,
    invalidate: () => {},
  } as unknown as ServiceLocator;

  const io: HttpIo = {
    async request(endpoint, route: HttpRoute) {
      const body = route.body === undefined ? undefined : JSON.stringify(route.body);
      const answer = service.handle(route.method, route.path, body, endpoint.token);
      if (answer.networkError) throw new Error(answer.networkError);
      const bytes = answer.bytes ?? new TextEncoder().encode(answer.json === undefined ? "" : JSON.stringify(answer.json));
      return { status: answer.status, statusText: answer.statusText ?? "", bytes };
    },
    openEventStream(_endpoint, handlers: EventStreamHandlers): EventStream {
      let open = true;
      const detach = service.attach(
        (event, data) => {
          if (open) handlers.onEvent({ event, data });
        },
        () => queueMicrotask(() => open && handlers.onOpen()),
      );
      return {
        close() {
          open = false;
          detach();
        },
      };
    },
  };

  const listeners = new Set<(data: unknown) => void>();
  const webview = {
    // Structured-clone every message in both directions, as VS Code does.
    postMessage(message: unknown): PromiseLike<boolean> {
      const copy = structuredClone(message);
      queueMicrotask(() => listeners.forEach((listener) => listener(copy)));
      return Promise.resolve(true);
    },
    onDidReceiveMessage(listener: (message: unknown) => void) {
      hostListeners.add(listener);
      return { dispose: () => hostListeners.delete(listener) };
    },
  };
  const hostListeners = new Set<(message: unknown) => void>();
  const bridge = new PanelBridge(webview, new HttpServiceClient(locator, io));

  const transport = new VsCodeTransport({
    api: {
      postMessage(message) {
        const copy = structuredClone(message);
        queueMicrotask(() => hostListeners.forEach((listener) => listener(copy)));
      },
    },
    listen(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  });
  return {
    transport,
    dispose() {
      transport.dispose();
      bridge.dispose();
    },
  };
}

const FACTORIES: Array<[string, (service: FakeService) => { transport: CadStudioTransport; dispose(): void }]> = [
  ["BrowserTransport", makeBrowser],
  ["VsCodeTransport via the extension host", makeVsCode],
];

describe.each(FACTORIES)("transport contract: %s", (_name, factory) => {
  let service: FakeService;
  let transport: CadStudioTransport;
  let dispose: () => void;
  const cleanups: Array<() => void> = [];

  function setup(respond?: FakeService["respond"]) {
    service = new FakeService();
    if (respond) service.respond = respond;
    const made = factory(service);
    transport = made.transport;
    dispose = made.dispose;
    return service;
  }

  afterEach(() => {
    for (const cleanup of cleanups.splice(0)) cleanup();
    dispose?.();
  });

  const waitFor = async (predicate: () => boolean) => {
    for (let i = 0; i < 200 && !predicate(); i += 1) await new Promise((resolve) => setTimeout(resolve, 1));
    expect(predicate()).toBe(true);
  };

  const failure = async (promise: Promise<unknown>): Promise<TransportError> => {
    const error = await promise.then(
      () => null,
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(TransportError);
    return error as TransportError;
  };

  it("health", async () => {
    const health = { schemaVersion: 1, service: "cadstudio", protocolVersion: 1, repoRoot: "/r", pid: 9 };
    setup(() => ({ status: 200, json: health }));
    expect(await transport.health()).toEqual(health);
    expect(service.requests.map((r) => `${r.method} ${r.path}`)).toEqual(["GET /v1/health"]);
  });

  it("listModels", async () => {
    const models = { schemaVersion: 1, projects: [{ name: "pocky", params_path: "p.toml", models: ["syringe"] }], models: ["pocky/syringe"] };
    setup(() => ({ status: 200, json: models }));
    expect(await transport.listModels()).toEqual(models);
    expect(service.requests[0]).toMatchObject({ method: "GET", path: "/v1/models", authorized: true });
  });

  it("getScene", async () => {
    const scene = { schemaVersion: 1, project: "pocky", model: "syringe", stale: false, error: null, job: null, artifactBase: "pocky/syringe/scene", scene: { parts: [] } };
    setup(() => ({ status: 200, json: scene }));
    expect(await transport.getScene("pocky/syringe")).toEqual(scene);
    expect(service.requests[0]).toMatchObject({ method: "GET", path: "/v1/models/pocky/syringe/scene" });
  });

  it("getArtifact returns the exact bytes in an ArrayBuffer", async () => {
    setup(() => ({ status: 200, bytes: BYTES }));
    const buffer = await transport.getArtifact("pocky/syringe/scene/scene.glb");
    expect(buffer).toBeInstanceOf(ArrayBuffer);
    expect(buffer.byteLength).toBe(BYTES.byteLength);
    expect([...new Uint8Array(buffer)]).toEqual([...BYTES]);
    expect(service.requests[0]).toMatchObject({ method: "GET", path: "/v1/artifacts/pocky/syringe/scene/scene.glb" });
  });

  it("getArtifact of an empty file is an empty ArrayBuffer", async () => {
    setup(() => ({ status: 200, bytes: new Uint8Array(0) }));
    expect((await transport.getArtifact("a/empty.bin")).byteLength).toBe(0);
  });

  it("getArtifact encodes each path segment", async () => {
    setup(() => ({ status: 200, bytes: BYTES }));
    await transport.getArtifact("a b/c#d");
    expect(service.requests[0].path).toBe("/v1/artifacts/a%20b/c%23d");
  });

  it("listRuns", async () => {
    const runs = { schemaVersion: 1, runs: [{ runId: "r2", path: "out/r2", status: "pass", modified: 2 }, { runId: "r1", path: "out/r1", status: null, modified: null }] };
    setup(() => ({ status: 200, json: runs }));
    expect(await transport.listRuns()).toEqual(runs);
    expect(service.requests[0]).toMatchObject({ method: "GET", path: "/v1/runs" });
  });

  it("getTrajectory", async () => {
    const trajectory = { schemaVersion: 1, runId: "pocky/r1", stale: false, error: null, artifactBase: "pocky/r1/.gui", trajectory: { frameCount: 3 } };
    setup(() => ({ status: 200, json: trajectory }));
    expect(await transport.getTrajectory("pocky/r1")).toEqual(trajectory);
    expect(service.requests[0]).toMatchObject({ method: "GET", path: "/v1/runs/pocky/r1/trajectory" });
  });

  it("startBuild without and with sets", async () => {
    setup(() => ({ status: 202, json: { job: JOB } }));
    expect(await transport.startBuild("pocky/syringe")).toEqual(JOB);
    expect(await transport.startBuild("pocky/syringe", { "fit.clearance": 0.5, label: "x" })).toEqual(JOB);
    expect(service.requests.map((r) => [r.method, r.path, r.body])).toEqual([
      ["POST", "/v1/models/pocky/syringe/build", {}],
      ["POST", "/v1/models/pocky/syringe/build", { set: { "fit.clearance": 0.5, label: "x" } }],
    ]);
  });

  it("getJob and cancelJob", async () => {
    setup((request) => ({ status: 200, json: { job: { ...JOB, status: request.path.endsWith("/cancel") ? "cancelled" : "running" } } }));
    expect((await transport.getJob("j1")).status).toBe("running");
    expect((await transport.cancelJob("j1")).status).toBe("cancelled");
    expect(service.requests.map((r) => `${r.method} ${r.path}`)).toEqual(["GET /v1/jobs/j1", "POST /v1/jobs/j1/cancel"]);
  });

  it("startRun sends exactly the documented body", async () => {
    setup(() => ({ status: 202, json: { job: { ...JOB, kind: "run" } } }));
    const req = { model: "pocky/syringe", scenario: "projects/pocky/s.toml", acceptance: "projects/pocky/a.toml" };
    expect((await transport.startRun(req)).kind).toBe("run");
    await transport.startRun({ ...req, options: "projects/pocky/o.toml" });
    expect(service.requests.map((r) => [r.method, r.path, r.body])).toEqual([
      ["POST", "/v1/runs", req],
      ["POST", "/v1/runs", { ...req, options: "projects/pocky/o.toml" }],
    ]);
  });

  it("listPhysicsInputs", async () => {
    const inputs = { schemaVersion: 1, project: "pocky", model: "syringe", scenarios: [{ name: "a", path: "projects/pocky/a.toml" }], acceptance: [], options: [] };
    setup(() => ({ status: 200, json: inputs }));
    expect(await transport.listPhysicsInputs("pocky/syringe")).toEqual(inputs);
    expect(service.requests[0]).toMatchObject({ method: "GET", path: "/v1/models/pocky/syringe/physics-inputs" });
  });

  describe("errors", () => {
    it("maps a 404 with the server's error text to {status, message, body}", async () => {
      const body = { schemaVersion: 1, error: "no scene built; run `cad build pocky/syringe`" };
      setup(() => ({ status: 404, statusText: "Not Found", json: body }));
      const error = await failure(transport.getScene("pocky/syringe"));
      expect(error.status).toBe(404);
      expect(error.message).toBe(body.error);
      expect(error.body).toEqual(body);
    });

    it("falls back to the status text, then to HTTP n, when the body has no error text", async () => {
      setup(() => ({ status: 500, statusText: "Internal Server Error" }));
      const withText = await failure(transport.listModels());
      expect([withText.status, withText.message, withText.body]).toEqual([500, "Internal Server Error", undefined]);
      setup(() => ({ status: 503, statusText: "" }));
      const without = await failure(transport.listModels());
      expect([without.status, without.message, without.body]).toEqual([503, "HTTP 503", undefined]);
    });

    it("maps errors on binary and job routes the same way", async () => {
      setup(() => ({ status: 404, statusText: "Not Found", json: { error: "no such artifact" } }));
      const artifact = await failure(transport.getArtifact("a/b.glb"));
      expect([artifact.status, artifact.message, artifact.body]).toEqual([404, "no such artifact", { error: "no such artifact" }]);
      setup(() => ({ status: 409, statusText: "Conflict", json: { error: "job queued", job: "j1" } }));
      const job = await failure(transport.startBuild("pocky/syringe"));
      expect([job.status, job.message, job.body]).toEqual([409, "job queued", { error: "job queued", job: "j1" }]);
    });

    it("maps a network failure to status 0 with the same wording", async () => {
      setup(() => ({ status: 0, networkError: "fetch failed" }));
      const error = await failure(transport.health());
      expect(error.status).toBe(0);
      expect(error.message).toBe("network error: fetch failed");
      const artifact = await failure(transport.getArtifact("a/b.glb"));
      expect(artifact.status).toBe(0);
      expect(artifact.message).toBe("network error: fetch failed");
    });

    it("rejects a 200 whose body is not a JSON object", async () => {
      setup(() => ({ status: 200, json: ["not", "an", "object"] }));
      const error = await failure(transport.listModels());
      expect(error.message).toBe("response is not a JSON object");
    });

    it("rejects a job route whose answer has no job", async () => {
      setup(() => ({ status: 200, json: { nope: true } }));
      const error = await failure(transport.getJob("j1"));
      expect(error.message).toBe("response has no job");
    });

    it("never exposes the token in an error", async () => {
      setup(() => ({ status: 401, statusText: "Unauthorized", json: { error: "unauthorized" } }));
      const error = await failure(transport.listModels());
      expect(JSON.stringify([error.status, error.message, error.body])).not.toContain(TOKEN);
    });
  });

  describe("subscribe", () => {
    const collect = () => {
      const events: ServiceEvent[] = [];
      const stop = transport.subscribe((event) => events.push(event));
      cleanups.push(stop);
      return { events, stop };
    };

    it("delivers connection, job and artifact events identically", async () => {
      setup();
      const { events } = collect();
      await waitFor(() => events.some((e) => e.type === "connection"));
      service.emit("job", { job: JOB });
      service.emit("artifact", { kind: "scene", model: "pocky/syringe" });
      service.emit("artifact", { kind: "run", runId: "r1" });
      await waitFor(() => events.length === 4);
      expect(events).toEqual([
        { type: "connection", state: "open" },
        { type: "job", job: JOB },
        { type: "artifact", kind: "scene", model: "pocky/syringe" },
        { type: "artifact", kind: "run", runId: "r1" },
      ]);
    });

    it("ignores other event names and malformed payloads", async () => {
      setup();
      const { events } = collect();
      await waitFor(() => events.length === 1);
      service.emit("ping", { job: JOB });
      service.emit("message", { job: JOB });
      service.emit("job", "{not json");
      service.emit("job", { unrelated: true });
      service.emit("artifact", { kind: "other" });
      service.emit("job", { job: { ...JOB, id: "after" } });
      await waitFor(() => events.length === 2);
      await new Promise((resolve) => setTimeout(resolve, 5));
      expect(events).toEqual([
        { type: "connection", state: "open" },
        { type: "job", job: { ...JOB, id: "after" } },
      ]);
    });

    it("stops delivering and closes the stream once the last listener unsubscribes", async () => {
      setup();
      const first = collect();
      const second = collect();
      await waitFor(() => first.events.length === 1 && second.events.length === 1);
      first.stop();
      service.emit("job", { job: JOB });
      await waitFor(() => second.events.some((e) => e.type === "job"));
      expect(first.events.filter((e) => e.type === "job")).toEqual([]);
      second.stop();
      await waitFor(() => service.subscribers === 0);
      expect(service.closedStreams).toBeGreaterThanOrEqual(1);
      service.emit("job", { job: JOB });
      await new Promise((resolve) => setTimeout(resolve, 5));
      expect(second.events.filter((e) => e.type === "job")).toHaveLength(1);
    });
  });
});

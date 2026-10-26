import { afterEach, describe, expect, it, vi } from "vitest";
import { BrowserTransport, encodePath, stripToken, TOKEN_STORAGE_KEY } from "./browser";
import { TransportError, type ServiceEvent } from "./types";

interface Call {
  url: string;
  init: RequestInit;
}

function fakeFetch(
  handler: (call: Call) => { status?: number; body?: unknown; statusText?: string } | Response,
) {
  const calls: Call[] = [];
  const impl = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const call = { url: String(input), init };
    calls.push(call);
    const result = handler(call);
    if (result instanceof Response) return result;
    const status = result.status ?? 200;
    const text = result.body === undefined ? "" : JSON.stringify(result.body);
    return new Response(text, { status, statusText: result.statusText ?? "" });
  }) as typeof fetch;
  return { impl, calls };
}

function transportWith(fetchImpl: typeof fetch, token: string | null = "tok") {
  return new BrowserTransport({ baseUrl: "http://127.0.0.1:4321", token, fetch: fetchImpl });
}

const job = {
  id: "abc",
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

describe("BrowserTransport requests", () => {
  it("calls health without a token and returns the body", async () => {
    const { impl, calls } = fakeFetch(() => ({
      body: { service: "cadstudio", protocolVersion: 1, repoRoot: "/r", pid: 1 },
    }));
    const health = await transportWith(impl, null).health();
    expect(health.protocolVersion).toBe(1);
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/health");
    expect(new Headers(calls[0].init.headers).has("Authorization")).toBe(false);
  });

  it("sends the bearer token and lists models", async () => {
    const { impl, calls } = fakeFetch(() => ({ body: { projects: [], models: [] } }));
    await transportWith(impl).listModels();
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/models");
    expect(new Headers(calls[0].init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("encodes each model path segment and fetches the scene", async () => {
    const { impl, calls } = fakeFetch(() => ({
      body: { project: "p", model: "m", stale: false, error: null, job: null, artifactBase: "p/m/scene", scene: {} },
    }));
    await transportWith(impl).getScene("p/m");
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/models/p/m/scene");
  });

  it("posts an empty object to startBuild without sets", async () => {
    const { impl, calls } = fakeFetch(() => ({ status: 202, body: { job } }));
    const started = await transportWith(impl).startBuild("pocky/syringe");
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/models/pocky/syringe/build");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.body).toBe("{}");
    expect(new Headers(calls[0].init.headers).get("Content-Type")).toBe("application/json");
    expect(started.id).toBe("abc");
  });

  it("posts {set} to startBuild with sets", async () => {
    const { impl, calls } = fakeFetch(() => ({ status: 202, body: { job } }));
    await transportWith(impl).startBuild("p/m", { "a.b": 1.5, name: "x" });
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ set: { "a.b": 1.5, name: "x" } });
  });

  it("lists runs and gets a trajectory with a slashed runId encoded per segment", async () => {
    const { impl, calls } = fakeFetch((call) =>
      call.url.endsWith("/v1/runs")
        ? { body: { runs: [] } }
        : { body: { runId: "p/m/physics/s/1", stale: false, error: null, artifactBase: "x", trajectory: {} } },
    );
    const transport = transportWith(impl);
    await transport.listRuns();
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/runs");
    await transport.getTrajectory("p/m/physics/s/1");
    expect(calls[1].url).toBe("http://127.0.0.1:4321/v1/runs/p/m/physics/s/1/trajectory");
  });

  it("encodes a runId segment that needs escaping", () => {
    expect(encodePath("a b/c#d")).toBe("a%20b/c%23d");
  });

  it("posts startRun without options and with them", async () => {
    const { impl, calls } = fakeFetch(() => ({ status: 202, body: { job } }));
    const transport = transportWith(impl);
    await transport.startRun({ model: "p/m", scenario: "s.json", acceptance: "a.json" });
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/runs");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      model: "p/m",
      scenario: "s.json",
      acceptance: "a.json",
    });
    await transport.startRun({ model: "p/m", scenario: "s", acceptance: "a", options: "o" });
    expect(JSON.parse(String(calls[1].init.body)).options).toBe("o");
  });

  it("unwraps {job} for getJob and cancelJob", async () => {
    const { impl, calls } = fakeFetch(() => ({ body: { job: { ...job, status: "succeeded" } } }));
    const transport = transportWith(impl);
    expect((await transport.getJob("abc")).status).toBe("succeeded");
    expect(calls[0].url).toBe("http://127.0.0.1:4321/v1/jobs/abc");
    expect((await transport.cancelJob("abc")).status).toBe("succeeded");
    expect(calls[1].url).toBe("http://127.0.0.1:4321/v1/jobs/abc/cancel");
    expect(calls[1].init.method).toBe("POST");
  });

  it("builds artifact URLs with an encoded token", () => {
    const transport = new BrowserTransport({
      baseUrl: "http://127.0.0.1:1/",
      token: "a b&c",
      fetch: fakeFetch(() => ({})).impl,
    });
    expect(transport.artifactUrl("p/m/scene/parts/a.glb")).toBe(
      "http://127.0.0.1:1/v1/artifacts/p/m/scene/parts/a.glb?token=a%20b%26c",
    );
  });
});

describe("BrowserTransport errors", () => {
  it("throws TransportError with status and body on 401", async () => {
    const { impl } = fakeFetch(() => ({ status: 401, body: { error: "missing or invalid token" } }));
    const error = await transportWith(impl)
      .listModels()
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).status).toBe(401);
    expect((error as TransportError).message).toBe("missing or invalid token");
  });

  it("keeps extra error fields such as command", async () => {
    const { impl } = fakeFetch(() => ({
      status: 404,
      body: { error: "no scene", command: "cad gui scene p/m" },
    }));
    const error = await transportWith(impl)
      .getScene("p/m")
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).status).toBe(404);
    expect((error as TransportError).body?.command).toBe("cad gui scene p/m");
  });

  it("reports a network failure as status 0", async () => {
    const impl = (async () => {
      throw new TypeError("connection refused");
    }) as unknown as typeof fetch;
    const error = await transportWith(impl)
      .health()
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).status).toBe(0);
  });
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, Array<(event: Event) => void>>();
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void): void {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

describe("BrowserTransport.subscribe", () => {
  afterEach(() => {
    FakeEventSource.instances = [];
  });

  it("puts the token in the query and maps job and artifact frames", () => {
    const transport = new BrowserTransport({
      baseUrl: "http://127.0.0.1:4321",
      token: "t k",
      fetch: fakeFetch(() => ({})).impl,
      EventSource: FakeEventSource as unknown as typeof EventSource,
    });
    const events: ServiceEvent[] = [];
    const unsubscribe = transport.subscribe((event) => events.push(event));
    const source = FakeEventSource.instances[0];
    expect(source.url).toBe("http://127.0.0.1:4321/v1/events?token=t%20k");

    source.emit("job", { job });
    source.emit("artifact", { kind: "scene", model: "p/m" });
    source.emit("artifact", { kind: "run", runId: "p/m/r" });
    source.emit("artifact", { kind: "other" });

    expect(events).toEqual([
      { type: "job", job },
      { type: "artifact", kind: "scene", model: "p/m" },
      { type: "artifact", kind: "run", runId: "p/m/r" },
    ]);

    unsubscribe();
    expect(source.closed).toBe(true);
  });

  it("maps open and error to connection events", () => {
    const transport = new BrowserTransport({
      baseUrl: "http://127.0.0.1:4321",
      token: null,
      fetch: fakeFetch(() => ({})).impl,
      EventSource: FakeEventSource as unknown as typeof EventSource,
    });
    const states: string[] = [];
    transport.subscribe((event) => {
      if (event.type === "connection") states.push(event.state);
    });
    const source = FakeEventSource.instances[0];
    source.onopen?.();
    source.onerror?.();
    expect(states).toEqual(["open", "error"]);
  });
});

describe("BrowserTransport.fromLocation", () => {
  function fakeWindow(search: string, stored: string | null = null) {
    const store = new Map<string, string>();
    if (stored) store.set(TOKEN_STORAGE_KEY, stored);
    const replaced: Array<string | null | undefined> = [];
    const win = {
      location: {
        origin: "http://127.0.0.1:4321",
        pathname: "/",
        search,
        hash: "#top",
      },
      history: {
        state: null,
        replaceState: (_state: unknown, _title: string, url?: string | null) => {
          replaced.push(url);
        },
      },
      sessionStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => void store.set(key, value),
        removeItem: (key: string) => void store.delete(key),
        clear: () => store.clear(),
        key: () => null,
        length: store.size,
      } as Storage,
    };
    return { win, replaced, store };
  }

  it("stores the URL token, strips it and keeps other params and the hash", () => {
    const { win, replaced, store } = fakeWindow("?token=secret&model=p%2Fm");
    const transport = BrowserTransport.fromLocation(win);
    expect(transport.token).toBe("secret");
    expect(store.get(TOKEN_STORAGE_KEY)).toBe("secret");
    expect(replaced).toEqual(["/?model=p%2Fm#top"]);
  });

  it("reads the token back from sessionStorage when the URL has none", () => {
    const { win, replaced } = fakeWindow("?model=p%2Fm", "stored-token");
    const transport = BrowserTransport.fromLocation(win);
    expect(transport.token).toBe("stored-token");
    expect(replaced).toEqual([]);
  });

  it("has no token when neither the URL nor sessionStorage has one", () => {
    const { win } = fakeWindow("");
    expect(BrowserTransport.fromLocation(win).token).toBeNull();
  });
});

describe("stripToken", () => {
  it("drops only the token parameter", () => {
    expect(stripToken("?a=1&token=x&b=2")).toBe("?a=1&b=2");
    expect(stripToken("?token=x")).toBe("");
    expect(stripToken("")).toBe("");
  });
});

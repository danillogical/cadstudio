import { describe, expect, it } from "vitest";
import { FORWARDED_EVENTS, PanelBridge, RECONNECT_MS } from "./bridge";
import { TRANSPORT_METHODS } from "./protocol";
import { FakeBridgeWebview, FakeClient, FakeTimers, flush } from "./test-utils";

function setup(options: { reconnectMs?: number } = {}) {
  const webview = new FakeBridgeWebview();
  const client = new FakeClient();
  const timers = new FakeTimers();
  const bridge = new PanelBridge(webview, client, { ...options, setTimer: timers.setTimer, clearTimer: timers.clearTimer });
  return { webview, client, timers, bridge };
}

const req = (id: number, method: string, args: unknown[]) => ({ kind: "request", id, method, args });

describe("PanelBridge: validation gate", () => {
  const REJECTED: unknown[] = [
    null,
    "health",
    [],
    {},
    { kind: "request" },
    req(1, "nope", []),
    req(1, "health", ["x"]),
    req(1, "getArtifact", ["../../etc/passwd"]),
    req(1, "getArtifact", ["/etc/passwd"]),
    req(1, "getArtifact", ["a\\b"]),
    req(1, "getArtifact", ["a\u0000b"]),
    req(1, "getTrajectory", ["a//b"]),
    req(1, "getScene", ["only-one"]),
    req(1, "getScene", ["a/b/c"]),
    req(1, "getJob", ["../jobs"]),
    req(1, "startBuild", ["p/m", { a: Number.NaN }]),
    req(1, "startRun", [{ model: "p/m", scenario: "s", acceptance: "a", extra: 1 }]),
    { ...req(1, "health", []), url: "http://evil" },
    { kind: "subscribe", extra: true },
  ];

  it.each(REJECTED.map((m, i) => [i, m] as const))("never forwards rejected message #%i", async (_i, message) => {
    const { bridge, client, webview } = setup();
    await bridge.handle(message);
    await flush();
    expect(client.requests).toEqual([]);
    expect(client.openCalls).toEqual([]);
    expect(bridge.pendingRequests).toBe(0);
    expect(bridge.isSubscribed).toBe(false);
    // Anything posted is a failed response for a usable id, never a result.
    for (const posted of webview.posted) expect(posted).toMatchObject({ kind: "response", ok: false });
  });

  it("answers a rejected request that has a usable id with a 400, and drops one without", async () => {
    const { bridge, webview } = setup();
    await bridge.handle(req(5, "getArtifact", ["../x"]));
    await bridge.handle({ kind: "request", method: "health", args: [] });
    await bridge.handle("garbage");
    expect(webview.posted).toHaveLength(1);
    expect(webview.posted[0]).toMatchObject({ kind: "response", id: 5, ok: false, error: { status: 400 } });
  });

  it("receives messages through the webview listener", async () => {
    const { webview, client } = setup();
    webview.receive(req(2, "health", []));
    await flush();
    expect(client.requests).toHaveLength(1);
    webview.receive(req(3, "getArtifact", ["../x"]));
    await flush();
    expect(client.requests).toHaveLength(1);
  });

  it("forwards each valid method as exactly one route", async () => {
    const { bridge, client } = setup();
    const calls: Array<[string, unknown[]]> = [
      ["health", []],
      ["listModels", []],
      ["getScene", ["p/m"]],
      ["startBuild", ["p/m", { a: 1 }]],
      ["listPhysicsInputs", ["p/m"]],
      ["listRuns", []],
      ["getTrajectory", ["r1"]],
      ["startRun", [{ model: "p/m", scenario: "s.toml", acceptance: "a.toml" }]],
      ["getJob", ["j"]],
      ["cancelJob", ["j"]],
      ["getArtifact", ["p/m/scene/scene.glb"]],
    ];
    expect(calls.map(([m]) => m).sort()).toEqual([...TRANSPORT_METHODS].sort());
    let id = 1;
    for (const [method, args] of calls) await bridge.handle(req(id++, method, args));
    expect(client.requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      "GET /v1/health",
      "GET /v1/models",
      "GET /v1/models/p/m/scene",
      "POST /v1/models/p/m/build",
      "GET /v1/models/p/m/physics-inputs",
      "GET /v1/runs",
      "GET /v1/runs/r1/trajectory",
      "POST /v1/runs",
      "GET /v1/jobs/j",
      "POST /v1/jobs/j/cancel",
      "GET /v1/artifacts/p/m/scene/scene.glb",
    ]);
  });
});

describe("PanelBridge: replies", () => {
  it("carries the request id on success and failure", async () => {
    const { bridge, client, webview } = setup();
    client.reply = async (route) =>
      route.path === "/v1/models"
        ? { ok: true, result: { models: [] } }
        : { ok: false, error: { status: 404, message: "nope", body: { error: "nope" } } };
    await bridge.handle(req(41, "listModels", []));
    await bridge.handle(req(42, "listRuns", []));
    expect(webview.posted).toEqual([
      { kind: "response", id: 41, ok: true, result: { models: [] } },
      { kind: "response", id: 42, ok: false, error: { status: 404, message: "nope", body: { error: "nope" } } },
    ]);
  });

  it("matches concurrent replies to their own ids when they finish out of order", async () => {
    const { bridge, client, webview } = setup();
    const resolvers: Record<string, (value: { ok: true; result: unknown }) => void> = {};
    client.reply = (route) => new Promise((resolve) => (resolvers[route.path] = resolve as never));
    const a = bridge.handle(req(1, "listModels", []));
    const b = bridge.handle(req(2, "listRuns", []));
    expect(bridge.pendingRequests).toBe(2);
    resolvers["/v1/runs"]({ ok: true, result: { which: "runs" } });
    resolvers["/v1/models"]({ ok: true, result: { which: "models" } });
    await Promise.all([a, b]);
    expect(webview.posted).toEqual([
      { kind: "response", id: 2, ok: true, result: { which: "runs" } },
      { kind: "response", id: 1, ok: true, result: { which: "models" } },
    ]);
    expect(bridge.pendingRequests).toBe(0);
  });

  it("survives a webview whose postMessage rejects", async () => {
    const { bridge, webview } = setup();
    webview.postMessage = () => Promise.reject(new Error("panel gone"));
    await expect(bridge.handle(req(1, "health", []))).resolves.toBeUndefined();
    await flush();
  });
});

describe("PanelBridge: dispose", () => {
  it("aborts in-flight requests, posts nothing afterwards and stops listening", async () => {
    const { bridge, client, webview } = setup();
    client.reply = (_route, signal) =>
      new Promise((resolve) => signal.addEventListener("abort", () => resolve({ ok: true, result: { late: true } })));
    const pending = bridge.handle(req(1, "health", []));
    expect(bridge.pendingRequests).toBe(1);
    bridge.dispose();
    await pending;
    expect(client.signals[0].aborted).toBe(true);
    expect(bridge.pendingRequests).toBe(0);
    expect(webview.posted).toEqual([]);
    expect(webview.listenerDisposed).toBe(true);
    expect(webview.listenerCount).toBe(0);
  });

  it("ignores messages after dispose", async () => {
    const { bridge, client } = setup();
    bridge.dispose();
    await bridge.handle(req(1, "health", []));
    await bridge.handle({ kind: "subscribe" });
    expect(client.requests).toEqual([]);
    expect(client.openCalls).toEqual([]);
  });

  it("closes the event stream, clears a reconnect timer, and is idempotent", async () => {
    const { bridge, client, timers } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    expect(client.streams).toHaveLength(1);
    bridge.dispose();
    bridge.dispose();
    expect(client.streams[0].closed).toBe(true);
    expect(bridge.isSubscribed).toBe(false);

    const second = setup();
    second.client.openError = new Error("down");
    await second.bridge.handle({ kind: "subscribe" });
    await flush();
    expect(second.timers.pending.size).toBe(1);
    second.bridge.dispose();
    expect(second.timers.pending.size).toBe(0);
    expect(timers.pending.size).toBe(0);
  });

  it("does not post a late stream event after dispose", async () => {
    const { bridge, client, webview } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    const handlers = client.streams[0].handlers;
    bridge.dispose();
    handlers.onEvent({ event: "job", data: '{"job":{}}' });
    handlers.onClose({ message: "x" });
    expect(webview.posted).toEqual([]);
  });

  it("closes a stream that finishes opening after dispose", async () => {
    const { bridge, client } = setup();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const original = client.openEvents.bind(client);
    client.openEvents = async (handlers, options) => {
      await gate;
      return original(handlers, options);
    };
    await bridge.handle({ kind: "subscribe" });
    bridge.dispose();
    release();
    await flush();
    expect(client.streams).toHaveLength(1);
    expect(client.streams[0].closed).toBe(true);
  });
});

describe("PanelBridge: event stream", () => {
  it("forwards only job and artifact events, parsed", async () => {
    const { bridge, client, webview } = setup();
    expect([...FORWARDED_EVENTS]).toEqual(["job", "artifact"]);
    await bridge.handle({ kind: "subscribe" });
    await flush();
    const { handlers } = client.streams[0];
    handlers.onOpen();
    handlers.onEvent({ event: "job", data: '{"job":{"id":"j"}}' });
    handlers.onEvent({ event: "artifact", data: '{"kind":"scene","model":"p/m"}' });
    handlers.onEvent({ event: "message", data: '{"job":{}}' });
    handlers.onEvent({ event: "ping", data: "{}" });
    handlers.onEvent({ event: "constructor", data: "{}" });
    handlers.onEvent({ event: "", data: "{}" });
    handlers.onEvent({ event: "job", data: "{not json" });
    expect(webview.posted).toEqual([
      { kind: "connection", state: "open" },
      { kind: "event", event: "job", data: { job: { id: "j" } } },
      { kind: "event", event: "artifact", data: { kind: "scene", model: "p/m" } },
    ]);
  });

  it("subscribe opens one stream, starting the service on the first attempt", async () => {
    const { bridge, client } = setup();
    await bridge.handle({ kind: "subscribe" });
    await bridge.handle({ kind: "subscribe" });
    await flush();
    expect(client.openCalls).toEqual([{ startService: true }]);
    expect(bridge.isSubscribed).toBe(true);
  });

  it("unsubscribe closes the stream and stops forwarding", async () => {
    const { bridge, client, webview } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    const { handlers } = client.streams[0];
    await bridge.handle({ kind: "unsubscribe" });
    expect(client.streams[0].closed).toBe(true);
    expect(bridge.isSubscribed).toBe(false);
    handlers.onEvent({ event: "job", data: '{"job":{}}' });
    handlers.onOpen();
    expect(webview.posted).toEqual([]);
  });

  it("unsubscribe without a subscription is harmless", async () => {
    const { bridge, client } = setup();
    await bridge.handle({ kind: "unsubscribe" });
    expect(client.openCalls).toEqual([]);
  });

  it("closes a stream that opens after an unsubscribe", async () => {
    const { bridge, client } = setup();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const original = client.openEvents.bind(client);
    client.openEvents = async (handlers, options) => {
      await gate;
      return original(handlers, options);
    };
    await bridge.handle({ kind: "subscribe" });
    await bridge.handle({ kind: "unsubscribe" });
    release();
    await flush();
    expect(client.streams[0].closed).toBe(true);
  });

  it("reconnects through the timer after a stream error, without restarting the service", async () => {
    const { bridge, client, timers, webview } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    client.streams[0].handlers.onClose({ message: "event stream ended" });
    expect(webview.posted).toEqual([{ kind: "connection", state: "error" }]);
    expect(timers.pending.size).toBe(1);
    expect([...timers.pending.values()][0].ms).toBe(RECONNECT_MS);
    expect(client.openCalls).toHaveLength(1); // nothing reconnects before the timer fires

    timers.fireAll();
    await flush();
    expect(client.openCalls).toEqual([{ startService: true }, { startService: false }]);

    client.streams[1].handlers.onClose({ message: "again" });
    timers.fireAll();
    await flush();
    expect(client.openCalls.map((c) => c.startService)).toEqual([true, false, false]);
  });

  it("uses the configured reconnect delay", async () => {
    const { bridge, client, timers } = setup({ reconnectMs: 123 });
    await bridge.handle({ kind: "subscribe" });
    await flush();
    client.streams[0].handlers.onClose({ message: "x" });
    expect([...timers.pending.values()][0].ms).toBe(123);
  });

  it("retries through the timer when opening the stream fails, still without a restart", async () => {
    const { bridge, client, timers, webview } = setup();
    client.openError = new Error("no service");
    await bridge.handle({ kind: "subscribe" });
    await flush();
    expect(webview.posted).toEqual([{ kind: "connection", state: "error" }]);
    expect(timers.pending.size).toBe(1);
    timers.fireAll();
    await flush();
    expect(client.openCalls.map((c) => c.startService)).toEqual([true, false]);
    expect(timers.pending.size).toBe(1); // keeps trying, once per timer tick
  });

  it("schedules a single reconnect timer even if close is reported twice", async () => {
    const { bridge, client, timers } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    const { handlers } = client.streams[0];
    handlers.onClose({ message: "a" });
    handlers.onClose({ message: "b" });
    expect(timers.pending.size).toBe(1);
  });

  it("unsubscribing cancels a pending reconnect", async () => {
    const { bridge, client, timers } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    client.streams[0].handlers.onClose({ message: "x" });
    await bridge.handle({ kind: "unsubscribe" });
    expect(timers.pending.size).toBe(0);
    timers.fireAll();
    await flush();
    expect(client.openCalls).toHaveLength(1);
  });

  it("a timer that fires after unsubscribe does not reconnect", async () => {
    const { bridge, client, timers } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    client.streams[0].handlers.onClose({ message: "x" });
    const stale = [...timers.pending.values()][0].callback;
    await bridge.handle({ kind: "unsubscribe" });
    stale();
    await flush();
    expect(client.openCalls).toHaveLength(1);
  });

  it("an old stream's close after resubscribing does not disturb the new subscription", async () => {
    const { bridge, client, timers, webview } = setup();
    await bridge.handle({ kind: "subscribe" });
    await flush();
    const old = client.streams[0];
    await bridge.handle({ kind: "unsubscribe" });
    await bridge.handle({ kind: "subscribe" });
    await flush();
    expect(client.streams).toHaveLength(2);
    old.handlers.onClose({ message: "late" });
    expect(timers.pending.size).toBe(0);
    expect(client.streams[1].closed).toBe(false);
    expect(webview.posted).toEqual([]);
  });
});

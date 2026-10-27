import { describe, expect, it, vi } from "vitest";
import { HttpServiceClient, PanelBridge, type HttpIo } from "./bridge";
import { handleOpenRequest, NOT_THIS_WINDOW, READY_TIMEOUT_MS, type OpenRequestDeps } from "./open";
import {
  navigateMessage,
  OPEN_REQUEST_ID,
  openAckRoute,
  openClaimRoute,
  openNackRoute,
  parseNavigateTarget,
  parseWebviewMessage,
  type HttpRoute,
  type NavigateTarget,
  type Reply,
} from "./protocol";
import { FakeBridgeWebview, FakeClient, fakeLocator, flush, record } from "./test-utils";

const ID = "req_ABCDEFGHIJKLMNOPQRSTUV-1";
const ROOT = "/work/cadstudio";

interface Harness {
  deps: OpenRequestDeps;
  log: string[];
  routes: HttpRoute[];
  warnings: string[];
  navigated: Array<NavigateTarget | null>;
}

/** Fake window + service. `claim` is the body of the claim reply; the log records call order. */
function harness(
  options: {
    claim?: Reply | null;
    workspaceRoot?: string | null;
    trusted?: boolean;
    openPanel?: boolean;
    navigate?: (target: NavigateTarget | null) => Promise<boolean>;
    ack?: Reply | null;
    sleep?: (ms: number) => Promise<void>;
  } = {},
): Harness {
  const log: string[] = [];
  const routes: HttpRoute[] = [];
  const warnings: string[] = [];
  const navigated: Array<NavigateTarget | null> = [];
  const claim: Reply | null =
    options.claim === undefined
      ? { ok: true, result: { id: ID, target: { model: "pocky/syringe" }, repoRoot: ROOT } }
      : options.claim;
  const deps: OpenRequestDeps = {
    workspaceRoot: options.workspaceRoot === undefined ? ROOT : options.workspaceRoot,
    trusted: options.trusted ?? true,
    request: async (route) => {
      routes.push(route);
      if (route.method === "GET") {
        log.push("claim");
        return claim;
      }
      log.push(route.path.endsWith("/ack") ? "ack" : "nack");
      if (route.path.endsWith("/ack")) return options.ack === undefined ? { ok: true, result: {} } : options.ack;
      return { ok: true, result: {} };
    },
    openPanel: () => {
      log.push("openPanel");
      return options.openPanel ?? true;
    },
    navigate: async (target) => {
      log.push("navigate");
      navigated.push(target);
      return options.navigate ? options.navigate(target) : true;
    },
    warn: (message) => warnings.push(message),
    sleep: options.sleep ?? (() => new Promise<void>(() => {})),
  };
  return { deps, log, routes, warnings, navigated };
}

const nackBody = (h: Harness) => (h.routes.find((r) => r.path.endsWith("/nack"))?.body as { reason: string }).reason;

describe("handleOpenRequest: success", () => {
  it("acks only after the panel exists and navigate was posted", async () => {
    const h = harness();
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome).toEqual({ status: "acked", target: { model: "pocky/syringe" } });
    expect(h.log).toEqual(["claim", "openPanel", "navigate", "ack"]);
    expect(h.navigated).toEqual([{ model: "pocky/syringe" }]);
    expect(h.routes[0]).toEqual(openClaimRoute(ID));
    expect(h.routes[1]).toEqual(openAckRoute(ID));
    expect(h.warnings).toEqual([]);
  });

  it("does not ack while navigate is still pending", async () => {
    let finish!: (posted: boolean) => void;
    const h = harness({ navigate: () => new Promise<boolean>((resolve) => (finish = resolve)) });
    const done = handleOpenRequest(ID, h.deps);
    await flush();
    expect(h.log).toEqual(["claim", "openPanel", "navigate"]);
    finish(true);
    await done;
    expect(h.log).toEqual(["claim", "openPanel", "navigate", "ack"]);
  });

  it("handles a run target and a null target", async () => {
    const run = harness({ claim: { ok: true, result: { id: ID, target: { run: "mj/r1" }, repoRoot: ROOT } } });
    expect(await handleOpenRequest(ID, run.deps)).toEqual({ status: "acked", target: { run: "mj/r1" } });
    expect(run.navigated).toEqual([{ run: "mj/r1" }]);
    const bare = harness({ claim: { ok: true, result: { id: ID, target: null, repoRoot: ROOT } } });
    expect(await handleOpenRequest(ID, bare.deps)).toEqual({ status: "acked", target: null });
    expect(bare.log).toEqual(["claim", "openPanel", "navigate", "ack"]);
  });

  it("reports ack-failed (and warns) when the service refuses the ack", async () => {
    const h = harness({ ack: { ok: false, error: { status: 409, message: "open request is nacked" } } });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome).toMatchObject({ status: "ack-failed", reason: "open request is nacked" });
    expect(h.warnings).toHaveLength(1);
    const gone = harness({ ack: null });
    expect(await handleOpenRequest(ID, gone.deps)).toMatchObject({ status: "ack-failed" });
  });
});

describe("handleOpenRequest: refusals nack with a specific reason", () => {
  it("nacks a repo-root mismatch, naming both folders, before opening anything", async () => {
    const h = harness({ workspaceRoot: "/work/other" });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome.status).toBe("nacked");
    expect(h.log).toEqual(["claim", "nack"]);
    expect(nackBody(h)).toContain(ROOT);
    expect(nackBody(h)).toContain("/work/other");
    expect(h.routes[1]).toEqual(openNackRoute(ID, nackBody(h)));
    expect(h.warnings).toHaveLength(1);
  });

  it("compares the roots exactly, not by prefix", async () => {
    for (const workspaceRoot of ["/work/cadstudio2", "/work", "/work/cadstudio/sub", "/work/cadstudio/"]) {
      const h = harness({ workspaceRoot });
      expect((await handleOpenRequest(ID, h.deps)).status).toBe("nacked");
      expect(h.log).toEqual(["claim", "nack"]);
    }
  });

  it("nacks an untrusted workspace without opening the panel", async () => {
    const h = harness({ trusted: false });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome).toMatchObject({ status: "nacked" });
    expect(nackBody(h)).toMatch(/not trusted/);
    expect(h.log).toEqual(["claim", "nack"]);
  });

  it("nacks when the panel cannot be opened, and never navigates or acks", async () => {
    const h = harness({ openPanel: false });
    expect((await handleOpenRequest(ID, h.deps)).status).toBe("nacked");
    expect(h.log).toEqual(["claim", "openPanel", "nack"]);
    expect(nackBody(h)).toMatch(/panel could not be opened/);
  });

  it("nacks when navigate reports it could not post", async () => {
    const h = harness({ navigate: async () => false });
    expect((await handleOpenRequest(ID, h.deps)).status).toBe("nacked");
    expect(h.log).toEqual(["claim", "openPanel", "navigate", "nack"]);
    expect(nackBody(h)).toMatch(/did not become ready/);
  });

  it("nacks when the page never becomes ready within the timeout", async () => {
    const sleeps: number[] = [];
    const h = harness({
      navigate: () => new Promise<boolean>(() => {}),
      sleep: async (ms) => void sleeps.push(ms),
    });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome.status).toBe("nacked");
    expect(sleeps).toEqual([READY_TIMEOUT_MS]);
    expect(READY_TIMEOUT_MS).toBeLessThan(10_000); // under the CLI's 10 s ack wait
    expect(h.log).toEqual(["claim", "openPanel", "navigate", "nack"]);
    expect(nackBody(h)).toMatch(/did not become ready within 8 s/);
  });

  it("honours readyTimeoutMs", async () => {
    const sleeps: number[] = [];
    const h = harness({ navigate: () => new Promise<boolean>(() => {}), sleep: async (ms) => void sleeps.push(ms) });
    await handleOpenRequest(ID, { ...h.deps, readyTimeoutMs: 1234 });
    expect(sleeps).toEqual([1234]);
  });

  it.each([
    ["no repoRoot", { id: ID, target: null }],
    ["non-string repoRoot", { id: ID, target: null, repoRoot: 5 }],
    ["missing target", { id: ID, repoRoot: ROOT }],
    ["target with two keys", { id: ID, target: { model: "p/m", run: "r" }, repoRoot: ROOT }],
    ["bad model spec", { id: ID, target: { model: "../x" }, repoRoot: ROOT }],
    ["traversal run", { id: ID, target: { run: "../x" }, repoRoot: ROOT }],
    ["absolute run", { id: ID, target: { run: "/etc" }, repoRoot: ROOT }],
    ["unknown target key", { id: ID, target: { path: "x" }, repoRoot: ROOT }],
    ["not an object", "oops"],
  ])("nacks a malformed claim (%s) and opens nothing", async (_name, result) => {
    const h = harness({ claim: { ok: true, result } });
    expect((await handleOpenRequest(ID, h.deps)).status).toBe("nacked");
    expect(h.log).toEqual(["claim", "nack"]);
    expect(nackBody(h)).toMatch(/malformed/);
  });
});

describe("handleOpenRequest: unavailable (nothing to nack)", () => {
  it("is unavailable without a workspace folder and sends no request at all", async () => {
    const h = harness({ workspaceRoot: null });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome).toMatchObject({ status: "unavailable" });
    expect(h.routes).toEqual([]);
    expect(h.log).toEqual([]);
    expect(h.warnings).toEqual([NOT_THIS_WINDOW]);
  });

  it("is unavailable when no service is registered for the folder, and neither opens nor nacks", async () => {
    const h = harness({ claim: null });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome).toMatchObject({ status: "unavailable" });
    expect(h.log).toEqual(["claim"]);
    expect(h.warnings).toEqual([NOT_THIS_WINDOW]);
  });

  it.each([404, 410, 401, 0])("is unavailable when the claim answers %i", async (status) => {
    const h = harness({ claim: { ok: false, error: { status, message: "nope" } } });
    const outcome = await handleOpenRequest(ID, h.deps);
    expect(outcome.status).toBe("unavailable");
    expect(h.log).toEqual(["claim"]);
  });
});

describe("protocol helpers for open requests", () => {
  it("builds the claim, ack and nack routes with the id percent-encoded", () => {
    expect(openClaimRoute(ID)).toEqual({ method: "GET", path: `/v1/open/${ID}`, binary: false });
    expect(openAckRoute(ID)).toMatchObject({ method: "POST", path: `/v1/open/${ID}/ack`, body: {} });
    expect(openNackRoute(ID, "why")).toMatchObject({ method: "POST", path: `/v1/open/${ID}/nack`, body: { reason: "why" } });
    expect(openClaimRoute("a/b").path).toBe("/v1/open/a%2Fb");
  });

  it("OPEN_REQUEST_ID matches the service's id rule", () => {
    expect(OPEN_REQUEST_ID.test("A".repeat(16))).toBe(true);
    expect(OPEN_REQUEST_ID.test("A".repeat(128))).toBe(true);
    expect(OPEN_REQUEST_ID.test("A".repeat(15))).toBe(false);
    expect(OPEN_REQUEST_ID.test("A".repeat(129))).toBe(false);
    expect(OPEN_REQUEST_ID.test("A".repeat(15) + ".")).toBe(false);
    expect(OPEN_REQUEST_ID.test("A".repeat(15) + "\n")).toBe(false);
  });

  it("parseNavigateTarget accepts null, {model} and {run} only", () => {
    expect(parseNavigateTarget(null)).toBeNull();
    expect(parseNavigateTarget({ model: "pocky/syringe" })).toEqual({ model: "pocky/syringe" });
    expect(parseNavigateTarget({ run: "mj/r1" })).toEqual({ run: "mj/r1" });
    for (const bad of [undefined, 5, "x", [], {}, { model: "a" }, { model: "a/b/c" }, { run: "a/../b" }, { run: "" },
      { model: "a/b", run: "r" }, { model: "a/b", extra: 1 }, { other: "x" }]) {
      expect(parseNavigateTarget(bad)).toBeUndefined();
    }
  });

  it("navigateMessage has exactly the kind and one target key", () => {
    expect(navigateMessage({ model: "p/m" })).toEqual({ kind: "navigate", model: "p/m" });
    expect(navigateMessage({ run: "r" })).toEqual({ kind: "navigate", run: "r" });
  });

  it("parseWebviewMessage accepts a bare ready and rejects ready with fields", () => {
    expect(parseWebviewMessage({ kind: "ready" })).toEqual({ ok: true, message: { kind: "ready" } });
    expect(parseWebviewMessage({ kind: "ready", extra: 1 })).toMatchObject({ ok: false });
    expect(parseWebviewMessage({ kind: "navigate", model: "p/m" })).toMatchObject({ ok: false });
  });
});

describe("PanelBridge ready", () => {
  it("calls onReady for a ready message and forwards nothing to the service", async () => {
    const webview = new FakeBridgeWebview();
    const client = new FakeClient();
    const onReady = vi.fn();
    new PanelBridge(webview, client, { onReady });
    webview.receive({ kind: "ready" });
    webview.receive({ kind: "ready", extra: true });
    await flush();
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(client.requests).toEqual([]);
    expect(client.openCalls).toEqual([]);
  });
});

describe("HttpServiceClient.requestRegistered", () => {
  const route: HttpRoute = { method: "GET", path: `/v1/open/${ID}`, binary: false };

  it("returns null when no service is registered, without starting one", async () => {
    const { locator, state } = fakeLocator([]);
    state.find.mockImplementation(async () => null as never);
    const request = vi.fn();
    const io = { request, openEventStream: vi.fn() } as unknown as HttpIo;
    const client = new HttpServiceClient(locator, io);
    expect(await client.requestRegistered(route)).toBeNull();
    expect(request).not.toHaveBeenCalled();
    expect(state.get).not.toHaveBeenCalled(); // `get` is the locator call that may start a service
  });

  it("sends the route to the registered service using find, never get", async () => {
    const { locator, state } = fakeLocator([record()]);
    const request = vi.fn(async () => ({ status: 200, statusText: "OK", bytes: new TextEncoder().encode('{"ok":1}') }));
    const io = { request, openEventStream: vi.fn() } as unknown as HttpIo;
    const client = new HttpServiceClient(locator, io);
    const reply = await client.requestRegistered(route);
    expect(reply).toEqual({ ok: true, result: { ok: 1 } });
    expect(request).toHaveBeenCalledTimes(1);
    expect(state.find).toHaveBeenCalled();
    expect(state.get).not.toHaveBeenCalled();
  });
});

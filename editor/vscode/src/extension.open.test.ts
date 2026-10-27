/** `cad gui open` through the real URI handler and `GuiPanels`, with the fake vscode API. */
import { mkdtempSync, realpathSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionContext } from "vscode";
import type { WorkspaceFolder } from "vscode";
import { activate, BAD_REQUEST_MESSAGE, COMMAND_ID, UNTRUSTED_MESSAGE } from "./extension";
import * as fake from "./__mocks__/vscode";
import type { HttpRoute, Reply } from "./protocol";
import { FakeClient, flush } from "./test-utils";

const ID = "reqABCDEFGHIJKLMNOP-_1234";
const ROOT = "/work/cadstudio";
const INDEX_HTML = `<!doctype html><html><head>
<script type="module" crossorigin src="./assets/index-abc.js"></script></head><body><div id="app"></div></body></html>`;

class RegisteredClient extends FakeClient {
  registered: HttpRoute[] = [];
  /** What the service answers; null means no service is registered. */
  registeredReply: (route: HttpRoute) => Reply | null = (route) =>
    route.method === "GET"
      ? { ok: true, result: { id: ID, target: { model: "pocky/syringe" }, repoRoot: ROOT } }
      : { ok: true, result: {} };
  onRegistered: (route: HttpRoute) => void = () => {};

  async requestRegistered(route: HttpRoute): Promise<Reply | null> {
    this.registered.push(route);
    this.onRegistered(route);
    return this.registeredReply(route);
  }
}

function setup() {
  const client = new RegisteredClient();
  const createClient = vi.fn(() => client);
  const context = {
    extensionUri: fake.makeUri("/ext"),
    extension: { packageJSON: { version: "0.0.1" } },
    subscriptions: [],
  } as unknown as ExtensionContext;
  activate(context, { readIndexHtml: () => INDEX_HTML, createClient });
  return { client, createClient };
}

const uri = (query: string) => fake.makeUri("/open", query);
const handle = (query: string) => fake.uriHandlers[0].handleUri(uri(query)) as Promise<void> | undefined;
const navigates = () => fake.createdPanels.flatMap((p) => p.webview.posted).filter((m) => (m as { kind: string }).kind === "navigate");
const paths = (client: RegisteredClient) => client.registered.map((r) => `${r.method} ${r.path}`);

beforeEach(() => fake.reset());
afterEach(() => {
  for (const panel of fake.createdPanels) panel.dispose();
  fake.reset();
});

describe("URI without req", () => {
  it("keeps the old behaviour: runs the open command with the query and talks to no service", async () => {
    const { client } = setup();
    const result = handle("x=1");
    expect(result).toBeUndefined();
    await flush();
    expect(fake.commands.executeCommand).toHaveBeenCalledWith(COMMAND_ID, "x=1");
    expect(fake.createdPanels).toHaveLength(1);
    expect(client.registered).toEqual([]);
    expect(client.requests).toEqual([]);
    expect(navigates()).toEqual([]);
  });
});

describe("malformed req", () => {
  it.each([["req=short"], [`req=${ID}&req=${ID}`], ["req="], [`req=${ID}%2F`]])(
    "warns and does nothing for %s",
    async (query) => {
      const { client, createClient } = setup();
      expect(handle(query)).toBeUndefined();
      await flush();
      expect(fake.window.showWarningMessage).toHaveBeenCalledWith(BAD_REQUEST_MESSAGE);
      expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
      expect(fake.commands.executeCommand).not.toHaveBeenCalled();
      expect(createClient).not.toHaveBeenCalled();
      expect(client.registered).toEqual([]);
    },
  );
});

describe("navigate delivery", () => {
  it("queues navigate until the page says ready, delivers it once, then acks", async () => {
    const { client } = setup();
    let navigatesAtAck = -1;
    client.onRegistered = (route) => {
      if (route.path.endsWith("/ack")) navigatesAtAck = navigates().length;
    };
    const done = handle(`req=${ID}`)!;
    await flush();
    const panel = fake.createdPanels[0];
    expect(panel).toBeDefined();
    expect(navigates()).toEqual([]);
    expect(paths(client)).toEqual([`GET /v1/open/${ID}`]);

    panel.webview.receive({ kind: "ready" });
    await done;
    expect(navigates()).toEqual([{ kind: "navigate", model: "pocky/syringe" }]);
    expect(paths(client)).toEqual([`GET /v1/open/${ID}`, `POST /v1/open/${ID}/ack`]);
    expect(navigatesAtAck).toBe(1); // posted before the ack went out

    panel.webview.receive({ kind: "ready" }); // a repeated ready does not redeliver
    await flush();
    expect(navigates()).toHaveLength(1);
  });

  it("delivers a run target", async () => {
    const { client } = setup();
    client.registeredReply = (route) =>
      route.method === "GET" ? { ok: true, result: { id: ID, target: { run: "mj/r1" }, repoRoot: ROOT } } : { ok: true, result: {} };
    const done = handle(`req=${ID}`)!;
    await flush();
    fake.createdPanels[0].webview.receive({ kind: "ready" });
    await done;
    expect(navigates()).toEqual([{ kind: "navigate", run: "mj/r1" }]);
  });

  it("a second URI while the panel exists reveals and navigates without a second panel", async () => {
    const { client } = setup();
    const first = handle(`req=${ID}`)!;
    await flush();
    const panel = fake.createdPanels[0];
    panel.webview.receive({ kind: "ready" });
    await first;

    const ID2 = "second_request_ABCDEFGHIJ";
    client.registeredReply = (route) =>
      route.method === "GET"
        ? { ok: true, result: { id: ID2, target: { run: "mj/r2" }, repoRoot: ROOT } }
        : { ok: true, result: {} };
    await handle(`req=${ID2}`);
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
    expect(panel.reveal).toHaveBeenCalledTimes(1);
    expect(navigates()).toEqual([
      { kind: "navigate", model: "pocky/syringe" },
      { kind: "navigate", run: "mj/r2" },
    ]);
    expect(paths(client).slice(-2)).toEqual([`GET /v1/open/${ID2}`, `POST /v1/open/${ID2}/ack`]);
  });

  it("a newer navigation replaces one still waiting for ready; only the newer is delivered", async () => {
    const { client } = setup();
    const first = handle(`req=${ID}`)!;
    await flush();
    const ID2 = "second_request_ABCDEFGHIJ";
    client.registeredReply = (route) =>
      route.method === "GET"
        ? { ok: true, result: { id: ID2, target: { run: "mj/r2" }, repoRoot: ROOT } }
        : { ok: true, result: {} };
    const second = handle(`req=${ID2}`)!;
    await flush();
    fake.createdPanels[0].webview.receive({ kind: "ready" });
    await Promise.all([first, second]);
    expect(navigates()).toEqual([{ kind: "navigate", run: "mj/r2" }]);
    expect(paths(client)).toContain(`POST /v1/open/${ID}/nack`);
    expect(paths(client)).toContain(`POST /v1/open/${ID2}/ack`);
    expect(paths(client)).not.toContain(`POST /v1/open/${ID}/ack`);
  });

  it("closing the panel before ready nacks and never posts or acks", async () => {
    const { client } = setup();
    const done = handle(`req=${ID}`)!;
    await flush();
    fake.createdPanels[0].dispose();
    await done;
    expect(navigates()).toEqual([]);
    expect(paths(client)).toEqual([`GET /v1/open/${ID}`, `POST /v1/open/${ID}/nack`]);
  });

  it("after a panel is closed and reopened, navigate waits for the new page's ready", async () => {
    const { client } = setup();
    const first = handle(`req=${ID}`)!;
    await flush();
    fake.createdPanels[0].webview.receive({ kind: "ready" });
    await first;
    fake.createdPanels[0].dispose();

    const done = handle(`req=${ID}`)!;
    await flush();
    expect(fake.createdPanels).toHaveLength(2);
    expect(navigates()).toHaveLength(1); // nothing yet for the fresh page
    fake.createdPanels[1].webview.receive({ kind: "ready" });
    await done;
    expect(navigates()).toHaveLength(2);
    expect(client.registered.filter((r) => r.path.endsWith("/ack"))).toHaveLength(2);
  });
});

describe("refusals through the URI handler", () => {
  it("nacks a repo-root mismatch and opens no panel", async () => {
    const { client } = setup();
    client.registeredReply = (route) =>
      route.method === "GET" ? { ok: true, result: { id: ID, target: null, repoRoot: "/elsewhere/cadstudio" } } : { ok: true, result: {} };
    await handle(`req=${ID}`);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    const nack = client.registered.find((r) => r.path.endsWith("/nack"))!;
    expect((nack.body as { reason: string }).reason).toContain("/elsewhere/cadstudio");
    expect(navigates()).toEqual([]);
  });

  it("nacks an untrusted workspace after claiming, with no panel", async () => {
    const { client } = setup();
    fake.workspace.isTrusted = false;
    await handle(`req=${ID}`);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(paths(client)).toEqual([`GET /v1/open/${ID}`, `POST /v1/open/${ID}/nack`]);
    expect(((client.registered[1].body as { reason: string }).reason)).toMatch(/not trusted/);
    expect(fake.window.showErrorMessage).not.toHaveBeenCalledWith(UNTRUSTED_MESSAGE);
  });

  it("a window with no folder sends nothing and warns", async () => {
    const { client } = setup();
    fake.workspace.workspaceFolders = undefined;
    await handle(`req=${ID}`);
    expect(client.registered).toEqual([]);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(fake.window.showWarningMessage).toHaveBeenCalled();
  });

  it("with no registered service it warns and never starts one, opens a panel, or nacks", async () => {
    const { client } = setup();
    client.registeredReply = () => null;
    await handle(`req=${ID}`);
    expect(paths(client)).toEqual([`GET /v1/open/${ID}`]);
    expect(client.requests).toEqual([]); // the starting `request` path is never used
    expect(client.openCalls).toEqual([]);
    expect(fake.tasks.executeTask).not.toHaveBeenCalled();
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(fake.window.showWarningMessage).toHaveBeenCalledTimes(1);
  });

  it("a client without requestRegistered counts as no service", async () => {
    const plain = new FakeClient();
    const context = {
      extensionUri: fake.makeUri("/ext"),
      extension: { packageJSON: { version: "0.0.1" } },
      subscriptions: [],
    } as unknown as ExtensionContext;
    activate(context, { readIndexHtml: () => INDEX_HTML, createClient: () => plain });
    await handle(`req=${ID}`);
    expect(plain.requests).toEqual([]);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
  });

  it("a thrown error is reported, not left as an unhandled rejection", async () => {
    const { client } = setup();
    client.requestRegistered = async () => {
      throw new Error("kaboom");
    };
    await expect(handle(`req=${ID}`)).resolves.toBeUndefined();
    expect(fake.window.showWarningMessage).toHaveBeenCalledWith(expect.stringContaining("kaboom"));
  });
});

describe("repo-root comparison uses the resolved workspace path", () => {
  let dir: string;
  let link: string;
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "cadstudio-open-"));
    link = join(tmpdir(), `cadstudio-open-link-${process.pid}-${Date.now()}`);
    symlinkSync(dir, link);
  });
  afterEach(() => {
    rmSync(link, { force: true });
    rmSync(dir, { recursive: true, force: true });
  });

  const folderAt = (path: string) => [{ uri: fake.makeUri(path), name: "ws", index: 0 }] as unknown as WorkspaceFolder[];

  it("acks when the folder is a symlink to the service's (resolved) repo root", async () => {
    const { client } = setup();
    fake.workspace.workspaceFolders = folderAt(link) as never;
    client.registeredReply = (route) =>
      route.method === "GET"
        ? { ok: true, result: { id: ID, target: null, repoRoot: realpathSync(dir) } }
        : { ok: true, result: {} };
    const done = handle(`req=${ID}`)!;
    await flush();
    fake.createdPanels[0].webview.receive({ kind: "ready" });
    await done;
    expect(client.registered.some((r) => r.path.endsWith("/ack"))).toBe(true);
    expect(client.registered.some((r) => r.path.endsWith("/nack"))).toBe(false);
  });

  it("nacks when the service's repo root is the unresolved symlink spelling", async () => {
    const { client } = setup();
    fake.workspace.workspaceFolders = folderAt(link) as never;
    client.registeredReply = (route) =>
      route.method === "GET" ? { ok: true, result: { id: ID, target: null, repoRoot: link } } : { ok: true, result: {} };
    await handle(`req=${ID}`);
    expect(client.registered.some((r) => r.path.endsWith("/nack"))).toBe(true);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
  });
});

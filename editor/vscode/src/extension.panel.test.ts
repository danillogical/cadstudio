import * as http from "node:http";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionContext, WorkspaceFolder } from "vscode";
import { activate, defaultDeps, deactivate, NO_FOLDER_MESSAGE, UNTRUSTED_MESSAGE, type ExtensionDeps } from "./extension";
import * as fake from "./__mocks__/vscode";
import { FakeClient, flush, TOKEN } from "./test-utils";

const EXT_DIR = fileURLToPath(new URL("../../../.vscode/extensions/cadstudio", import.meta.url));

const INDEX_HTML = `<!doctype html><html><head>
<script type="module" crossorigin src="./assets/index-abc.js"></script>
<link rel="stylesheet" crossorigin href="./assets/index-def.css"></head><body><div id="app"></div></body></html>`;

interface Harness {
  context: ExtensionContext;
  client: FakeClient;
  createClient: ReturnType<typeof vi.fn>;
  readIndexHtml: ReturnType<typeof vi.fn>;
  deps: ExtensionDeps;
}

function harness(extensionPath = "/ext", index: string | (() => string) = INDEX_HTML): Harness {
  const client = new FakeClient();
  const createClient = vi.fn(() => client);
  const readIndexHtml = vi.fn(() => (typeof index === "function" ? index() : index));
  const context = {
    extensionUri: fake.makeUri(extensionPath),
    extension: { packageJSON: { version: "0.0.1" } },
    subscriptions: [],
  } as unknown as ExtensionContext;
  activate(context, { readIndexHtml, createClient });
  return { context, client, createClient, readIndexHtml, deps: { readIndexHtml, createClient } };
}

const open = () => fake.registeredCommands.get("cadstudio.openGui")!();
const serializer = () => fake.serializers.get("cadstudio.gui")!;
const call = (id: number, method: string, args: unknown[] = []) => ({ kind: "request", id, method, args });

beforeEach(() => fake.reset());
afterEach(() => {
  for (const panel of fake.createdPanels) panel.dispose();
  fake.reset();
});

describe("open command", () => {
  it("creates one panel, then only reveals it however many times it runs", () => {
    harness();
    open();
    open();
    open();
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
    expect(fake.createdPanels[0].reveal).toHaveBeenCalledTimes(2);
    expect(fake.createdPanels).toHaveLength(1);
  });

  it("creates a fresh panel, with a fresh nonce, after the first was closed", () => {
    harness();
    open();
    const nonceOf = (html: string) => /nonce-([^']+)'/.exec(html)![1];
    const first = nonceOf(fake.createdPanels[0].webview.html);
    fake.createdPanels[0].dispose();
    open();
    expect(fake.createdPanels).toHaveLength(2);
    expect(nonceOf(fake.createdPanels[1].webview.html)).not.toBe(first);
  });

  it("reveal does not re-render or re-attach", () => {
    const h = harness();
    open();
    const panel = fake.createdPanels[0];
    const html = panel.webview.html;
    open();
    expect(panel.webview.html).toBe(html);
    expect(panel.webview.listenerCount()).toBe(1);
    expect(h.readIndexHtml).toHaveBeenCalledTimes(1);
  });

  it("restricts the webview to the bundle and keeps scripts on", () => {
    harness();
    open();
    const options = fake.createdPanels[0].options as { enableScripts: boolean; localResourceRoots: Array<{ path: string }> };
    expect(options.enableScripts).toBe(true);
    expect(options.localResourceRoots.map((r) => r.path)).toEqual(["/ext/media"]);
  });

  it("serves a working bridge: a request is forwarded and the reply carries its id", async () => {
    const h = harness();
    h.client.reply = async () => ({ ok: true, result: { models: [] } });
    open();
    const panel = fake.createdPanels[0];
    panel.webview.receive(call(17, "listModels"));
    await flush();
    expect(h.client.requests.map((r) => r.path)).toEqual(["/v1/models"]);
    expect(panel.webview.posted).toEqual([{ kind: "response", id: 17, ok: true, result: { models: [] } }]);
  });

  it("does not forward an invalid message from the panel", async () => {
    const h = harness();
    open();
    fake.createdPanels[0].webview.receive(call(1, "getArtifact", ["../../etc/passwd"]));
    fake.createdPanels[0].webview.receive({ kind: "exec", cmd: "rm -rf /" });
    await flush();
    expect(h.client.requests).toEqual([]);
  });

  it("shares one service client between a panel and its successor", () => {
    const h = harness();
    open();
    fake.createdPanels[0].dispose();
    open();
    expect(h.createClient).toHaveBeenCalledTimes(1);
  });
});

describe("panel close", () => {
  it("disposes the message listener and the bridge's work", async () => {
    const h = harness();
    h.client.reply = (_route, signal) => new Promise((resolve) => signal.addEventListener("abort", () => resolve({ ok: true, result: {} })));
    open();
    const panel = fake.createdPanels[0];
    panel.webview.receive(call(1, "health"));
    panel.webview.receive({ kind: "subscribe" });
    await flush();
    expect(panel.webview.listenerCount()).toBe(1);
    expect(h.client.streams).toHaveLength(1);

    panel.dispose();
    expect(panel.webview.listenerCount()).toBe(0);
    expect(h.client.signals[0].aborted).toBe(true);
    expect(h.client.streams[0].closed).toBe(true);
    await flush();
    expect(panel.webview.posted).toEqual([]);
  });

  it("disposing the extension's subscriptions disposes a live panel's listeners", () => {
    const h = harness();
    open();
    const panel = fake.createdPanels[0];
    for (const sub of h.context.subscriptions) sub.dispose();
    expect(panel.webview.listenerCount()).toBe(0);
    expect(fake.registeredCommands.has("cadstudio.openGui")).toBe(false);
    expect(fake.serializers.has("cadstudio.gui")).toBe(false);
  });
});

describe("serializer restore", () => {
  it("registers a serializer for the view type", () => {
    harness();
    expect(fake.window.registerWebviewPanelSerializer).toHaveBeenCalledWith("cadstudio.gui", expect.anything());
  });

  it("restores a panel with the real UI HTML and a working bridge", async () => {
    const h = harness(EXT_DIR, () => defaultDeps.readIndexHtml(fake.makeUri(EXT_DIR) as never));
    h.client.reply = async () => ({ ok: true, result: { restored: true } });
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    await serializer().deserializeWebviewPanel(revived, undefined);

    const html = revived.webview.html;
    expect(html).toContain("connect-src 'none'");
    expect(html).toMatch(/<script [^>]*nonce="[^"]+"[^>]*src="vscode-resource:[^"]*\/media\/assets\/[^"]+\.js"|<script [^>]*src="vscode-resource:[^"]*\/media\/assets\/[^"]+\.js"[^>]*nonce=/);
    expect(html).toContain('id="viewport"');
    expect(html).not.toContain("./assets/");
    expect(revived.webview.options).toMatchObject({ enableScripts: true });

    revived.webview.receive(call(3, "health"));
    await flush();
    expect(revived.webview.posted).toEqual([{ kind: "response", id: 3, ok: true, result: { restored: true } }]);
  });

  it("disposes the restored panel's listeners when it closes", () => {
    harness();
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    expect(revived.webview.listenerCount()).toBe(1);
    revived.dispose();
    expect(revived.webview.listenerCount()).toBe(0);
  });

  it("becomes the single panel: opening afterwards reveals it instead of creating another", () => {
    harness();
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    open();
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(revived.reveal).toHaveBeenCalledTimes(1);
  });

  it("closes a second restored panel and reveals the existing one", () => {
    harness();
    open();
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    expect(revived.disposed).toBe(true);
    expect(fake.createdPanels[0].reveal).toHaveBeenCalledTimes(1);
    expect(fake.createdPanels[0].disposed).toBe(false);
    expect(revived.webview.listenerCount()).toBe(0);
  });

  it("closes a restored panel and tells the user when the bundle is missing", () => {
    harness("/ext", () => {
      throw new Error("ENOENT: media/index.html");
    });
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    expect(revived.disposed).toBe(true);
    expect(fake.window.showErrorMessage).toHaveBeenCalledWith(expect.stringContaining("ENOENT"));
  });

  it("closes a restored panel whose bundle is unsafe", () => {
    harness("/ext", '<html><head><script>alert(1)</script></head></html>');
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    expect(revived.disposed).toBe(true);
    expect(revived.webview.html).toBe("");
    expect(fake.window.showErrorMessage).toHaveBeenCalledTimes(1);
  });

  it("refuses to restore in an untrusted workspace", () => {
    const h = harness();
    fake.workspace.isTrusted = false;
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    expect(revived.disposed).toBe(true);
    expect(revived.webview.html).toBe("");
    expect(revived.webview.listenerCount()).toBe(0);
    expect(h.createClient).not.toHaveBeenCalled();
    expect(fake.window.showErrorMessage).toHaveBeenCalledWith(UNTRUSTED_MESSAGE);
  });
});

describe("refusals", () => {
  it("an untrusted workspace gets a message, no panel, no client and no service", async () => {
    const h = harness();
    fake.workspace.isTrusted = false;
    open();
    open();
    expect(fake.window.showErrorMessage).toHaveBeenCalledWith(UNTRUSTED_MESSAGE);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(h.createClient).not.toHaveBeenCalled();
    expect(h.readIndexHtml).not.toHaveBeenCalled();
    expect(h.client.requests).toEqual([]);
    expect(h.client.openCalls).toEqual([]);
  });

  it("the URI handler cannot open a panel in an untrusted workspace", async () => {
    const h = harness();
    fake.workspace.isTrusted = false;
    await fake.uriHandlers[0].handleUri(fake.makeUri("/open", "x=1"));
    await flush();
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(h.createClient).not.toHaveBeenCalled();
  });

  it("opens normally once the workspace is trusted", () => {
    harness();
    fake.workspace.isTrusted = false;
    open();
    fake.workspace.isTrusted = true;
    open();
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
  });

  it("a window with no folder gets a message and no panel", () => {
    const h = harness();
    fake.workspace.workspaceFolders = undefined;
    open();
    expect(fake.window.showErrorMessage).toHaveBeenCalledWith(NO_FOLDER_MESSAGE);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(h.createClient).not.toHaveBeenCalled();
  });

  it("a missing bundle shows an error and creates no panel", () => {
    harness("/ext", () => {
      throw new Error("ENOENT");
    });
    open();
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
    expect(fake.window.showErrorMessage).toHaveBeenCalledWith(expect.stringContaining("ENOENT"));
  });

  it("a bundle with an inline script is never shown: the panel is closed unrendered and the user told", () => {
    const h = harness("/ext", "<html><head><script>alert(1)</script></head></html>");
    open();
    for (const panel of fake.createdPanels) {
      expect(panel.disposed).toBe(true);
      expect(panel.webview.html).toBe("");
      expect(panel.webview.listenerCount()).toBe(0);
    }
    expect(h.createClient).not.toHaveBeenCalled();
    expect(fake.window.showErrorMessage).toHaveBeenCalledTimes(1);
    open(); // nothing is retained, so the next attempt tries again rather than revealing a dead panel
    expect(fake.createdPanels.every((panel) => panel.disposed)).toBe(true);
  });
});

describe("deactivate", () => {
  it("does not touch the service: no request, no stream, no stop", async () => {
    const h = harness();
    open();
    const executeBefore = fake.commands.executeCommand.mock.calls.length;
    expect(deactivate()).toBeUndefined();
    await flush();
    expect(h.client.requests).toEqual([]);
    expect(h.client.openCalls).toEqual([]);
    expect(fake.commands.executeCommand.mock.calls.length).toBe(executeBefore);
  });

  it("the extension never terminates tasks or other processes (the service outlives a reload)", () => {
    harness();
    open();
    const names = Object.keys(fake.window).concat(Object.keys(fake.commands), Object.keys(fake.workspace));
    expect(names.filter((n) => /terminate|kill|stop/i.test(n))).toEqual([]);
    for (const [id] of fake.commands.executeCommand.mock.calls) expect(String(id)).not.toMatch(/terminate|kill|stop/i);
  });
});

describe("default deps against a real loopback service", () => {
  let dir: string;
  let server: http.Server;
  let port: number;
  let seenAuth: Array<string | undefined>;

  beforeEach(async () => {
    dir = mkdtempSync(join(tmpdir(), "cadstudio-ext-"));
    seenAuth = [];
    server = http.createServer((req, res) => {
      seenAuth.push(req.headers.authorization);
      res.writeHead(200, { "Content-Type": "application/json" });
      if (req.url === "/v1/health") {
        res.end(JSON.stringify({ service: "cadstudio", protocolVersion: 1, repoRoot: realpathSync(dir), pid: process.pid }));
      } else {
        res.end(JSON.stringify({ models: ["p/m"], authed: req.headers.authorization === `Bearer ${TOKEN}` }));
      }
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    port = (server.address() as AddressInfo).port;
  });

  afterEach(async () => {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    rmSync(dir, { recursive: true, force: true });
  });

  function writeRecord(repoRoot: string) {
    mkdirSync(join(dir, ".cadstudio", "gui"), { recursive: true });
    writeFileSync(
      join(dir, ".cadstudio", "gui", "service.json"),
      JSON.stringify({ pid: process.pid, port, token: TOKEN, repoRoot, protocolVersion: 1, startedAt: 1 }),
    );
  }

  const folderAt = (path: string) => ({ uri: fake.makeUri(path), name: "ws", index: 0 }) as unknown as WorkspaceFolder;

  it("reuses a healthy service for the workspace and authenticates with the registered token", async () => {
    writeRecord(realpathSync(dir));
    const client = defaultDeps.createClient(folderAt(dir));
    const reply = await client.request({ method: "GET", path: "/v1/models", binary: false }, new AbortController().signal);
    expect(reply).toEqual({ ok: true, result: { models: ["p/m"], authed: true } });
    expect(seenAuth).toContain(`Bearer ${TOKEN}`);
  });

  it("matches the service's resolved repo root when the workspace path is a symlink", async () => {
    const link = join(tmpdir(), `cadstudio-link-${process.pid}-${Date.now()}`);
    symlinkSync(dir, link);
    try {
      writeRecord(realpathSync(dir));
      const client = defaultDeps.createClient(folderAt(link));
      const reply = await client.request({ method: "GET", path: "/v1/models", binary: false }, new AbortController().signal);
      expect(reply).toMatchObject({ ok: true });
    } finally {
      rmSync(link, { force: true });
    }
  });
});

describe("panel never steals focus", () => {
  it("creates the panel with show options {preserveFocus: true}", () => {
    harness();
    open();
    const showOptions = fake.window.createWebviewPanel.mock.calls[0][2] as { preserveFocus?: boolean };
    expect(showOptions.preserveFocus).toBe(true);
  });

  it("keeps retainContextWhenHidden on the new panel", () => {
    harness();
    open();
    const options = fake.window.createWebviewPanel.mock.calls[0][3] as { retainContextWhenHidden?: boolean };
    expect(options.retainContextWhenHidden).toBe(true);
  });

  it("keeps retainContextWhenHidden on a restored panel", () => {
    harness();
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    expect((revived.webview.options as { retainContextWhenHidden?: boolean }).retainContextWhenHidden).toBe(true);
  });

  it("passes preserveFocus = true on every reveal of the open panel", () => {
    harness();
    open();
    open();
    open();
    const reveal = fake.createdPanels[0].reveal;
    expect(reveal).toHaveBeenCalledTimes(2);
    for (const args of reveal.mock.calls) expect(args[1]).toBe(true);
  });

  it("passes preserveFocus = true when a URI request reveals the existing panel", async () => {
    harness();
    open();
    await fake.commands.executeCommand("cadstudio.openGui", "x=1");
    const reveal = fake.createdPanels[0].reveal;
    expect(reveal).toHaveBeenCalledTimes(1);
    expect(reveal.mock.calls[0][1]).toBe(true);
  });

  it("passes preserveFocus = true when opening after a panel was restored", () => {
    harness();
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    open();
    expect(revived.reveal).toHaveBeenCalledTimes(1);
    expect(revived.reveal.mock.calls[0][1]).toBe(true);
  });

  it("passes preserveFocus = true when a second restored panel is closed in favour of the open one", () => {
    harness();
    open();
    const revived = fake.makePanel("cadstudio.gui", "CADStudio");
    serializer().deserializeWebviewPanel(revived, undefined);
    const reveal = fake.createdPanels[0].reveal;
    expect(reveal).toHaveBeenCalledTimes(1);
    expect(reveal.mock.calls[0][1]).toBe(true);
  });
});

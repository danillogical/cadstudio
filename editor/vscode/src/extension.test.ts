import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionContext } from "vscode";
import type { ServiceClient } from "./bridge";
import { activate, deactivate, type ExtensionDeps } from "./extension";
import * as fake from "./__mocks__/vscode";

const INDEX_HTML = `<!doctype html>
<html lang="en">
  <head>
    <title>CADStudio</title>
    <script type="module" crossorigin src="./assets/index-abc.js"></script>
    <link rel="stylesheet" crossorigin href="./assets/index-def.css">
  </head>
  <body><div id="app"></div></body>
</html>
`;

const client: ServiceClient = {
  request: async () => ({ ok: true, result: {} }),
  openEvents: async () => ({ close() {} }),
};

const deps: ExtensionDeps = {
  readIndexHtml: () => INDEX_HTML,
  createClient: () => client,
};

function makeContext(): ExtensionContext {
  return {
    extensionUri: fake.makeUri("/ext"),
    extension: { packageJSON: { version: "0.0.1" } },
    subscriptions: [],
  } as unknown as ExtensionContext;
}

function activateWithContext(): ExtensionContext {
  const context = makeContext();
  activate(context, deps);
  return context;
}

function runCommand(...args: unknown[]): unknown {
  const handler = fake.registeredCommands.get("cadstudio.openGui");
  expect(handler).toBeDefined();
  return handler!(...args);
}

describe("activate", () => {
  beforeEach(() => {
    fake.reset();
  });

  afterEach(() => {
    for (const panel of fake.createdPanels) panel.dispose();
    fake.reset();
  });

  it("registers the command and a URI handler", () => {
    const context = activateWithContext();
    expect(fake.commands.registerCommand).toHaveBeenCalledWith(
      "cadstudio.openGui",
      expect.any(Function),
    );
    expect(fake.window.registerUriHandler).toHaveBeenCalledTimes(1);
    expect(context.subscriptions.length).toBeGreaterThanOrEqual(2);
  });

  it("creates a scripted webview panel that serves the bundled UI", () => {
    activateWithContext();
    runCommand();
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
    const [viewType, title, , options] = fake.window.createWebviewPanel.mock.calls[0];
    expect(viewType).toBe("cadstudio.gui");
    expect(title).toBe("CADStudio");
    expect(options).toMatchObject({ enableScripts: true });
    const roots = (options as { localResourceRoots: Array<{ path: string }> }).localResourceRoots;
    expect(roots.map((root) => root.path)).toEqual(["/ext/media"]);

    const html = fake.createdPanels[0].webview.html;
    expect(html).toContain("connect-src 'none'");
    expect(html).toContain('src="vscode-resource:/ext/media/assets/index-abc.js"');
    expect(html).toContain('href="vscode-resource:/ext/media/assets/index-def.css"');
  });

  it("reveals the existing panel instead of creating a second one", () => {
    activateWithContext();
    runCommand();
    const html = fake.createdPanels[0].webview.html;
    runCommand("x=1");
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
    expect(fake.createdPanels[0].reveal).toHaveBeenCalledTimes(1);
    expect(fake.createdPanels[0].webview.html).toBe(html);
  });

  it("ignores a non-string command argument", () => {
    activateWithContext();
    runCommand({ not: "a string" });
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
  });

  it("routes an /open URI through the same command", () => {
    activateWithContext();
    const handler = fake.uriHandlers[0];
    handler.handleUri(fake.makeUri("/open", "x=1"));
    expect(fake.commands.executeCommand).toHaveBeenCalledWith("cadstudio.openGui", "x=1");
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
  });

  it("warns and does not open a panel for an unknown URI path", () => {
    activateWithContext();
    fake.uriHandlers[0].handleUri(fake.makeUri("/viewer", "run=x"));
    expect(fake.commands.executeCommand).not.toHaveBeenCalled();
    expect(fake.window.showWarningMessage).toHaveBeenCalledTimes(1);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
  });

  it("has a no-op deactivate", () => {
    expect(deactivate()).toBeUndefined();
  });
});

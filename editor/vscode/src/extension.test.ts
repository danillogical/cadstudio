import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionContext } from "vscode";
import { activate, deactivate } from "./extension";
import * as fake from "./__mocks__/vscode";

function makeContext(): ExtensionContext {
  return {
    extensionUri: fake.makeUri("/ext"),
    extension: { packageJSON: { version: "0.0.1" } },
    subscriptions: [],
  } as unknown as ExtensionContext;
}

function activateWithContext(): ExtensionContext {
  const context = makeContext();
  activate(context);
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

  it("creates a scripted webview panel with the folder and version", () => {
    activateWithContext();
    runCommand();
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
    const [viewType, title, , options] = fake.window.createWebviewPanel.mock.calls[0];
    expect(viewType).toBe("cadstudio.gui");
    expect(title).toBe("CADStudio");
    expect(options).toMatchObject({ enableScripts: true });
    const roots = (options as { localResourceRoots: Array<{ path: string }> }).localResourceRoots;
    expect(roots[0].path.endsWith("/dist")).toBe(true);

    const html = fake.createdPanels[0].webview.html;
    expect(html).toContain("cadstudio");
    expect(html).toContain("0.0.1");
    expect(html).toContain('id="query">(none)');
    expect(html).toContain('id="script-status"');
  });

  it("reveals the existing panel instead of creating a second one", () => {
    activateWithContext();
    runCommand();
    runCommand("x=1");
    expect(fake.window.createWebviewPanel).toHaveBeenCalledTimes(1);
    expect(fake.createdPanels[0].reveal).toHaveBeenCalledTimes(1);
    expect(fake.createdPanels[0].webview.html).toContain('id="query">x=1');
  });

  it("shows (none) for a non-string command argument", () => {
    activateWithContext();
    runCommand({ not: "a string" });
    expect(fake.createdPanels[0].webview.html).toContain('id="query">(none)');
  });

  it("routes an /open URI through the same command", () => {
    activateWithContext();
    const handler = fake.uriHandlers[0];
    handler.handleUri({ path: "/open", query: "x=1" });
    expect(fake.commands.executeCommand).toHaveBeenCalledWith("cadstudio.openGui", "x=1");
    expect(fake.createdPanels[0].webview.html).toContain('id="query">x=1');
  });

  it("warns and does not open a panel for an unknown URI path", () => {
    activateWithContext();
    fake.uriHandlers[0].handleUri({ path: "/viewer", query: "run=x" });
    expect(fake.commands.executeCommand).not.toHaveBeenCalled();
    expect(fake.window.showWarningMessage).toHaveBeenCalledTimes(1);
    expect(fake.window.createWebviewPanel).not.toHaveBeenCalled();
  });

  it("has a no-op deactivate", () => {
    expect(deactivate()).toBeUndefined();
  });
});

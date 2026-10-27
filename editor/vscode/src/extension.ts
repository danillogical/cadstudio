import * as vscode from "vscode";
import { readFileSync, realpathSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { HttpServiceClient, PanelBridge, type ServiceClient } from "./bridge";
import { makeNonce, renderPanelHtml } from "./html";
import { fetchHealth } from "./http";
import { ServiceLocator } from "./service";
import { startServeTask } from "./tasks";
import { parseOpenUri } from "./uri";

export const COMMAND_ID = "cadstudio.openGui";
export const VIEW_TYPE = "cadstudio.gui";
/** The copied `ui/dist` bundle inside the built extension. */
export const MEDIA_DIR = "media";
export const UNTRUSTED_MESSAGE =
  "CADStudio is disabled in untrusted workspaces. Trust this workspace to open the GUI.";
export const NO_FOLDER_MESSAGE = "CADStudio: open the cadstudio repository folder to use the GUI.";

/** The I/O the extension does, replaceable in tests. */
export interface ExtensionDeps {
  /** The built `media/index.html`. */
  readIndexHtml(extensionUri: vscode.Uri): string;
  /** The service client for a workspace folder; one is kept per folder. */
  createClient(folder: vscode.WorkspaceFolder): ServiceClient;
}

/** The service resolves its repo root, so compare against the resolved workspace path. */
function canonicalPath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
}

export const defaultDeps: ExtensionDeps = {
  readIndexHtml: (extensionUri) => readFileSync(join(extensionUri.fsPath, MEDIA_DIR, "index.html"), "utf8"),
  createClient: (folder) =>
    new HttpServiceClient(
      new ServiceLocator({
        workspaceRoot: canonicalPath(folder.uri.fsPath),
        readFile: (path) => readFile(path, "utf8").catch(() => null),
        health: (port) => fetchHealth(port),
        startService: () => startServeTask(folder),
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        now: () => Date.now(),
      }),
    ),
};

/** Scripts on, resources only from the bundle, and the 3D context kept while the tab is hidden. */
export function panelOptions(extensionUri: vscode.Uri): vscode.WebviewPanelOptions & vscode.WebviewOptions {
  return {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extensionUri, MEDIA_DIR)],
    retainContextWhenHidden: true,
  };
}

/** Owns the single GUI panel: create or reveal it, restore it after a reload, and wire its bridge. */
export class GuiPanels {
  private panel: vscode.WebviewPanel | undefined;
  private bridge: PanelBridge | undefined;
  private client: { key: string; client: ServiceClient } | undefined;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly deps: ExtensionDeps,
  ) {}

  get current(): vscode.WebviewPanel | undefined {
    return this.panel;
  }

  /** Reveal the open panel, or create one; refuses in an untrusted or folderless window. */
  open(): vscode.WebviewPanel | undefined {
    if (this.refused()) return undefined;
    if (this.panel) {
      this.panel.reveal();
      return this.panel;
    }
    const index = this.readIndex();
    if (index === undefined) return undefined;
    const panel = vscode.window.createWebviewPanel(
      VIEW_TYPE,
      "CADStudio",
      vscode.ViewColumn.Active,
      panelOptions(this.context.extensionUri),
    );
    this.attach(panel, index);
    return panel;
  }

  /** Take over a panel VS Code revived after a reload; a refused one is closed. */
  restore(panel: vscode.WebviewPanel): void {
    if (this.refused()) {
      panel.dispose();
      return;
    }
    if (this.panel && this.panel !== panel) {
      panel.dispose();
      this.panel.reveal();
      return;
    }
    const index = this.readIndex();
    if (index === undefined) {
      panel.dispose();
      return;
    }
    panel.webview.options = panelOptions(this.context.extensionUri);
    this.attach(panel, index);
  }

  dispose(): void {
    this.bridge?.dispose();
    this.bridge = undefined;
    this.panel = undefined;
  }

  private refused(): boolean {
    if (!vscode.workspace.isTrusted) {
      void vscode.window.showErrorMessage(UNTRUSTED_MESSAGE);
      return true;
    }
    if (!vscode.workspace.workspaceFolders?.[0]) {
      void vscode.window.showErrorMessage(NO_FOLDER_MESSAGE);
      return true;
    }
    return false;
  }

  private readIndex(): string | undefined {
    try {
      return this.deps.readIndexHtml(this.context.extensionUri);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      void vscode.window.showErrorMessage(`CADStudio: the GUI bundle is missing (${reason}). Rebuild editor/vscode.`);
      return undefined;
    }
  }

  private clientFor(folder: vscode.WorkspaceFolder): ServiceClient {
    const key = folder.uri.toString();
    if (this.client?.key !== key) this.client = { key, client: this.deps.createClient(folder) };
    return this.client.client;
  }

  private attach(panel: vscode.WebviewPanel, index: string): void {
    const folder = vscode.workspace.workspaceFolders![0];
    const webview = panel.webview;
    const media = vscode.Uri.joinPath(this.context.extensionUri, MEDIA_DIR);
    let html: string;
    try {
      html = renderPanelHtml(index, {
        nonce: makeNonce(),
        assetUri: (path) => webview.asWebviewUri(vscode.Uri.joinPath(media, ...path.split("/"))).toString(),
      });
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      void vscode.window.showErrorMessage(`CADStudio: could not load the GUI bundle: ${reason}`);
      panel.dispose();
      return;
    }
    // The bridge listens before the page loads, so no early message is lost.
    const bridge = new PanelBridge(webview, this.clientFor(folder));
    this.panel = panel;
    this.bridge = bridge;
    panel.onDidDispose(() => {
      bridge.dispose();
      if (this.panel === panel) {
        this.panel = undefined;
        this.bridge = undefined;
      }
    });
    webview.html = html;
  }
}

export function activate(context: vscode.ExtensionContext, deps: ExtensionDeps = defaultDeps): void {
  const panels = new GuiPanels(context, deps);
  context.subscriptions.push({ dispose: () => panels.dispose() });

  context.subscriptions.push(
    vscode.commands.registerCommand(COMMAND_ID, () => {
      panels.open();
    }),
  );

  context.subscriptions.push(
    vscode.window.registerWebviewPanelSerializer(VIEW_TYPE, {
      async deserializeWebviewPanel(panel: vscode.WebviewPanel) {
        panels.restore(panel);
      },
    }),
  );

  context.subscriptions.push(
    vscode.window.registerUriHandler({
      handleUri(uri: vscode.Uri) {
        const open = parseOpenUri(uri);
        if (!open) {
          void vscode.window.showWarningMessage(
            `CADStudio: unsupported URI path "${uri.path}"`,
          );
          return;
        }
        void vscode.commands.executeCommand(COMMAND_ID, open.query);
      },
    }),
  );
}

/** The service keeps running: a reload must find and reuse it, not start a second one. */
export function deactivate(): void {}

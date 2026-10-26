import * as vscode from "vscode";
import { makeNonce, renderHtml } from "./html";
import { parseOpenUri } from "./uri";

const COMMAND_ID = "cadstudio.openGui";

let panel: vscode.WebviewPanel | undefined;

function setPanelHtml(
  context: vscode.ExtensionContext,
  webview: vscode.Webview,
  query: string | undefined,
): void {
  webview.html = renderHtml({
    cspSource: webview.cspSource,
    nonce: makeNonce(),
    scriptUri: webview
      .asWebviewUri(vscode.Uri.joinPath(context.extensionUri, "dist", "webview.js"))
      .toString(),
    workspaceName: vscode.workspace.workspaceFolders?.[0]?.name ?? "(no folder)",
    version: String(context.extension.packageJSON.version),
    query,
  });
}

// One panel only: a repeated open reveals and re-renders instead of stacking.
function openPanel(context: vscode.ExtensionContext, query: string | undefined): void {
  if (panel) {
    setPanelHtml(context, panel.webview, query);
    panel.reveal();
    return;
  }
  const created = vscode.window.createWebviewPanel("cadstudio.gui", "CADStudio", vscode.ViewColumn.Active, {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "dist")],
  });
  panel = created;
  created.onDidDispose(() => {
    if (panel === created) panel = undefined;
  });
  setPanelHtml(context, created.webview, query);
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMAND_ID, (arg?: unknown) => {
      openPanel(context, typeof arg === "string" ? arg : undefined);
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

export function deactivate(): void {}

"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/extension.ts
var extension_exports = {};
__export(extension_exports, {
  activate: () => activate,
  deactivate: () => deactivate
});
module.exports = __toCommonJS(extension_exports);
var vscode = __toESM(require("vscode"));

// src/html.ts
var import_node_crypto = require("node:crypto");
function makeNonce() {
  return (0, import_node_crypto.randomBytes)(16).toString("base64");
}
var ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
};
function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ESCAPES[char]);
}
function renderHtml(options) {
  const { nonce, scriptUri, workspaceName, version, query } = options;
  const csp = [
    "default-src 'none'",
    `script-src 'nonce-${nonce}'`,
    `style-src 'nonce-${nonce}'`
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp};">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CADStudio</title>
<style nonce="${nonce}">
  body { font-family: var(--vscode-font-family); padding: 1rem; }
  dt { font-weight: 600; }
</style>
</head>
<body>
<h1>CADStudio</h1>
<dl>
  <dt>Workspace</dt>
  <dd id="workspace-name">${escapeHtml(workspaceName)}</dd>
  <dt>Version</dt>
  <dd id="extension-version">${escapeHtml(version)}</dd>
  <dt>Query</dt>
  <dd id="query">${escapeHtml(query ?? "(none)")}</dd>
  <dt>Webview script</dt>
  <dd><span id="script-status">not loaded</span></dd>
</dl>
<script nonce="${nonce}" src="${escapeHtml(scriptUri)}"></script>
</body>
</html>
`;
}

// src/uri.ts
var OPEN_PATH = "/open";
function parseOpenUri(uri) {
  const path = uri.path.endsWith("/") ? uri.path.slice(0, -1) : uri.path;
  if (path !== OPEN_PATH) return void 0;
  return { query: uri.query };
}

// src/extension.ts
var COMMAND_ID = "cadstudio.openGui";
var panel;
function setPanelHtml(context, webview, query) {
  webview.html = renderHtml({
    cspSource: webview.cspSource,
    nonce: makeNonce(),
    scriptUri: webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri, "dist", "webview.js")).toString(),
    workspaceName: vscode.workspace.workspaceFolders?.[0]?.name ?? "(no folder)",
    version: String(context.extension.packageJSON.version),
    query
  });
}
function openPanel(context, query) {
  if (panel) {
    setPanelHtml(context, panel.webview, query);
    panel.reveal();
    return;
  }
  const created = vscode.window.createWebviewPanel("cadstudio.gui", "CADStudio", vscode.ViewColumn.Active, {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "dist")]
  });
  panel = created;
  created.onDidDispose(() => {
    if (panel === created) panel = void 0;
  });
  setPanelHtml(context, created.webview, query);
}
function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMAND_ID, (arg) => {
      openPanel(context, typeof arg === "string" ? arg : void 0);
    })
  );
  context.subscriptions.push(
    vscode.window.registerUriHandler({
      handleUri(uri) {
        const open = parseOpenUri(uri);
        if (!open) {
          void vscode.window.showWarningMessage(
            `CADStudio: unsupported URI path "${uri.path}"`
          );
          return;
        }
        void vscode.commands.executeCommand(COMMAND_ID, open.query);
      }
    })
  );
}
function deactivate() {
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  activate,
  deactivate
});

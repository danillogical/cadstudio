import { randomBytes } from "node:crypto";

export interface HtmlOptions {
  cspSource: string;
  nonce: string;
  scriptUri: string;
  workspaceName: string;
  version: string;
  query?: string;
}

export function makeNonce(): string {
  return randomBytes(16).toString("base64");
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

// The query string comes from an external URL, so everything interpolated is escaped.
export function renderHtml(options: HtmlOptions): string {
  const { nonce, scriptUri, workspaceName, version, query } = options;
  const csp = [
    "default-src 'none'",
    `script-src 'nonce-${nonce}'`,
    `style-src 'nonce-${nonce}'`,
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

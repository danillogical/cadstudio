import { randomBytes } from "node:crypto";

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

/**
 * The panel's Content-Security-Policy: nothing by default, scripts and stylesheets only when
 * they carry this page's nonce, and no network access at all (`connect-src 'none'`), so the
 * webview can reach the service only through the extension host.
 */
export function buildCsp(nonce: string): string {
  return [
    "default-src 'none'",
    `script-src 'nonce-${nonce}'`,
    `style-src 'nonce-${nonce}'`,
    "connect-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join("; ");
}

export interface PanelHtmlOptions {
  nonce: string;
  /** Webview URI for a bundle-relative asset path such as `assets/index-abc.js`. */
  assetUri: (relativePath: string) => string;
}

const ATTRIBUTE = /([^\s"'<>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;

function parseAttributes(source: string): Array<[string, string | null]> {
  const attributes: Array<[string, string | null]> = [];
  for (const match of source.matchAll(ATTRIBUTE)) {
    attributes.push([match[1].toLowerCase(), match[2] ?? match[3] ?? match[4] ?? null]);
  }
  return attributes;
}

function renderTag(name: string, attributes: Array<[string, string | null]>): string {
  const rendered = attributes.map(([key, value]) => (value === null ? key : `${key}="${escapeHtml(value)}"`));
  return `<${name}${rendered.length ? " " + rendered.join(" ") : ""}>`;
}

/** A bundle-relative path (`./assets/x.js` or `assets/x.js`); anything that could leave the bundle throws. */
export function bundlePath(value: string): string {
  const path = value.startsWith("./") ? value.slice(2) : value;
  if (
    path === "" ||
    /^[a-z][a-z0-9+.-]*:/i.test(path) ||
    path.startsWith("/") ||
    /[\\?#]/.test(path) ||
    path.split("/").some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error(`ui/dist/index.html references ${JSON.stringify(value)}, which is not a bundle asset`);
  }
  return path;
}

/**
 * Rewrite the built `ui/dist/index.html` for the webview: every `<script>` and stylesheet
 * `<link>` gets a webview URI and the fresh nonce, any CSP or `<base>` in the source is dropped,
 * and the panel's CSP meta becomes the first element of `<head>`. Inline scripts are refused
 * rather than nonced, so only bundle files ever run.
 */
export function renderPanelHtml(indexHtml: string, options: PanelHtmlOptions): string {
  const { nonce, assetUri } = options;
  if (!/^[A-Za-z0-9+/=]+$/.test(nonce)) throw new Error("nonce must be base64");
  const scripts = (indexHtml.match(/<script\b/gi) ?? []).length;
  let rewritten = 0;
  let html = indexHtml.replace(/<meta\b[^>]*http-equiv\s*=\s*["']?content-security-policy["']?[^>]*>/gi, "");
  if (/<base\b/i.test(html)) throw new Error("ui/dist/index.html must not contain <base>");

  html = html.replace(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi, (_tag, source: string, body: string) => {
    const attributes = parseAttributes(source).filter(([key]) => key !== "nonce");
    const src = attributes.find(([key]) => key === "src");
    if (!src || src[1] === null || body.trim() !== "") {
      throw new Error("ui/dist/index.html has an inline script; the webview runs bundle files only");
    }
    src[1] = assetUri(bundlePath(src[1]));
    attributes.push(["nonce", nonce]);
    rewritten += 1;
    return `${renderTag("script", attributes)}</script>`;
  });
  if (rewritten !== scripts) throw new Error("ui/dist/index.html has a <script> without a closing tag");

  html = html.replace(/<link\b([^>]*?)\/?>/gi, (_tag, source: string) => {
    const attributes = parseAttributes(source).filter(([key]) => key !== "nonce");
    const href = attributes.find(([key]) => key === "href");
    if (href && href[1] !== null) href[1] = assetUri(bundlePath(href[1]));
    const rel = (attributes.find(([key]) => key === "rel")?.[1] ?? "").toLowerCase().split(/\s+/);
    if (rel.includes("stylesheet") || rel.includes("modulepreload")) attributes.push(["nonce", nonce]);
    return renderTag("link", attributes);
  });

  if (/<style\b/i.test(html)) throw new Error("ui/dist/index.html has an inline <style>; use the bundled stylesheet");
  const head = /<head\b[^>]*>/i.exec(html);
  if (!head) throw new Error("ui/dist/index.html has no <head>");
  const meta = `\n<meta http-equiv="Content-Security-Policy" content="${buildCsp(nonce)}">`;
  const at = head.index + head[0].length;
  return html.slice(0, at) + meta + html.slice(at);
}

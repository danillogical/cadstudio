import { describe, expect, it } from "vitest";
import { escapeHtml, makeNonce, renderHtml } from "./html";

const nonce = "abc123";

function render(query?: string): string {
  return renderHtml({
    cspSource: "vscode-resource:",
    nonce,
    scriptUri: "vscode-resource:/ext/dist/webview.js",
    workspaceName: "cadstudio",
    version: "0.0.1",
    query,
  });
}

function cspOf(html: string): string {
  const match = html.match(/Content-Security-Policy" content="([^"]+)"/);
  expect(match).not.toBeNull();
  return match![1];
}

describe("renderHtml", () => {
  it("uses a default-src none CSP with a nonce-only script policy", () => {
    const csp = cspOf(render());
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain(`script-src 'nonce-${nonce}'`);
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).not.toContain("script-src 'self'");
    expect(csp).not.toContain("*");
  });

  it("loads exactly one script from the extension URI with the nonce", () => {
    const html = render();
    const tags = html.match(/<script\b[^>]*>/g) ?? [];
    expect(tags).toHaveLength(1);
    expect(tags[0]).toContain(`nonce="${nonce}"`);
    expect(tags[0]).toContain('src="vscode-resource:/ext/dist/webview.js"');
    expect(html).not.toMatch(/<script\b[^>]*>\s*[^<\s]/);
  });

  it("shows the heading, workspace folder and version", () => {
    const html = render();
    expect(html).toContain("<h1>CADStudio</h1>");
    expect(html).toContain("cadstudio");
    expect(html).toContain("0.0.1");
  });

  it("shows (none) when there is no query", () => {
    expect(render()).toContain('id="query">(none)');
  });

  it("escapes an attacker-controlled query", () => {
    const html = render("<script>alert(1)</script>");
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  it("escapes quotes and ampersands", () => {
    expect(escapeHtml(`<a href="x">&'`)).toBe("&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
  });
});

describe("makeNonce", () => {
  it("returns distinct values with at least 16 bytes of entropy", () => {
    const a = makeNonce();
    const b = makeNonce();
    expect(a).not.toBe(b);
    expect(Buffer.from(a, "base64").length).toBeGreaterThanOrEqual(16);
  });
});

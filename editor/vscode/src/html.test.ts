import { describe, expect, it } from "vitest";
import { buildCsp, bundlePath, escapeHtml, makeNonce, renderPanelHtml } from "./html";

const nonce = "abc123";

// The shape Vite writes to ui/dist/index.html (base "./").
const INDEX = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>CADStudio</title>
    <script type="module" crossorigin src="./assets/index-abc.js"></script>
    <link rel="stylesheet" crossorigin href="./assets/index-def.css">
  </head>
  <body><div id="app"></div></body>
</html>
`;

function render(index = INDEX): string {
  return renderPanelHtml(index, {
    nonce,
    assetUri: (path) => `vscode-resource:/ext/media/${path}`,
  });
}

function cspOf(html: string): string {
  const matches = [...html.matchAll(/Content-Security-Policy" content="([^"]+)"/g)];
  expect(matches).toHaveLength(1);
  return matches[0][1];
}

describe("renderPanelHtml", () => {
  it("uses a default-src none CSP with nonce-only scripts and no network", () => {
    const csp = cspOf(render());
    expect(csp).toBe(buildCsp(nonce));
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain(`script-src 'nonce-${nonce}'`);
    expect(csp).toContain("connect-src 'none'");
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).not.toContain("'self'");
    expect(csp).not.toContain("*");
    expect(csp).not.toMatch(/https?:/);
  });

  it("puts the CSP before any script or stylesheet", () => {
    const html = render();
    const csp = html.indexOf("Content-Security-Policy");
    expect(csp).toBeGreaterThan(html.indexOf("<head>"));
    expect(csp).toBeLessThan(html.indexOf("<script"));
    expect(csp).toBeLessThan(html.indexOf("<link"));
  });

  it("loads every script from the extension URI with the nonce", () => {
    const html = render();
    const tags = html.match(/<script\b[^>]*>/g) ?? [];
    expect(tags).toHaveLength(1);
    expect(tags[0]).toContain(`nonce="${nonce}"`);
    expect(tags[0]).toContain('src="vscode-resource:/ext/media/assets/index-abc.js"');
    expect(html).not.toMatch(/<script\b[^>]*>\s*[^<\s]/);
  });

  it("rewrites the stylesheet to the extension URI with the nonce", () => {
    const tags = render().match(/<link\b[^>]*>/g) ?? [];
    expect(tags).toHaveLength(1);
    expect(tags[0]).toContain('href="vscode-resource:/ext/media/assets/index-def.css"');
    expect(tags[0]).toContain(`nonce="${nonce}"`);
  });

  it("replaces a CSP and nonces already in the source", () => {
    const index = INDEX.replace(
      "<head>",
      `<head><meta http-equiv="Content-Security-Policy" content="default-src *">`,
    ).replace('<script type="module"', '<script nonce="stale" type="module"');
    const html = render(index);
    expect(cspOf(html)).toBe(buildCsp(nonce));
    expect(html).not.toContain("stale");
  });

  it("refuses an inline script instead of noncing it", () => {
    const index = INDEX.replace("</head>", "<script>alert(1)</script></head>");
    expect(() => render(index)).toThrow(/inline script/);
  });

  it("refuses remote, absolute and escaping asset URLs", () => {
    for (const src of ["https://example.invalid/x.js", "//example.invalid/x.js", "/assets/x.js", "../x.js", "a/../../x.js"]) {
      const index = INDEX.replace("./assets/index-abc.js", src);
      expect(() => render(index), src).toThrow(/not a bundle asset/);
    }
  });

  it("refuses a <base> element and an inline <style>", () => {
    expect(() => render(INDEX.replace("<head>", '<head><base href="https://example.invalid/">'))).toThrow(/base/);
    expect(() => render(INDEX.replace("</head>", "<style>body{}</style></head>"))).toThrow(/style/);
  });

  it("escapes asset URIs", () => {
    const html = renderPanelHtml(INDEX, { nonce, assetUri: (path) => `x"><script>${path}` });
    expect(html).not.toContain('x"><script>');
    expect(html).toContain("x&quot;&gt;&lt;script&gt;assets/index-abc.js");
  });

  it("rejects a nonce that could break out of the CSP", () => {
    expect(() => renderPanelHtml(INDEX, { nonce: "a' 'unsafe-inline", assetUri: (p) => p })).toThrow(/nonce/);
  });

  it("escapes quotes and ampersands", () => {
    expect(escapeHtml(`<a href="x">&'`)).toBe("&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
  });
});

describe("bundlePath", () => {
  it("accepts ./-relative and bare bundle paths", () => {
    expect(bundlePath("./assets/a.js")).toBe("assets/a.js");
    expect(bundlePath("assets/a.css")).toBe("assets/a.css");
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

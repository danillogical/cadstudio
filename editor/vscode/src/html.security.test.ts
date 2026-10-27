import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildCsp, makeNonce, renderPanelHtml } from "./html";

const NONCE = "dGVzdG5vbmNlMTIzNDU2Nw==";
const assetUri = (path: string) => `vscode-resource:/ext/media/${path}`;
const render = (html: string, nonce = NONCE) => renderPanelHtml(html, { nonce, assetUri });
const page = (head: string, body = '<div id="app"></div>') =>
  `<!doctype html><html><head>${head}</head><body>${body}</body></html>`;

const GOOD = page(
  '<script type="module" crossorigin src="./assets/a.js"></script><link rel="stylesheet" href="./assets/a.css">',
);

function directives(csp: string): Map<string, string[]> {
  return new Map(
    csp
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...values] = part.split(/\s+/);
        return [name, values] as const;
      }),
  );
}

describe("buildCsp", () => {
  it("forbids the network and everything remote, and allows only nonced script and style", () => {
    const d = directives(buildCsp(NONCE));
    expect(d.get("default-src")).toEqual(["'none'"]);
    expect(d.get("connect-src")).toEqual(["'none'"]);
    expect(d.get("script-src")).toEqual([`'nonce-${NONCE}'`]);
    expect(d.get("style-src")).toEqual([`'nonce-${NONCE}'`]);
    expect(d.get("base-uri")).toEqual(["'none'"]);
    expect(d.get("form-action")).toEqual(["'none'"]);
    expect([...d.keys()].sort()).toEqual(
      ["base-uri", "connect-src", "default-src", "form-action", "script-src", "style-src"].sort(),
    );
  });

  it("has no unsafe, wildcard, scheme or host source anywhere", () => {
    const csp = buildCsp(NONCE);
    for (const bad of ["unsafe-inline", "unsafe-eval", "unsafe-hashes", "strict-dynamic", "*", "http:", "https:", "ws:", "wss:", "data:", "blob:", "//", "self"]) {
      expect(csp).not.toContain(bad);
    }
  });

  it("includes the nonce only in script-src and style-src", () => {
    const csp = buildCsp(NONCE);
    expect(csp.split(NONCE)).toHaveLength(3);
  });
});

describe("renderPanelHtml: scripts and styles", () => {
  it("gives every script and stylesheet the nonce and a webview URI", () => {
    const html = render(
      page(
        '<script type="module" src="./assets/a.js"></script><script src="assets/b.js"></script>' +
          '<link rel="stylesheet" href="./assets/a.css"><link rel="stylesheet" href="assets/b.css">' +
          '<link rel="modulepreload" href="./assets/c.js">',
      ),
    );
    const scripts = html.match(/<script\b[^>]*>/g)!;
    expect(scripts).toHaveLength(2);
    for (const tag of scripts) expect(tag).toContain(`nonce="${NONCE}"`);
    const links = html.match(/<link\b[^>]*>/g)!;
    expect(links).toHaveLength(3);
    for (const tag of links) expect(tag).toContain(`nonce="${NONCE}"`);
    expect(html).toContain('src="vscode-resource:/ext/media/assets/a.js"');
    expect(html).toContain('src="vscode-resource:/ext/media/assets/b.js"');
    expect(html).toContain('href="vscode-resource:/ext/media/assets/a.css"');
    expect(html).toContain('href="vscode-resource:/ext/media/assets/b.css"');
    expect(html).toContain('href="vscode-resource:/ext/media/assets/c.js"');
    expect(html).not.toContain("./assets");
  });

  it("replaces an attacker-supplied nonce and keeps just one nonce attribute per tag", () => {
    const html = render(page('<script src="./assets/a.js" nonce="evil"></script><link rel="stylesheet" href="./assets/a.css" nonce="evil">'));
    expect(html).not.toContain("evil");
    for (const tag of html.match(/<(script|link)\b[^>]*>/g)!) expect(tag.match(/nonce=/g)).toHaveLength(1);
  });

  it("handles upper-case tags, unquoted and newline-separated attributes", () => {
    const html = render(page('<SCRIPT\n  TYPE=module\n  SRC=./assets/a.js></SCRIPT>'));
    expect(html).toMatch(/<script [^>]*src="vscode-resource:\/ext\/media\/assets\/a\.js"/);
    expect(html).toContain(`nonce="${NONCE}"`);
  });

  it("emits exactly one CSP meta, first in head, with the nonce of this render", () => {
    const html = render(page('<meta http-equiv="Content-Security-Policy" content="default-src *"><meta charset="utf-8"><script src="./assets/a.js"></script>'));
    const metas = html.match(/<meta http-equiv="Content-Security-Policy"[^>]*>/gi)!;
    expect(metas).toHaveLength(1);
    expect(metas[0]).toContain(buildCsp(NONCE));
    expect(html).not.toContain("default-src *");
    expect(html.indexOf(metas[0])).toBeLessThan(html.indexOf("<script"));
    expect(html.indexOf(metas[0])).toBeLessThan(html.indexOf('charset="utf-8"'));
    expect(html.indexOf("<head>") + "<head>".length).toBe(html.indexOf("\n<meta http-equiv"));
  });

  it("removes a differently-written CSP meta (single quotes, reordered attributes, mixed case)", () => {
    const html = render(page("<META CONTENT='default-src *' HTTP-EQUIV='content-security-policy'><script src=\"./assets/a.js\"></script>"));
    expect(html).not.toContain("default-src *");
  });
});

describe("renderPanelHtml: refusals", () => {
  const REFUSED: Array<[string, string]> = [
    ["a <base> tag", page('<base href="https://evil/"><script src="./assets/a.js"></script>')],
    ["an upper-case <BASE>", page('<BASE href="https://evil/">')],
    ["an inline script", page("<script>alert(1)</script>")],
    ["an inline module script", page('<script type="module">import("x")</script>')],
    ["an inline script that also has a src", page('<script src="./assets/a.js">alert(1)</script>')],
    ["an import map", page('<script type="importmap">{"imports":{}}</script>')],
    ["a script with no src", page("<script></script>")],
    ["a script with an empty src", page('<script src=""></script>')],
    ["a remote script", page('<script src="https://evil.example/x.js"></script>')],
    ["a protocol-relative script", page('<script src="//evil.example/x.js"></script>')],
    ["an absolute-path script", page('<script src="/assets/x.js"></script>')],
    ["a parent-directory script", page('<script src="../x.js"></script>')],
    ["a nested parent-directory script", page('<script src="./assets/../../x.js"></script>')],
    ["a javascript: script", page('<script src="javascript:alert(1)"></script>')],
    ["a data: script", page('<script src="data:text/javascript,alert(1)"></script>')],
    ["a script with a query", page('<script src="./assets/a.js?x=1"></script>')],
    ["a script with a backslash", page('<script src=".\\assets\\a.js"></script>')],
    ["a remote stylesheet", page('<link rel="stylesheet" href="https://evil.example/x.css">')],
    ["an absolute stylesheet", page('<link rel="stylesheet" href="/x.css">')],
    ["a parent-directory stylesheet", page('<link rel="stylesheet" href="../x.css">')],
    ["a remote icon link", page('<link rel="icon" href="https://evil.example/x.ico">')],
    ["an inline <style>", page("<style>body{}</style>")],
    ["an unclosed script", page('<script src="./assets/a.js">')],
    ["no <head>", '<html><body><script src="./assets/a.js"></script></body></html>'],
  ];

  it.each(REFUSED)("refuses %s", (_name, html) => {
    expect(() => render(html)).toThrow();
  });

  it.each(["", "abc def", "a';script-src *", "a\"b", "a;b", "<x>", "a\nb", "é"])("refuses nonce %j", (nonce) => {
    expect(() => render(GOOD, nonce)).toThrow(/nonce/);
  });

  it("escapes quotes in an asset URI so an attribute cannot be closed early", () => {
    const html = renderPanelHtml(GOOD, { nonce: NONCE, assetUri: () => 'x" onload="alert(1)' });
    expect(html).not.toMatch(/" onload="/);
    expect(html).toContain("&quot;");
  });
});

describe("nonce freshness", () => {
  it("makes a new base64 nonce of at least 16 bytes every time", () => {
    const seen = new Set(Array.from({ length: 200 }, () => makeNonce()));
    expect(seen.size).toBe(200);
    for (const nonce of seen) {
      expect(nonce).toMatch(/^[A-Za-z0-9+/]+={0,2}$/);
      expect(Buffer.from(nonce, "base64").length).toBeGreaterThanOrEqual(16);
    }
  });

  it("two renders of the same page use different nonces throughout", () => {
    const a = render(GOOD, makeNonce());
    const b = render(GOOD, makeNonce());
    const nonceOf = (html: string) => /nonce-([^']+)'/.exec(html)![1];
    expect(nonceOf(a)).not.toBe(nonceOf(b));
    expect(a).not.toContain(nonceOf(b));
    expect(b).not.toContain(nonceOf(a));
  });
});

describe("the built UI bundle", () => {
  const indexPath = fileURLToPath(new URL("../../../.vscode/extensions/cadstudio/media/index.html", import.meta.url));
  const index = readFileSync(indexPath, "utf8");

  it("renders under the strict CSP with every asset rewritten and nonced", () => {
    const html = render(index);
    const scripts = html.match(/<script\b[^>]*>/g) ?? [];
    expect(scripts.length).toBeGreaterThan(0);
    for (const tag of scripts) {
      expect(tag).toContain(`nonce="${NONCE}"`);
      expect(tag).toMatch(/src="vscode-resource:\/ext\/media\/assets\/[^"]+\.js"/);
    }
    for (const tag of html.match(/<link\b[^>]*>/g) ?? []) expect(tag).not.toMatch(/https?:|\/\//);
    expect(html).toContain("connect-src 'none'");
  });

  it("references only files that exist in the bundle", () => {
    const html = render(index);
    const refs = [...html.matchAll(/(?:src|href)="vscode-resource:\/ext\/media\/([^"]+)"/g)].map((m) => m[1]);
    expect(refs.length).toBeGreaterThan(0);
    for (const ref of refs) {
      expect(() => readFileSync(fileURLToPath(new URL(`../../../.vscode/extensions/cadstudio/media/${ref}`, import.meta.url)))).not.toThrow();
    }
  });
});

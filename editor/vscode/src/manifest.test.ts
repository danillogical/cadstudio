import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../..", import.meta.url));
const builtDir = `${root}/.vscode/extensions/cadstudio`;

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

describe("committed extension build", () => {
  const manifest = readJson(`${builtDir}/package.json`);

  it("has the workspace extension identity and engine", () => {
    expect(manifest.name).toBe("cadstudio");
    expect(manifest.publisher).toBe("danillogical");
    expect(manifest.engines).toEqual({ vscode: "^1.89.0" });
    expect(manifest.main).toBe("./dist/extension.js");
  });

  it("contributes the open command and activation events", () => {
    expect(manifest.contributes).toEqual({
      commands: [{ command: "cadstudio.openGui", title: "CADStudio: Open GUI" }],
    });
    expect(manifest.activationEvents).toEqual([
      "onCommand:cadstudio.openGui",
      "onUri",
    ]);
  });

  it("is disabled in untrusted workspaces", () => {
    expect(manifest.capabilities).toEqual({
      untrustedWorkspaces: { supported: false },
    });
  });

  it("carries only the runtime manifest keys", () => {
    expect(Object.keys(manifest).sort()).toEqual(
      [
        "activationEvents",
        "capabilities",
        "contributes",
        "description",
        "displayName",
        "engines",
        "main",
        "name",
        "publisher",
        "version",
      ].sort(),
    );
    expect(manifest.scripts).toBeUndefined();
    expect(manifest.devDependencies).toBeUndefined();
    expect(manifest.type).toBeUndefined();
  });

  it("is recommended for this workspace", () => {
    const extensions = readJson(`${root}/.vscode/extensions.json`);
    expect(extensions.recommendations).toContain(
      `${String(manifest.publisher)}.${String(manifest.name)}`,
    );
  });

  it("locks every package to the public npm registry", () => {
    const lock = readFileSync(`${root}/editor/vscode/package-lock.json`, "utf8");
    const urls = [...lock.matchAll(/"resolved":\s*"([^"]+)"/g)].map((m) => m[1]);
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) {
      expect(url.startsWith("https://registry.npmjs.org/")).toBe(true);
    }
  });
});

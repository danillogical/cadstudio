import { afterAll, describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const sourceDir = fileURLToPath(new URL("..", import.meta.url));
const committedDir = fileURLToPath(
  new URL("../../../.vscode/extensions/cadstudio", import.meta.url),
);

function listFiles(root: string, prefix = ""): string[] {
  const entries = readdirSync(join(root, prefix), { withFileTypes: true });
  return entries.flatMap((entry) => {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    return entry.isDirectory() ? listFiles(root, relative) : [relative];
  });
}

const tmp = mkdtempSync(join(tmpdir(), "cadstudio-build-"));

afterAll(() => {
  rmSync(tmp, { recursive: true, force: true });
});

describe("committed build", () => {
  it(
    "matches a fresh build; run `npm run build` in editor/vscode and commit the result",
    () => {
      execFileSync(process.execPath, [join(sourceDir, "build.mjs"), "--outdir", tmp], {
        cwd: sourceDir,
        stdio: "pipe",
      });

      const fresh = listFiles(tmp).sort();
      const committed = listFiles(committedDir).sort();
      expect(committed, "built file list is stale").toEqual(fresh);

      for (const file of fresh) {
        const expected = readFileSync(join(tmp, file));
        const actual = readFileSync(join(committedDir, file));
        expect(
          actual.equals(expected),
          `${file} is out of date; run \`npm run build\` in editor/vscode and commit the result`,
        ).toBe(true);
        expect(statSync(join(committedDir, file)).size).toBeGreaterThan(0);
      }
    },
    30_000,
  );
});

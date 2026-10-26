// Builds the workspace extension into .vscode/extensions/cadstudio.
import { build } from "esbuild";
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const defaultOut = resolve(here, "../../.vscode/extensions/cadstudio");

// The built manifest is a subset of the source manifest; tooling keys stay out.
const MANIFEST_KEYS = [
  "name",
  "displayName",
  "description",
  "version",
  "publisher",
  "engines",
  "main",
  "activationEvents",
  "contributes",
  "capabilities",
];

function parseOutDir(argv) {
  const i = argv.indexOf("--outdir");
  if (i === -1) return defaultOut;
  const value = argv[i + 1];
  if (!value) throw new Error("--outdir needs a directory");
  return resolve(value);
}

function writeManifest(outDir) {
  const source = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));
  const manifest = {};
  for (const key of MANIFEST_KEYS) manifest[key] = source[key];
  manifest.engines = { vscode: source.engines.vscode };
  writeFileSync(join(outDir, "package.json"), JSON.stringify(manifest, null, 2) + "\n");
}

async function main() {
  const outDir = parseOutDir(process.argv.slice(2));
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(join(outDir, "dist"), { recursive: true });

  const shared = {
    bundle: true,
    sourcemap: false,
    minify: false,
    metafile: false,
    absWorkingDir: here,
    logLevel: "warning",
  };
  await build({
    ...shared,
    entryPoints: ["src/extension.ts"],
    outfile: join(outDir, "dist/extension.js"),
    platform: "node",
    format: "cjs",
    target: "node18",
    external: ["vscode"],
  });
  await build({
    ...shared,
    entryPoints: ["src/webview.ts"],
    outfile: join(outDir, "dist/webview.js"),
    platform: "browser",
    format: "iife",
    target: "es2022",
  });

  writeManifest(outDir);
  copyFileSync(join(here, "README.extension.md"), join(outDir, "README.md"));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

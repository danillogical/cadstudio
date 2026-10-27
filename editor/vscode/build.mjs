// Builds the workspace extension into .vscode/extensions/cadstudio.
import { build } from "esbuild";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const defaultOut = resolve(here, "../../.vscode/extensions/cadstudio");
const uiDist = resolve(here, "../../ui/dist");

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

// Byte-for-byte copy of ui/dist into media/, in sorted order so the result never depends on readdir.
function copyTree(from, to) {
  mkdirSync(to, { recursive: true });
  const entries = readdirSync(from, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1));
  for (const entry of entries) {
    const source = join(from, entry.name);
    const target = join(to, entry.name);
    if (entry.isDirectory()) copyTree(source, target);
    else if (entry.isFile()) copyFileSync(source, target);
    else throw new Error(`ui/dist/${entry.name} is not a regular file`);
  }
}

async function main() {
  const outDir = parseOutDir(process.argv.slice(2));
  if (!existsSync(join(uiDist, "index.html"))) {
    throw new Error("ui/dist is missing; run `npm ci && npm run build` in ui/ first");
  }
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
  copyTree(uiDist, join(outDir, "media"));
  writeManifest(outDir);
  copyFileSync(join(here, "README.extension.md"), join(outDir, "README.md"));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

import { defineConfig } from "vitest/config";

// Relative asset URLs so the bundle also works from a VS Code webview.
export default defineConfig({
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "node" },
});

import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

const mock = fileURLToPath(new URL("./src/__mocks__/vscode.ts", import.meta.url));

export default defineConfig({
  resolve: {
    alias: { vscode: mock },
  },
  test: {
    environment: "node",
  },
});

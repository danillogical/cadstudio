import { vi } from "vitest";

// Minimal stand-in for the vscode API, enough to exercise activation and the webview.
const commandHandlers = new Map<string, (...args: unknown[]) => unknown>();

export interface FakeUri {
  path: string;
  query: string;
  toString(): string;
}

export function makeUri(path: string, query = ""): FakeUri {
  return { path, query, toString: () => `file://${path}${query ? `?${query}` : ""}` };
}

export interface FakeWebview {
  html: string;
  cspSource: string;
  asWebviewUri(uri: FakeUri): FakeUri;
  onDidReceiveMessage: ReturnType<typeof vi.fn>;
}

export interface FakePanel {
  viewType: string;
  title: string;
  webview: FakeWebview;
  reveal: ReturnType<typeof vi.fn>;
  onDidDispose: (listener: () => void) => { dispose(): void };
  dispose(): void;
}

export const registeredCommands = commandHandlers;

export const commands = {
  registerCommand: vi.fn((id: string, handler: (...args: unknown[]) => unknown) => {
    commandHandlers.set(id, handler);
    return { dispose: () => commandHandlers.delete(id) };
  }),
  executeCommand: vi.fn(async (id: string, ...args: unknown[]) => {
    const handler = commandHandlers.get(id);
    return handler?.(...args);
  }),
};

export const createdPanels: FakePanel[] = [];
export const uriHandlers: Array<{ handleUri(uri: FakeUri): unknown }> = [];

export const window = {
  createWebviewPanel: vi.fn(
    (viewType: string, title: string, _column: unknown, _options: unknown): FakePanel => {
      let disposeListener: (() => void) | undefined;
      const panel: FakePanel = {
        viewType,
        title,
        webview: {
          html: "",
          cspSource: "vscode-resource:",
          asWebviewUri: (uri: FakeUri) => makeUri(`vscode-resource:${uri.path}`),
          onDidReceiveMessage: vi.fn(),
        },
        reveal: vi.fn(),
        onDidDispose: (listener) => {
          disposeListener = listener;
          return { dispose: () => (disposeListener = undefined) };
        },
        dispose: () => disposeListener?.(),
      };
      createdPanels.push(panel);
      return panel;
    },
  ),
  registerUriHandler: vi.fn((handler: { handleUri(uri: FakeUri): unknown }) => {
    uriHandlers.push(handler);
    return { dispose: () => uriHandlers.splice(uriHandlers.indexOf(handler), 1) };
  }),
  showWarningMessage: vi.fn(async (_message: string) => undefined),
};

export const workspace = {
  workspaceFolders: [{ name: "cadstudio", uri: makeUri("/work/cadstudio") }] as
    | Array<{ name: string; uri: FakeUri }>
    | undefined,
};

export const Uri = {
  joinPath(base: FakeUri, ...parts: string[]): FakeUri {
    const joined = [base.path.replace(/\/$/, ""), ...parts].join("/");
    return makeUri(joined);
  },
};

export const ViewColumn = { Active: -1 };

export function reset(): void {
  commandHandlers.clear();
  createdPanels.length = 0;
  uriHandlers.length = 0;
  commands.registerCommand.mockClear();
  commands.executeCommand.mockClear();
  window.createWebviewPanel.mockClear();
  window.registerUriHandler.mockClear();
  window.showWarningMessage.mockClear();
  workspace.workspaceFolders = [{ name: "cadstudio", uri: makeUri("/work/cadstudio") }];
}

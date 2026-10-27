import { vi } from "vitest";

// Minimal stand-in for the vscode API, enough to exercise activation, the panel and its bridge.
const commandHandlers = new Map<string, (...args: unknown[]) => unknown>();

export interface FakeUri {
  path: string;
  fsPath: string;
  query: string;
  toString(): string;
}

export function makeUri(path: string, query = ""): FakeUri {
  return { path, fsPath: path, query, toString: () => `file://${path}${query ? `?${query}` : ""}` };
}

export interface FakeWebview {
  html: string;
  options: unknown;
  cspSource: string;
  asWebviewUri(uri: FakeUri): FakeUri;
  /** Messages the extension posted to the webview. */
  posted: unknown[];
  postMessage: ReturnType<typeof vi.fn>;
  onDidReceiveMessage: ReturnType<typeof vi.fn>;
  /** Deliver a message from the webview to every registered listener. */
  receive(message: unknown): void;
  listenerCount(): number;
}

export interface FakePanel {
  viewType: string;
  title: string;
  options: unknown;
  webview: FakeWebview;
  reveal: ReturnType<typeof vi.fn>;
  onDidDispose: (listener: () => void) => { dispose(): void };
  dispose(): void;
  disposed: boolean;
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
export const serializers = new Map<string, { deserializeWebviewPanel(panel: FakePanel, state: unknown): unknown }>();

export function makeWebview(): FakeWebview {
  const listeners = new Set<(message: unknown) => void>();
  const webview: FakeWebview = {
    html: "",
    options: undefined,
    cspSource: "vscode-resource:",
    asWebviewUri: (uri: FakeUri) => ({ ...makeUri(uri.path), toString: () => `vscode-resource:${uri.path}` }),
    posted: [],
    postMessage: vi.fn(async (message: unknown) => {
      webview.posted.push(message);
      return true;
    }),
    onDidReceiveMessage: vi.fn((listener: (message: unknown) => void) => {
      listeners.add(listener);
      return { dispose: () => listeners.delete(listener) };
    }),
    receive: (message) => listeners.forEach((listener) => listener(message)),
    listenerCount: () => listeners.size,
  };
  return webview;
}

/** A panel as VS Code creates it, or as it hands one to a serializer after a reload. */
export function makePanel(viewType: string, title: string, options?: unknown): FakePanel {
  const disposeListeners = new Set<() => void>();
  const panel: FakePanel = {
    viewType,
    title,
    options,
    webview: makeWebview(),
    reveal: vi.fn(),
    onDidDispose: (listener) => {
      disposeListeners.add(listener);
      return { dispose: () => disposeListeners.delete(listener) };
    },
    dispose: () => {
      if (panel.disposed) return;
      panel.disposed = true;
      disposeListeners.forEach((listener) => listener());
    },
    disposed: false,
  };
  if (options) panel.webview.options = options;
  return panel;
}

export const window = {
  createWebviewPanel: vi.fn(
    (viewType: string, title: string, _column: unknown, options: unknown): FakePanel => {
      const panel = makePanel(viewType, title, options);
      createdPanels.push(panel);
      return panel;
    },
  ),
  registerUriHandler: vi.fn((handler: { handleUri(uri: FakeUri): unknown }) => {
    uriHandlers.push(handler);
    return { dispose: () => uriHandlers.splice(uriHandlers.indexOf(handler), 1) };
  }),
  registerWebviewPanelSerializer: vi.fn(
    (viewType: string, serializer: { deserializeWebviewPanel(panel: FakePanel, state: unknown): unknown }) => {
      serializers.set(viewType, serializer);
      return { dispose: () => serializers.delete(viewType) };
    },
  ),
  showWarningMessage: vi.fn(async (_message: string) => undefined),
  showErrorMessage: vi.fn(async (_message: string) => undefined),
};

function defaultFolders(): Array<{ name: string; uri: FakeUri; index: number }> {
  return [{ name: "cadstudio", uri: makeUri("/work/cadstudio"), index: 0 }];
}

export const workspace = {
  isTrusted: true,
  workspaceFolders: defaultFolders() as Array<{ name: string; uri: FakeUri; index: number }> | undefined,
};

export const Uri = {
  joinPath(base: FakeUri, ...parts: string[]): FakeUri {
    const joined = [base.path.replace(/\/$/, ""), ...parts].join("/");
    return makeUri(joined);
  },
};

export const ViewColumn = { Active: -1 };

export const TaskRevealKind = { Always: 1, Silent: 2, Never: 3 };
export const TaskPanelKind = { Shared: 1, Dedicated: 2, New: 3 };

export class ShellExecution {
  constructor(
    readonly command: string,
    readonly args: string[],
    readonly options?: { cwd?: string },
  ) {}
}

export class Task {
  isBackground = false;
  presentationOptions: unknown;
  constructor(
    readonly definition: { type: string; [key: string]: unknown },
    readonly scope: unknown,
    readonly name: string,
    readonly source: string,
    readonly execution: ShellExecution,
  ) {}
}

type TaskEvent = { execution: { task: Task }; exitCode?: number };

/** Stand-in for `vscode.tasks`: tests push executions and fire the end events by hand. */
const endProcessListeners = new Set<(event: TaskEvent) => void>();
const endTaskListeners = new Set<(event: TaskEvent) => void>();
export const tasks = {
  taskExecutions: [] as Array<{ task: Task }>,
  executeTask: vi.fn(async (task: Task) => {
    const execution = { task };
    tasks.taskExecutions.push(execution);
    return execution;
  }),
  onDidEndTaskProcess: vi.fn((listener: (event: TaskEvent) => void) => {
    endProcessListeners.add(listener);
    return { dispose: () => endProcessListeners.delete(listener) };
  }),
  onDidEndTask: vi.fn((listener: (event: TaskEvent) => void) => {
    endTaskListeners.add(listener);
    return { dispose: () => endTaskListeners.delete(listener) };
  }),
  fireEndProcess: (event: TaskEvent) => [...endProcessListeners].forEach((listener) => listener(event)),
  fireEndTask: (event: TaskEvent) => [...endTaskListeners].forEach((listener) => listener(event)),
  listenerCount: () => endProcessListeners.size + endTaskListeners.size,
};

export function reset(): void {
  commandHandlers.clear();
  createdPanels.length = 0;
  uriHandlers.length = 0;
  serializers.clear();
  commands.registerCommand.mockClear();
  commands.executeCommand.mockClear();
  window.createWebviewPanel.mockClear();
  window.registerUriHandler.mockClear();
  window.registerWebviewPanelSerializer.mockClear();
  window.showWarningMessage.mockClear();
  window.showErrorMessage.mockClear();
  workspace.isTrusted = true;
  workspace.workspaceFolders = defaultFolders();
  tasks.taskExecutions.length = 0;
  tasks.executeTask.mockClear();
  tasks.onDidEndTaskProcess.mockClear();
  tasks.onDidEndTask.mockClear();
  endProcessListeners.clear();
  endTaskListeners.clear();
}

/** The VS Code task that runs `cad gui serve` for this workspace. */
import * as vscode from "vscode";
import type { StartedTask } from "./service";

export const TASK_TYPE = "cadstudio";
export const SERVE_TASK = "serve";
export const SERVE_TASK_NAME = "GUI service";
/** `uv run --frozen --extra physics cad gui serve --no-browser --json`, as the plan specifies. */
export const SERVE_COMMAND = "uv";
export const SERVE_ARGS = ["run", "--frozen", "--extra", "physics", "cad", "gui", "serve", "--no-browser", "--json"];

export function isServeTask(task: vscode.Task): boolean {
  return task.definition.type === TASK_TYPE && task.definition.task === SERVE_TASK;
}

export function makeServeTask(folder: vscode.WorkspaceFolder): vscode.Task {
  const task = new vscode.Task(
    { type: TASK_TYPE, task: SERVE_TASK },
    folder,
    SERVE_TASK_NAME,
    "CADStudio",
    new vscode.ShellExecution(SERVE_COMMAND, SERVE_ARGS, { cwd: folder.uri.fsPath }),
  );
  task.isBackground = true;
  task.presentationOptions = {
    reveal: vscode.TaskRevealKind.Silent,
    panel: vscode.TaskPanelKind.Dedicated,
    focus: false,
    clear: false,
    echo: true,
  };
  return task;
}

/**
 * Only one serve task runs per window, so any ending serve task is ours. Listeners are registered
 * outside the promise, so a failing registration throws here instead of rejecting `exited` unhandled.
 */
function watchExit(): StartedTask {
  const listeners: vscode.Disposable[] = [];
  const dispose = () => listeners.splice(0).forEach((listener) => listener.dispose());
  let settle: (code: number | undefined) => void = () => {};
  const exited = new Promise<number | undefined>((resolve) => {
    settle = resolve;
  });
  try {
    listeners.push(
      vscode.tasks.onDidEndTaskProcess((event) => {
        if (isServeTask(event.execution.task)) settle(event.exitCode);
      }),
    );
    listeners.push(
      vscode.tasks.onDidEndTask((event) => {
        if (isServeTask(event.execution.task)) settle(undefined);
      }),
    );
  } catch (error) {
    dispose();
    throw error;
  }
  void exited.then(dispose);
  return { exited, dispose };
}

/** Start the serve task, or attach to the one already running, and report when it exits. */
export async function startServeTask(folder: vscode.WorkspaceFolder): Promise<StartedTask> {
  const started = watchExit();
  if (vscode.tasks.taskExecutions.some((execution) => isServeTask(execution.task))) return started;
  try {
    await vscode.tasks.executeTask(makeServeTask(folder));
  } catch (error) {
    started.dispose?.();
    throw error;
  }
  return started;
}

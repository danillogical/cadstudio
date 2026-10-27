import { beforeEach, describe, expect, it } from "vitest";
import type { WorkspaceFolder } from "vscode";
import { flush } from "./test-utils";
import { isServeTask, makeServeTask, SERVE_ARGS, SERVE_COMMAND, startServeTask } from "./tasks";
import * as fake from "./__mocks__/vscode";

const folder = { uri: fake.makeUri("/work/cadstudio"), name: "cadstudio", index: 0 } as unknown as WorkspaceFolder;

beforeEach(() => fake.reset());

describe("serve task", () => {
  it("runs the plan's command in the workspace folder, as a silent background task", () => {
    const task = makeServeTask(folder) as unknown as fake.Task;
    expect(task.definition).toEqual({ type: "cadstudio", task: "serve" });
    expect(task.execution.command).toBe("uv");
    expect(task.execution.args).toEqual(["run", "--frozen", "--extra", "physics", "cad", "gui", "serve", "--no-browser", "--json"]);
    expect(SERVE_COMMAND).toBe("uv");
    expect(SERVE_ARGS).toContain("--no-browser");
    expect(task.execution.options).toEqual({ cwd: "/work/cadstudio" });
    expect(task.isBackground).toBe(true);
  });

  it("recognises only its own task definition", () => {
    expect(isServeTask(makeServeTask(folder))).toBe(true);
    const other = new fake.Task({ type: "shell", task: "serve" }, folder, "x", "y", new fake.ShellExecution("ls", []));
    expect(isServeTask(other as never)).toBe(false);
    const another = new fake.Task({ type: "cadstudio", task: "other" }, folder, "x", "y", new fake.ShellExecution("ls", []));
    expect(isServeTask(another as never)).toBe(false);
  });

  it("starts the task once, and reuses one that is already running", async () => {
    await startServeTask(folder);
    expect(fake.tasks.executeTask).toHaveBeenCalledTimes(1);
    await startServeTask(folder);
    expect(fake.tasks.executeTask).toHaveBeenCalledTimes(1);
  });

  it("reports the exit code of the serve task, ignores other tasks, and drops its listeners", async () => {
    const started = await startServeTask(folder);
    let code: number | undefined | "pending" = "pending";
    void started.exited.then((value) => (code = value));
    const other = new fake.Task({ type: "shell" }, folder, "o", "o", new fake.ShellExecution("ls", []));
    fake.tasks.fireEndProcess({ execution: { task: other }, exitCode: 9 });
    await flush();
    expect(code).toBe("pending");
    fake.tasks.fireEndProcess({ execution: { task: makeServeTask(folder) as never }, exitCode: 3 });
    await flush();
    expect(code).toBe(3);
    expect(fake.tasks.listenerCount()).toBe(0);
  });

  it("settles with undefined when the task ends without a process exit code", async () => {
    const started = await startServeTask(folder);
    fake.tasks.fireEndTask({ execution: { task: makeServeTask(folder) as never } });
    expect(await started.exited).toBeUndefined();
  });

  it("disposes its listeners when asked to, and when the task cannot be started", async () => {
    const started = await startServeTask(folder);
    expect(fake.tasks.listenerCount()).toBe(2);
    started.dispose?.();
    expect(fake.tasks.listenerCount()).toBe(0);

    fake.tasks.taskExecutions.length = 0; // nothing running, so a new task must be started
    fake.tasks.executeTask.mockRejectedValueOnce(new Error("no shell"));
    await expect(startServeTask(folder)).rejects.toThrow("no shell");
    expect(fake.tasks.listenerCount()).toBe(0);
  });
});

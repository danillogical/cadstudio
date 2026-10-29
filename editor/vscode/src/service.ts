/**
 * Finding (and if need be starting) the workspace's GUI service. The service registers itself in
 * `<workspace>/.cadstudio/gui/service.json`; a record is used only when it parses, names this workspace
 * as its repo root, and the process on its port answers `/v1/health` as that same service.
 * All I/O is injected through `ServiceDeps`, so the logic here is testable without a service.
 */
import { join } from "node:path";

export const PROTOCOL_VERSION = 1;
/** Matches the smoke script: a first `uv run` may have to sync the environment. */
export const START_TIMEOUT_MS = 180_000;
export const POLL_INTERVAL_MS = 500;

/** The fields of `service.json` the host relies on. The token never leaves the host. */
export interface ServiceRecord {
  pid: number;
  port: number;
  token: string;
  repoRoot: string;
  protocolVersion: number;
}

export function discoveryPath(workspaceRoot: string): string {
  return join(workspaceRoot, ".cadstudio", "gui", "service.json");
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

/** Parse `service.json`; null when it is not JSON or misses a field the host needs. */
export function parseDiscovery(text: string): ServiceRecord | null {
  let doc: unknown;
  try {
    doc = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) return null;
  const record = doc as Record<string, unknown>;
  const { pid, port, token, repoRoot, protocolVersion } = record;
  if (!isPositiveInt(pid) || !isPositiveInt(port) || port > 65535) return null;
  if (typeof token !== "string" || token.length === 0) return null;
  if (typeof repoRoot !== "string" || repoRoot.length === 0) return null;
  if (protocolVersion !== PROTOCOL_VERSION) return null;
  return { pid, port, token, repoRoot, protocolVersion };
}

/** Whether a `/v1/health` body is the registered service for `workspaceRoot`. */
export function isHealthy(health: unknown, record: ServiceRecord, workspaceRoot: string): boolean {
  if (typeof health !== "object" || health === null) return false;
  const body = health as Record<string, unknown>;
  return (
    body.service === "cadstudio" &&
    body.protocolVersion === PROTOCOL_VERSION &&
    body.repoRoot === workspaceRoot &&
    body.pid === record.pid
  );
}

/** A started serve task; `exited` settles with its exit code when the process ends. */
export interface StartedTask {
  exited: Promise<number | undefined>;
  /** Stop watching for the exit once the wait is over. */
  dispose?(): void;
}

export interface ServiceDeps {
  /** The workspace folder, canonicalised the way the service canonicalises its repo root. */
  workspaceRoot: string;
  /** File contents, or null when the file cannot be read. */
  readFile(path: string): Promise<string | null>;
  /** The parsed `/v1/health` body on 127.0.0.1:`port`, or null on any failure. */
  health(port: number): Promise<unknown>;
  /** Start `cad gui serve` in a VS Code task (reusing one that is already running). */
  startService(): Promise<StartedTask>;
  sleep(ms: number): Promise<void>;
  now(): number;
}

export class ServiceUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ServiceUnavailableError";
  }
}

/** The registered, healthy service for this workspace, or null. Never starts anything. */
export async function findService(deps: ServiceDeps): Promise<ServiceRecord | null> {
  const text = await deps.readFile(discoveryPath(deps.workspaceRoot));
  if (text === null) return null;
  const record = parseDiscovery(text);
  if (!record || record.repoRoot !== deps.workspaceRoot) return null;
  const health = await deps.health(record.port);
  return isHealthy(health, record, deps.workspaceRoot) ? record : null;
}

/**
 * Poll until a healthy service registers. Gives up at the deadline, or soon after the task
 * exits (a `cad gui serve` that found a service already running exits 0, so look once more).
 */
export async function waitForService(
  deps: ServiceDeps,
  task: StartedTask,
  timeoutMs = START_TIMEOUT_MS,
  pollMs = POLL_INTERVAL_MS,
): Promise<ServiceRecord> {
  const ended: { done: boolean; code?: number } = { done: false };
  void task.exited.then((code) => {
    ended.done = true;
    ended.code = code;
  });
  const deadline = deps.now() + timeoutMs;
  for (;;) {
    const found = await findService(deps);
    if (found) return found;
    if (ended.done) {
      const again = await findService(deps);
      if (again) return again;
      throw new ServiceUnavailableError(
        `\`cad gui serve\` exited (code ${ended.code ?? "unknown"}) without registering a healthy service; ` +
          "see the CADStudio GUI service terminal",
      );
    }
    if (deps.now() >= deadline) {
      throw new ServiceUnavailableError(
        `the GUI service did not become healthy within ${Math.round(timeoutMs / 1000)} s; ` +
          "see the CADStudio GUI service terminal",
      );
    }
    await deps.sleep(pollMs);
  }
}

/**
 * Caches the service record for one workspace. `get()` reuses a registered healthy service or
 * starts one and waits; concurrent callers share one attempt, so only one task is ever started.
 * `invalidate()` drops the cache after a refused connection or a rejected token.
 */
export class ServiceLocator {
  private cached: ServiceRecord | null = null;
  private inflight: Promise<ServiceRecord> | null = null;

  constructor(
    private readonly deps: ServiceDeps,
    private readonly timeoutMs = START_TIMEOUT_MS,
    private readonly pollMs = POLL_INTERVAL_MS,
  ) {}

  get workspaceRoot(): string {
    return this.deps.workspaceRoot;
  }

  /** A healthy service, started if necessary; rejects with `ServiceUnavailableError`. */
  get(): Promise<ServiceRecord> {
    if (this.cached) return Promise.resolve(this.cached);
    if (!this.inflight) {
      this.inflight = this.locate().finally(() => {
        this.inflight = null;
      });
    }
    return this.inflight;
  }

  /** The cached or registered healthy service, without starting one; null when there is none. */
  async find(): Promise<ServiceRecord | null> {
    if (this.cached) return this.cached;
    if (this.inflight) return this.inflight.catch(() => null);
    const found = await findService(this.deps);
    if (found) this.cached = found;
    return found;
  }

  invalidate(record?: ServiceRecord): void {
    if (!record || this.cached === record) this.cached = null;
  }

  private async locate(): Promise<ServiceRecord> {
    const found = await findService(this.deps);
    if (found) {
      this.cached = found;
      return found;
    }
    let task: StartedTask;
    try {
      task = await this.deps.startService();
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new ServiceUnavailableError(`could not start \`cad gui serve\`: ${reason}`);
    }
    try {
      const started = await waitForService(this.deps, task, this.timeoutMs, this.pollMs);
      this.cached = started;
      return started;
    } finally {
      task.dispose?.();
    }
  }
}

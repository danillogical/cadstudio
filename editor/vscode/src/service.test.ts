import { describe, expect, it, vi } from "vitest";
import {
  discoveryPath,
  findService,
  isHealthy,
  parseDiscovery,
  PROTOCOL_VERSION,
  ServiceLocator,
  ServiceUnavailableError,
  waitForService,
  type ServiceDeps,
  type ServiceRecord,
  type StartedTask,
} from "./service";

const ROOT = "/real/repo";
const REC: ServiceRecord = { pid: 77, port: 4001, token: "tok", repoRoot: ROOT, protocolVersion: PROTOCOL_VERSION };
const doc = (overrides: Record<string, unknown> = {}) => JSON.stringify({ ...REC, startedAt: 1, ...overrides });
const healthFor = (rec: ServiceRecord = REC, overrides: Record<string, unknown> = {}) => ({
  schemaVersion: 1,
  service: "cadstudio",
  protocolVersion: rec.protocolVersion,
  repoRoot: rec.repoRoot,
  pid: rec.pid,
  ...overrides,
});

describe("parseDiscovery", () => {
  it("reads the fields the host needs and ignores the rest", () => {
    expect(parseDiscovery(doc())).toEqual(REC);
  });

  it.each([
    ["not json", "{"],
    ["empty", ""],
    ["an array", "[]"],
    ["null", "null"],
    ["a string", '"x"'],
    ["no pid", doc({ pid: undefined })],
    ["pid zero", doc({ pid: 0 })],
    ["pid string", doc({ pid: "1" })],
    ["pid float", doc({ pid: 1.5 })],
    ["port zero", doc({ port: 0 })],
    ["port too large", doc({ port: 65536 })],
    ["port string", doc({ port: "80" })],
    ["no token", doc({ token: undefined })],
    ["empty token", doc({ token: "" })],
    ["numeric token", doc({ token: 5 })],
    ["no repoRoot", doc({ repoRoot: undefined })],
    ["empty repoRoot", doc({ repoRoot: "" })],
    ["other protocol", doc({ protocolVersion: 2 })],
    ["no protocol", doc({ protocolVersion: undefined })],
  ])("rejects %s", (_name, text) => {
    expect(parseDiscovery(text)).toBeNull();
  });

  it("places the file at out/.gui/service.json", () => {
    expect(discoveryPath("/w")).toBe("/w/out/.gui/service.json");
  });
});

describe("isHealthy", () => {
  it("accepts the matching service", () => {
    expect(isHealthy(healthFor(), REC, ROOT)).toBe(true);
  });

  it.each([
    ["a different repo root", { repoRoot: "/other/repo" }],
    ["a repo root that differs only by a trailing slash", { repoRoot: ROOT + "/" }],
    ["a different pid", { pid: 78 }],
    ["a string pid", { pid: "77" }],
    ["a different protocol", { protocolVersion: 2 }],
    ["no protocol", { protocolVersion: undefined }],
    ["another service name", { service: "something-else" }],
    ["no service name", { service: undefined }],
  ])("refuses %s", (_name, override) => {
    expect(isHealthy(healthFor(REC, override), REC, ROOT)).toBe(false);
  });

  it("refuses a record whose repoRoot differs from the workspace even if health agrees with the record", () => {
    const foreign = { ...REC, repoRoot: "/foreign" };
    expect(isHealthy(healthFor(foreign), foreign, ROOT)).toBe(false);
  });

  it.each([null, undefined, "ok", 5, true])("refuses a non-object health body %j", (body) => {
    expect(isHealthy(body, REC, ROOT)).toBe(false);
  });
});

function makeDeps(overrides: Partial<ServiceDeps> = {}): ServiceDeps & { clock: { t: number } } {
  const clock = { t: 0 };
  return {
    clock,
    workspaceRoot: ROOT,
    readFile: vi.fn(async () => null),
    health: vi.fn(async () => null),
    startService: vi.fn(async () => ({ exited: new Promise<number | undefined>(() => {}) })),
    sleep: vi.fn(async (ms: number) => void (clock.t += ms)),
    now: () => clock.t,
    ...overrides,
  };
}

describe("findService", () => {
  it("returns null without a service.json and never probes a port", async () => {
    const deps = makeDeps();
    expect(await findService(deps)).toBeNull();
    expect(deps.health).not.toHaveBeenCalled();
    expect(deps.readFile).toHaveBeenCalledWith("/real/repo/out/.gui/service.json");
  });

  it("returns null for an unparseable service.json", async () => {
    const deps = makeDeps({ readFile: vi.fn(async () => "{") });
    expect(await findService(deps)).toBeNull();
    expect(deps.health).not.toHaveBeenCalled();
  });

  it("does not reuse a foreign repo's record, and does not even probe its port", async () => {
    const deps = makeDeps({ readFile: vi.fn(async () => doc({ repoRoot: "/foreign" })) });
    expect(await findService(deps)).toBeNull();
    expect(deps.health).not.toHaveBeenCalled();
  });

  it("does not reuse a stale record whose port answers nothing", async () => {
    const deps = makeDeps({ readFile: vi.fn(async () => doc()), health: vi.fn(async () => null) });
    expect(await findService(deps)).toBeNull();
    expect(deps.health).toHaveBeenCalledWith(4001);
  });

  it("does not reuse a record when another process took the port (pid mismatch)", async () => {
    const deps = makeDeps({ readFile: vi.fn(async () => doc()), health: vi.fn(async () => healthFor(REC, { pid: 999 })) });
    expect(await findService(deps)).toBeNull();
  });

  it("does not reuse a record whose service reports a different repo root or protocol", async () => {
    for (const override of [{ repoRoot: "/other" }, { protocolVersion: 9 }]) {
      const deps = makeDeps({ readFile: vi.fn(async () => doc()), health: vi.fn(async () => healthFor(REC, override)) });
      expect(await findService(deps)).toBeNull();
    }
  });

  it("returns the record of a healthy service", async () => {
    const deps = makeDeps({ readFile: vi.fn(async () => doc()), health: vi.fn(async () => healthFor()) });
    expect(await findService(deps)).toEqual(REC);
  });
});

function task() {
  let exit!: (code?: number) => void;
  const exited = new Promise<number | undefined>((resolve) => (exit = resolve));
  const dispose = vi.fn<() => void>();
  return { exited, exit, dispose } satisfies StartedTask & { exit(code?: number): void };
}

describe("waitForService", () => {
  it("polls until a healthy service registers", async () => {
    let calls = 0;
    const deps = makeDeps({
      readFile: vi.fn(async () => (++calls >= 3 ? doc() : null)),
      health: vi.fn(async () => healthFor()),
    });
    const found = await waitForService(deps, task(), 10_000, 500);
    expect(found).toEqual(REC);
    expect(deps.sleep).toHaveBeenCalledTimes(2);
    expect(deps.sleep).toHaveBeenCalledWith(500);
  });

  it("stops early, without waiting for the deadline, when the task exits", async () => {
    const t = task();
    const deps = makeDeps();
    const waiting = waitForService(deps, t, 180_000, 500);
    t.exit(3);
    await expect(waiting).rejects.toThrow(/exited \(code 3\)/);
    await expect(waiting).rejects.toBeInstanceOf(ServiceUnavailableError);
    expect(deps.clock.t).toBeLessThan(5_000);
  });

  it("reports an unknown exit code", async () => {
    const t = task();
    t.exit(undefined);
    await expect(waitForService(makeDeps(), t, 180_000, 500)).rejects.toThrow(/code unknown/);
  });

  it("looks once more after the task exits, since a duplicate serve exits 0 with the service running", async () => {
    const t = task();
    t.exit(0);
    let registered = false;
    const deps = makeDeps({
      readFile: vi.fn(async () => (registered ? doc() : null)),
      health: vi.fn(async () => healthFor()),
      sleep: vi.fn(async () => {
        registered = true;
      }),
    });
    // First poll finds nothing, but by the time the exit is noticed the service is registered.
    deps.readFile = vi.fn(async () => {
      const text = registered ? doc() : null;
      registered = true;
      return text;
    });
    expect(await waitForService(deps, t, 180_000, 500)).toEqual(REC);
  });

  it("times out when the task keeps running without a healthy service", async () => {
    const deps = makeDeps();
    await expect(waitForService(deps, task(), 2_000, 500)).rejects.toThrow(/did not become healthy within 2 s/);
    expect(deps.clock.t).toBeGreaterThanOrEqual(2_000);
    expect(deps.clock.t).toBeLessThan(3_000);
  });
});

describe("ServiceLocator", () => {
  function healthyDeps(overrides: Partial<ServiceDeps> = {}) {
    return makeDeps({ readFile: vi.fn(async () => doc()), health: vi.fn(async () => healthFor()), ...overrides });
  }

  it("reuses a healthy registered service and never starts one", async () => {
    const deps = healthyDeps();
    const locator = new ServiceLocator(deps);
    expect(await locator.get()).toEqual(REC);
    expect(deps.startService).not.toHaveBeenCalled();
  });

  it("caches the record: later calls do no further probing", async () => {
    const deps = healthyDeps();
    const locator = new ServiceLocator(deps);
    await locator.get();
    await locator.get();
    await locator.find();
    expect(deps.health).toHaveBeenCalledTimes(1);
    expect(deps.readFile).toHaveBeenCalledTimes(1);
  });

  it("starts at most one task for concurrent callers", async () => {
    let registered = false;
    const t = task();
    const deps = makeDeps({
      readFile: vi.fn(async () => (registered ? doc() : null)),
      health: vi.fn(async () => healthFor()),
      startService: vi.fn(async () => t),
      sleep: vi.fn(async () => {
        registered = true;
      }),
    });
    const locator = new ServiceLocator(deps, 10_000, 100);
    const results = await Promise.all(Array.from({ length: 8 }, () => locator.get()));
    expect(deps.startService).toHaveBeenCalledTimes(1);
    for (const r of results) expect(r).toEqual(REC);
    expect(t.dispose).toHaveBeenCalledTimes(1);
  });

  it("find() does not start a service", async () => {
    const deps = makeDeps();
    const locator = new ServiceLocator(deps);
    expect(await locator.find()).toBeNull();
    expect(deps.startService).not.toHaveBeenCalled();
  });

  it("find() joins an attempt already in flight and sees null if it fails", async () => {
    const deps = makeDeps({ startService: vi.fn(async () => { throw new Error("no uv"); }) });
    const locator = new ServiceLocator(deps);
    const getting = locator.get();
    const finding = locator.find();
    await expect(getting).rejects.toBeInstanceOf(ServiceUnavailableError);
    expect(await finding).toBeNull();
  });

  it("wraps a failure to start the task, and lets the next get() try again", async () => {
    const start = vi.fn().mockRejectedValueOnce(new Error("no uv")).mockResolvedValue(task());
    let registered = false;
    const deps = makeDeps({
      readFile: vi.fn(async () => (registered ? doc() : null)),
      health: vi.fn(async () => healthFor()),
      startService: start,
      sleep: vi.fn(async () => {
        registered = true;
      }),
    });
    const locator = new ServiceLocator(deps, 10_000, 100);
    await expect(locator.get()).rejects.toThrow(/could not start `cad gui serve`: no uv/);
    expect(await locator.get()).toEqual(REC);
    expect(start).toHaveBeenCalledTimes(2);
  });

  it("disposes the task watcher even when waiting fails", async () => {
    const t = task();
    const deps = makeDeps({ startService: vi.fn(async () => t) });
    const locator = new ServiceLocator(deps, 1_000, 500);
    await expect(locator.get()).rejects.toBeInstanceOf(ServiceUnavailableError);
    expect(t.dispose).toHaveBeenCalledTimes(1);
  });

  it("invalidate() with the cached record forces a fresh probe; with another record it does not", async () => {
    const deps = healthyDeps();
    const locator = new ServiceLocator(deps);
    const first = await locator.get();
    locator.invalidate({ ...first });
    await locator.get();
    expect(deps.health).toHaveBeenCalledTimes(1);
    locator.invalidate(first);
    await locator.get();
    expect(deps.health).toHaveBeenCalledTimes(2);
    locator.invalidate();
    await locator.get();
    expect(deps.health).toHaveBeenCalledTimes(3);
    expect(deps.startService).not.toHaveBeenCalled();
  });

  it("exposes the workspace root", () => {
    expect(new ServiceLocator(makeDeps()).workspaceRoot).toBe(ROOT);
  });
});

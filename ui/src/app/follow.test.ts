// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CadStudioTransport } from "../transport/types";
import { FOLLOW_RENEW_MS, FOLLOW_STORAGE_KEY, FollowManager } from "./follow";

function fakeTransport() {
  const follow = vi.fn(async (model: string) => ({ model, expiresAt: 0, leaseSeconds: 60, following: [] }));
  const unfollow = vi.fn(async (_model: string) => {});
  return { follow, unfollow, transport: { follow, unfollow } as unknown as CadStudioTransport };
}

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("FollowManager: default and persistence", () => {
  it("is on by default", () => {
    const { transport } = fakeTransport();
    expect(new FollowManager({ transport, storage: memoryStorage() }).enabled).toBe(true);
    expect(new FollowManager({ transport }).enabled).toBe(true);
  });

  it("is on with the real sessionStorage empty, and off once 'off' is stored there", () => {
    const { transport } = fakeTransport();
    expect(new FollowManager({ transport }).enabled).toBe(true);
    sessionStorage.setItem(FOLLOW_STORAGE_KEY, "off");
    expect(new FollowManager({ transport }).enabled).toBe(false);
  });

  it("persists the choice in sessionStorage and a new manager reads it back", () => {
    const { transport } = fakeTransport();
    const first = new FollowManager({ transport });
    first.setEnabled(false);
    expect(sessionStorage.getItem(FOLLOW_STORAGE_KEY)).toBe("off");
    expect(new FollowManager({ transport }).enabled).toBe(false);
    first.setEnabled(true);
    expect(sessionStorage.getItem(FOLLOW_STORAGE_KEY)).toBe("on");
    expect(new FollowManager({ transport }).enabled).toBe(true);
  });

  it("survives storage that throws", () => {
    const { transport } = fakeTransport();
    const broken = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    const manager = new FollowManager({ transport, storage: broken });
    expect(manager.enabled).toBe(true);
    expect(() => manager.setEnabled(false)).not.toThrow();
    expect(manager.enabled).toBe(false);
  });

  it("does not follow anything while off, even for a selected model", () => {
    const { transport, follow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage({ [FOLLOW_STORAGE_KEY]: "off" }) });
    manager.setModel("p/m");
    vi.advanceTimersByTime(FOLLOW_RENEW_MS * 3);
    expect(follow).not.toHaveBeenCalled();
  });
});

describe("FollowManager: follow and renew", () => {
  it("POSTs follow for the selected model right away, with no unfollow", () => {
    const { transport, follow, unfollow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/m");
    expect(follow.mock.calls).toEqual([["p/m"]]);
    expect(unfollow).not.toHaveBeenCalled();
    expect(manager.following).toBe("p/m");
  });

  it("renews every 20 s, not before", () => {
    expect(FOLLOW_RENEW_MS).toBe(20_000);
    const { transport, follow } = fakeTransport();
    new FollowManager({ transport, storage: memoryStorage() }).setModel("p/m");
    vi.advanceTimersByTime(19_999);
    expect(follow).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(follow).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(20_000);
    expect(follow).toHaveBeenCalledTimes(3);
    vi.advanceTimersByTime(60_000);
    expect(follow).toHaveBeenCalledTimes(6);
    expect(follow.mock.calls.every(([model]) => model === "p/m")).toBe(true);
  });

  it("renews well inside the service's 60 s lease", () => {
    expect(FOLLOW_RENEW_MS).toBeLessThan(60_000 / 2);
  });

  it("does not stack a second timer when the same model is set again", () => {
    const { transport, follow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/m");
    manager.setModel("p/m");
    expect(follow).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(FOLLOW_RENEW_MS);
    expect(follow).toHaveBeenCalledTimes(2);
  });

  it("reports following, and the error text when the service refuses", async () => {
    const statuses: string[] = [];
    const { transport, follow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage(), onStatus: (text) => statuses.push(text) });
    manager.setModel("p/m");
    await vi.advanceTimersByTimeAsync(0);
    expect(statuses.at(-1)).toBe("following");
    follow.mockRejectedValueOnce(new Error("no service"));
    await vi.advanceTimersByTimeAsync(FOLLOW_RENEW_MS);
    expect(statuses.at(-1)).toBe("follow unavailable: no service");
    // A failed renewal does not stop the timer.
    await vi.advanceTimersByTimeAsync(FOLLOW_RENEW_MS);
    expect(follow).toHaveBeenCalledTimes(3);
    expect(statuses.at(-1)).toBe("following");
  });
});

describe("FollowManager: unfollow", () => {
  it("unfollows the old model and follows the new one when the model changes", () => {
    const { transport, follow, unfollow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/a");
    manager.setModel("p/b");
    expect(unfollow.mock.calls).toEqual([["p/a"]]);
    expect(follow.mock.calls).toEqual([["p/a"], ["p/b"]]);
    expect(manager.following).toBe("p/b");
  });

  it("renews only the new model after a change", () => {
    const { transport, follow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/a");
    manager.setModel("p/b");
    follow.mockClear();
    vi.advanceTimersByTime(FOLLOW_RENEW_MS * 2);
    expect(follow.mock.calls).toEqual([["p/b"], ["p/b"]]);
  });

  it("unfollows when toggled off, stops renewing, and persists off", () => {
    const storage = memoryStorage();
    const { transport, follow, unfollow } = fakeTransport();
    const manager = new FollowManager({ transport, storage });
    manager.setModel("p/m");
    manager.setEnabled(false);
    expect(unfollow.mock.calls).toEqual([["p/m"]]);
    expect(manager.following).toBeNull();
    expect(storage.data.get(FOLLOW_STORAGE_KEY)).toBe("off");
    follow.mockClear();
    vi.advanceTimersByTime(FOLLOW_RENEW_MS * 5);
    expect(follow).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("follows the current model again when toggled back on", () => {
    const storage = memoryStorage();
    const { transport, follow } = fakeTransport();
    const manager = new FollowManager({ transport, storage });
    manager.setModel("p/m");
    manager.setEnabled(false);
    follow.mockClear();
    manager.setEnabled(true);
    expect(follow.mock.calls).toEqual([["p/m"]]);
    expect(storage.data.get(FOLLOW_STORAGE_KEY)).toBe("on");
    vi.advanceTimersByTime(FOLLOW_RENEW_MS);
    expect(follow).toHaveBeenCalledTimes(2);
  });

  it("a model picked while off is followed once it is turned on, and not before", () => {
    const { transport, follow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage({ [FOLLOW_STORAGE_KEY]: "off" }) });
    manager.setModel("p/m");
    expect(follow).not.toHaveBeenCalled();
    manager.setEnabled(true);
    expect(follow.mock.calls).toEqual([["p/m"]]);
  });

  it("switching model while off sends no unfollow", () => {
    const { transport, unfollow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/a");
    manager.setEnabled(false);
    unfollow.mockClear();
    manager.setModel("p/b");
    expect(unfollow).not.toHaveBeenCalled();
  });

  it("an unfollow that rejects is swallowed", async () => {
    const { transport, unfollow } = fakeTransport();
    unfollow.mockRejectedValue(new Error("gone"));
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/a");
    expect(() => manager.setModel("p/b")).not.toThrow();
    await vi.advanceTimersByTimeAsync(0);
    expect(manager.following).toBe("p/b");
  });

  it("dispose unfollows and stops the timer", () => {
    const { transport, follow, unfollow } = fakeTransport();
    const manager = new FollowManager({ transport, storage: memoryStorage() });
    manager.setModel("p/m");
    manager.dispose();
    expect(unfollow.mock.calls).toEqual([["p/m"]]);
    follow.mockClear();
    vi.advanceTimersByTime(FOLLOW_RENEW_MS * 3);
    expect(follow).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});

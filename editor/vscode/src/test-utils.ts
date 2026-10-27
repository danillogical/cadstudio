/** Shared fakes for the bridge, HTTP client and extension tests. Not bundled into the extension. */
import { vi } from "vitest";
import type { BridgeWebview, HttpIo, ServiceClient } from "./bridge";
import type { EventStream, EventStreamHandlers } from "./http";
import type { HttpRoute, Reply } from "./protocol";
import type { ServiceLocator, ServiceRecord } from "./service";

export const TOKEN = "SECRET-TOKEN-9f3a";

export function record(overrides: Partial<ServiceRecord> = {}): ServiceRecord {
  return { pid: 4242, port: 5555, token: TOKEN, repoRoot: "/work/cadstudio", protocolVersion: 1, ...overrides };
}

/** The webview side of a `PanelBridge`: records posts, lets a test deliver messages. */
export class FakeBridgeWebview implements BridgeWebview {
  posted: unknown[] = [];
  private listeners = new Set<(message: unknown) => void>();
  listenerDisposed = false;

  postMessage(message: unknown): PromiseLike<boolean> {
    this.posted.push(message);
    return Promise.resolve(true);
  }

  onDidReceiveMessage(listener: (message: unknown) => void): { dispose(): void } {
    this.listeners.add(listener);
    return {
      dispose: () => {
        this.listenerDisposed = true;
        this.listeners.delete(listener);
      },
    };
  }

  receive(message: unknown): void {
    for (const listener of [...this.listeners]) listener(message);
  }

  get listenerCount(): number {
    return this.listeners.size;
  }
}

export interface FakeStream extends EventStream {
  handlers: EventStreamHandlers;
  startService: boolean;
  closed: boolean;
}

/** A `ServiceClient` that records every call and answers from a replaceable handler. */
export class FakeClient implements ServiceClient {
  requests: HttpRoute[] = [];
  signals: AbortSignal[] = [];
  streams: FakeStream[] = [];
  openCalls: Array<{ startService: boolean }> = [];
  reply: (route: HttpRoute, signal: AbortSignal) => Promise<Reply> = async () => ({ ok: true, result: {} });
  openError: Error | null = null;

  request(route: HttpRoute, signal: AbortSignal): Promise<Reply> {
    this.requests.push(route);
    this.signals.push(signal);
    return this.reply(route, signal);
  }

  async openEvents(handlers: EventStreamHandlers, options: { startService: boolean }): Promise<EventStream> {
    this.openCalls.push({ ...options });
    if (this.openError) throw this.openError;
    const stream: FakeStream = {
      handlers,
      startService: options.startService,
      closed: false,
      close() {
        stream.closed = true;
      },
    };
    this.streams.push(stream);
    return stream;
  }
}

/** A manual timer for `PanelBridge`'s reconnect delay. */
export class FakeTimers {
  pending = new Map<number, { callback: () => void; ms: number }>();
  private next = 1;
  cleared: number[] = [];
  setTimer = (callback: () => void, ms: number): unknown => {
    const handle = this.next++;
    this.pending.set(handle, { callback, ms });
    return handle;
  };
  clearTimer = (handle: unknown): void => {
    this.cleared.push(handle as number);
    this.pending.delete(handle as number);
  };
  fireAll(): void {
    const due = [...this.pending.entries()];
    this.pending.clear();
    for (const [, entry] of due) entry.callback();
  }
}

export async function flush(times = 10): Promise<void> {
  for (let i = 0; i < times; i += 1) await Promise.resolve();
}

/** A `ServiceLocator` stand-in; the real class has private state so tests cast it. */
export function fakeLocator(records: ServiceRecord[]) {
  let index = 0;
  const state = {
    gets: 0,
    invalidated: [] as ServiceRecord[],
    get: vi.fn(async () => {
      state.gets += 1;
      return records[Math.min(index, records.length - 1)];
    }),
    find: vi.fn(async () => records[Math.min(index, records.length - 1)] ?? null),
    invalidate: vi.fn((rec?: ServiceRecord) => {
      if (rec) state.invalidated.push(rec);
      index += 1;
    }),
  };
  return { locator: state as unknown as ServiceLocator, state };
}

export type { HttpIo };

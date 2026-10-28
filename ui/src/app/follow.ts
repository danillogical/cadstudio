/**
 * Follow mode: while on, the service rebuilds the current model when its sources change and
 * the page shows scene updates and live runs. The service lease lapses after 60 s, so the
 * follow is renewed on a timer; turning it off or changing model unfollows.
 */
import type { CadStudioTransport } from "../transport/types";

export const FOLLOW_STORAGE_KEY = "cadstudio.follow";
/** Renewal period (ms), well inside the service's 60 s lease. */
export const FOLLOW_RENEW_MS = 20_000;

export interface FollowOptions {
  transport: CadStudioTransport;
  /** Where the on/off choice is kept; defaults to `sessionStorage` when there is one. */
  storage?: Pick<Storage, "getItem" | "setItem"> | null;
  setInterval?: (callback: () => void, ms: number) => unknown;
  clearInterval?: (handle: unknown) => void;
  /** Called with a short status ("" when there is nothing to say). */
  onStatus?: (text: string) => void;
}

function defaultStorage(): FollowOptions["storage"] {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export class FollowManager {
  private readonly transport: CadStudioTransport;
  private readonly storage: FollowOptions["storage"];
  private readonly setTimer: (callback: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;
  private readonly onStatus: (text: string) => void;
  private on: boolean;
  private model: string | null = null;
  /** The model the service was last told to follow. */
  private active: string | null = null;
  private timer: unknown = null;

  constructor(options: FollowOptions) {
    this.transport = options.transport;
    this.storage = options.storage === undefined ? defaultStorage() : options.storage;
    this.setTimer = options.setInterval ?? ((cb, ms) => globalThis.setInterval(cb, ms));
    this.clearTimer =
      options.clearInterval ?? ((handle) => globalThis.clearInterval(handle as ReturnType<typeof setInterval>));
    this.onStatus = options.onStatus ?? (() => {});
    let stored: string | null = null;
    try {
      stored = this.storage?.getItem(FOLLOW_STORAGE_KEY) ?? null;
    } catch {
      // Unreadable storage means the default.
    }
    // On unless the user turned it off.
    this.on = stored !== "off";
  }

  get enabled(): boolean {
    return this.on;
  }

  /** The model currently being followed on the service, if any. */
  get following(): string | null {
    return this.active;
  }

  setEnabled(enabled: boolean): void {
    if (enabled === this.on) return;
    this.on = enabled;
    try {
      this.storage?.setItem(FOLLOW_STORAGE_KEY, enabled ? "on" : "off");
    } catch {
      // The choice just does not persist.
    }
    this.sync();
  }

  /** The model on screen; null when none. */
  setModel(model: string | null): void {
    this.model = model;
    this.sync();
  }

  dispose(): void {
    this.stopTimer();
    this.model = null;
    this.sync();
  }

  private sync(): void {
    const desired = this.on ? this.model : null;
    const previous = this.active;
    if (previous !== null && previous !== desired) {
      this.active = null;
      void this.transport.unfollow(previous).catch(() => {});
    }
    if (desired === null) {
      this.stopTimer();
      this.onStatus("");
      return;
    }
    if (desired !== previous) {
      this.active = desired;
      this.renew(desired);
    }
    if (this.timer === null) {
      this.timer = this.setTimer(() => {
        if (this.active !== null) this.renew(this.active);
      }, FOLLOW_RENEW_MS);
    }
  }

  private renew(model: string): void {
    void this.transport.follow(model).then(
      () => {
        if (this.active === model) this.onStatus("following");
      },
      (error: unknown) => {
        if (this.active !== model) return;
        const text = error instanceof Error ? error.message : String(error);
        this.onStatus(`follow unavailable: ${text}`);
      },
    );
  }

  private stopTimer(): void {
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
  }
}

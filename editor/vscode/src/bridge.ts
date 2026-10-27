/**
 * The per-panel bridge between a webview and the GUI service. The webview's messages are
 * validated (`parseWebviewMessage`) and forwarded only as `routeFor` routes; answers, artifact
 * bytes and SSE events come back as messages, so the webview never connects anywhere itself
 * and never sees the service token.
 */
import type { EventStream, EventStreamHandlers } from "./http";
import { HttpFailure, openEventStream, serviceRequest, type Endpoint, type HttpAnswer } from "./http";
import {
  mapHttpResponse,
  networkError,
  parseWebviewMessage,
  rejectedError,
  routeFor,
  type HttpRoute,
  type Reply,
} from "./protocol";
import { ServiceUnavailableError, type ServiceLocator, type ServiceRecord } from "./service";

/** SSE event names forwarded to the webview, as `BrowserTransport` listens for. */
export const FORWARDED_EVENTS = ["job", "artifact"] as const;
/** EventSource's usual retry delay. */
export const RECONNECT_MS = 3_000;

/** What the bridge needs from the service; faked in tests. */
export interface ServiceClient {
  /** Forward one route; resolves with the reply to post and never rejects. */
  request(route: HttpRoute, signal: AbortSignal): Promise<Reply>;
  /**
   * Open the event stream. With `startService` false it only reconnects to a service that is
   * already registered, so a service the user stopped is not restarted behind their back.
   */
  openEvents(handlers: EventStreamHandlers, options: { startService: boolean }): Promise<EventStream>;
  /**
   * Forward one route to the service already registered for the folder, never starting one;
   * null when none is registered. Used for `cad gui open` requests, which must not start a service.
   */
  requestRegistered?(route: HttpRoute, signal?: AbortSignal): Promise<Reply | null>;
}

export interface HttpIo {
  request(endpoint: Endpoint, route: HttpRoute, signal?: AbortSignal): Promise<HttpAnswer>;
  openEventStream(endpoint: Endpoint, handlers: EventStreamHandlers): EventStream;
}

const NODE_IO: HttpIo = { request: serviceRequest, openEventStream };

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * `ServiceClient` over the real service. A refused connection or a 401 drops the cached record
 * and retries once, which picks up a restarted service (new port or token) transparently.
 */
export class HttpServiceClient implements ServiceClient {
  constructor(
    private readonly locator: ServiceLocator,
    private readonly io: HttpIo = NODE_IO,
  ) {}

  async request(route: HttpRoute, signal: AbortSignal): Promise<Reply> {
    const reply = await this.forward(route, signal, () => this.locator.get());
    return reply ?? { ok: false, error: { status: 0, message: "no healthy GUI service is registered" } };
  }

  requestRegistered(route: HttpRoute, signal: AbortSignal = new AbortController().signal): Promise<Reply | null> {
    return this.forward(route, signal, () => this.locator.find());
  }

  /** Locate the service, send the route, and retry once after a refused connection or a 401. */
  private async forward(
    route: HttpRoute,
    signal: AbortSignal,
    locate: () => Promise<ServiceRecord | null>,
  ): Promise<Reply | null> {
    for (let attempt = 0; ; attempt += 1) {
      let record: ServiceRecord | null;
      try {
        record = await locate();
      } catch (error) {
        return { ok: false, error: { status: 0, message: messageOf(error) } };
      }
      if (!record) return null;
      if (signal.aborted) return { ok: false, error: networkError(new Error("request cancelled")) };
      let answer: HttpAnswer;
      try {
        answer = await this.io.request(record, route, signal);
      } catch (error) {
        if (attempt === 0 && error instanceof HttpFailure && error.refused && !signal.aborted) {
          this.locator.invalidate(record);
          continue;
        }
        return { ok: false, error: networkError(error) };
      }
      if (answer.status === 401 && attempt === 0) {
        this.locator.invalidate(record);
        continue;
      }
      return mapHttpResponse(answer.status, answer.statusText, answer.bytes, route.binary);
    }
  }

  async openEvents(handlers: EventStreamHandlers, options: { startService: boolean }): Promise<EventStream> {
    const record = options.startService ? await this.locator.get() : await this.locator.find();
    if (!record) throw new ServiceUnavailableError("no healthy GUI service is registered");
    return this.io.openEventStream(record, {
      onOpen: handlers.onOpen,
      onEvent: handlers.onEvent,
      onClose: (reason) => {
        // The next attempt re-reads service.json, so a restarted service is found.
        this.locator.invalidate(record);
        handlers.onClose(reason);
      },
    });
  }
}

export interface BridgeWebview {
  postMessage(message: unknown): PromiseLike<boolean>;
  onDidReceiveMessage(listener: (message: unknown) => void): { dispose(): void };
}

export interface BridgeOptions {
  /** Called on each `{kind: "ready"}` from the page. */
  onReady?: () => void;
  reconnectMs?: number;
  setTimer?: (callback: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

export class PanelBridge {
  private readonly listener: { dispose(): void };
  private readonly inflight = new Set<AbortController>();
  private readonly reconnectMs: number;
  private readonly setTimer: (callback: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;
  private readonly onReady: (() => void) | undefined;
  private stream: EventStream | null = null;
  private timer: unknown = null;
  private subscribed = false;
  /** Bumped on every (un)subscribe so a late stream from an old attempt is closed, not used. */
  private generation = 0;
  private attempts = 0;
  private disposed = false;

  constructor(
    private readonly webview: BridgeWebview,
    private readonly client: ServiceClient,
    options: BridgeOptions = {},
  ) {
    this.onReady = options.onReady;
    this.reconnectMs = options.reconnectMs ?? RECONNECT_MS;
    this.setTimer = options.setTimer ?? ((callback, ms) => setTimeout(callback, ms));
    this.clearTimer = options.clearTimer ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
    this.listener = webview.onDidReceiveMessage((message) => void this.handle(message));
  }

  /** Requests currently being forwarded. */
  get pendingRequests(): number {
    return this.inflight.size;
  }

  get isSubscribed(): boolean {
    return this.subscribed;
  }

  /** Validate and act on one webview message; resolves once any reply has been posted. */
  async handle(raw: unknown): Promise<void> {
    if (this.disposed) return;
    const parsed = parseWebviewMessage(raw);
    if (!parsed.ok) {
      if (parsed.id !== null) this.post({ kind: "response", id: parsed.id, ok: false, error: rejectedError(parsed.error) });
      return;
    }
    const { message } = parsed;
    if (message.kind === "subscribe") return this.subscribe();
    if (message.kind === "unsubscribe") return this.unsubscribe();
    if (message.kind === "ready") return this.onReady?.();

    const controller = new AbortController();
    this.inflight.add(controller);
    try {
      const reply = await this.client.request(routeFor(message.call), controller.signal);
      if (!controller.signal.aborted) this.post({ kind: "response", id: message.id, ...reply });
    } finally {
      this.inflight.delete(controller);
    }
  }

  /** Abort in-flight requests, close the event stream and stop listening to the webview. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.listener.dispose();
    for (const controller of this.inflight) controller.abort();
    this.inflight.clear();
    this.stopEvents();
  }

  private post(message: unknown): void {
    if (this.disposed) return;
    Promise.resolve(this.webview.postMessage(message)).then(undefined, () => {
      // The panel went away mid-reply; nothing is listening any more.
    });
  }

  private subscribe(): void {
    if (this.subscribed) return;
    this.subscribed = true;
    this.attempts = 0;
    void this.connect(++this.generation);
  }

  private unsubscribe(): void {
    this.stopEvents();
  }

  private stopEvents(): void {
    this.subscribed = false;
    this.generation += 1;
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
    this.stream?.close();
    this.stream = null;
  }

  private async connect(generation: number): Promise<void> {
    const current = () => !this.disposed && this.subscribed && generation === this.generation;
    const startService = this.attempts === 0;
    this.attempts += 1;
    let stream: EventStream;
    try {
      stream = await this.client.openEvents(
        {
          onOpen: () => {
            if (current()) this.post({ kind: "connection", state: "open" });
          },
          onEvent: (event) => {
            if (!current() || !(FORWARDED_EVENTS as readonly string[]).includes(event.event)) return;
            let data: unknown;
            try {
              data = JSON.parse(event.data);
            } catch {
              return; // A malformed frame is not worth tearing the stream down for.
            }
            this.post({ kind: "event", event: event.event, data });
          },
          onClose: () => {
            if (!current()) return;
            this.stream = null;
            this.post({ kind: "connection", state: "error" });
            this.scheduleReconnect(generation);
          },
        },
        { startService },
      );
    } catch {
      if (!current()) return;
      this.post({ kind: "connection", state: "error" });
      this.scheduleReconnect(generation);
      return;
    }
    if (!current()) {
      stream.close();
      return;
    }
    this.stream = stream;
  }

  private scheduleReconnect(generation: number): void {
    if (this.timer !== null) return;
    this.timer = this.setTimer(() => {
      this.timer = null;
      if (!this.disposed && this.subscribed && generation === this.generation) void this.connect(generation);
    }, this.reconnectMs);
  }
}

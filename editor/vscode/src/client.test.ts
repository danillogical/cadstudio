import { describe, expect, it, vi } from "vitest";
import { HttpServiceClient, PanelBridge, type HttpIo } from "./bridge";
import { HttpFailure, type Endpoint, type EventStream, type EventStreamHandlers, type HttpAnswer } from "./http";
import type { HttpRoute } from "./protocol";
import { ServiceUnavailableError } from "./service";
import { FakeBridgeWebview, fakeLocator, flush, record, TOKEN } from "./test-utils";

const enc = (value: string) => new TextEncoder().encode(value);
const answer = (status: number, body: string | Uint8Array, statusText = ""): HttpAnswer => ({
  status,
  statusText,
  bytes: typeof body === "string" ? enc(body) : body,
});
const GET_MODELS: HttpRoute = { method: "GET", path: "/v1/models", binary: false };
const signal = () => new AbortController().signal;

function fakeIo(handler: (endpoint: Endpoint, route: HttpRoute, signal?: AbortSignal) => HttpAnswer | Error) {
  const requests: Array<{ endpoint: Endpoint; route: HttpRoute }> = [];
  const streams: Array<{ endpoint: Endpoint; handlers: EventStreamHandlers; closed: boolean }> = [];
  const io: HttpIo = {
    async request(endpoint, route, sig) {
      requests.push({ endpoint, route });
      const result = handler(endpoint, route, sig);
      if (result instanceof Error) throw result;
      return result;
    },
    openEventStream(endpoint, handlers): EventStream {
      const entry = { endpoint, handlers, closed: false };
      streams.push(entry);
      return { close: () => void (entry.closed = true) };
    },
  };
  return { io, requests, streams };
}

describe("HttpServiceClient.request", () => {
  it("sends the registered port and token to the io layer and maps the answer", async () => {
    const rec = record();
    const { locator } = fakeLocator([rec]);
    const { io, requests } = fakeIo(() => answer(200, '{"models":[]}'));
    const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
    expect(reply).toEqual({ ok: true, result: { models: [] } });
    expect(requests).toHaveLength(1);
    expect(requests[0].endpoint.port).toBe(rec.port);
    expect(requests[0].endpoint.token).toBe(TOKEN);
    expect(requests[0].route).toEqual(GET_MODELS);
  });

  it("maps HTTP errors to {status, message, body}: server text, else status text, else HTTP n", async () => {
    const { locator } = fakeLocator([record()]);
    const answers = [
      answer(404, '{"schemaVersion":1,"error":"no scene; run cad build"}', "Not Found"),
      answer(500, "<html/>", "Internal Server Error"),
      answer(503, "", ""),
    ];
    const { io } = fakeIo(() => answers.shift()!);
    const client = new HttpServiceClient(locator, io);
    expect(await client.request(GET_MODELS, signal())).toEqual({
      ok: false,
      error: { status: 404, message: "no scene; run cad build", body: { schemaVersion: 1, error: "no scene; run cad build" } },
    });
    expect(await client.request(GET_MODELS, signal())).toEqual({
      ok: false,
      error: { status: 500, message: "Internal Server Error" },
    });
    expect(await client.request(GET_MODELS, signal())).toEqual({ ok: false, error: { status: 503, message: "HTTP 503" } });
  });

  it("delivers a binary artifact as an exact-size ArrayBuffer, not a Node Buffer", async () => {
    const { locator } = fakeLocator([record()]);
    const pooled = Buffer.from([1, 2, 3, 4, 5]);
    const { io } = fakeIo(() => answer(200, pooled));
    const reply = await new HttpServiceClient(locator, io).request(
      { method: "GET", path: "/v1/artifacts/a.bin", binary: true },
      signal(),
    );
    expect(reply.ok).toBe(true);
    const result = (reply as { result: ArrayBuffer }).result;
    expect(result).toBeInstanceOf(ArrayBuffer);
    expect(Buffer.isBuffer(result)).toBe(false);
    expect(result.byteLength).toBe(5);
    expect([...new Uint8Array(result)]).toEqual([1, 2, 3, 4, 5]);
  });

  it("reports a network failure with status 0", async () => {
    const { locator } = fakeLocator([record()]);
    const { io, requests } = fakeIo(() => new Error("socket hang up"));
    const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
    expect(reply).toEqual({ ok: false, error: { status: 0, message: "network error: socket hang up" } });
    expect(requests).toHaveLength(1); // not a refused connection: no retry
  });

  it("reports a service that cannot be found or started with status 0", async () => {
    const { locator, state } = fakeLocator([record()]);
    state.get.mockRejectedValueOnce(new ServiceUnavailableError("could not start `cad gui serve`: no uv"));
    const { io, requests } = fakeIo(() => answer(200, "{}"));
    const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
    expect(reply).toEqual({ ok: false, error: { status: 0, message: "could not start `cad gui serve`: no uv" } });
    expect(requests).toHaveLength(0);
  });

  describe("retry once", () => {
    const first = record({ port: 5001, token: "old-token", pid: 1 });
    const second = record({ port: 5002, token: "new-token", pid: 2 });

    it("retries after ECONNREFUSED with the cached record invalidated and the new endpoint", async () => {
      const { locator, state } = fakeLocator([first, second]);
      const { io, requests } = fakeIo((endpoint) =>
        endpoint.port === 5001 ? new HttpFailure("connect ECONNREFUSED", true) : answer(200, '{"ok":1}'),
      );
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
      expect(reply).toEqual({ ok: true, result: { ok: 1 } });
      expect(requests.map((r) => [r.endpoint.port, r.endpoint.token])).toEqual([
        [5001, "old-token"],
        [5002, "new-token"],
      ]);
      expect(state.invalidated).toEqual([first]);
      expect(state.gets).toBe(2);
    });

    it("retries after a 401 with the cached record invalidated", async () => {
      const { locator, state } = fakeLocator([first, second]);
      const { io, requests } = fakeIo((endpoint) =>
        endpoint.token === "old-token" ? answer(401, '{"error":"bad token"}', "Unauthorized") : answer(200, "{}"),
      );
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
      expect(reply).toEqual({ ok: true, result: {} });
      expect(requests).toHaveLength(2);
      expect(state.invalidated).toEqual([first]);
    });

    it("does not retry forever on repeated 401s", async () => {
      const { locator, state } = fakeLocator([first, second]);
      const { io, requests } = fakeIo(() => answer(401, '{"error":"bad token"}', "Unauthorized"));
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
      expect(requests).toHaveLength(2);
      expect(state.invalidated).toHaveLength(1);
      expect(reply).toEqual({
        ok: false,
        error: { status: 401, message: "bad token", body: { error: "bad token" } },
      });
    });

    it("does not retry forever on repeated refused connections", async () => {
      const { locator } = fakeLocator([first, second]);
      const { io, requests } = fakeIo(() => new HttpFailure("connect ECONNREFUSED", true));
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
      expect(requests).toHaveLength(2);
      expect(reply).toMatchObject({ ok: false, error: { status: 0 } });
    });

    it("does not retry a failure that is not a refused connection", async () => {
      const { locator, state } = fakeLocator([first, second]);
      const { io, requests } = fakeIo(() => new HttpFailure("connection closed before the response ended", false));
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
      expect(requests).toHaveLength(1);
      expect(state.invalidated).toEqual([]);
      expect(reply).toMatchObject({ ok: false, error: { status: 0 } });
    });

    it("does not retry other statuses such as 403 or 500", async () => {
      for (const status of [403, 404, 500]) {
        const { locator, state } = fakeLocator([first, second]);
        const { io, requests } = fakeIo(() => answer(status, "{}"));
        await new HttpServiceClient(locator, io).request(GET_MODELS, signal());
        expect(requests).toHaveLength(1);
        expect(state.invalidated).toEqual([]);
      }
    });

    it("does not retry once the request was aborted", async () => {
      const { locator, state } = fakeLocator([first, second]);
      const controller = new AbortController();
      const { io, requests } = fakeIo(() => {
        controller.abort();
        return new HttpFailure("aborted", true);
      });
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, controller.signal);
      expect(requests).toHaveLength(1);
      expect(state.invalidated).toEqual([]);
      expect(reply).toMatchObject({ ok: false, error: { status: 0 } });
    });

    it("does not touch the network when already aborted", async () => {
      const { locator } = fakeLocator([first]);
      const controller = new AbortController();
      controller.abort();
      const { io, requests } = fakeIo(() => answer(200, "{}"));
      const reply = await new HttpServiceClient(locator, io).request(GET_MODELS, controller.signal);
      expect(requests).toHaveLength(0);
      expect(reply).toMatchObject({ ok: false, error: { status: 0 } });
    });
  });
});

describe("HttpServiceClient.openEvents", () => {
  const handlers = (): EventStreamHandlers & { closes: unknown[] } => {
    const closes: unknown[] = [];
    return { closes, onOpen: vi.fn(), onEvent: vi.fn(), onClose: (reason) => void closes.push(reason) };
  };

  it("starts the service (locator.get) when asked to, and uses the registered endpoint", async () => {
    const rec = record({ port: 6000 });
    const { locator, state } = fakeLocator([rec]);
    const { io, streams } = fakeIo(() => answer(200, "{}"));
    await new HttpServiceClient(locator, io).openEvents(handlers(), { startService: true });
    expect(state.get).toHaveBeenCalledTimes(1);
    expect(state.find).not.toHaveBeenCalled();
    expect(streams[0].endpoint.port).toBe(6000);
    expect(streams[0].endpoint.token).toBe(TOKEN);
  });

  it("only looks for a registered service when startService is false", async () => {
    const { locator, state } = fakeLocator([record()]);
    const { io, streams } = fakeIo(() => answer(200, "{}"));
    await new HttpServiceClient(locator, io).openEvents(handlers(), { startService: false });
    expect(state.get).not.toHaveBeenCalled();
    expect(state.find).toHaveBeenCalledTimes(1);
    expect(streams).toHaveLength(1);
  });

  it("throws ServiceUnavailableError and opens nothing when no service is registered", async () => {
    const { locator, state } = fakeLocator([record()]);
    state.find.mockResolvedValueOnce(null as never);
    const { io, streams } = fakeIo(() => answer(200, "{}"));
    await expect(
      new HttpServiceClient(locator, io).openEvents(handlers(), { startService: false }),
    ).rejects.toBeInstanceOf(ServiceUnavailableError);
    expect(streams).toHaveLength(0);
    expect(state.get).not.toHaveBeenCalled();
  });

  it("invalidates the record when the stream closes so the next attempt re-reads service.json", async () => {
    const rec = record();
    const { locator, state } = fakeLocator([rec]);
    const { io, streams } = fakeIo(() => answer(200, "{}"));
    const h = handlers();
    await new HttpServiceClient(locator, io).openEvents(h, { startService: true });
    streams[0].handlers.onClose({ message: "gone", status: 401 });
    expect(state.invalidated).toEqual([rec]);
    expect(h.closes).toEqual([{ message: "gone", status: 401 }]);
  });

  it("passes open and event callbacks through", async () => {
    const { locator } = fakeLocator([record()]);
    const { io, streams } = fakeIo(() => answer(200, "{}"));
    const h = handlers();
    await new HttpServiceClient(locator, io).openEvents(h, { startService: true });
    streams[0].handlers.onOpen();
    streams[0].handlers.onEvent({ event: "job", data: "{}" });
    expect(h.onOpen).toHaveBeenCalledTimes(1);
    expect(h.onEvent).toHaveBeenCalledWith({ event: "job", data: "{}" });
  });

  it("closes the underlying stream when the bridge is disposed", async () => {
    const { locator } = fakeLocator([record()]);
    const { io, streams } = fakeIo(() => answer(200, "{}"));
    const webview = new FakeBridgeWebview();
    const bridge = new PanelBridge(webview, new HttpServiceClient(locator, io));
    await bridge.handle({ kind: "subscribe" });
    await flush();
    expect(streams).toHaveLength(1);
    bridge.dispose();
    expect(streams[0].closed).toBe(true);
  });
});

describe("the token never reaches the webview", () => {
  it("is absent from every posted message, success and failure, events included", async () => {
    const rec = record({ token: "tok-" + "Zq8".repeat(12) });
    const { locator } = fakeLocator([rec]);
    const answers: Array<HttpAnswer | Error> = [
      answer(200, '{"models":[]}'),
      answer(404, '{"error":"missing"}', "Not Found"),
      answer(200, Buffer.from("artifact-bytes")),
      new Error("connect failed"),
      answer(401, '{"error":"unauthorized"}', "Unauthorized"),
      answer(401, '{"error":"unauthorized"}', "Unauthorized"),
    ];
    const { io, streams } = fakeIo(() => answers.shift()!);
    const webview = new FakeBridgeWebview();
    const bridge = new PanelBridge(webview, new HttpServiceClient(locator, io));
    const calls: Array<[string, unknown[]]> = [
      ["listModels", []],
      ["getScene", ["p/m"]],
      ["getArtifact", ["p/m/scene/a.bin"]],
      ["listRuns", []],
      ["health", []],
    ];
    let id = 1;
    for (const [method, args] of calls) await bridge.handle({ kind: "request", id: id++, method, args });
    await bridge.handle({ kind: "subscribe" });
    await flush();
    streams[0].handlers.onOpen();
    streams[0].handlers.onEvent({ event: "job", data: '{"job":{"id":"j"}}' });
    streams[0].handlers.onClose({ message: "closed" });
    await flush();

    expect(webview.posted.length).toBeGreaterThanOrEqual(7);
    for (const message of webview.posted) {
      const text = JSON.stringify(message, (_k, v) => (v instanceof ArrayBuffer ? Array.from(new Uint8Array(v)) : v));
      expect(text).not.toContain(rec.token);
      expect(text.toLowerCase()).not.toContain("bearer");
      expect(text.toLowerCase()).not.toContain("authorization");
      expect(Object.keys(message as object)).not.toContain("token");
    }
  });
});

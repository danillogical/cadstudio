/**
 * Node HTTP to the loopback service. Requests always go to 127.0.0.1 on the registered port,
 * carry the bearer token, and use only paths built by `routeFor`.
 */
import * as http from "node:http";
import type { HttpRoute } from "./protocol";
import { SseParser, type SseEvent } from "./sse";

export const HEALTH_TIMEOUT_MS = 2_000;
/** Three missed 15 s keepalives mean the event stream is dead. */
export const EVENTS_IDLE_TIMEOUT_MS = 45_000;
const MAX_HEALTH_BYTES = 64 * 1024;

export interface HttpAnswer {
  status: number;
  statusText: string;
  bytes: Uint8Array;
}

/** No HTTP answer; `refused` means the connection was never made, so a retry cannot double a POST. */
export class HttpFailure extends Error {
  constructor(
    message: string,
    readonly refused: boolean,
  ) {
    super(message);
    this.name = "HttpFailure";
  }
}

export interface Endpoint {
  port: number;
  token: string;
}

function failure(error: unknown): HttpFailure {
  if (error instanceof HttpFailure) return error;
  const code = (error as { code?: unknown } | null)?.code;
  const message = error instanceof Error ? error.message : String(error);
  return new HttpFailure(message, code === "ECONNREFUSED");
}

/** One request/response; the whole body is buffered (artifacts included). */
export function serviceRequest(endpoint: Endpoint, route: HttpRoute, signal?: AbortSignal): Promise<HttpAnswer> {
  return new Promise((resolve, reject) => {
    const body = route.body === undefined ? undefined : Buffer.from(JSON.stringify(route.body), "utf8");
    const headers: Record<string, string> = {
      Authorization: `Bearer ${endpoint.token}`,
      Accept: route.binary ? "*/*" : "application/json",
    };
    if (body) {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = String(body.length);
    }
    const request = http.request(
      { host: "127.0.0.1", port: endpoint.port, method: route.method, path: route.path, headers, signal },
      (response) => {
        const chunks: Buffer[] = [];
        response.on("data", (chunk: Buffer) => chunks.push(chunk));
        response.on("end", () => {
          if (!response.complete) {
            reject(new HttpFailure("connection closed before the response ended", false));
            return;
          }
          resolve({
            status: response.statusCode ?? 0,
            statusText: response.statusMessage ?? "",
            bytes: Buffer.concat(chunks),
          });
        });
        response.on("error", (error) => reject(failure(error)));
      },
    );
    request.on("error", (error) => reject(failure(error)));
    // Settles a request that closed without an error or a complete response; a no-op otherwise.
    request.on("close", () => reject(new HttpFailure("connection closed before the response ended", false)));
    request.end(body);
  });
}

/** The parsed `/v1/health` body, or null on any failure (no token is sent). */
export function fetchHealth(port: number, timeoutMs = HEALTH_TIMEOUT_MS): Promise<unknown> {
  return new Promise((resolve) => {
    const request = http.get(
      { host: "127.0.0.1", port, path: "/v1/health", headers: { Accept: "application/json" }, timeout: timeoutMs },
      (response) => {
        const chunks: Buffer[] = [];
        let size = 0;
        response.on("data", (chunk: Buffer) => {
          size += chunk.length;
          if (size > MAX_HEALTH_BYTES) request.destroy(new Error("health answer too large"));
          else chunks.push(chunk);
        });
        response.on("end", () => {
          if (response.statusCode !== 200 || !response.complete) return resolve(null);
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
          } catch {
            resolve(null);
          }
        });
        response.on("error", () => resolve(null));
      },
    );
    request.on("timeout", () => request.destroy(new Error("health check timed out")));
    request.on("error", () => resolve(null));
    request.on("close", () => resolve(null));
  });
}

export interface EventStreamHandlers {
  onOpen(): void;
  onEvent(event: SseEvent): void;
  /** Called once when the stream ends for any reason other than `close()`; `status` is set for a non-200 answer. */
  onClose(reason: { message: string; status?: number }): void;
}

export interface EventStream {
  close(): void;
}

/** Open `GET /v1/events` and feed parsed frames to `handlers` until it ends or is closed. */
export function openEventStream(endpoint: Endpoint, handlers: EventStreamHandlers): EventStream {
  let closed = false;
  const finish = (reason: { message: string; status?: number }) => {
    if (closed) return;
    closed = true;
    handlers.onClose(reason);
  };
  const request = http.get(
    {
      host: "127.0.0.1",
      port: endpoint.port,
      path: "/v1/events",
      headers: { Authorization: `Bearer ${endpoint.token}`, Accept: "text/event-stream" },
    },
    (response) => {
      if (response.statusCode !== 200) {
        response.resume();
        finish({ message: `event stream answered HTTP ${response.statusCode}`, status: response.statusCode });
        request.destroy();
        return;
      }
      handlers.onOpen();
      const parser = new SseParser();
      const decoder = new TextDecoder();
      response.on("data", (chunk: Buffer) => {
        if (closed) return;
        for (const event of parser.push(decoder.decode(chunk, { stream: true }))) handlers.onEvent(event);
      });
      response.on("end", () => finish({ message: "event stream ended" }));
      response.on("error", (error) => finish({ message: error.message }));
    },
  );
  request.setTimeout(EVENTS_IDLE_TIMEOUT_MS, () => request.destroy(new Error("event stream went quiet")));
  request.on("error", (error) => finish({ message: error.message }));
  request.on("close", () => finish({ message: "event stream closed" }));
  return {
    close() {
      closed = true;
      request.destroy();
    },
  };
}

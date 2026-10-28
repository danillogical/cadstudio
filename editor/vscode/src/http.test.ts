import * as http from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fetchHealth, HttpFailure, openEventStream, serviceRequest, type EventStreamHandlers } from "./http";
import type { SseEvent } from "./sse";

// These tests run a real HTTP server on 127.0.0.1 so the Node client code is exercised for real.
interface Seen {
  method?: string;
  url?: string;
  headers: http.IncomingHttpHeaders;
  body: string;
}

let server: http.Server;
let port: number;
let seen: Seen[];
let handler: (req: http.IncomingMessage, res: http.ServerResponse) => void;

beforeEach(async () => {
  seen = [];
  handler = (_req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end("{}");
  };
  server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body: Buffer.concat(chunks).toString("utf8") });
      handler(req, res);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  port = (server.address() as AddressInfo).port;
});

afterEach(async () => {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

const TOKEN = "tok-abc";

describe("serviceRequest", () => {
  it("sends the bearer token, JSON accept header, method, path and body, to 127.0.0.1 only", async () => {
    await serviceRequest(
      { port, token: TOKEN },
      { method: "POST", path: "/v1/models/p/m/build", body: { set: { a: 1 } }, binary: false },
    );
    expect(seen).toHaveLength(1);
    expect(seen[0].method).toBe("POST");
    expect(seen[0].url).toBe("/v1/models/p/m/build");
    expect(seen[0].headers.authorization).toBe(`Bearer ${TOKEN}`);
    expect(seen[0].headers.accept).toBe("application/json");
    expect(seen[0].headers["content-type"]).toBe("application/json");
    expect(seen[0].headers["content-length"]).toBe(String(Buffer.byteLength('{"set":{"a":1}}')));
    expect(seen[0].headers.host).toBe(`127.0.0.1:${port}`);
    expect(seen[0].body).toBe('{"set":{"a":1}}');
  });

  it("forwards a route's extra headers, but they cannot override Authorization", async () => {
    await serviceRequest(
      { port, token: TOKEN },
      { method: "GET", path: "/v1/artifacts/x", binary: true, headers: { Range: "bytes=10-", Authorization: "Bearer evil" } },
    );
    expect(seen[0].headers.range).toBe("bytes=10-");
    expect(seen[0].headers.authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("does not let a differently-cased authorization header override the token either", async () => {
    await serviceRequest(
      { port, token: TOKEN },
      { method: "GET", path: "/v1/artifacts/x", binary: true, headers: { authorization: "Bearer evil" } },
    );
    expect(seen[0].headers.authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("sends DELETE with a JSON body", async () => {
    await serviceRequest({ port, token: TOKEN }, { method: "DELETE", path: "/v1/follow", body: { model: "p/m" }, binary: false });
    expect(seen[0].method).toBe("DELETE");
    expect(seen[0].body).toBe('{"model":"p/m"}');
  });

  it("sends no body or content type on a GET", async () => {
    await serviceRequest({ port, token: TOKEN }, { method: "GET", path: "/v1/runs", binary: false });
    expect(seen[0].method).toBe("GET");
    expect(seen[0].body).toBe("");
    expect(seen[0].headers["content-type"]).toBeUndefined();
  });

  it("returns status, status text and exact bytes", async () => {
    const payload = Buffer.from([0, 1, 2, 250, 251, 252, 255]);
    handler = (_req, res) => {
      res.writeHead(200, "Fine", { "Content-Type": "application/octet-stream" });
      res.end(payload);
    };
    const answer = await serviceRequest({ port, token: TOKEN }, { method: "GET", path: "/v1/artifacts/x", binary: true });
    expect(answer.status).toBe(200);
    expect(answer.statusText).toBe("Fine");
    expect([...answer.bytes]).toEqual([...payload]);
  });

  it("returns a large body intact", async () => {
    const payload = Buffer.alloc(3 * 1024 * 1024, 7);
    handler = (_req, res) => void res.end(payload);
    const answer = await serviceRequest({ port, token: TOKEN }, { method: "GET", path: "/v1/artifacts/x", binary: true });
    expect(answer.bytes.byteLength).toBe(payload.byteLength);
  });

  it("returns non-2xx answers instead of throwing", async () => {
    handler = (_req, res) => {
      res.writeHead(404, "Not Found", { "Content-Type": "application/json" });
      res.end('{"error":"nope"}');
    };
    const answer = await serviceRequest({ port, token: TOKEN }, { method: "GET", path: "/v1/runs", binary: false });
    expect(answer.status).toBe(404);
    expect(new TextDecoder().decode(answer.bytes)).toBe('{"error":"nope"}');
  });

  it("fails with a refused HttpFailure when nothing is listening", async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    const error = await serviceRequest({ port, token: TOKEN }, { method: "GET", path: "/v1/runs", binary: false }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(HttpFailure);
    expect((error as HttpFailure).refused).toBe(true);
    server = http.createServer(); // keep afterEach's close() valid
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  });

  it("fails without `refused` when the connection drops mid-response", async () => {
    handler = (_req, res) => {
      res.writeHead(200, { "Content-Length": "100" });
      res.write("partial");
      setTimeout(() => res.destroy(), 10);
    };
    const error = await serviceRequest({ port, token: TOKEN }, { method: "GET", path: "/v1/runs", binary: false }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(HttpFailure);
    expect((error as HttpFailure).refused).toBe(false);
  });

  it("rejects when aborted", async () => {
    handler = () => {
      /* never answers */
    };
    const controller = new AbortController();
    const pending = serviceRequest(
      { port, token: TOKEN },
      { method: "GET", path: "/v1/jobs/x", binary: false },
      controller.signal,
    );
    setTimeout(() => controller.abort(), 20);
    const error = await pending.catch((e: unknown) => e);
    expect(error).toBeInstanceOf(HttpFailure);
    expect((error as HttpFailure).refused).toBe(false);
  });
});

describe("fetchHealth", () => {
  it("fetches /v1/health without a token", async () => {
    handler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end('{"service":"cadstudio","pid":5}');
    };
    expect(await fetchHealth(port)).toEqual({ service: "cadstudio", pid: 5 });
    expect(seen[0].url).toBe("/v1/health");
    expect(seen[0].headers.authorization).toBeUndefined();
  });

  it("returns null for a non-200 answer, non-JSON, an oversized body and a closed port", async () => {
    handler = (_req, res) => void res.writeHead(500).end("{}");
    expect(await fetchHealth(port)).toBeNull();
    handler = (_req, res) => void res.writeHead(200).end("not json");
    expect(await fetchHealth(port)).toBeNull();
    handler = (_req, res) => void res.writeHead(200).end("x".repeat(100 * 1024));
    expect(await fetchHealth(port)).toBeNull();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    expect(await fetchHealth(port)).toBeNull();
    server = http.createServer();
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  });

  it("returns null when the service stays silent past the timeout", async () => {
    handler = () => {
      /* never answers */
    };
    expect(await fetchHealth(port, 100)).toBeNull();
  });
});

function collect() {
  const events: SseEvent[] = [];
  const log: string[] = [];
  const closes: Array<{ message: string; status?: number }> = [];
  const handlers: EventStreamHandlers = {
    onOpen: () => void log.push("open"),
    onEvent: (event) => void events.push(event),
    onClose: (reason) => void closes.push(reason),
  };
  return { events, log, closes, handlers };
}

async function until(predicate: () => boolean, ms = 2000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("timed out waiting for condition");
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

describe("openEventStream", () => {
  it("authenticates with the header (not the query) and parses events split across chunks", async () => {
    let response!: http.ServerResponse;
    handler = (_req, res) => {
      response = res;
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      res.write(": keepalive\n\nevent: jo");
    };
    const c = collect();
    const stream = openEventStream({ port, token: TOKEN }, c.handlers);
    await until(() => c.log.includes("open"));
    response.write('b\ndata: {"job":');
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(c.events).toEqual([]);
    response.write('{"id":"a"}}\n\nevent: artifact\r\ndata: {"kind":"run","runId":"r"}\r\n\r\n');
    await until(() => c.events.length === 2);
    expect(c.events).toEqual([
      { event: "job", data: '{"job":{"id":"a"}}' },
      { event: "artifact", data: '{"kind":"run","runId":"r"}' },
    ]);
    expect(seen[0].url).toBe("/v1/events");
    expect(seen[0].headers.authorization).toBe(`Bearer ${TOKEN}`);
    expect(seen[0].headers.accept).toBe("text/event-stream");
    stream.close();
  });

  it("decodes a multi-byte character split across chunks", async () => {
    let response!: http.ServerResponse;
    handler = (_req, res) => {
      response = res;
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      res.flushHeaders();
    };
    const c = collect();
    const stream = openEventStream({ port, token: TOKEN }, c.handlers);
    await until(() => c.log.includes("open"));
    const bytes = Buffer.from("event: job\ndata: é\n\n");
    const split = bytes.indexOf(0xc3) + 1;
    response.write(bytes.subarray(0, split));
    await new Promise((resolve) => setTimeout(resolve, 20));
    response.write(bytes.subarray(split));
    await until(() => c.events.length === 1);
    expect(c.events[0].data).toBe("é");
    stream.close();
  });

  it("reports a non-200 answer once, with its status, and never opens", async () => {
    handler = (_req, res) => void res.writeHead(401).end('{"error":"unauthorized"}');
    const c = collect();
    openEventStream({ port, token: TOKEN }, c.handlers);
    await until(() => c.closes.length > 0);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(c.log).toEqual([]);
    expect(c.closes).toEqual([{ message: "event stream answered HTTP 401", status: 401 }]);
  });

  it("reports one close when the server ends the stream", async () => {
    handler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      res.write("event: job\ndata: {}\n\n");
      setTimeout(() => res.end(), 10);
    };
    const c = collect();
    openEventStream({ port, token: TOKEN }, c.handlers);
    await until(() => c.closes.length > 0);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(c.events).toHaveLength(1);
    expect(c.closes).toHaveLength(1);
  });

  it("reports a close when nothing is listening", async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    const c = collect();
    openEventStream({ port, token: TOKEN }, c.handlers);
    await until(() => c.closes.length > 0);
    expect(c.closes).toHaveLength(1);
    expect(c.log).toEqual([]);
    server = http.createServer();
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  });

  it("close() ends the connection and then reports nothing", async () => {
    let serverSawClose = false;
    handler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      res.write(": hi\n\n");
      res.on("close", () => void (serverSawClose = true));
    };
    const c = collect();
    const stream = openEventStream({ port, token: TOKEN }, c.handlers);
    await until(() => c.log.includes("open"));
    stream.close();
    await until(() => serverSawClose);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(c.closes).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";
import { BrowserTransport } from "./browser";
import { TransportError } from "./types";
import { VsCodeTransport } from "./vscode";

interface Call {
  url: string;
  init: RequestInit;
}

function browser(handler: (call: Call) => Response) {
  const calls: Call[] = [];
  const impl = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const call = { url: String(input), init };
    calls.push(call);
    return handler(call);
  }) as typeof fetch;
  return { transport: new BrowserTransport({ baseUrl: "http://127.0.0.1:4321", token: "tok", fetch: impl }), calls };
}

const header = (call: Call, name: string) => new Headers(call.init.headers).get(name);
const bytesOf = (buffer: ArrayBuffer) => [...new Uint8Array(buffer)];

describe("BrowserTransport: follow, live and ranged artifacts", () => {
  it("follow POSTs {model} and unfollow DELETEs {model}", async () => {
    const { transport, calls } = browser(() => new Response('{"model":"p/m","expiresAt":1,"leaseSeconds":60,"following":[]}'));
    await transport.follow("p/m");
    await transport.unfollow("p/m");
    expect(calls.map((c) => [c.init.method, c.url, c.init.body])).toEqual([
      ["POST", "http://127.0.0.1:4321/v1/follow", '{"model":"p/m"}'],
      ["DELETE", "http://127.0.0.1:4321/v1/follow", '{"model":"p/m"}'],
    ]);
    expect(header(calls[0], "Authorization")).toBe("Bearer tok");
    expect(header(calls[0], "Content-Type")).toBe("application/json");
  });

  it("listLive and getLive GET their routes", async () => {
    const { transport, calls } = browser(() => new Response('{"lives":[]}'));
    await transport.listLive();
    await transport.getLive("p/runs/r 1");
    expect(calls.map((c) => [c.init.method ?? "GET", c.url])).toEqual([
      ["GET", "http://127.0.0.1:4321/v1/live"],
      ["GET", "http://127.0.0.1:4321/v1/live/p/runs/r%201"],
    ]);
  });

  it("sends Range: bytes=N- for an offset and returns the 206 body", async () => {
    const { transport, calls } = browser(() => new Response(new Uint8Array([7, 8, 9]), { status: 206 }));
    expect(bytesOf(await transport.getArtifact("p/runs/r.live/poses.bin", { offset: 140 }))).toEqual([7, 8, 9]);
    expect(header(calls[0], "Range")).toBe("bytes=140-");
    expect(header(calls[0], "Authorization")).toBe("Bearer tok");
  });

  it("sends no Range without an offset or at offset 0", async () => {
    const { transport, calls } = browser(() => new Response(new Uint8Array([1])));
    await transport.getArtifact("a/b");
    await transport.getArtifact("a/b", { offset: 0 });
    expect(calls.map((c) => header(c, "Range"))).toEqual([null, null]);
  });

  it("treats 416 on a ranged read as empty and 416 without one as an error", async () => {
    const { transport } = browser(() => new Response('{"error":"range not satisfiable"}', { status: 416 }));
    const empty = await transport.getArtifact("a/b", { offset: 28 });
    expect(empty).toBeInstanceOf(ArrayBuffer);
    expect(empty.byteLength).toBe(0);
    await expect(transport.getArtifact("a/b")).rejects.toMatchObject({ status: 416, message: "range not satisfiable" });
    await expect(transport.getArtifact("a/b", { offset: 0 })).rejects.toBeInstanceOf(TransportError);
  });

  it("keeps only the tail when the server ignored Range and sent the whole file with 200", async () => {
    const { transport } = browser(() => new Response(new Uint8Array([0, 1, 2, 3, 4, 5])));
    expect(bytesOf(await transport.getArtifact("a/b", { offset: 4 }))).toEqual([4, 5]);
  });

  it("still fails other errors on a ranged read", async () => {
    const { transport } = browser(() => new Response('{"error":"no such artifact"}', { status: 404 }));
    await expect(transport.getArtifact("a/b", { offset: 4 })).rejects.toMatchObject({ status: 404 });
  });
});

function vscodeSetup() {
  const posted: Array<{ kind: string; id: number; method: string; args: unknown[] }> = [];
  let deliver: (data: unknown) => void = () => {};
  const transport = new VsCodeTransport({
    api: { postMessage: (message) => void posted.push(message as never) },
    listen: (listener) => {
      deliver = listener;
      return () => {};
    },
  });
  const answer = (index: number, reply: Record<string, unknown>) => deliver({ kind: "response", id: posted[index].id, ...reply });
  return { transport, posted, answer };
}

describe("VsCodeTransport: follow, live and ranged artifacts", () => {
  it("posts follow, unfollow, listLive and getLive with the documented argument shapes", async () => {
    const { transport, posted, answer } = vscodeSetup();
    const calls = [
      transport.follow("p/m"),
      transport.unfollow("p/m"),
      transport.listLive(),
      transport.getLive("p/runs/r1"),
    ];
    expect(posted.map((m) => [m.method, m.args])).toEqual([
      ["follow", [{ model: "p/m" }]],
      ["unfollow", [{ model: "p/m" }]],
      ["listLive", []],
      ["getLive", [{ liveId: "p/runs/r1" }]],
    ]);
    answer(0, { ok: true, result: { model: "p/m", expiresAt: 1, leaseSeconds: 60, following: [] } });
    answer(1, { ok: true, result: { following: [] } });
    answer(2, { ok: true, result: { lives: [] } });
    answer(3, { ok: true, result: { liveId: "p/runs/r1" } });
    const [lease, unfollowed, lives, doc] = await Promise.all(calls);
    expect(lease).toMatchObject({ leaseSeconds: 60 });
    expect(unfollowed).toBeUndefined();
    expect(lives).toEqual({ lives: [] });
    expect(doc).toMatchObject({ liveId: "p/runs/r1" });
  });

  it("posts [path, {offset}] only when offset > 0", async () => {
    const { transport, posted, answer } = vscodeSetup();
    const calls = [
      transport.getArtifact("a/b.bin"),
      transport.getArtifact("a/b.bin", { offset: 0 }),
      transport.getArtifact("a/b.bin", { offset: 28 }),
    ];
    expect(posted.map((m) => m.args)).toEqual([["a/b.bin"], ["a/b.bin"], ["a/b.bin", { offset: 28 }]]);
    for (let i = 0; i < 3; i += 1) answer(i, { ok: true, result: new Uint8Array([i]).buffer });
    expect((await Promise.all(calls)).map(bytesOf)).toEqual([[0], [1], [2]]);
  });

  it("treats a 416 error on a ranged read as empty and on an unranged one as an error", async () => {
    const { transport, answer } = vscodeSetup();
    const ranged = transport.getArtifact("a/b.bin", { offset: 28 });
    answer(0, { ok: false, error: { status: 416, message: "range not satisfiable" } });
    expect((await ranged).byteLength).toBe(0);
    const plain = transport.getArtifact("a/b.bin");
    answer(1, { ok: false, error: { status: 416, message: "range not satisfiable" } });
    await expect(plain).rejects.toMatchObject({ status: 416 });
  });

  it("returns the host's empty ArrayBuffer for a ranged read at the end", async () => {
    const { transport, answer } = vscodeSetup();
    const ranged = transport.getArtifact("a/b.bin", { offset: 28 });
    answer(0, { ok: true, result: new ArrayBuffer(0) });
    const buffer = await ranged;
    expect(buffer).toBeInstanceOf(ArrayBuffer);
    expect(buffer.byteLength).toBe(0);
  });

  it("fails a ranged read whose result is not binary", async () => {
    const { transport, answer } = vscodeSetup();
    const ranged = transport.getArtifact("a/b.bin", { offset: 28 });
    answer(0, { ok: true, result: { not: "bytes" } });
    await expect(ranged).rejects.toMatchObject({ status: 0, message: "artifact response is not binary" });
  });
});

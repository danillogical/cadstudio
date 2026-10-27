import { describe, expect, it } from "vitest";
import { SseParser, type SseEvent } from "./sse";

function parseAll(chunks: string[]): SseEvent[] {
  const parser = new SseParser();
  return chunks.flatMap((chunk) => parser.push(chunk));
}

const STREAM = 'event: job\ndata: {"job":{"id":"a"}}\n\nevent: artifact\ndata: {"kind":"scene","model":"p/m"}\n\n';
const EXPECTED: SseEvent[] = [
  { event: "job", data: '{"job":{"id":"a"}}' },
  { event: "artifact", data: '{"kind":"scene","model":"p/m"}' },
];

describe("SseParser", () => {
  it("parses whole events in one chunk", () => {
    expect(parseAll([STREAM])).toEqual(EXPECTED);
  });

  it("is independent of where the chunk boundaries fall (every split point, and byte-at-a-time)", () => {
    for (let i = 0; i <= STREAM.length; i += 1) {
      expect(parseAll([STREAM.slice(0, i), STREAM.slice(i)])).toEqual(EXPECTED);
    }
    expect(parseAll([...STREAM])).toEqual(EXPECTED);
  });

  it("handles CRLF line ends at every split point, including between \\r and \\n", () => {
    const crlf = STREAM.replace(/\n/g, "\r\n");
    expect(parseAll([crlf])).toEqual(EXPECTED);
    for (let i = 0; i <= crlf.length; i += 1) {
      expect(parseAll([crlf.slice(0, i), crlf.slice(i)])).toEqual(EXPECTED);
    }
    expect(parseAll([...crlf])).toEqual(EXPECTED);
  });

  it("handles bare \\r line ends", () => {
    // A lone trailing \r might be half of \r\n, so the final blank line resolves on the next byte.
    const parser = new SseParser();
    const bare = STREAM.replace(/\n/g, "\r");
    expect([...parser.push(bare), ...parser.push("data")]).toEqual(EXPECTED);
  });

  it("does not dispatch an event until its blank line arrives", () => {
    const parser = new SseParser();
    expect(parser.push("event: job\ndata: {}\n")).toEqual([]);
    expect(parser.push("data: more")).toEqual([]);
    expect(parser.push("\n")).toEqual([]);
    expect(parser.push("\n")).toEqual([{ event: "job", data: "{}\nmore" }]);
  });

  it("ignores comment lines and keepalives, also mid-event", () => {
    expect(parseAll([": keepalive\n\n", ":\n\n", "event: job\n: note\ndata: 1\n\n", ": tail\n"])).toEqual([
      { event: "job", data: "1" },
    ]);
  });

  it("joins multi-line data with newlines", () => {
    expect(parseAll(["event: job\ndata: a\ndata: b\ndata:\ndata: d\n\n"])).toEqual([{ event: "job", data: "a\nb\n\nd" }]);
  });

  it("names an event without an event field `message`", () => {
    expect(parseAll(["data: hi\n\n"])).toEqual([{ event: "message", data: "hi" }]);
  });

  it("strips only one leading space from the value, and allows a missing space", () => {
    expect(parseAll(["event:job\ndata:  two\n\n"])).toEqual([{ event: "job", data: " two" }]);
  });

  it("does not dispatch an event with no data, and resets the event name afterwards", () => {
    expect(parseAll(["event: job\n\n", "data: x\n\n"])).toEqual([{ event: "message", data: "x" }]);
  });

  it("ignores unknown fields such as id and retry", () => {
    expect(parseAll(["id: 5\nretry: 100\nfoo: bar\nevent: job\ndata: x\n\n"])).toEqual([{ event: "job", data: "x" }]);
  });

  it("keeps a colon inside the value", () => {
    expect(parseAll(["data: a:b:c\n\n"])).toEqual([{ event: "message", data: "a:b:c" }]);
  });

  it("returns events in order across many pushes", () => {
    const parser = new SseParser();
    const out: SseEvent[] = [];
    for (let i = 0; i < 20; i += 1) out.push(...parser.push(`event: job\ndata: ${i}\n\n`));
    expect(out.map((e) => e.data)).toEqual(Array.from({ length: 20 }, (_, i) => String(i)));
  });
});

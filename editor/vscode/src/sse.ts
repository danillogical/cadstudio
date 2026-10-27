/** One dispatched Server-Sent Event. */
export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Incremental `text/event-stream` parser: feed decoded chunks, get whole events back.
 * Handles `\n`, `\r\n` and `\r` line ends, multi-line `data:`, and `:` comment lines
 * (the service's keepalives); an event with no `event:` field is named `message`.
 */
export class SseParser {
  private buffer = "";
  private event = "";
  private data: string[] = [];

  push(chunk: string): SseEvent[] {
    this.buffer += chunk;
    const out: SseEvent[] = [];
    for (;;) {
      const match = /\r\n|\r|\n/.exec(this.buffer);
      if (!match) break;
      // A lone trailing \r may be the first half of \r\n; wait for the next chunk.
      if (match[0] === "\r" && match.index === this.buffer.length - 1) break;
      const line = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const dispatched = this.line(line);
      if (dispatched) out.push(dispatched);
    }
    return out;
  }

  private line(line: string): SseEvent | null {
    if (line === "") {
      const ready = this.data.length > 0 ? { event: this.event || "message", data: this.data.join("\n") } : null;
      this.event = "";
      this.data = [];
      return ready;
    }
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }
}

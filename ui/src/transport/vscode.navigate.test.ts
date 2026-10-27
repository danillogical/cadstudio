import { describe, expect, it } from "vitest";
import type { NavigateTarget } from "./messages";
import { VsCodeTransport } from "./vscode";

function setup() {
  const posted: unknown[] = [];
  let deliver: (data: unknown) => void = () => {};
  let stopped = false;
  const transport = new VsCodeTransport({
    api: { postMessage: (message) => void posted.push(message) },
    listen: (listener) => {
      deliver = listener;
      return () => {
        stopped = true;
      };
    },
  });
  return { transport, posted, deliver: (data: unknown) => deliver(data), isStopped: () => stopped };
}

describe("VsCodeTransport.onNavigate", () => {
  it("delivers validated navigates to every listener", () => {
    const { transport, deliver } = setup();
    const a: NavigateTarget[] = [];
    const b: NavigateTarget[] = [];
    transport.onNavigate((t) => a.push(t));
    transport.onNavigate((t) => b.push(t));
    deliver({ kind: "navigate", model: "pocky/syringe" });
    deliver({ kind: "navigate", run: "mj/r1" });
    expect(a).toEqual([{ model: "pocky/syringe" }, { run: "mj/r1" }]);
    expect(b).toEqual(a);
  });

  it("ignores invalid navigates", () => {
    const { transport, deliver } = setup();
    const seen: NavigateTarget[] = [];
    transport.onNavigate((t) => seen.push(t));
    deliver({ kind: "navigate" });
    deliver({ kind: "navigate", model: "a/b/c" });
    deliver({ kind: "navigate", run: "../x" });
    deliver({ kind: "navigate", run: "r", model: "p/m" });
    deliver({ kind: "navigate", model: "p/m", extra: true });
    deliver({ kind: "navigate", run: "/etc/passwd" });
    deliver("navigate");
    deliver(null);
    expect(seen).toEqual([]);
  });

  it("the remover stops delivery and dispose clears listeners", () => {
    const { transport, deliver } = setup();
    const seen: NavigateTarget[] = [];
    const remove = transport.onNavigate((t) => seen.push(t));
    deliver({ kind: "navigate", model: "p/m" });
    remove();
    deliver({ kind: "navigate", model: "p/m2" });
    expect(seen).toEqual([{ model: "p/m" }]);
    transport.onNavigate((t) => seen.push(t));
    transport.dispose();
    deliver({ kind: "navigate", model: "p/m3" });
    expect(seen).toHaveLength(1);
  });

  it("a navigate does not disturb requests or events", async () => {
    const { transport, posted, deliver } = setup();
    transport.onNavigate(() => {});
    const events: unknown[] = [];
    transport.subscribe((e) => events.push(e));
    const pending = transport.health();
    deliver({ kind: "navigate", model: "p/m" });
    deliver({ kind: "response", id: 1, ok: true, result: { service: "cadstudio" } });
    await expect(pending).resolves.toEqual({ service: "cadstudio" });
    expect(posted).toContainEqual({ kind: "subscribe" });
  });
});

describe("VsCodeTransport.ready", () => {
  it("posts exactly the ready message", () => {
    const { transport, posted } = setup();
    transport.ready();
    expect(posted).toEqual([{ kind: "ready" }]);
  });

  it("posts nothing on construction or on onNavigate", () => {
    const { transport, posted } = setup();
    transport.onNavigate(() => {});
    expect(posted).toEqual([]);
  });
});

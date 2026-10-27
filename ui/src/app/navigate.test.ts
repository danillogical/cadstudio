import { describe, expect, it } from "vitest";
import { isModelSpec, isRunId, parseNavigate } from "../transport/messages";
import { targetFromSearch } from "./navigate";

describe("parseNavigate", () => {
  it("accepts exactly {kind, model} or {kind, run}", () => {
    expect(parseNavigate({ kind: "navigate", model: "pocky/syringe" })).toEqual({ model: "pocky/syringe" });
    expect(parseNavigate({ kind: "navigate", run: "mj/two-cycle/r1" })).toEqual({ run: "mj/two-cycle/r1" });
    expect(parseNavigate({ run: "r1", kind: "navigate" })).toEqual({ run: "r1" });
  });

  it("rejects extra keys and both targets", () => {
    expect(parseNavigate({ kind: "navigate", model: "p/m", extra: 1 })).toBeNull();
    expect(parseNavigate({ kind: "navigate", model: "p/m", run: "r" })).toBeNull();
    expect(parseNavigate({ kind: "navigate", run: "r", url: "http://evil" })).toBeNull();
  });

  it("rejects a missing target, the wrong kind and non-objects", () => {
    expect(parseNavigate({ kind: "navigate" })).toBeNull();
    expect(parseNavigate({ kind: "navigate", other: "x" })).toBeNull();
    expect(parseNavigate({ kind: "event", model: "p/m" })).toBeNull();
    expect(parseNavigate({ model: "p/m" })).toBeNull();
    for (const bad of [null, undefined, 5, "navigate", ["navigate", "p/m"], true]) {
      expect(parseNavigate(bad)).toBeNull();
    }
  });

  it("rejects bad model specs", () => {
    for (const model of ["", "pocky", "a/b/c", "/pocky/syringe", "pocky/", "../x", "pocky/..", "a b/c", "p\\m",
      "p/m\u0000", ".hidden/m", "p/-m", 5, null, undefined, ["p/m"], { a: 1 }]) {
      expect(parseNavigate({ kind: "navigate", model }), String(model)).toBeNull();
    }
  });

  it("rejects traversal, absolute and malformed run ids", () => {
    for (const run of ["", "/etc/passwd", "../x", "a/../b", "a/./b", "a//b", "a/", "./a", "a\\b", "a\u0000b",
      "a\nb", "a\u007fb", "x".repeat(1025), 5, null, undefined, ["r"], { a: 1 }]) {
      expect(parseNavigate({ kind: "navigate", run }), String(run)).toBeNull();
    }
  });

  it("accepts run ids with dots, dashes and nested directories", () => {
    expect(parseNavigate({ kind: "navigate", run: "out-1/run.2/wedge_clamped" })).toEqual({
      run: "out-1/run.2/wedge_clamped",
    });
    expect(parseNavigate({ kind: "navigate", run: "..a/b" })).toEqual({ run: "..a/b" });
  });
});

describe("isModelSpec / isRunId", () => {
  it("agree with the service's segment rule", () => {
    expect(isModelSpec("pocky/packet_dummy")).toBe(true);
    expect(isModelSpec("armor/armor_neon.v2")).toBe(true);
    expect(isModelSpec("pocky")).toBe(false);
    expect(isRunId("a/b")).toBe(true);
    expect(isRunId("a/..")).toBe(false);
  });
});

describe("targetFromSearch", () => {
  it("reads ?model=", () => {
    expect(targetFromSearch("?token=t&model=pocky%2Fsyringe")).toEqual({ model: "pocky/syringe" });
    expect(targetFromSearch("model=pocky/syringe")).toEqual({ model: "pocky/syringe" });
  });

  it("reads ?run=", () => {
    expect(targetFromSearch("?run=mj%2Fr1&token=t")).toEqual({ run: "mj/r1" });
  });

  it("is null without a target or with an invalid one", () => {
    expect(targetFromSearch("")).toBeNull();
    expect(targetFromSearch("?token=t")).toBeNull();
    expect(targetFromSearch("?model=")).toBeNull();
    expect(targetFromSearch("?model=nope")).toBeNull();
    expect(targetFromSearch("?model=a%2Fb%2Fc")).toBeNull();
    expect(targetFromSearch("?run=")).toBeNull();
    expect(targetFromSearch("?run=..%2Fx")).toBeNull();
    expect(targetFromSearch("?run=%2Fetc")).toBeNull();
    expect(targetFromSearch("?run=a%5Cb")).toBeNull();
  });

  it("an invalid model does not fall through to a valid run", () => {
    expect(targetFromSearch("?model=bad&run=mj%2Fr1")).toBeNull();
  });
});

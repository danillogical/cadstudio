import { describe, expect, it } from "vitest";
import { OPEN_PATH, parseOpenRequestId, parseOpenUri } from "./uri";

describe("parseOpenUri", () => {
  it("accepts the open route and keeps the query", () => {
    expect(parseOpenUri({ path: OPEN_PATH, query: "x=1" })).toEqual({ query: "x=1" });
  });

  it("accepts the open route with a trailing slash", () => {
    expect(parseOpenUri({ path: "/open/", query: "a=b" })).toEqual({ query: "a=b" });
  });

  it("keeps an empty query as an empty string", () => {
    expect(parseOpenUri({ path: "/open", query: "" })).toEqual({ query: "" });
  });

  it("rejects other routes", () => {
    expect(parseOpenUri({ path: "/viewer", query: "run=x" })).toBeUndefined();
    expect(parseOpenUri({ path: "/", query: "" })).toBeUndefined();
  });
});

describe("parseOpenRequestId", () => {
  const ID = "abcDEF123_-abcDEF123_-";

  it("is undefined when there is no req (the plain open route)", () => {
    expect(parseOpenRequestId("")).toBeUndefined();
    expect(parseOpenRequestId("x=1")).toBeUndefined();
    expect(parseOpenRequestId("request=" + ID)).toBeUndefined();
  });

  it("returns a well-formed id, alone or among other parameters", () => {
    expect(parseOpenRequestId(`req=${ID}`)).toBe(ID);
    expect(parseOpenRequestId(`x=1&req=${ID}&y=2`)).toBe(ID);
    expect(parseOpenRequestId(`req=${"a".repeat(16)}`)).toBe("a".repeat(16));
    expect(parseOpenRequestId(`req=${"a".repeat(128)}`)).toBe("a".repeat(128));
  });

  it("is null when the id is malformed", () => {
    for (const bad of ["req=", "req=short", `req=${"a".repeat(15)}`, `req=${"a".repeat(129)}`,
      `req=${ID}.`, `req=${ID}%2F..`, "req=%00" + "a".repeat(20), `req=${ID}%20`, `req=a%2Fb${"c".repeat(16)}`]) {
      expect(parseOpenRequestId(bad), bad).toBeNull();
    }
  });

  it("is null when req is repeated, even with identical values", () => {
    expect(parseOpenRequestId(`req=${ID}&req=${ID}`)).toBeNull();
    expect(parseOpenRequestId(`req=${ID}&req=${"b".repeat(20)}`)).toBeNull();
  });
});

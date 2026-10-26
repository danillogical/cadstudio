import { describe, expect, it } from "vitest";
import { OPEN_PATH, parseOpenUri } from "./uri";

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

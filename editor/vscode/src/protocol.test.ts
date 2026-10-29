import { describe, expect, it } from "vitest";
import {
  exactArrayBuffer,
  isRelativePath,
  mapHttpResponse,
  MAX_PATH_LENGTH,
  MAX_SETS,
  networkError,
  parseModelSpec,
  parseWebviewMessage,
  rejectedError,
  routeFor,
  TRANSPORT_METHODS,
  type ValidCall,
} from "./protocol";

function request(method: unknown, args: unknown, id: unknown = 1, extra: Record<string, unknown> = {}) {
  return { kind: "request", id, method, args, ...extra };
}

function parseCall(method: string, args: unknown[]): ValidCall {
  const parsed = parseWebviewMessage(request(method, args));
  if (!parsed.ok || parsed.message.kind !== "request") throw new Error(`rejected: ${JSON.stringify(parsed)}`);
  return parsed.message.call;
}

const RUN = { model: "pocky/syringe", scenario: "projects/starter/scenarios/a.toml", acceptance: "projects/starter/acc.toml" };

const VALID: Array<[string, unknown[]]> = [
  ["health", []],
  ["listModels", []],
  ["listRuns", []],
  ["getScene", ["pocky/syringe"]],
  ["listPhysicsInputs", ["pocky/syringe"]],
  ["startBuild", ["armor/armor_neon"]],
  ["startBuild", ["armor/armor_neon", {}]],
  ["startBuild", ["armor/armor_neon", { "fit.slide_clearance": 0.5, label: "x", n: -3 }]],
  ["getTrajectory", ["run_2024-01-01"]],
  ["getTrajectory", ["pocky/runs/run_1"]],
  ["startRun", [RUN]],
  ["startRun", [{ ...RUN, options: "projects/starter/opts.toml" }]],
  ["getJob", ["a1b2c3"]],
  ["cancelJob", ["a1b2c3"]],
  ["getArtifact", ["pocky/syringe/scene/scene.glb"]],
  ["getArtifact", ["pocky/runs/r1.live/poses.bin", { offset: 0 }]],
  ["follow", [{ model: "pocky/syringe" }]],
  ["unfollow", [{ model: "pocky/syringe" }]],
  ["listLive", []],
  ["getLive", [{ liveId: "pocky/runs/r1" }]],
];

describe("parseWebviewMessage: accepted", () => {
  it("covers every transport method in the valid table", () => {
    const covered = new Set(VALID.map(([method]) => method));
    expect([...covered].sort()).toEqual([...TRANSPORT_METHODS].sort());
  });

  it.each(VALID)("accepts %s with valid args", (method, args) => {
    const parsed = parseWebviewMessage(request(method, args, 7));
    expect(parsed.ok).toBe(true);
    if (parsed.ok && parsed.message.kind === "request") {
      expect(parsed.message.id).toBe(7);
      expect(parsed.message.call.method).toBe(method);
    }
  });

  it("splits a model spec into project and model", () => {
    expect(parseCall("getScene", ["a/b.c-d_e"])).toEqual({ method: "getScene", project: "a", model: "b.c-d_e" });
  });

  it("accepts subscribe and unsubscribe with no other keys", () => {
    expect(parseWebviewMessage({ kind: "subscribe" })).toEqual({ ok: true, message: { kind: "subscribe" } });
    expect(parseWebviewMessage({ kind: "unsubscribe" })).toEqual({ ok: true, message: { kind: "unsubscribe" } });
  });

  it("accepts id 0 and a path of exactly the maximum length", () => {
    expect(parseWebviewMessage(request("health", [], 0)).ok).toBe(true);
    expect(parseWebviewMessage(request("getArtifact", ["a".repeat(MAX_PATH_LENGTH)])).ok).toBe(true);
    expect(parseWebviewMessage(request("startBuild", ["p/m", Object.fromEntries(Array.from({ length: MAX_SETS }, (_, i) => [`k${i}`, i]))])).ok).toBe(true);
  });
});

describe("parseWebviewMessage: envelope", () => {
  it.each([
    ["null", null],
    ["a string", "request"],
    ["a number", 7],
    ["an array", [{ kind: "request" }]],
    ["undefined", undefined],
  ])("drops %s with id null", (_name, raw) => {
    const parsed = parseWebviewMessage(raw);
    expect(parsed).toMatchObject({ ok: false, id: null });
  });

  it("drops an unknown kind", () => {
    expect(parseWebviewMessage({ kind: "evil" })).toMatchObject({ ok: false, id: null });
    expect(parseWebviewMessage({})).toMatchObject({ ok: false, id: null });
  });

  it.each([
    ["missing", undefined],
    ["a string", "1"],
    ["a float", 1.5],
    ["negative", -1],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["unsafe", Number.MAX_SAFE_INTEGER + 2],
    ["null", null],
  ])("drops a request whose id is %s", (_name, id) => {
    const raw: Record<string, unknown> = { kind: "request", method: "health", args: [] };
    if (id !== undefined) raw.id = id;
    expect(parseWebviewMessage(raw)).toMatchObject({ ok: false, id: null });
  });

  it("rejects extra envelope keys but keeps the id so the call can be answered", () => {
    expect(parseWebviewMessage(request("health", [], 9, { url: "http://evil" }))).toMatchObject({ ok: false, id: 9 });
    expect(parseWebviewMessage(request("health", [], 9, { token: "x" }))).toMatchObject({ ok: false, id: 9 });
  });

  it("rejects extra keys on subscribe and unsubscribe, dropping them", () => {
    expect(parseWebviewMessage({ kind: "subscribe", url: "x" })).toMatchObject({ ok: false, id: null });
    expect(parseWebviewMessage({ kind: "unsubscribe", id: 3 })).toMatchObject({ ok: false, id: null });
  });

  it.each([
    ["unknown", "deleteEverything"],
    ["wrong case", "ListModels"],
    ["prototype name", "constructor"],
    ["proto", "__proto__"],
    ["toString", "toString"],
    ["empty", ""],
    ["a number", 5],
    ["null", null],
    ["an object", { toString: () => "health" }],
    ["subscribe as a method", "subscribe"],
  ])("rejects method %s with the request id", (_name, method) => {
    expect(parseWebviewMessage(request(method, []))).toMatchObject({ ok: false, id: 1 });
  });

  it.each([
    ["missing", undefined],
    ["an object", {}],
    ["a string", "p/m"],
    ["null", null],
  ])("rejects args that are %s", (_name, args) => {
    const raw: Record<string, unknown> = { kind: "request", id: 4, method: "listModels" };
    if (args !== undefined) raw.args = args;
    expect(parseWebviewMessage(raw)).toMatchObject({ ok: false, id: 4 });
  });
});

describe("parseWebviewMessage: arguments", () => {
  const BAD: Array<[string, string, unknown[]]> = [
    ["health extra arg", "health", ["x"]],
    ["listModels extra arg", "listModels", [1]],
    ["listRuns extra arg", "listRuns", [null]],
    ["getScene no arg", "getScene", []],
    ["getScene two args", "getScene", ["p/m", "p/m"]],
    ["getScene number", "getScene", [42]],
    ["getScene null", "getScene", [null]],
    ["getScene array", "getScene", [["p/m"]]],
    ["getScene object", "getScene", [{ toString: () => "p/m" }]],
    ["listPhysicsInputs number", "listPhysicsInputs", [1]],
    ["startBuild no arg", "startBuild", []],
    ["startBuild three args", "startBuild", ["p/m", {}, 1]],
    ["startBuild sets null", "startBuild", ["p/m", null]],
    ["startBuild sets number", "startBuild", ["p/m", 5]],
    ["startBuild sets string", "startBuild", ["p/m", "a=1"]],
    ["startBuild sets array", "startBuild", ["p/m", [["a", 1]]]],
    ["startBuild sets boolean value", "startBuild", ["p/m", { a: true }]],
    ["startBuild sets null value", "startBuild", ["p/m", { a: null }]],
    ["startBuild sets object value", "startBuild", ["p/m", { a: { b: 1 } }]],
    ["startBuild sets array value", "startBuild", ["p/m", { a: [1] }]],
    ["startBuild sets NaN", "startBuild", ["p/m", { a: Number.NaN }]],
    ["startBuild sets Infinity", "startBuild", ["p/m", { a: Number.POSITIVE_INFINITY }]],
    ["startBuild sets -Infinity", "startBuild", ["p/m", { a: Number.NEGATIVE_INFINITY }]],
    ["startBuild sets empty key", "startBuild", ["p/m", { "": 1 }]],
    ["startBuild sets oversized string", "startBuild", ["p/m", { a: "x".repeat(1025) }]],
    ["startBuild too many sets", "startBuild", ["p/m", Object.fromEntries(Array.from({ length: MAX_SETS + 1 }, (_, i) => [`k${i}`, i]))]],
    ["getTrajectory no arg", "getTrajectory", []],
    ["getTrajectory number", "getTrajectory", [3]],
    ["getJob number", "getJob", [3]],
    ["getJob no arg", "getJob", []],
    ["cancelJob object", "cancelJob", [{ id: "x" }]],
    ["cancelJob two args", "cancelJob", ["a", "b"]],
    ["getArtifact number", "getArtifact", [3]],
    ["getArtifact no arg", "getArtifact", []],
    ["getArtifact too long", "getArtifact", ["a".repeat(MAX_PATH_LENGTH + 1)]],
    ["startRun no arg", "startRun", []],
    ["startRun string", "startRun", ["pocky/syringe"]],
    ["startRun array", "startRun", [[RUN]]],
    ["startRun null", "startRun", [null]],
    ["startRun two args", "startRun", [RUN, RUN]],
    ["startRun missing scenario", "startRun", [{ model: RUN.model, acceptance: RUN.acceptance }]],
    ["startRun missing acceptance", "startRun", [{ model: RUN.model, scenario: RUN.scenario }]],
    ["startRun missing model", "startRun", [{ scenario: RUN.scenario, acceptance: RUN.acceptance }]],
    ["startRun scenario number", "startRun", [{ ...RUN, scenario: 1 }]],
    ["startRun options null", "startRun", [{ ...RUN, options: null }]],
    ["startRun extra key", "startRun", [{ ...RUN, cwd: "/" }]],
    ["startRun extra key args", "startRun", [{ ...RUN, args: ["--evil"] }]],
    ["startRun extra key set", "startRun", [{ ...RUN, set: { a: 1 } }]],
  ];

  it.each(BAD)("rejects %s", (_name, method, args) => {
    expect(parseWebviewMessage(request(method, args, 11))).toMatchObject({ ok: false, id: 11 });
  });

  const TRAVERSAL = [
    "..",
    "../x",
    "a/../b",
    "a/..",
    "a/./b",
    "./a",
    ".",
    "/etc/passwd",
    "/",
    "a//b",
    "a/",
    "a\\b",
    "..\\x",
    "C:\\x",
    "a\u0000b",
    "a/b\u0000",
    "a\nb",
    "a\rb",
    "a\tb",
    "a\u001fb",
    "a\u007fb",
    "",
  ];

  it.each(TRAVERSAL)("isRelativePath refuses %j", (path) => {
    expect(isRelativePath(path)).toBe(false);
  });

  it.each(TRAVERSAL)("refuses %j as an artifact path, run id, scenario, acceptance and options", (path) => {
    expect(parseWebviewMessage(request("getArtifact", [path]))).toMatchObject({ ok: false });
    expect(parseWebviewMessage(request("getTrajectory", [path]))).toMatchObject({ ok: false });
    expect(parseWebviewMessage(request("startRun", [{ ...RUN, scenario: path }]))).toMatchObject({ ok: false });
    expect(parseWebviewMessage(request("startRun", [{ ...RUN, acceptance: path }]))).toMatchObject({ ok: false });
    expect(parseWebviewMessage(request("startRun", [{ ...RUN, options: path }]))).toMatchObject({ ok: false });
  });

  it.each(["..", ".", "", "/x", "a/b", "a b", "a\u0000", "a\n", "..\\x", "-x", ".hidden"])(
    "refuses %j as a job id",
    (id) => {
      expect(parseWebviewMessage(request("getJob", [id]))).toMatchObject({ ok: false });
      expect(parseWebviewMessage(request("cancelJob", [id]))).toMatchObject({ ok: false });
    },
  );

  it("refuses a job id over 128 characters", () => {
    expect(parseWebviewMessage(request("getJob", ["a".repeat(129)]))).toMatchObject({ ok: false });
    expect(parseWebviewMessage(request("getJob", ["a".repeat(128)])).ok).toBe(true);
  });

  const BAD_SPECS = [
    "",
    "p",
    "p/",
    "/m",
    "p//m",
    "p/m/x",
    "/p/m",
    "p/m/",
    "../m",
    "p/..",
    "p/.",
    "./m",
    "p\\m",
    "p/m\n",
    "p /m",
    "p/m q",
    "p/m?x=1",
    "p/m#x",
    "p/m%2f",
    "p:80/m",
    "p@h/m",
    "p/m\u0000",
    "pé/m",
    ".p/m",
    "-p/m",
    "p/" + "a".repeat(MAX_PATH_LENGTH),
  ];

  it.each(BAD_SPECS)("parseModelSpec refuses %j", (spec) => {
    expect(parseModelSpec(spec)).toBeNull();
    for (const method of ["getScene", "listPhysicsInputs", "startBuild"]) {
      expect(parseWebviewMessage(request(method, [spec]))).toMatchObject({ ok: false });
    }
    expect(parseWebviewMessage(request("startRun", [{ ...RUN, model: spec }]))).toMatchObject({ ok: false });
  });

  it("refuses a non-string model spec", () => {
    for (const spec of [null, undefined, 1, ["p", "m"], { project: "p", model: "m" }]) {
      expect(parseModelSpec(spec)).toBeNull();
    }
  });

  it("keeps the request id on a rejected call so the webview can reject it", () => {
    expect(parseWebviewMessage(request("getScene", ["../x"], 123))).toMatchObject({ ok: false, id: 123 });
  });
});

describe("routeFor", () => {
  it("maps every method to its documented endpoint", () => {
    const cases: Array<[string, unknown[], string, string, boolean]> = [
      ["health", [], "GET", "/v1/health", false],
      ["listModels", [], "GET", "/v1/models", false],
      ["listRuns", [], "GET", "/v1/runs", false],
      ["getScene", ["pocky/syringe"], "GET", "/v1/models/pocky/syringe/scene", false],
      ["listPhysicsInputs", ["pocky/syringe"], "GET", "/v1/models/pocky/syringe/physics-inputs", false],
      ["startBuild", ["pocky/syringe"], "POST", "/v1/models/pocky/syringe/build", false],
      ["getTrajectory", ["run_1"], "GET", "/v1/runs/run_1/trajectory", false],
      ["startRun", [RUN], "POST", "/v1/runs", false],
      ["getJob", ["j1"], "GET", "/v1/jobs/j1", false],
      ["cancelJob", ["j1"], "POST", "/v1/jobs/j1/cancel", false],
      ["getArtifact", ["pocky/syringe/scene/scene.glb"], "GET", "/v1/artifacts/pocky/syringe/scene/scene.glb", true],
      ["follow", [{ model: "pocky/syringe" }], "POST", "/v1/follow", false],
      ["unfollow", [{ model: "pocky/syringe" }], "DELETE", "/v1/follow", false],
      ["listLive", [], "GET", "/v1/live", false],
      ["getLive", [{ liveId: "pocky/runs/r1" }], "GET", "/v1/live/pocky/runs/r1", false],
    ];
    expect(cases.map(([method]) => method).sort()).toEqual([...TRANSPORT_METHODS].sort());
    for (const [method, args, httpMethod, path, binary] of cases) {
      const route = routeFor(parseCall(method, args));
      expect(route).toMatchObject({ method: httpMethod, path, binary });
    }
  });

  it("sends {} for a build without sets and {set} with them, as BrowserTransport does", () => {
    expect(routeFor(parseCall("startBuild", ["p/m"])).body).toEqual({});
    expect(routeFor(parseCall("startBuild", ["p/m", { a: 1, b: "x" }])).body).toEqual({ set: { a: 1, b: "x" } });
  });

  it("sends exactly model, scenario, acceptance and options for a run", () => {
    expect(routeFor(parseCall("startRun", [RUN])).body).toEqual(RUN);
    expect(routeFor(parseCall("startRun", [{ ...RUN, options: "o.toml" }])).body).toEqual({ ...RUN, options: "o.toml" });
  });

  it("only POSTs to the documented mutating endpoints and sends no body on GETs", () => {
    for (const [method, args] of VALID) {
      const route = routeFor(parseCall(method, args));
      if (route.method === "GET") expect(route.body).toBeUndefined();
      else expect(["startBuild", "startRun", "cancelJob", "follow", "unfollow"]).toContain(method);
    }
  });

  it("percent-encodes each segment and keeps the separators", () => {
    const route = routeFor(parseCall("getArtifact", ["a b/c#d/e?f=1/%2e/ü"]));
    expect(route.path).toBe("/v1/artifacts/a%20b/c%23d/e%3Ff%3D1/%252e/%C3%BC");
  });

  it("encodes percent signs so an encoded dot-dot stays a literal name", () => {
    expect(routeFor(parseCall("getArtifact", ["%2e%2e/x"])).path).toBe("/v1/artifacts/%252e%252e/x");
    expect(routeFor(parseCall("getTrajectory", ["%2E%2E"])).path).toBe("/v1/runs/%252E%252E/trajectory");
  });

  const HOSTILE = [
    "@evil.com/x",
    "evil.com:80/x",
    "x?token=stolen",
    "x#frag",
    "x?a=1&b=2",
    "a b",
    "a%00b",
    "a%2fb",
    "x\\y",
    "http:",
    "user:pw@host",
    "a'b",
    "a\"b",
    "<script>",
    "ü/ß",
  ];

  it.each(HOSTILE)("cannot change host, port or query via %j", (value) => {
    const base = "http://127.0.0.1:5555";
    const calls: Array<[string, unknown[]]> = [
      ["getArtifact", [value]],
      ["getTrajectory", [value]],
      ["getJob", [value]],
      ["cancelJob", [value]],
      ["getScene", [`${value}/m`]],
      ["startBuild", [`p/${value}`]],
    ];
    for (const [method, args] of calls) {
      const parsed = parseWebviewMessage(request(method, args));
      if (!parsed.ok || parsed.message.kind !== "request") continue; // refused earlier: also fine
      const route = routeFor(parsed.message.call);
      const url = new URL(route.path, base);
      expect(url.origin).toBe(base);
      expect(url.search).toBe("");
      expect(url.hash).toBe("");
      expect(url.username).toBe("");
      expect(route.path.startsWith("/v1/")).toBe(true);
      expect(route.path).toMatch(/^[A-Za-z0-9._~!*'()%\-/]*$/);
    }
  });

  it("never emits a query string for any valid call", () => {
    for (const [method, args] of VALID) {
      expect(routeFor(parseCall(method, args)).path).not.toMatch(/[?#]/);
    }
  });
});

describe("mapHttpResponse", () => {
  const enc = (value: string) => new TextEncoder().encode(value);

  it("returns the JSON object of a 2xx JSON route", () => {
    expect(mapHttpResponse(200, "OK", enc('{"a":1}'), false)).toEqual({ ok: true, result: { a: 1 } });
    expect(mapHttpResponse(202, "Accepted", enc('{"job":{"id":"x"}}'), false)).toEqual({
      ok: true,
      result: { job: { id: "x" } },
    });
  });

  it("rejects a 2xx JSON route whose body is not an object", () => {
    for (const text of ["", "[]", "3", "null", "not json", '"str"']) {
      expect(mapHttpResponse(200, "OK", enc(text), false)).toEqual({
        ok: false,
        error: { status: 200, message: "response is not a JSON object" },
      });
    }
  });

  it("prefers the server's error text, then the status text, then HTTP n", () => {
    expect(mapHttpResponse(404, "Not Found", enc('{"schemaVersion":1,"error":"no scene built"}'), false)).toEqual({
      ok: false,
      error: { status: 404, message: "no scene built", body: { schemaVersion: 1, error: "no scene built" } },
    });
    expect(mapHttpResponse(500, "Internal Server Error", enc("<html>boom</html>"), false)).toEqual({
      ok: false,
      error: { status: 500, message: "Internal Server Error" },
    });
    expect(mapHttpResponse(502, "", enc(""), false)).toEqual({ ok: false, error: { status: 502, message: "HTTP 502" } });
    expect(mapHttpResponse(400, "Bad Request", enc('{"error":7}'), false)).toEqual({
      ok: false,
      error: { status: 400, message: "Bad Request", body: { error: 7 } },
    });
    expect(mapHttpResponse(403, "", enc('{"other":1}'), false)).toEqual({
      ok: false,
      error: { status: 403, message: "HTTP 403", body: { other: 1 } },
    });
  });

  it("maps a non-2xx binary route to the same JSON error", () => {
    expect(mapHttpResponse(404, "Not Found", enc('{"error":"no such artifact"}'), true)).toEqual({
      ok: false,
      error: { status: 404, message: "no such artifact", body: { error: "no such artifact" } },
    });
  });

  it("treats 199 and 300 as errors", () => {
    expect(mapHttpResponse(300, "Multiple", enc("{}"), false)).toMatchObject({ ok: false });
    expect(mapHttpResponse(199, "", enc("{}"), false)).toMatchObject({ ok: false });
  });

  it("returns an exactly-sized ArrayBuffer for a binary route, from a pooled Buffer too", () => {
    const pooled = Buffer.from("glTF-bytes"); // small Buffers share a pool, so byteOffset is usually non-zero
    const reply = mapHttpResponse(200, "OK", pooled, true);
    expect(reply.ok).toBe(true);
    if (!reply.ok) return;
    const result = reply.result as ArrayBuffer;
    expect(result).toBeInstanceOf(ArrayBuffer);
    expect(Buffer.isBuffer(result)).toBe(false);
    expect(result.byteLength).toBe(pooled.byteLength);
    expect(new TextDecoder().decode(result)).toBe("glTF-bytes");
  });

  it("copies out of a larger backing store at an offset", () => {
    const backing = new Uint8Array([9, 9, 1, 2, 3, 9, 9]);
    const view = backing.subarray(2, 5);
    const result = exactArrayBuffer(view);
    expect([...new Uint8Array(result)]).toEqual([1, 2, 3]);
    expect(result.byteLength).toBe(3);
    backing[2] = 77; // the copy is independent
    expect(new Uint8Array(result)[0]).toBe(1);
  });

  it("returns an empty ArrayBuffer for an empty artifact", () => {
    const reply = mapHttpResponse(200, "OK", new Uint8Array(0), true);
    expect(reply).toMatchObject({ ok: true });
    expect((reply as { result: ArrayBuffer }).result.byteLength).toBe(0);
  });
});

describe("error constructors", () => {
  it("words a network failure like BrowserTransport", () => {
    expect(networkError(new Error("fetch failed"))).toEqual({ status: 0, message: "network error: fetch failed" });
    expect(networkError("boom")).toEqual({ status: 0, message: "network error: boom" });
  });

  it("marks a rejected message with status 400", () => {
    expect(rejectedError("nope")).toEqual({ status: 400, message: "rejected by the CADStudio extension: nope" });
  });
});

describe("follow, unfollow, live and ranged artifacts", () => {
  it("routes follow as POST and unfollow as DELETE on /v1/follow with the model in the body", () => {
    expect(routeFor(parseCall("follow", [{ model: "pocky/syringe" }]))).toEqual({
      method: "POST",
      path: "/v1/follow",
      body: { model: "pocky/syringe" },
      binary: false,
    });
    expect(routeFor(parseCall("unfollow", [{ model: "pocky/syringe" }]))).toEqual({
      method: "DELETE",
      path: "/v1/follow",
      body: { model: "pocky/syringe" },
      binary: false,
    });
  });

  it("routes listLive and getLive as body-less GETs", () => {
    expect(routeFor(parseCall("listLive", []))).toEqual({ method: "GET", path: "/v1/live", binary: false });
    expect(routeFor(parseCall("getLive", [{ liveId: "pocky/runs/r1" }]))).toEqual({
      method: "GET",
      path: "/v1/live/pocky/runs/r1",
      binary: false,
    });
  });

  const BAD_FOLLOW: unknown[][] = [
    [],
    [{}],
    [{ model: "pocky/syringe", extra: 1 }],
    [{ model: "pocky/syringe", project: "pocky" }],
    [{ model: 3 }],
    [{ model: null }],
    [{ model: ["pocky", "syringe"] }],
    [{ model: "pocky" }],
    [{ model: "pocky/syringe/x" }],
    [{ model: "../syringe" }],
    ["pocky/syringe"],
    [null],
    [["pocky/syringe"]],
    [{ model: "pocky/syringe" }, { model: "pocky/syringe" }],
  ];

  it.each(["follow", "unfollow"])("%s accepts exactly [{model: 'p/m'}]", (method) => {
    expect(parseWebviewMessage(request(method, [{ model: "p/m" }])).ok).toBe(true);
    for (const args of BAD_FOLLOW) {
      expect(parseWebviewMessage(request(method, args, 9)), JSON.stringify(args)).toMatchObject({ ok: false, id: 9 });
    }
  });

  const BAD_LIVE: unknown[][] = [
    [],
    ["pocky/runs/r1"],
    [null],
    [["pocky/runs/r1"]],
    [3],
    [{}],
    [{ liveId: 3 }],
    [{ liveId: "" }],
    [{ liveId: "../x" }],
    [{ liveId: "a/../b" }],
    [{ liveId: "a/./b" }],
    [{ liveId: "a//b" }],
    [{ liveId: "/etc/passwd" }],
    [{ liveId: "a\\b" }],
    [{ liveId: "a\u0000b" }],
    [{ liveId: "pocky/runs/r1", extra: 1 }],
    [{ liveId: "pocky/runs/r1" }, {}],
  ];

  it("getLive accepts a relative id and rejects .., absolute paths and non-object args", () => {
    expect(parseWebviewMessage(request("getLive", [{ liveId: "pocky/runs/r1" }])).ok).toBe(true);
    for (const args of BAD_LIVE) {
      expect(parseWebviewMessage(request("getLive", args, 9)), JSON.stringify(args)).toMatchObject({ ok: false, id: 9 });
    }
  });

  it("listLive takes no arguments", () => {
    expect(parseWebviewMessage(request("listLive", [{}], 9))).toMatchObject({ ok: false, id: 9 });
  });

  it.each([0, 1, 4096, 2 ** 40])("getArtifact accepts offset %i and sends Range: bytes=N-", (offset) => {
    const route = routeFor(parseCall("getArtifact", ["pocky/runs/r1.live/poses.bin", { offset }]));
    expect(route).toEqual({
      method: "GET",
      path: "/v1/artifacts/pocky/runs/r1.live/poses.bin",
      binary: true,
      headers: { Range: `bytes=${offset}-` },
    });
  });

  it("getArtifact without an offset sends no Range header", () => {
    expect(routeFor(parseCall("getArtifact", ["a/b.bin"])).headers).toBeUndefined();
  });

  const BAD_OFFSET: unknown[] = [
    -1,
    1.5,
    "3",
    null,
    undefined,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    2 ** 60,
    true,
    [3],
  ];

  it.each(BAD_OFFSET.map((v) => [String(v), v] as const))("getArtifact rejects offset %s", (_name, offset) => {
    expect(parseWebviewMessage(request("getArtifact", ["a/b.bin", { offset }], 4))).toMatchObject({ ok: false, id: 4 });
  });

  it("getArtifact rejects a malformed range argument", () => {
    for (const range of [null, 3, "3", [], [3], {}, { offset: 1, extra: 1 }, { start: 1 }, { Range: "bytes=1-" }]) {
      expect(parseWebviewMessage(request("getArtifact", ["a/b.bin", range], 4)), JSON.stringify(range)).toMatchObject({
        ok: false,
        id: 4,
      });
    }
    expect(parseWebviewMessage(request("getArtifact", ["a/b.bin", { offset: 1 }, { offset: 2 }], 4))).toMatchObject({
      ok: false,
    });
  });

  it("still applies the path rule to a ranged artifact", () => {
    expect(parseWebviewMessage(request("getArtifact", ["../x", { offset: 0 }]))).toMatchObject({ ok: false });
  });

  it("returns an empty ArrayBuffer (success) for a 416 on a ranged binary route", () => {
    const reply = mapHttpResponse(416, "Range Not Satisfiable", new TextEncoder().encode('{"error":"range"}'), true, true);
    expect(reply.ok).toBe(true);
    const result = (reply as { result: ArrayBuffer }).result;
    expect(result).toBeInstanceOf(ArrayBuffer);
    expect(result.byteLength).toBe(0);
  });

  it("still fails a 416 without a range, and a ranged 416 on a JSON route", () => {
    const body = new TextEncoder().encode('{"error":"range"}');
    expect(mapHttpResponse(416, "Range Not Satisfiable", body, true)).toEqual({
      ok: false,
      error: { status: 416, message: "range", body: { error: "range" } },
    });
    expect(mapHttpResponse(416, "Range Not Satisfiable", body, true, false)).toMatchObject({ ok: false });
    expect(mapHttpResponse(416, "Range Not Satisfiable", body, false, true)).toMatchObject({ ok: false });
  });

  it("still fails other errors on a ranged binary route", () => {
    expect(mapHttpResponse(404, "Not Found", new TextEncoder().encode("{}"), true, true)).toMatchObject({ ok: false });
    expect(mapHttpResponse(500, "", new Uint8Array(0), true, true)).toMatchObject({ ok: false });
  });

  it("accepts a 206 partial answer as the bytes", () => {
    const reply = mapHttpResponse(206, "Partial Content", new Uint8Array([1, 2, 3]), true, true);
    expect(reply.ok).toBe(true);
    expect((reply as { result: ArrayBuffer }).result.byteLength).toBe(3);
  });
});

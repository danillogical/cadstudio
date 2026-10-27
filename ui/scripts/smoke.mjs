#!/usr/bin/env node
// End-to-end smoke: start `cad gui serve`, then fetch health, a scene and a trajectory through
// the real BrowserTransport in Node. Exits 0 on success and stops only the service it started.
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const UI_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(UI_DIR, "..");
const OUT_ROOT = path.join(REPO_ROOT, "out");
const UV_RUN = ["run", "--frozen", "--extra", "physics"];
const SCENE_MODEL = "pocky/packet_dummy";
const START_TIMEOUT_MS = 180_000;
const JOB_TIMEOUT_MS = 600_000;
const STOP_TIMEOUT_MS = 10_000;

// The cheapest saved run: the generic drop_box fixture (same as tests/test_cadkit_gui_trajectory.py).
const SCENARIO = {
  schema_version: "m4a-1", scenario_id: "drop", fixture: "drop_box", seed: 1,
  timestep_s: 0.001, sampling_interval_s: 0.05,
  budgets: { max_steps: 20000, max_sim_time_s: 10.0, max_trace_rows: 20000 },
  phases: [{ name: "reset", kind: "reset" },
           { name: "settle", kind: "settle", duration_s: 0.6 },
           { name: "hold", kind: "hold", duration_s: 0.2 }],
};
const ACCEPTANCE = {
  schema_version: "m4a-1", acceptance_id: "drop_acceptance",
  validity: { max_penetration_m: 0.001, max_speed_m_s: 10.0, max_energy_j: 1.0 },
  checks: [
    { name: "contact", kind: "contact_force_bound", body_a: "box", body_b: "floor", max: 100.0, units: "N" },
    { name: "penetration", kind: "penetration_bound", max: 0.001, units: "m" },
  ],
};

function log(message) {
  console.log(`smoke: ${message}`);
}

function check(condition, message) {
  if (!condition) throw new Error(message);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Write the fixture into a fresh dir under out/gui-smoke/ and run it through `cad physics scenario`. */
function makeRun() {
  const base = path.join(OUT_ROOT, "gui-smoke");
  mkdirSync(base, { recursive: true });
  const dir = mkdtempSync(path.join(base, "run-"));
  const scenario = path.join(dir, "scenario.json");
  const acceptance = path.join(dir, "acceptance.json");
  writeFileSync(scenario, JSON.stringify(SCENARIO));
  writeFileSync(acceptance, JSON.stringify(ACCEPTANCE));
  const runDir = path.join(dir, "run");
  const result = spawnSync("uv", [...UV_RUN, "cad", "physics", "scenario", scenario,
    "--acceptance", acceptance, "--out", runDir], { cwd: REPO_ROOT, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(`cad physics scenario exited ${result.status}: ${result.stderr || result.stdout}`);
  }
  return { dir, runId: path.relative(OUT_ROOT, runDir).split(path.sep).join("/") };
}

/** Start the service; resolves with its `--json` record and the child process. */
function startService() {
  const child = spawn("uv", [...UV_RUN, "cad", "gui", "serve", "--port", "0", "--no-browser", "--json"], {
    cwd: REPO_ROOT,
    detached: true,
    stdio: ["ignore", "pipe", "inherit"],
  });
  return new Promise((resolve, reject) => {
    let buffer = "";
    const timer = setTimeout(() => reject(new Error("cad gui serve printed no URL in time")), START_TIMEOUT_MS);
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("exit", (code) => {
      if (!buffer.includes("\n")) {
        clearTimeout(timer);
        reject(new Error(`cad gui serve exited ${code} before printing its URL`));
      }
    });
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline < 0) return;
      clearTimeout(timer);
      try {
        resolve({ record: JSON.parse(buffer.slice(0, newline)), child });
      } catch (error) {
        reject(new Error(`cad gui serve printed non-JSON output: ${buffer.slice(0, newline)}`));
      }
    });
  });
}

/** SIGTERM the service's process group (uv and the Python server), then SIGKILL if needed. */
async function stopService(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", resolve));
  const signal = (name) => {
    try {
      process.kill(-child.pid, name);
    } catch {
      // Already gone.
    }
  };
  signal("SIGTERM");
  const done = await Promise.race([exited.then(() => true), sleep(STOP_TIMEOUT_MS).then(() => false)]);
  if (!done) {
    signal("SIGKILL");
    await exited;
  }
}

async function waitJob(transport, job) {
  const deadline = Date.now() + JOB_TIMEOUT_MS;
  let current = job;
  while (!["succeeded", "failed", "cancelled"].includes(current.status)) {
    check(Date.now() < deadline, `job ${job.id} did not finish in time`);
    await sleep(250);
    current = await transport.getJob(job.id);
  }
  return current;
}

function isGlb(bytes) {
  return bytes.byteLength > 12 && new TextDecoder().decode(new Uint8Array(bytes, 0, 4)) === "glTF";
}

async function main() {
  let vite = null;
  let started = null;
  let runDir = null;
  try {
    log("generating a small drop run");
    const run = makeRun();
    runDir = run.dir;

    log("starting cad gui serve");
    const { record, child } = await startService();
    if (record.reused) {
      log(`reusing the healthy registered service on port ${record.port}`);
    } else {
      started = child;
      log(`service started on port ${record.port}`);
    }
    const url = new URL(record.url);
    const token = url.searchParams.get("token");
    check(token, "the service URL carries no token");

    vite = await createServer({
      root: UI_DIR,
      configFile: false,
      logLevel: "error",
      appType: "custom",
      server: { middlewareMode: true, hmr: false, ws: false },
      optimizeDeps: { noDiscovery: true, include: [] },
    });
    const { BrowserTransport } = await vite.ssrLoadModule("/src/transport/browser.ts");
    const frames = await vite.ssrLoadModule("/src/playback/frames.ts");
    const transport = new BrowserTransport({ baseUrl: url.origin, token });

    const health = await transport.health();
    check(health.service === "cadstudio", `unexpected service ${health.service}`);
    check(health.protocolVersion === 1, `unexpected protocol ${health.protocolVersion}`);
    check(health.repoRoot === realpathSync(REPO_ROOT), `service is for another repo: ${health.repoRoot}`);
    log(`health ok (pid ${health.pid})`);

    const inputs = await transport.listPhysicsInputs("pocky/syringe");
    check(inputs.scenarios.length > 0 && inputs.acceptance.length > 0, "no physics inputs listed");
    log(`physics inputs ok (${inputs.scenarios.length} scenarios, ${inputs.acceptance.length} acceptance, ${inputs.options.length} options)`);

    log(`building ${SCENE_MODEL}`);
    const job = await waitJob(transport, await transport.startBuild(SCENE_MODEL));
    check(job.status === "succeeded", `build ${job.status}: ${job.error}`);
    const scene = await transport.getScene(SCENE_MODEL);
    check(scene.stale === false, "the scene is stale");
    check(scene.scene.parts.length > 0, "the scene has no parts");
    const part = scene.scene.parts[0];
    const partBytes = await transport.getArtifact(`${scene.artifactBase}/${part.mesh}`);
    check(isGlb(partBytes), `part ${part.id} is not a GLB`);
    log(`scene ok (${scene.scene.parts.length} part(s), ${part.id}.glb ${partBytes.byteLength} bytes)`);

    const runs = await transport.listRuns();
    check(runs.runs.some((entry) => entry.runId === run.runId), `run ${run.runId} is not listed`);
    const response = await transport.getTrajectory(run.runId);
    const doc = frames.parseTrajectory(response.trajectory);
    const poses = frames.parsePoses(
      await transport.getArtifact(`${response.artifactBase}/${doc.poses.path}`),
      doc.frameCount,
      doc.bodies.length,
    );
    const middle = (doc.times[0] + doc.times[doc.times.length - 1]) / 2;
    const sampled = frames.posesAt(doc.times, poses, doc.bodies.length, middle);
    check(sampled.length === doc.bodies.length, "pose sampling lost bodies");
    const mesh = doc.bodies[0].meshes[0];
    const meshBytes = await transport.getArtifact(`${response.artifactBase}/${mesh.mesh}`);
    check(isGlb(meshBytes), `body mesh ${mesh.mesh} is not a GLB`);
    log(`trajectory ok (${doc.frameCount} frames, ${doc.bodies.length} bodies, ${doc.phases.length} phases)`);
    log("PASS");
    return 0;
  } catch (error) {
    console.error(`smoke: FAIL: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  } finally {
    if (vite) await vite.close();
    if (started) await stopService(started);
    if (runDir) {
      rmSync(runDir, { recursive: true, force: true });
      try {
        rmdirSync(path.dirname(runDir));
      } catch {
        // Another smoke run still has a directory there.
      }
    }
  }
}

process.exitCode = await main();

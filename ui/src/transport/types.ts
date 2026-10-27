/** Wire types for the loopback GUI service (`cadkit/gui/server.py`). */

export interface HealthInfo {
  schemaVersion: number;
  service: string;
  protocolVersion: number;
  repoRoot: string;
  pid: number;
}

export interface ModelEntry {
  name: string;
  params_path: string;
  models: string[];
}

export interface ModelList {
  schemaVersion: number;
  projects: ModelEntry[];
  models: string[];
}

export interface Provenance {
  commit: string | null;
  dirty: boolean | null;
  paramsPath: string;
  paramsSha256: string;
  overrides: Record<string, number | string>;
  builtAt: string;
}

export type Vec3 = [number, number, number];

export interface BBox {
  min: Vec3;
  max: Vec3;
}

export interface ScenePart {
  id: string;
  name: string;
  mesh: string;
  bbox: BBox;
  /** Cubic millimetres. */
  volume: number;
  /** Hex colour string, e.g. `#6f9a86`. */
  color: string;
  /** Row-major 4x4 bed pose; assembly geometry is already in the GLB. */
  printPose?: number[][];
}

export interface SceneDoc {
  schemaVersion: number;
  project: string;
  model: string;
  units: string;
  provenance: Provenance;
  parts: ScenePart[];
}

export interface SceneResponse {
  schemaVersion: number;
  project: string;
  model: string;
  stale: boolean;
  error: string | null;
  job: string | null;
  artifactBase: string;
  scene: SceneDoc;
}

export interface RunEntry {
  runId: string;
  path: string;
  status: string | null;
}

export interface RunList {
  schemaVersion: number;
  runs: RunEntry[];
}

export interface TrajectoryResponse {
  schemaVersion: number;
  runId: string;
  stale: boolean;
  error: string | null;
  artifactBase: string;
  /** Validated by `parseTrajectory` (playback/frames.ts); kept loose so the transport does not pin it. */
  trajectory: Record<string, unknown>;
}

/** One mesh of a trajectory body; `pose` is the geom's local `[x,y,z,qw,qx,qy,qz]` (mm). */
export interface TrajectoryMesh {
  geom: string;
  mesh: string;
  pose: [number, number, number, number, number, number, number];
}

export interface TrajectoryBody {
  name: string;
  /** Welded to the world, so its pose never changes. */
  fixed: boolean;
  meshes: TrajectoryMesh[];
}

/** A scenario phase span in sim seconds. */
export interface Phase {
  name: string;
  t0: number;
  t1: number;
}

export interface PosesInfo {
  path: string;
  dtype: "float32";
  byteOrder: "little";
  /** `[frameCount, bodyCount, 7]`. */
  shape: [number, number, number];
  layout: string;
  positionUnits: string;
}

export interface ContactsInfo {
  path: string;
  dtype: "float32";
  byteOrder: "little";
  count: number;
  layout: string;
  forceUnits: string;
}

/** `trajectory.json` as written by `cadkit/gui/trajectory.py`. */
export interface TrajectoryDoc {
  schemaVersion: number;
  units: string;
  runId: string;
  manifestSha256: string;
  fps: number;
  frameCount: number;
  /** Sim seconds per frame, non-decreasing. */
  times: number[];
  bodies: TrajectoryBody[];
  phases: Phase[];
  poses: PosesInfo;
  /** Present only when the export ran with `--contacts`. */
  contacts: ContactsInfo | null;
}

/** A file a run may use; `path` is repo-relative and is what `startRun` sends back. */
export interface PhysicsInputFile {
  name: string;
  path: string;
}

export interface PhysicsInputs {
  schemaVersion: number;
  project: string;
  model: string;
  scenarios: PhysicsInputFile[];
  acceptance: PhysicsInputFile[];
  options: PhysicsInputFile[];
}

export interface Job {
  id: string;
  kind: string;
  key: string;
  model: string;
  status: string;
  createdAt: number;
  startedAt: number | null;
  finishedAt: number | null;
  error: string | null;
  exitCode: number | null;
  log: string[];
  artifacts: Record<string, string>;
}

export interface StartRunRequest {
  model: string;
  scenario: string;
  acceptance: string;
  options?: string;
}

export type ServiceEvent =
  | { type: "job"; job: Job }
  | { type: "artifact"; kind: "scene"; model: string }
  | { type: "artifact"; kind: "run"; runId: string }
  | { type: "connection"; state: "open" | "error" };

/** A failed request; `status` is 0 for a network/transport failure. */
export class TransportError extends Error {
  readonly status: number;
  readonly body?: Record<string, unknown>;

  constructor(status: number, message: string, body?: Record<string, unknown>) {
    super(message);
    this.name = "TransportError";
    this.status = status;
    this.body = body;
  }
}

/** The GUI service contract. Browser-free so a webview transport can implement it too. */
export interface CadStudioTransport {
  health(): Promise<HealthInfo>;
  listModels(): Promise<ModelList>;
  /** `model` is `<project>/<model>`. */
  getScene(model: string): Promise<SceneResponse>;
  startBuild(model: string, sets?: Record<string, number | string>): Promise<Job>;
  /** Scenario, acceptance and options files `startRun` accepts for `<project>/<model>`. */
  listPhysicsInputs(model: string): Promise<PhysicsInputs>;
  listRuns(): Promise<RunList>;
  getTrajectory(runId: string): Promise<TrajectoryResponse>;
  startRun(req: StartRunRequest): Promise<Job>;
  getJob(id: string): Promise<Job>;
  cancelJob(id: string): Promise<Job>;
  subscribe(listener: (event: ServiceEvent) => void): () => void;
  /** URL for an `out/`-relative artifact path. */
  artifactUrl(path: string): string;
}

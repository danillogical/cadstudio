# plan-gui.md: cadstudio GUI (browser + VS Code webview)

**Status:** H0 browser-first fallback selected. G0–G5 merged and verified; H3 and H4 PASS (user, 2026-10-26). H5 pending (user, laptop). G3c onward runs on the laptop with local workers instead of packetd; pushes still go through webstudio.
**Date:** 2026-10-25.
**Started from:** `~/Downloads/plan-draft-gui.md`, adapted to the repo as it stands at `81649e6`.
**Runs on:** webstudio.local, through packetd (Codex skill `packetd`, MCP server `http://127.0.0.1:7766/mcp`).
**Used on:** the laptop (VS Code, Claude Code and Codex in its terminal).

**G0 execution (2026-10-25):** packet `pk-czcd072f` and dependency repair `pk-x4hh8jyw` both ACCEPTED in round 1, squash-merged as `45be859` and `d66aef0`. The final merge gate passed: 1,474 Python/physics tests passed (12 skipped), 25 extension tests passed, the committed build stayed byte-identical, `uv.lock` stayed unchanged, the private-mirror scan passed, and npm audit reported zero vulnerabilities. H0's browser-first fallback is selected; live VS Code checks remain pending in `editor/vscode/README.md`.

## 0. Decision summary

- **One app with several adapters.**
  - **Python engine (`cadkit/`).** It stays the source of truth for geometry, physics, exports and checks, and every operation keeps working headless.
  - **Local service (`cadkit/gui/`).** A loopback HTTP service exposes those operations and their artifacts.
  - **One GUI (`ui/`).** TypeScript and Three.js, the same bundle in a browser and in VS Code.
  - **VS Code extension.** A thin, repo-local workspace extension hosts that bundle in a webview.
  - **Agent skills.** Claude and Codex skills drive the GUI only through the `cad` CLI.
- **No desktop shell, embedded terminal or MCP server** in this plan. Claude and Codex keep running in VS Code's own terminal.
- **Rule:** no build or simulation may depend on the service, the GUI, VS Code or an agent being present.

What changed from the draft, after reading the repo:

| Draft | This plan | Why |
|---|---|---|
| `cadstudio` CLI and package | Extend the existing `cad` CLI (`cadkit/cli.py:582`) and the `cadkit` package | `CLAUDE.md` forbids a second competing CLI; the package is `cadkit`, and projects live in `projects/<name>/` |
| ASGI server | Python stdlib `http.server` plus Server-Sent Events | No new Python dependency, so `uv.lock` doesn't move (see 2.3) |
| WebSocket events | SSE (`GET /v1/events`) | Works with stdlib and `EventSource`; client-to-server traffic is plain POSTs |
| Generic mesh export | Per-part `.glb` in assembly coordinates, from the `ModelPart` shapes | `cad build` STL/3MF files are in **print pose**, so they are wrong for an assembled view |
| Trajectory from MuJoCo directly | Re-play an existing run dir (`scene.xml`, `states.npz`, `assets/*.stl`) | `cad physics run` already writes these, and `projects/pocky/preview.py` already re-plays them |
| `.claude/` and `.agents/` skill copies of a canonical skill | `.claude/skills/cadstudio/` and `.agents/skills/cadstudio/`, each a short file pointing at the same `cad gui` commands | `.claude/skills/connect-ide/` already exists and is the pattern |

**G1 execution (2026-10-26):** packet `pk-sr2fm104` ACCEPTED in round 1 with no findings, squash-merged as `d98d66b`. The merge gate passed: 1,484 Python/physics tests passed (12 skipped), 25 extension tests passed, the committed build stayed byte-identical, `uv.lock` stayed unchanged, and the private-mirror scan passed.

**G2a execution (2026-10-26):** packet `pk-dgaq1x7w` ACCEPTED in round 1 with no findings. Scene acceptance: 11 tests passed; the syringe command exported all eight parts as valid JSON, and 10 CLI/import-boundary tests passed. Squash-merged as `cd260bb` after G1's gate. The full merge gate passed: 1,497 Python/physics tests passed (10 skipped), 25 extension tests passed, the committed build stayed byte-identical, `uv.lock` stayed unchanged, and the private-mirror scan passed.

**G2b execution (2026-10-26):** packet `pk-1np4tv0g` ACCEPTED in round 1 with no findings, squash-merged as `e2324e0`. Acceptance: 27 trajectory/replay tests and four preview tests passed; an additional Pocky/replay regression passed (453 passed, 121 skipped). The full merge gate passed: 1,511 Python/physics tests passed (10 skipped), 25 extension tests passed, the committed build stayed byte-identical, `uv.lock` stayed unchanged, and the private-mirror scan passed.

**G3a execution (2026-10-26):** packet `pk-5qvayr8b` ACCEPTED in round 2 with no remaining findings, squash-merged as `ce21c5c`. The round-1 cancellation race and checkout-dependent fallback-page test were fixed and covered by regressions. Acceptance: 20 service tests and 10 CLI/import-boundary tests passed. The full merge gate passed: 1,531 Python/physics tests passed (10 skipped), 25 extension tests passed, the committed build stayed byte-identical, `uv.lock` stayed unchanged, and the private-mirror scan passed. A real-data service probe served all syringe and two-cycle meshes and poses, rejected unauthenticated API requests, and preserved the old scene as stale after an invalid build.

**G3b execution (2026-10-26):** packet `pk-mvxte15t` ACCEPTED in round 2 with no remaining findings, squash-merged as `091531e`. A failed switch to another model clears the old scene and panels; a failed same-model reload preserves the last good scene. The automated merge gate passed: 1,531 Python/physics tests passed (10 skipped), 65 UI tests passed, TypeScript and the UI production build passed, 25 extension tests/build passed, the committed extension build stayed byte-identical, `uv.lock` stayed unchanged, and the private-mirror scan passed. npm reported zero vulnerabilities. Real-browser desktop verification passed: the eight-part syringe renders, tree/viewport selection updates properties, the token leaves the address bar, and reload works using the stored session token; no browser console errors were reported. The 400 px visual check found the unresolved overlap below; this does not record H3 as PASS.

**G3c continuation (2026-10-26):** prepared packet `pk-6r910v3a` includes the original G3c task and constraints plus the responsive-layout finding. Its planner is suspended in ERROR by the Claude Opus session limit (reported reset: 16:10 America/Los_Angeles); no implementation or review ran. One supported resume attempt hit the same limit. Resume this packet once Opus is available. Initial packet `pk-mtkkd15z` hit the same limit and was cancelled when replacing its brief; its worktree and evidence are preserved.

**Responsive finding for G3c:** at 400 × 800, select `pocky/syringe`, then `housing`. The narrow grid's first track shrinks below the viewport's 50vh minimum: the viewport occupies y=8..408 while the sidebar starts at y=163.29, covering the model picker and upper parts. Use sizing that keeps the viewport and controls separate and makes all playback/job controls reachable by scrolling. Recheck in a real 400 px browser before H3; this remains unresolved.

**H3 preparation (2026-10-26):** the referenced two-cycle run was absent locally. Generated `out/mujoco-two-cycle/wedge_clamped` with the existing documented scenario, acceptance and wedge-clamped options: PASS, all 22 checks. The existing preview loads its 236,001 states over 14.75 s; its dry-run summary is saved under `out/.gui-verification/` and is byte-identical after G2b. Real-run trajectory export passed: 886 frames, six bodies (including all three packets), 13 phases, and 45,583 contact samples; the source run listing, sizes and mtimes stayed unchanged. H3 itself remains pending.

**G3c execution (2026-10-26):** done on the laptop by local workers, not packetd, so packet `pk-6r910v3a` is superseded. One worker implemented it and a different worker wrote the gating unit tests. Those tests found two implementation bugs, both fixed: the clock could rewind on an earlier `now`, and a failed reload of the same run wasn't marked stale. G3c added `GET /v1/models/{project}/{model}/physics-inputs`, and `POST /v1/runs` now accepts only listed files. Merged as `ad33ec2`. Merge gate: 1,549 Python/physics tests, 172 UI tests, 25 extension tests and all builds passed. The committed extension build stayed byte-identical, and the private-mirror scan passed. The full suite rewrote `uv.lock` against the laptop's private mirror; it was restored, and nothing from it was committed. A headless browser at 1400×900 and 400×800 played `mujoco-two-cycle/wedge_clamped` at 10.2 s with contacts, without overlap or console errors. Follow-up `02dc48b` lists runs newest first and sizes playback's `states.npz` cap from the run's scenario budget, as replay does, so the 636 MB free-housing runs load.

**H3 (2026-10-26): PASS**, reported by the user.

**G4 execution (2026-10-26):** done on the laptop by local workers; one implemented it and another wrote the gating tests. The webview loads the committed `media/` copy of `ui/dist` under the CSP `default-src 'none'; script-src 'nonce-N'; style-src 'nonce-N'; connect-src 'none'; base-uri 'none'; form-action 'none'`. `VsCodeTransport` posts every call to the extension host, which validates it against an allowlist and forwards it to the health-checked service. Answers, artifact bytes and SSE events return as messages, and the token stays in the host. Artifacts now load from bytes (`getArtifact`), so the webview never fetches a URL. The shared transport contract suite exposed one mismatch, now fixed: a job reply without `job` is rejected by both transports. Merge gate: 1,551 Python/physics tests, 216 UI tests, 471 extension tests, builds, a deterministic committed extension build, `uv.lock` unchanged, mirror scan clean. The smoke test passes when run with `node` outside the sandbox; under `npm` the sandbox blocks binding the port. Not verified, left for H4: the live install, the panel loading its script and stylesheet in a real webview, panel restore after a reload, and the service pid staying the same.

**H4 (2026-10-26): PASS**, reported by the user. This also confirms the H0 workspace install that was deferred: the extension installed from Workspace Recommendations and opened in the same window.

**G5 execution (2026-10-26):** done on the laptop by local workers; one implemented it and another wrote the gating tests (119 Python, plus extension and UI tests). Open requests are in-memory, single use and expire after 60 s. The CLI waits up to 10 s for an ack and reports a nack's reason at once. When it stops waiting, it nacks its own request so a late claim can't open a second view. Ack only follows the navigate message being posted to the panel. A window whose folder or service differs can't see the request, so that case ends in the timeout. Merge gate: 1,670 Python/physics tests, 233 UI tests, 528 extension tests, builds, deterministic committed extension output, `uv.lock` unchanged, mirror scan clean. The first two full runs each failed one end-to-end test. The CLI redacted tokens to `…`, and by that point in the suite the test process decoded the CLI's stderr as US-ASCII, so it crashed. Redaction now writes `REDACTED`. What switches the process encoding wasn't identified. Not verified, left for H5: a real `code --open-url`, the extension acking, panel navigation, and the wrong-window and uninstalled-extension fallbacks.

## 1. Goals and boundaries

**Goals:**
- Everything lives in this repo: no Marketplace extension, no global install.
- "Use the cadstudio skill and open the GUI for pocky/syringe" works from Claude Code or Codex in VS Code's terminal.
- The same GUI opens in a plain browser when the extension is missing or VS Code can't be reached.
- It shows a model's assembly (parts, tree, properties, mm units) and plays back a real `cad physics run` (body poses from the saved states, plus optional contacts).
- Every GUI action maps to a `cad` command with `--json` output, so agents and tests can do the same thing headless.
- Projects stay isolated (`armor`, `pocky`, future ones).

**Not in this plan:**
- Geometry editing, parametric editing in the GUI, embedded terminals, remote VS Code, a desktop shell, an MCP adapter.
- Running arbitrary code from GUI requests.
- Any change to the Pocky geometry, physics parameters, frozen acceptance files or thresholds. The GUI only displays them.
- Reference meshes, videos or frames of the purchased Pocky reference (see `projects/pocky/README.md`, "Licence").

## 2. How this plan is executed

### 2.1 Roles

- **Orchestrator.** Codex (or Claude) on webstudio, using the `packetd` skill. It:
  - creates and starts packets, in the order given in section 4;
  - reads the ACCEPTED diff;
  - runs the merge gate (2.4) on webstudio's `main`;
  - squash-merges `packetd/<id>` into `main`.

  It never pushes to GitHub without the user's go-ahead, and never edits code itself, except for trivial merge fixes noted in the commit message.
- **packetd.** Claude plans, DeepSeek implements in `<repo-parent>/.packetd-worktrees/<id>`, and Claude reviews. The implementer sees **only the packet's task text**. The reviewer can't run commands, so every acceptance criterion has to be either a command whose output the implementer reports or something visible in the diff.
- **User, on the laptop.** Runs the human gates (marked **H**) that need VS Code, a screen, or Claude/Codex sessions. Gets the code with `git pull webstudio.local:src/cadstudio main`, or from GitHub after a push.

### 2.2 Packet rules

- One packet per row of section 4, created in order. A packet starts only after the previous one is merged into `main`, because packets branch from `main`.
- Use the task text in section 4 **verbatim**. Then append the common constraints (2.3), also verbatim.
- On **FAILED**, split or clarify the packet; don't retry the same text unchanged. On **BLOCKED**, switch route (`workbuddy` → `workbuddy-sg`) and resume. Never set or paraphrase a verdict.
- At an **H** gate, the orchestrator stops and reports to the user. It doesn't start the next packet until the user reports PASS, or chooses the stated fallback.

### 2.3 Common constraints (append to every packet task)

```
Repository: cadstudio (Python >=3.11 via uv, build123d, optional MuJoCo). Read CLAUDE.md first.
- The CLI is `cad` (cadkit/cli.py). Do not add a second CLI. Engine code is in cadkit/, projects in projects/<name>/.
- Always run Python with `uv run --frozen ...` (add `--extra physics` for anything that imports mujoco).
  Do not change pyproject.toml dependencies or uv.lock. `git diff --exit-code uv.lock` must pass.
  No new Python runtime dependencies; use the standard library, numpy, trimesh, build123d, mujoco (physics extra).
- Node work (ui/, editor/vscode/) uses npm with a committed package-lock.json. Node >= 22.
- cadkit core modules (everything outside cadkit/gui/) must not import cadkit.gui, http.server, or any UI code.
- Do not modify projects/pocky geometry, physics parameters, scenarios, acceptance files, or tests that pin them.
- Never add internal or company hostnames (any package index other than pypi.org), tokens, or absolute /Users/ paths.
- Generated output goes under out/ (gitignored). Never commit generated meshes, runs, videos or node_modules.
- New tests go in tests/test_cadkit_gui_*.py (Python) or next to the TypeScript source (vitest).
- Comments: one line where possible; explain what and why, no history.
- Finish by running the packet's acceptance commands and report each exit code in the evidence report.
```

### 2.4 Merge gate (orchestrator, on webstudio `main` after squash-merge)

```
uv run --frozen --extra physics pytest tests -q          # full suite, about 15 min; must pass
git diff --exit-code uv.lock
! git grep -nE 'pypi\.[a-z]+\.com' -- ':!docs' ':!report-current-progress.md' ':!pyproject.toml'   # private package mirrors
(cd ui && npm ci && npm test && npm run build)            # once ui/ exists
(cd editor/vscode && npm ci && npm test && npm run build) # once editor/vscode/ exists
```

If the gate fails after the merge, revert the merge commit, then open a repair packet that quotes the failure.

## 3. Architecture

```
 laptop: VS Code window                         any browser
 ┌──────────────────────────────┐              ┌──────────────┐
 │ terminal: claude / codex     │              │ ui/ bundle   │
 │   └─ skill → cad gui open    │              │ (browser     │
 │ workspace extension          │              │  transport)  │
 │   └─ webview: ui/ bundle     │              └──────┬───────┘
 │      (postMessage transport) │                     │ HTTP + SSE, token
 │   └─ extension host bridge ──┼─────────────────────┤
 └──────────────────────────────┘                     │
                                   cadkit/gui/server.py (127.0.0.1, random port)
                                                      │
                     cadkit: build/export (build123d) · physics run/replay (MuJoCo)
                                                      │
                                       out/<project>/<model>/…, run dirs
```

Dependency direction (enforced by a test in G1):
- `cadkit/*` (core) imports nothing from `cadkit/gui`.
- `cadkit/gui` calls core functions directly, never through the CLI or HTTP.
- `ui/` talks only through a `CadStudioTransport` interface.
- `editor/vscode/` contains no CAD or physics logic.

### 3.1 Artifact contracts

**Scene** (`out/<project>/<model>/scene/`, written by `cad gui scene <model>`):
- `scene.json` contains:
  - `schemaVersion: 1`, `project`, `model`, `units: "mm"`;
  - provenance: git commit, a dirty flag, a params-file sha256, `--set` overrides, and the build time;
  - `parts[]`, each with `id` (the `ModelPart` key), `name`, `mesh` (relative `.glb` path), bbox (min/max mm), volume in mm³, and a colour;
  - an optional `printPose` 4×4 per part.
- `parts/<id>.glb` holds the part in **assembly coordinates**, tessellated once.

**Trajectory** (`<run>/../<run-name>.gui/`, written by `cad gui trajectory RUN_DIR`; the run dir itself is never written to):
- `trajectory.json` contains:
  - `schemaVersion: 1`, `units: "mm"`, the run id, and the source `manifest.json` sha256;
  - `bodies[]`, each with `name`, a list of meshes (geom name, `.glb` path, local pose) and `fixed` (welded to the world);
  - `phases[]` (name, t0, t1);
  - `frameCount`, `times`, and a pointer to the poses.
- `poses.bin` is little-endian float32, `[frame][body][x,y,z,qw,qx,qy,qz]`, positions in mm. It is sampled at a fixed fps (default 60 sim-fps) from `states.npz`.
- `contacts.bin` (optional) holds per-frame contact points and normal forces.
- Body meshes come from the run's `assets/*.stl`. The geom-to-body mapping comes from compiling the run's `scene.xml`.

**Service discovery:** `out/.gui/service.json` with pid, port, token, protocol version, repo root, start time and mode `0600`.

### 3.2 Service surface (`schemaVersion` on every response)

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | identity, protocol version, repo root (no token needed; no secrets) |
| `GET /v1/models` | `cad list` as JSON |
| `GET /v1/models/{project}/{model}/scene` | latest scene manifest, or 404 with the command that would build it |
| `POST /v1/models/{project}/{model}/build` | job: build, check, then scene export |
| `GET /v1/runs` | physics run dirs found under `out/` (has `summary.json` and `states.npz`) |
| `GET /v1/runs/{runId}/trajectory` | trajectory manifest (exports on first request) |
| `POST /v1/runs` | job: `cad physics run` with a scenario, acceptance and options chosen from files already in the project |
| `GET /v1/jobs/{id}`, `POST /v1/jobs/{id}/cancel` | job state, log tail, artifacts |
| `GET /v1/artifacts/{path}` | stream a file **only** from `out/<project>/…/scene/` or a `.gui/` trajectory dir, after canonicalising the path |
| `GET /v1/events` | SSE stream of job and artifact changes |
| `POST /v1/open` | `cad gui open`: create a one-time open request for `{model}`, `{run}` or `{}` (validated like the scene and trajectory routes); `{id, expiresAt, target}`, single use, expires after 60 s, held in memory |
| `GET /v1/open/{id}` | the extension claims the request: `{id, target, repoRoot}`; a second claim is 404, an expired one 410 |
| `POST /v1/open/{id}/ack`, `POST /v1/open/{id}/nack` | the extension opened the target, or refused with `{reason}` (wrong repo, untrusted, panel not ready); the CLI also nacks its own request when it stops waiting |
| `GET /v1/open/{id}/status` | what `cad gui open` polls: `pending`, `claimed`, `acked`, `nacked` (with `reason`) or `expired` |
| `GET /` | the built `ui/dist` |

Rules:
- Every `/v1/*` route except health requires `Authorization: Bearer <token>`, or the `?token=` query the server gives the browser on open. The compiled `ui/dist` files and fallback page are public build output and do not require a token; Host/Origin checks still apply. This G3a planner recommendation keeps browser reloads working after G3b removes the token from the address bar.
- Requests whose `Host` isn't `127.0.0.1:<port>` or `localhost:<port>` are rejected.
- Requests with an `Origin` other than the server's own are rejected.
- Jobs on the same model or run queue one at a time, and read-only viewers are unlimited.
- A failed job never replaces the last good scene or trajectory; the old one is returned marked `stale: true`.

## 4. Packets and gates

Each packet below gives its **title** and its **task** text. Section 2.3 is appended to every task.

### Milestone 0: the workspace extension works at all

**Packet G0: Minimal repo-local VS Code workspace extension**

> Create a minimal VS Code extension that VS Code can install as a *workspace extension* (VS Code 1.89+ local workspace extensions: a folder under `<workspace>/.vscode/extensions/<name>/` with a `package.json` and compiled JS).
> - Source in `editor/vscode/` (TypeScript, esbuild, vitest). `npm run build` compiles into `.vscode/extensions/cadstudio/` (`package.json`, `dist/extension.js`, `README.md`). Keep that built folder **committed** (it is small) so a clean clone shows it in Workspace Recommendations; add a test that fails if the committed build is out of date with the source (rebuild into a temp dir and compare).
> - Manifest:
>   - `name: "cadstudio"`, `publisher: "danillogical"`, `engines.vscode: "^1.89.0"`;
>   - `contributes.commands` with `cadstudio.openGui` titled "CADStudio: Open GUI";
>   - `activationEvents` `onCommand:cadstudio.openGui` and `onUri`;
>   - `capabilities.untrustedWorkspaces.supported: false`.
> - The command opens a webview panel titled "CADStudio" with static HTML: a heading, the workspace folder name, the extension version. It also has a strict CSP (`default-src 'none'`, scripts only from the extension via `asWebviewUri` with a nonce).
> - Register a URI handler for `vscode://danillogical.cadstudio/open`. It calls the same command and shows the query string in the panel.
> - Add `.vscode/extensions.json` recommending `danillogical.cadstudio`.
> - Add `editor/vscode/README.md` describing the manual install steps (to be confirmed at gate H0).
> - Unit-test the activation, command registration, HTML/CSP generation and URI parsing with a mocked `vscode` module.
>
> Acceptance:
> - `cd editor/vscode && npm ci && npm test && npm run build`
> - `git diff --exit-code .vscode/extensions/cadstudio` after the build
> - `uv run --frozen pytest tests -q -k "not physics"`

**Gate H0 (user, laptop):**
1. Pull and open the repo in VS Code. Trust the workspace, then install "cadstudio" from Workspace Recommendations ("Install Workspace Extension").
2. Run "CADStudio: Open GUI" and confirm the panel opens **in this window**.
3. From the integrated terminal, run `code --open-url "vscode://danillogical.cadstudio/open?x=1"` with two VS Code windows open, and note which window gets it.
4. Edit the source, rebuild, and note what VS Code needs to pick up the change (reload, or reinstall).

The orchestrator records the answers in `editor/vscode/README.md` (trivial doc commit).

- **PASS:** the panel opens in the same window with no global install.
- **Fallback:** if workspace install is unreliable, keep going browser-first. VS Code then gets a private VSIX (`code --install-extension`) as an explicit opt-in, documented as such.

**Disposition (2026-10-26):** the user accepted the recommendation to take the browser-first fallback and continue to G1. The live workspace-install, webview and rebuild checks remain unverified and are deferred to the editor work in G4/G5. Keep the G0 extension; private VSIX installation remains an explicit opt-in. VS Code documents URI dispatch to the topmost window, so retain G5's repo-root check, acknowledgment and browser fallback. This selects the fallback without recording H0 as PASS.

### Milestone 1: CLI boundary

**Packet G1: Machine-readable `cad` output and a core/GUI import boundary**

> Add JSON output to the existing CLI without changing its human output:
> - `cad list --json`: projects, models, default params path.
> - `cad build ... --json`: written paths, check results (name, status, detail per part), exit code unchanged.
> - `cad doctor --json` (new): Python, uv, build123d, mujoco availability and version, node and npm availability, output dir writable, ui/dist present, extension build present.
>
> In JSON mode stdout carries **only** the JSON document; progress goes to stderr. Add a test that imports every `cadkit` module outside `cadkit/gui/` and asserts none of them imports `cadkit.gui` or `http.server` (create an empty `cadkit/gui/__init__.py`).
>
> Acceptance:
> - `uv run --frozen pytest tests/test_cadkit_gui_cli.py -q`
> - `uv run --frozen cad list --json | python3 -m json.tool`
> - `uv run --frozen cad build pocky/packet_dummy --check --views standard --json --out /tmp/g1 | python3 -m json.tool`

### Milestone 2: artifact contracts

**Packet G2a: Scene export (`cad gui scene`)**

> Implement `cadkit/gui/scene.py` and the `cad gui scene <model> [--set K=V] [--params P] [--out DIR] [--json]` command, writing the scene contract in plan-gui.md section 3.1 (copy the contract into a module docstring).
> - Tessellate each `ModelPart.shape` in **assembly coordinates**, not print pose, to binary glTF (`trimesh` can export `.glb`), with tolerances matching `cadkit/export.py`.
> - Record `printPose` from `print_location`.
> - Provenance: `git rev-parse HEAD`, a dirty flag from `git status --porcelain`, a params file sha256, overrides.
> - Re-running with unchanged inputs must produce byte-identical `scene.json`, excluding the time field.
>
> Tests use `pocky/packet_dummy` and a multi-part model (`pocky/syringe`). They check:
> - every part has a glb;
> - the glb vertex bounds match the part bbox within 0.05 mm;
> - units are mm;
> - an unknown model exits non-zero with a JSON error.
>
> Acceptance:
> - `uv run --frozen pytest tests/test_cadkit_gui_scene.py -q`
> - `uv run --frozen cad gui scene pocky/syringe --json`

**Packet G2b: Trajectory export from a physics run**

> Move the run-loading and state-restoring logic of `projects/pocky/preview.py` (class `Run`: loading `scene.xml` and `states.npz`, `restore(row)`, `row_at(t)`, phase list, and the framing that ignores bodies that leave the assembly) into a generic `cadkit/physics/playback.py`. `projects/pocky/preview.py` must import it, and its behaviour must stay the same: its `--dry-run` output for a given run must be identical before and after (add a test that compares them on a generated run).
>
> Then implement `cadkit/gui/trajectory.py` and `cad gui trajectory RUN_DIR [--fps N] [--contacts] [--json]`, writing the trajectory contract in plan-gui.md section 3.1:
> - Write into a sibling `<run-name>.gui/` directory. Never write into the run dir (assert that its file listing and mtimes are unchanged).
> - Convert positions from metres to millimetres.
> - Convert each body's mesh assets to `.glb` in the body frame.
> - Tests generate a small run in a temp dir with the existing headless smoke/gravity-drop path (`cad physics smoke`, or the function it calls). They assert:
>   - the frame count matches the duration × fps;
>   - a falling body's z decreases under gravity;
>   - re-running is byte-identical;
>   - a tampered `states.npz` is reported as an error, not exported.
>
> Acceptance:
> - `uv run --frozen --extra physics pytest tests/test_cadkit_gui_trajectory.py tests/test_cadkit_physics_replay_caps.py -q`
> - `uv run --frozen --extra physics pytest tests -q -k preview`

### Milestone 3: service and browser GUI

**Packet G3a: Local service (`cad gui serve`)**

> Implement `cadkit/gui/server.py` on `http.server.ThreadingHTTPServer` with the endpoints, auth, Host/Origin checks, path rules, job queueing, SSE and discovery file in plan-gui.md sections 3.1–3.2 (copy them into the module docstring).
> - `cad gui serve [--port 0] [--no-browser] [--json]`:
>   - binds 127.0.0.1;
>   - writes `out/.gui/service.json` (mode 0600) and prints the URL with the token;
>   - removes the file on SIGINT/SIGTERM;
>   - refuses to start if a healthy service for the same repo root is already registered (prints its URL instead);
>   - replaces a stale file whose pid is dead.
> - Jobs run the existing core functions in a worker thread. Physics jobs run `cad physics run` as a subprocess so they can be cancelled; the scenario, acceptance and options files must already exist inside the project.
> - Serve `ui/dist` at `/` if present, otherwise a plain page saying how to build it.
>
> Tests start the server on port 0 in a thread and check:
> - health;
> - 401 without a token;
> - 403 for a bad Host or Origin;
> - 404 for an unknown model;
> - path traversal (`..`, absolute, symlink out of `out/`) is refused;
> - a build job of `pocky/packet_dummy` finishes and its scene is served;
> - two concurrent build requests for the same model run once each in order;
> - a failing build leaves the previous scene served with `stale: true`;
> - SSE delivers job events;
> - a stale discovery file is replaced.
>
> Acceptance: `uv run --frozen --extra physics pytest tests/test_cadkit_gui_server.py -q`

**Packet G3b: GUI scaffold, transport, viewport, part tree, properties**

> Create `ui/`: TypeScript, Vite, Three.js, vitest, no UI framework unless a tiny one is clearly needed; a committed package-lock.
> - Define `CadStudioTransport` (`health`, `listModels`, `getScene`, `startBuild`, `listRuns`, `getTrajectory`, `startRun`, `getJob`, `cancelJob`, `subscribe`, `artifactUrl`).
> - Implement `BrowserTransport` (fetch and EventSource, token from the page URL, then kept in sessionStorage and removed from the address bar).
> - Build the viewport:
>   - orbit, pan and zoom, plus fit-to-model;
>   - grid and axes with a mm scale;
>   - Z up, matching cadkit.
> - Add a model picker, a part tree with selection synced to the viewport (click either one), and a read-only properties panel (id, bbox, volume, provenance).
> - Show a stale or error banner. Resize well down to a 400 px wide VS Code panel.
>
> Unit-test the transport against a fake fetch, the scene-to-Three mapping (part ids, mm units, transforms) with a fixture `scene.json` checked into `ui/test/fixtures` (tiny generated glb, no project geometry), selection sync, and stale handling. `npm run build` outputs `ui/dist` (gitignored).
>
> Acceptance: `cd ui && npm ci && npm test && npm run build && npx tsc --noEmit`

**Packet G3c: Playback and job controls**

> In `ui/`:
> - Add a runs list.
> - Add trajectory playback driven by `poses.bin`:
>   - play/pause, seek slider, speed 0.1x–4x, restart;
>   - time and phase display;
>   - per-body transparency;
>   - an optional contact overlay.
> - Add Build and Run buttons that start jobs. Runs pick from the scenario, acceptance and options files the server lists. Show job progress and the log tail, with cancel.
> - Interpolate poses between frames (slerp) and show the frame index.
> - A failed job shows an error and keeps the previous scene or trajectory, marked stale.
>
> Unit-test frame lookup and interpolation, phase lookup, job state handling, and that a failed job doesn't replace the displayed artifact. Add one end-to-end smoke script, `ui/scripts/smoke.mjs`. It starts `uv run --frozen --extra physics cad gui serve --port 0 --no-browser`, fetches health, scene and trajectory through `BrowserTransport` in Node, and exits 0.
>
> Acceptance:
> - `cd ui && npm ci && npm test && npm run build`
> - `node ui/scripts/smoke.mjs`

**Gate H3 (user, laptop):**
1. Run `uv run --frozen --extra physics cad gui serve` and open the printed URL.
2. Pick `pocky/syringe` and click a part in the tree and in the viewport.
3. Open the run `out/mujoco-two-cycle/wedge_clamped` and play, seek, change speed, and watch packet 2 drop and dispense.
4. Start a build with a bad `--set` and confirm the old scene stays, marked stale.

- **PASS:** all four work.

### Milestone 4: GUI inside VS Code

**Packet G4: Host the GUI in the workspace extension**

> Extend `editor/vscode/`:
> - "CADStudio: Open GUI" opens (or reveals, never duplicates) a webview that loads the built `ui/dist` assets via `asWebviewUri` with a strict CSP (no remote scripts, no inline scripts without a nonce, `connect-src` none).
> - Implement `VsCodeTransport` in `ui/src/transport/` using `acquireVsCodeApi().postMessage`. The extension host validates each message against the transport method list and forwards it to the service found in `<workspace>/out/.gui/service.json` (health-checked; starts `uv run --frozen --extra physics cad gui serve --no-browser` in a VS Code task if absent).
> - Stream SSE events back to the webview as messages, and keep artifact bytes on the same message path, so the webview never connects to localhost itself.
> - Restore the panel on reload (`registerWebviewPanelSerializer`). Dispose its listeners.
> - Refuse to run in an untrusted workspace.
> - The build step copies `ui/dist` into `.vscode/extensions/cadstudio/media/`. Keep the committed build current: update the out-of-date test from G0 to cover `media/`.
>
> Unit-test message validation (unknown methods and bad args rejected), forwarding with a fake service, reveal-not-duplicate, and serializer restore, with the mocked `vscode` module. Add a transport contract test in `ui/` run against both `BrowserTransport` and `VsCodeTransport` with fakes.
>
> Acceptance:
> - `cd ui && npm ci && npm test && npm run build`
> - `cd editor/vscode && npm ci && npm test && npm run build && git diff --exit-code ../../.vscode/extensions/cadstudio`

**Gate H4 (user, laptop):**
1. Reload VS Code (or reinstall the workspace extension, as H0 found) and run "CADStudio: Open GUI".
2. Repeat the H3 checks inside the panel.
3. Reload the window and confirm the panel comes back without starting a second service (`out/.gui/service.json` pid unchanged).

- **PASS:** all three work.

### Milestone 5: agents open the GUI

**Packet G5: `cad gui open` and the cadstudio skills**

> Implement `cad gui open [<model> | --run RUN_DIR] [--editor auto|vscode|browser] [--no-open] [--json]`:
> - Start or reuse the service (same rules as `cad gui serve`), then ask the service to create a one-time open request id.
> - **vscode:** run `code --open-url "vscode://danillogical.cadstudio/open?req=<id>"`. The extension's URI handler fetches the request from the service, checks that its repo root equals this window's workspace folder, opens the panel on that model or run, and acknowledges (`POST /v1/open/<id>/ack`). `cad gui open` waits up to 10 s for the ack.
> - **auto:** try vscode when `code` is on PATH and `TERM_PROGRAM=vscode`, else browser. Fall back to the browser URL if there's no ack, and say so on stderr and in JSON (`"opened": "browser", "reason": ...`).
> - **vscode:** exits 3 with diagnostics when there's no ack (extension missing, untrusted workspace, wrong window).
> - **browser:** `open`/`xdg-open` the tokened URL.
> - Never claim success without an ack or a launched browser.
>
> Add the skills:
> - `.claude/skills/cadstudio/SKILL.md` and `.agents/skills/cadstudio/SKILL.md`. Each is short, and both document the same commands (`cad doctor --json`, `cad list --json`, `cad gui open ...`, `cad gui trajectory`) and the exit codes.
> - Update `.claude/skills/connect-ide/SKILL.md` to prefer `cad gui open` for models and runs.
>
> Test the open-request lifecycle (single use, expiry, repo-root mismatch refused), the ack wait and fallback with a fake `code` executable on PATH, and the JSON output.
>
> Acceptance:
> - `uv run --frozen --extra physics pytest tests/test_cadkit_gui_open.py -q`
> - `cd editor/vscode && npm test && npm run build && git diff --exit-code ../../.vscode/extensions/cadstudio`

**Gate H5 (user, laptop):**
1. In VS Code's terminal, start Claude Code and ask "use the cadstudio skill and open the GUI for pocky/syringe"; then do the same with Codex. The GUI opens in this window.
2. With a second VS Code window in front, repeat; the result is the right window or an explicit browser fallback.
3. Uninstall the extension; `--editor auto` falls back to the browser and says why.

`code` needs the ACC tool allowlist entry (already present).

- **PASS:** all three work.

### Milestone 6: release candidate

**Packet G6: Bootstrap, lifecycle hardening and docs**

> Add:
> - `scripts/bootstrap.sh`: `uv sync --frozen --extra physics`, `npm ci` and builds for ui and the extension, then `cad doctor --json`. It must not modify `uv.lock` or global config.
> - Lifecycle tests:
>   - a port collision;
>   - a killed service (stale pid);
>   - two repo checkouts running services at once, which mustn't see each other;
>   - cancelling a physics job kills its subprocess tree;
>   - repeated `cad gui open` calls leave exactly one service process.
> - A "GUI" section in `README.md` and a pointer in `CLAUDE.md`. The README section covers install, the workspace extension steps from H0, the browser fallback, and an end-to-end Pocky inspection (`cad build pocky/syringe`, `cad gui open pocky/syringe`, open the two-cycle run).
> - A security checklist, `docs/gui-security.md`. It maps each rule in plan-gui.md section 3.2 to the test that enforces it.
>
> Acceptance:
> - `bash scripts/bootstrap.sh`
> - `uv run --frozen --extra physics pytest tests -q`
> - `git diff --exit-code uv.lock`

**Gate H6 (user):**
1. Make a fresh clone on the laptop and run `bash scripts/bootstrap.sh`.
2. Install the workspace extension.
3. Run `cad gui open pocky/syringe`.

- **PASS:** this works without anything installed globally beyond uv, node, VS Code and the agents.

## 5. Final acceptance (all required)

- [ ] A clean checkout installs the extension for this workspace only (H0, H6).
- [ ] Claude Code and Codex each open the GUI from VS Code's terminal with `cad gui open` (H5).
- [ ] The GUI opens in the intended window, or falls back to the browser and says so (H5).
- [ ] The same `ui/` bundle works in a plain browser (H3).
- [ ] Assemblies show every part with stable selection and mm units (G2a tests, H3).
- [ ] Playback follows the saved simulation states, including gravity, not a made-up animation (G2b tests, H3).
- [ ] `cad build`, `cad physics run` and the exports work with no service, GUI, VS Code or agent running (G1, G2 tests).
- [ ] Failed builds and runs show in GUI and CLI and keep the last good result (G3a, G3c tests, H3).
- [ ] Projects stay isolated, and the GUI picks models by `<project>/<model>` (G3a tests).
- [ ] Repeated opens don't leak services or duplicate jobs (G6 tests).
- [ ] A missing or untrusted extension never blocks the browser path (H5).
- [ ] The README walks through a Pocky inspection end to end (G6).

## 6. Risks

| Risk | Where it shows | Response |
|---|---|---|
| Workspace extensions don't install or update cleanly on the user's VS Code | H0 | Browser-first; opt-in private VSIX |
| `code --open-url` goes to the frontmost window, not this one | H0, H5 | Repo-root check plus ack; browser fallback |
| The committed extension build drifts from its source | every merge | Out-of-date test in G0/G4 |
| npm installs touch the network from webstudio | G0, G3b | Lockfiles committed; `npm ci` only |
| DeepSeek implementer edits Pocky physics or `uv.lock` to make tests pass | any packet | Common constraints; merge gate checks `uv.lock` and the full suite |
| Large runs make `poses.bin` heavy (14.75 s × 60 fps × 13 bodies is small, but contacts aren't) | G2b | Contacts opt-in, fps flag |
| ACC sandbox on the laptop blocks `code` or loopback | H gates | `code` is allowlisted; per `~/.claude/CLAUDE.md`, try twice, then the user intervenes |

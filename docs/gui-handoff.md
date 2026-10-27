# GUI continuation prompt

Continue the cadstudio GUI plan using the `packetd` skill. Read `CLAUDE.md`,
`plan-gui.md`, this file, and `~/.codex/skills/packetd/SKILL.md` first.
The repository is `~/src/cadstudio`; `webstudio.local` is this Mac, so use the
local packetd service rather than SSH. This handoff records the state on
2026-10-26. Inspect current Git and packet status before taking action.

## Resume point

G0 through G3b have been reviewed, squash-merged into `main`, and verified.
The latest implementation commit is `091531e`; progress records through
`b6f87bb` contain the completed G3b merge gate and the pending continuation.
G3c has not been implemented. H3 has not passed; G4 through G6 remain pending.

Resume the existing packet **`pk-6r910v3a`**, titled
“G3c: Playback, job controls, responsive-layout repair and browser smoke”.
Its route is `workbuddy`, branch is `packetd/pk-6r910v3a`, and worktree is
`../.packetd-worktrees/pk-6r910v3a`. Its base is
`a4a23583979f249cb9a811560c3882a92c2d331d`; subsequent main commits only
record verification and handoff information.

At handoff, `packet_get` reports ERROR, round 0, no review, and no in-flight
attempts. Claude Opus planning failed with:

> You've hit your session limit · resets 4:10pm (America/Los_Angeles)

The reported reset was 2026-10-26 at 16:10 Pacific. One supported resume
attempt already encountered the same limit. Check the current time and
availability; resume when Opus is available, then poll every 30–60 seconds.
Do not assume the quota has reset merely because this handoff exists.
Switching DeepSeek implementation routes does not resolve a Claude planner
quota. Preserve Claude Opus planning and review. No scheduled retry exists.

Use the complete task already stored in this packet. It includes the original
G3c row and common constraints verbatim, plus the concrete responsive defect
below. Do not resume cancelled predecessor `pk-mtkkd15z`; its worktree and
evidence were preserved when its brief was replaced.

## Authorized decisions

- Act on the best-supported recommendation within the authorized task;
  escalate only when no sound recommendation can be made. Keep packetd simple
  and rely on Claude Opus planning and review. Do not mirror OMP's workflow.
- H0's **browser-first fallback** was explicitly accepted. Retain the G0
  extension and defer live VS Code install/webview/rebuild checks to G4/G5.
  Private VSIX installation is opt-in. H0 is fallback selected, not PASS.
- The user authorized committing and pushing the completed work in both
  cadstudio and packetd. This handoff itself does not authorize future pushes.
- At H3, stop and report the human checks. Do not start G4 until the user
  reports PASS or selects a fallback provided by the plan.

## G3c scope and known defect

Implement runs listing, real trajectory playback from `poses.bin`, play/pause,
seek, speed 0.1x–4x, restart, time/phase/frame display, per-body transparency,
optional contacts, and quaternion slerp. Add Build/Run controls using server
scenario/acceptance/options listings, progress/logs/cancel, and preservation of
the last good artifact marked stale on failure. The server's project-file
listing may need a small addition; G3a deliberately deferred it.

Cover interpolation/frame/phase lookup and job/failure state with unit tests.
Add `ui/scripts/smoke.mjs`, which starts a service on an ephemeral port and
fetches health, scene and trajectory through `BrowserTransport` in Node.
Packet acceptance is the UI install/test/build plus this smoke script.
The worker runs targeted acceptance; the orchestrator runs the full merge gate.

Repair the actual browser defect found at **400 × 800**: load `pocky/syringe`
and select `housing`. The narrow layout uses
`grid-template-rows: minmax(0, 1fr) auto`, while `.viewport-panel` has a
`min-height: 50vh`. The viewport occupies y=8..408 but the sidebar starts at
y=163.29, so the canvas covers the picker and upper parts. The layout's height
and scrollHeight are both 800, leaving those controls unreachable by scrolling.
Use simple sizing that keeps viewport and controls separate and allows vertical
scrolling, including the new playback/job controls. Preserve desktop layout.
Recheck in an actual 400 px browser after merge; no new browser-test dependency
is required merely for this CSS fix. This check has not passed yet.

## Verification already completed

G3b packet `pk-mvxte15t` was ACCEPTED in round 2 with no remaining findings,
then squash-merged as `091531e`. The latest full merge gate passed:

- Python/physics: **1,531 passed, 10 skipped**, in about 24 minutes. The single
  known warning comes from an intentional duplicate archive member fixture.
- UI: **65 tests**, TypeScript checking and production build passed; npm
  reported zero vulnerabilities.
- Extension: **25 tests** and build passed; committed output stayed
  byte-identical. `uv.lock` and the private-package-mirror check stayed clean.
- Real desktop browser: eight syringe parts render; tree and viewport
  selection update properties; the token leaves the address bar; reload works
  with the session token; no browser console errors were reported.
- Real service: all scene/trajectory meshes and poses served; unauthenticated
  API requests rejected; an invalid build preserved the old scene as stale.

The G3b review fixed stale panels after a failed switch to a different model.
A failed same-model reload preserves the last good scene. Camera position is
preserved across same-model rebuilds. The 400 px defect remains outstanding.

## Review, merge and gate

Follow the plan's packet ordering and common constraints. The orchestrator
reads the accepted disposition, evidence and diff, then squash-merges the
reviewed result and runs section 2.4 on main. packetd does not merge.
Never invent or set a review verdict. On gate failure, follow the plan's revert
and repair-packet rule. Do not edit implementation directly except trivial
merge fixes documented in the commit.

Accepted packet changes may still be uncommitted in the worktree. Before
committing them, compare the intended files byte-for-byte against the immutable
revision snapshot under
`~/Library/Application Support/packetd/artifacts/revisions/<packet>/<fingerprint>/files`.
Text patches can also be checked with `git apply --reverse --check`; GLB binary
patches may lack full index information, so use direct snapshot comparison for
those. Commit only the reviewed files, then squash-merge. Preserve worktrees
and review evidence.

Run the full gate once after the next implementation merge:

```sh
uv run --frozen --extra physics pytest tests -q
git diff --exit-code uv.lock
! git grep -nE 'pypi\.[a-z]+\.com' -- ':!docs' ':!report-current-progress.md' ':!pyproject.toml'
(cd ui && npm ci && npm test && npm run build)
(cd editor/vscode && npm ci && npm test && npm run build)
```

Keep `--extra physics` on main's uv invocations while this gate runs so another
uv command does not remove the solver extra. Do not change Python dependencies,
`uv.lock`, Pocky geometry/physics/scenarios/acceptance files or their frozen
tests. Keep core imports independent of GUI/HTTP modules. Keep generated output
under ignored `out/`; never commit tokens, node_modules, machine-specific home
paths, or generated geometry beyond explicitly approved tiny test fixtures.

## Local artifacts and H3

The two-cycle source run exists locally at
`out/mujoco-two-cycle/wedge_clamped`: 22 acceptance checks passed, 236,001
states over 14.75 seconds. Its sibling `.gui` export has 886 frames, six bodies
(including all three packets), 13 phases and 45,583 contact samples.
The source run was unchanged by export. Verification reports are under
`out/.gui-verification/`; the eight-part scene is under
`out/pocky/syringe/scene/`. These ignored artifacts are not pushed.

On a fresh checkout, regenerate the run with the existing inputs:

```sh
uv run --frozen --extra physics cad physics run pocky/syringe \
  --scenario projects/pocky/physics/scenarios/syringe_two_cycle.json \
  --acceptance projects/pocky/physics/syringe_two_cycle_acceptance.json \
  --options projects/pocky/physics/options/syringe_two_cycle_wedge_clamped.toml \
  --out out/mujoco-two-cycle/wedge_clamped
```

A local viewer was left running. Discover it through `out/.gui/service.json`
and verify health/repo identity; port, PID and token are ephemeral. Keep its
token private. Reuse a healthy service rather than starting duplicates.

After G3c and its merge gate, verify the desktop and 400 px browser, then stop
at the exact H3 checks in `plan-gui.md`: selection in tree/viewport, real
two-cycle playback/seek/speed with the second packet, and a failed build
preserving the old scene marked stale. Do not record human PASS on the user's
behalf.

## Companion packetd changes

`~/src/packetd` has two completed main commits:
`ab83ad1` repairs macOS sandbox shell execution through a confined command
broker, and `ed21245` makes the orchestrator act on supported recommendations.
The sandbox repair passed 765 tests (12 skipped), focused checks, typecheck
and build, and was deployed to the local service. Do not restart packetd
casually; it may have unrelated packets. Its installed and canonical
`codex/skills/packetd/SKILL.md` copies match. OMP was not changed.

 You are continuing M0 of the Pocky packet dispenser in /Users/daniel_l_newman/src/cadstudio
  (Python CAD on build123d, uv; NOT a git repo, so any before/after diff needs a file snapshot).
  Read CLAUDE.md, plan-pockey-dispenser.md (spec; §9 = M0 scope), and the approved plan at
  /Users/daniel_l_newman/.claude/plans/misty-knitting-widget.md.

  ## Settled decisions — do not reopen
  - Licence: the user has Riva3D's permission for AI analysis of the reference
    (~/Downloads/Archivos STL + Video de armado/). Meshes, video, frames and traced outlines must
    never enter the repo or outputs; only numbers and prose. Our design must be original.
  - The pocky project lives inside cadstudio; cadstudio is now multi-project.
  - The in-repo reference copy has been deleted on purpose; ~/Downloads is the only copy.

  ## Done and gated
  1. Tooling check: build123d 0.13.0, trimesh 5.1.1, pyvista 0.49.1, ffmpeg 9.0.2.
     Baseline snapshot at /tmp/cadstudio-baseline; baseline outputs at /tmp/cadstudio-base-out1.
     Outputs are deterministic (STL/PNG/report byte-identical across runs; 3MF is not, so it is skipped).
  2a/2b. Multi-project refactor:
     - cadkit/ is generic: cadkit/project.py holds the Project record and discovery; params,
       checks and render are generic.
     - Armor lives in projects/armor/ (params.py, part.py with ArmorPart, checks.py, render.py, models/).
     - CLI addresses models as <project>/<model>; output goes to out/<project>/<model>/.
     - Gate: all 5 armor models byte-identical to baseline via `zsh /tmp/cadstudio-gate/compare.sh`.
       179 tests pass with the same IDs; the only assertion change is "demo_cube" -> "armor/demo_cube".
  4. Reference reverse-engineering: projects/pocky/docs/reference-notes.md and kinematic-diagram.png.
     - Pivot fully pinned; Ø4 tip pin on a 25.37 mm arm; 61.2° over a 9.53 mm stroke.
     - About 2.85:1 average gain; no dead point.
     - About 12.7 mm sideways tip scrub.
     - Floor channel gives clearance only (it does not guide the tip).
     - Exit gap is 5.0 mm, while our packet is 5.2 mm.
  5. Pocky skeleton: projects/pocky/{__init__,params}.py, params.toml, geometry/packet.py
     (packet, packet_stack), models/packet_dummy.py, README.md.
     `uv run cad build pocky/packet_dummy --render --check --views standard`: 5 pass, 0 fail, 0 warn.
  6. tests/test_pocky_params.py and tests/test_pocky_geometry.py: 33 pass. They were written from
     the spec by a different worker than the one that wrote the code.

  ## Remaining
  A. Verify step 3 (docs). CLAUDE.md, README.md and MEASURING.md were updated for the new layout
     but not verified.
     - Run every `uv run cad ...` command quoted in their Commands sections, using
       --views standard and --out /tmp/docs-check/...
     - Check every path:line reference in CLAUDE.md with `sed -n`.
     - Confirm a "Pocky project" section points at projects/pocky/README.md.
     - Fix whatever is stale. Don't rewrite what's correct.
  B. Step 7, mechanism proposal. Nothing was written; start fresh. Write
     projects/pocky/docs/mechanism-proposal.md, plus projects/pocky/docs/proposal_sweep.py
     (numpy/matplotlib, standalone) and the proposal-diagram.png it generates.
     Work from reference-notes.md; don't re-read ~/Downloads. The proposal covers:
     - an original slider -> bell-crank pin-slot ejector with a straight packet exit;
     - a +X (push the 55 mm end seal) vs +Y (push the 165 mm side) comparison and recommendation;
     - a broad rounded pusher instead of a point tip, given the scrub;
     - separator gap and shim scheme (the reference gap is 5.0 vs our 5.2 mm packet);
       presentation lip; return/retract chamfer; metal compression spring; hard stops;
     - unverified physical behaviours;
     - open questions for the user.
     Rules:
     - Existing param names in params.toml are fixed: packet.length/width/height,
       magazine.length_i/width_i/headroom/capacity_test, separator.gap, structure.min_wall.
     - New linkage params go in a table marked "proposed for M1, not yet in params.toml".
     - Do NOT edit params.toml.
     This needs real mechanism-design judgement; use the strongest model available.
  C. Run the full `uv run pytest tests -q` (about 3.5 min), then write projects/pocky/docs/m0-report.md:
     - PASS/FAIL for each M0 item in plan §9;
     - exact commands run;
     - artifact paths;
     - unresolved items (dispense axis, separator gap, scrub acceptability, real packet
       thickness distribution and seal width);
     - an explicit "M1 not authorized until user review".
     Then STOP for user review. Do not start M1.

  ## Known loose ends (mention in the report, don't fix unasked)
  - The old output dirs out/armor_* and out/demo_cube etc. still sit next to out/armor/.
  - `magazine.capacity_test` loads as float, because cadkit's override always coerces to float.
  - The `"150" in detail` assert in test_cadkit_check_set_reflected is a loose substring match.
  - The snapshots under /tmp are scratch and can be deleted after M0.

# M5a-1 handoff — generic layer done, Pocky adapter not started

**State:** the M5a-1 implementation was started by human instruction from the accepted plan,
`docs/mujoco-m5a-plan.md` §6.1, and stopped partway by human request. This commit holds the
**generic `cadkit` additions and their tests only**. No Pocky adapter, scenario, acceptance
file or simulation evidence exists yet. `projects/pocky/physics/` still contains only the
frozen `acceptance.toml`, whose raw SHA256 is unchanged:
`518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`. No CAD, params or
export was edited, and no physical or product claim is made.

The next agent starts from this commit on `main`. The human pushes it.

## Done in this commit

| Plan item | Files | Notes |
|---|---|---|
| Per-collider friction and priority (§3.4, §8.1) | `cadkit/physics/schema.py`, `scene.py`, `runner.py`, `replay.py` | `ColliderSpec.friction` and `priority` are validated. XML attributes are emitted only when set, so existing XML and scene hashes are byte-identical. `physical_inputs` records the resolved friction and the priority. The compiled check is now **per geom by name** in both the runner and replay; the old check looked at geom 0 only. Replay falls back to the geom-0 check for summaries recorded before this change. |
| `cad physics run` and `Project.physics_with_options` (§8.1) | `cadkit/cli.py` (`_physics_run`), `cadkit/project.py`, `runner.py`, `replay.py` | Strict, bounded options TOML (at most 64 KiB, scalars or flat arrays). The lock is `assembly_options.lock.toml` and its raw SHA256 goes into the summary, the manifest and the identity. Replay verifies the lock. Project runs require `scenario.timestep_s == spec.timestep_s` (the `require_scenario_timestep` keyword). With no `--options`, a canonical empty lock is still written and hashed. |
| `cadkit/physics/support.py` (§4, §8.1) | new file | `SupportMargin`, `support_margin`, `bearing_carries`, with line and point degeneracy. It needs no mujoco. It reproduces the plan's strip width of 4.23 mm and margin of −4.54 mm. |
| Overlay camera and clip | `cadkit/physics/overlay.py` | `render_overlay(..., camera=, view=, clip=)`. The defaults keep the old iso view at azimuth 35 and elevation 22. |
| Tests | `tests/test_cadkit_physics_friction_priority.py`, `tests/test_cadkit_physics_support.py`, `tests/test_cadkit_physics_cli_run.py` | A different worker wrote these from the plan spec, not from the implementation. They include a check of effective `data.contact.friction` (0.30 with priority 1, 0.50 at equal priority). |
| Approved test narrowing | `tests/test_cadkit_physics_export_cli.py` (`test_project_physics_defaults_to_none`) | **The human approved this.** It now asserts the `Project` defaults and armor's hooks are None, rather than "every project", because Pocky must gain a hook. It is the only edit to an accepted test. |

Verification at commit: `uv run --frozen --extra physics pytest tests/test_cadkit_physics_*.py -q`
gave **488 passed, 1 warning** (a pre-existing zip duplicate-name warning) in 94 s. The full
suite was **not** run.

## Not done (remaining M5a-1 work, in order)

The approved step plan is reproduced here so it does not depend on any session file.

1. **S0 check kinds (generic; hardest remaining generic step).**
   - Add `relative_pose`, `relative_translation` and `contact_duration`, plus the new `CheckSpec` fields (`max_rotation_rad`, `axis`, `frame`, `lower`, `upper`, `force_threshold_n`, `window`).
   - Add `window="max_over_phase"`, including on `body_speed`.
   - Add strict loading. `frame="world"` is allowed only with `axis="z"`, and `relative_translation` requires both `lower` and `upper`.
   - Telemetry tracks, every step:
     - `p_rel(t)=R_a(t)ᵀ(p_b−p_a)` and `R_rel=R_aᵀR_b`, never freezing `R_a(initial)`;
     - summed normal force over all geom pairs of a body pair, and the longest run above the threshold.
   - Runner and replay must both derive these watches from the acceptance spec.
   - Add an **opt-in** near-threshold INCONCLUSIVE band (20%) at the acceptance level, off by default, so accepted M4 results are unchanged.
   - Spec: `docs/mujoco-m5a-plan.md:460-522, 560-582, 688-700`.
   - Edit points: `scenario.py` `CHECK_KINDS` (~:35), `_CHECK_FIELDS` (~:929), and a `_load_check` branch placed **before** the catch-all `else` (~:1018); `CheckSpec.to_dict()` (the lock round-trip); `telemetry.py` following the event-watch pattern (`_event_body_ids`, the `_accumulate` loops); `evaluate._evaluate_check`; the `TelemetryRecorder` kwargs in `runner.py` and `replay.py` (~:563).
2. **S0 check tests**, by a worker other than the one that implements item 1.
   - The yaw-90 A/B counterexample, rejecting the wrong order.
   - A rigid pair under common rotation gives Δp=0. The old formula gives 1.414214 mm and must be rejected.
   - Fixed-transform invariance.
   - True motion and no motion.
   - A 0.4 mm fall and a 0.4 mm lift both fail [−0.10, +0.10] mm.
   - World x/y is rejected.
   - Zero contact passes.
   - `max_over_phase`, near-threshold, and replay recomputation.
3. **Pocky colliders and fidelity:** `projects/pocky/physics/colliders.py`. This was started and cancelled, and **nothing was kept**.
   - Primitives: about 22 boxes for the body, about 30 for the chassis, about 15 for the lip, and so on (§3.5).
   - No hulls and no filled slots or bores. The f=1 peg relief is local. The boss is ring sectors in two Z bands.
   - 0.02 mm critical planar surfaces.
   - Negative variants: a hulled body and a slot-filled crank.
4. **Pocky assembly, options and hooks:** `assembly.py`, `options.py`, and lazy `physics` and `physics_with_options` hooks in `projects/pocky/__init__.py`.
   - Build at fraction 0 with bodies and joints per §3.2–3.3, and spring reference +0.003 m.
   - Friction and priority: PETG 0.40/0, packet 0.30/1, floor 0.50.
   - Analytic floor with its top at z = −19.2 mm.
   - Derive the reset from `linkage_from`, `pose_at_phi` and `phi_for_button_fraction`. Cross-check the compiled transforms at all five fractions, with linear-reset and sign-flip negatives.
5. **Static preflight and clearance audit:** `projects/pocky/physics/support.py` and `clearance_audit.py`.
   - Exact overlap at five fractions and the tilted-seat inventory.
   - Collider-vs-CAD audit on compiled `geom_xpos`/`geom_xmat` after each reset. A difference over 0.02 mm is `SCENE_INVALID`.
   - No exact min-distance helper exists. Use build123d `Shape.distance_to` and the pattern in `projects/pocky/docs/prototype_sweep.py:68-248`.
6. **Scenarios and acceptance.**
   - `scenarios/s0_f000…s0_f100.json`, `s0_spring_low.json`, `s0_spring_high.json` and `s0_half_dt.json`, each with `sampling_interval_s = timestep_s` and every-step budgets.
   - `s0_acceptance.json`, with thresholds verbatim from §5.3.
   - `options/s0_*.toml` and `report.py`.
7. **Pocky tests**, by a worker that did not write items 3–6 (§9, `:821-831`).
8. **Evidence runs** under `out/mujoco-m5a/` (§9 commands): export, preflight, five S0 runs, spring low/high, half-dt, replay of S0 f=0, and overlays.
9. **Reports:** `docs/mujoco-m5a-report.md` and `projects/pocky/docs/physics-m5a.md`, plus the after-manifest. Then the full suite once, then code review.

## Gotchas found this session

- **Use `uv run --frozen --extra physics …`.** Plain `uv run pytest` silently **skips every physics test**, because mujoco is in the optional `physics` extra. Without `--frozen`, `uv` also rewrites `uv.lock` to the `pypi.apple.com` registry. That rewrite was reverted before this commit.
- **`out/` does not exist in a fresh checkout**, so the plan's `out/mujoco-m5a-planning/` evidence (`cad_probe.json`, manifests) is gone and must be regenerated. A before-manifest of the 195 tracked files at `ca9a305` was written to the untracked `out/mujoco-m5a/before-manifest.json`. Treat the parent of this commit (`ca9a305`) as the before-baseline.
- **`runner.py` still reads `model.geom_solref[0]`** in its compiled-solref check (~:517). It has the same geom-0 assumption the friction check had. It is harmless while no collider sets its own solref.
- `OPTIONS_LOCK` is defined in both `runner.py` and `replay.py`, so replay does not import the runner.
- The tampered-friction replay test hits the manifest/summary solver-facts guard first. The compiled-vs-recorded per-geom branch in replay (~:526) is exercised only by the passing replay path.
- The open plan decisions from `docs/mujoco-m5a-plan.md` §10 still stand, and so does the prediction recorded before running: S0 is expected to FAIL on `body_drop` and `body_on_pusher`. A credible FAIL is a valid result. Do not tune the scene to avoid it.

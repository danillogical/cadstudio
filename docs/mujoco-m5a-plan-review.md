# M5a plan review record

**Plan artifact:** `docs/mujoco-m5a-plan.md`
**Review type:** configured ordinary independent review (read-only). No security-reviewer gate.
**Reviewer:** bundled `reviewer` agent, configured role `slow`, selected by the agent's own
bundled mapping. Actual model recorded from the reviewer subagent session:
`anthropic / claude-opus-5-5` (`anthropic-messages`). No model, provider, effort, role,
fallback or substitute was chosen or changed by OMP.
**Native evidence:** reviewer subagent transcript
`/Users/daniel_l_newman/.omp/agent/sessions/-src-cadstudio/2026-10-22T03-07-55-754Z_01a16194-5dea-710e-9171-1b5000f7f312/M5aPlanReview.jsonl`
(204 records after three review rounds plus remediation and correction follow-ups; every assistant record with model metadata is `anthropic/claude-opus-5-5`).
There is no native plan-mode activation in the managed bridge; this is artifact-based
planning in the existing managed session, not native plan mode.
**Boundary:** the reviewer edited no files and ran no product build/export/test or simulation.
It read the plan, the named sources and the CAD probe. Review limits are stated per round.

**Correlation IDs:** run `run_0mviyq59q90622f804e919ceb`; plan-only operation
`op_0mviyqlkz462e1d0a2dee9f1e`, turn 1; no authorization id; 10 operations / 2 remediation
cycles / deadline `1792667380525`; cumulative before admission 19 operations / 7 remediation
cycles. No bridge decision was recorded and no implementation was authorized.

---

## Round 1 — reject with demonstrated defects

Verdict: **reject**. The reviewer accepted the overall free-assembly design and the frozen
boundary (it re-hashed `projects/pocky/physics/acceptance.toml` to
`518a45ff…6ca2`), but found defects that would make M5a-1 fail with ERROR, an invalid scene,
or an unbound verdict.

| ID | Finding | Fix in the plan |
|---|---|---|
| M1 | `pusher_x` range used the 23.094 mm button stroke; the pusher actually moves 50 mm (−103→−53, face −87→−37). S0 at f≥0.5 would ERROR. | Range 0…0.0505 m; reset table gives `pusher_x = 0.050·f`; test compares `pose_at_phi(phi1)−pose_at_phi(phi0)` to the range. |
| M2 | Joint-zero convention contradicted building the assembly at fraction f. | Runtime scene always built at fraction 0; reset writes joint coordinates; `springref=+3 mm` fixed; the anchor is stated in the crank body frame; the spring visual/mass is welded and collision-disabled. |
| M3 | P0 packet at x=−20 would overlap the back wall by ~686 mm³. | P0 center x=−2.4 mm in the viable window −2.5…−2.0; 0.1 mm rear and 0.4 mm front clearance; zero-overlap preflight. |
| M4 | Packet 2 is 2.95 mm above packet 1, not 0.55 mm; the horizontal start is not a rigid-box seat. | Derived 1.0368° tilted seat through the bottom packet rear and the blade rear edge; 0.55 mm is the blade-underside clearance; the stack is tilted; zero-overlap gate. |
| M5 | 0.5 mm coverage / 0.2 mm deviation are wider than the 0.027–0.4 mm gaps being tested; the relief coordinates were a long strip. | 0.02 mm on declared planar critical surfaces; collider-to-CAD clearance audit; local f=1 relief x≈−57…−49, y 31.4…32.4. |
| M6 | Equal-priority MuJoCo friction takes the maximum; packet 0.30 against PETG 0.40 becomes 0.40. | Packet geom priority 1; effective `data.contact[i].friction` test; PETG↔wrapper and wrapper↔wrapper declared one coupled parameter. |
| M7 | `Project.physics(model, params)` cannot carry packets/mass/spring/timestep. | Hashed options file + `Project.physics_with_options`; options lock copied into the run; scenario timestep required and matched. |
| M8 | A post-run S0 sidecar would be unbound and unreplayed; TOML criteria would be rejected by the generic loader. | Three generic check kinds (`relative_pose`, `relative_translation`, `contact_duration`), S0 acceptance JSON, generic evaluator, acceptance lock, replay recomputation. No sidecar. |
| M9 | P cases started from the CAD pose, not a settled state. | P1–P3 include an explicit settle phase and a post-settle measured window; each report compares the settled housing pose with S0 f=0. Cross-run import is deferred to M5b (same body set), with a blocked-gate statement if Codex requires it for M5a-2. |

Minor/nit fixes: lip-on-moving-part checks, spring-return transient, parent-child filtering
and joint-stop idealization, spring provenance `assumed`, spring mass 1.919 g, contact-row
budget, CAD probe artifact, 2 ms wording, 9.4/6.5 mN·m, before-manifest location, no
`out/mujoco-m5a/review`.

## Round 2 — approve with required fixes

Verdict: **approve with required fixes** (R1/R2 before M5a-1; R3/R4 before M5a-2). The
reviewer confirmed M1–M9 resolved and re-checked the CAD numbers.

| ID | Finding | Fix |
|---|---|---|
| R1 | `contact_duration` did not define how multi-point forces combine; peg checks cannot be written because pegs are welded parts; `lip_on_crank` missing; 0.0715 N is 5% of the hanging group, not the body. | Sum normal forces over all geom pairs between the two bodies per step; peg checks removed; `lip_on_crank` added; threshold labeled 5% of 145.89 g (body-only 0.0684 N noted). |
| R2 | Clearance audit ran only at fraction 0, missing the f=1 peg-head/relief and lip-rail/rod-head gaps. | Audit after each of the five resets using compiled `geom_xpos`/`geom_xmat` and exact CAD at the same fraction; lip-rail↔rod-head pair added. |
| R3 | Stack tops were 6.69 mm too high (packet-2 origin added twice). | Correct tops 54.98/132.97 mm; every packet origin/rotation recorded in `cad_probe.json`; 1 µm seating clearance removes a 9.1e−5 mm³ tangential overlap; 25 rear −84.745 mm / 0.255 mm. |
| R4 | `gravity_acceptance.json` had no defined checks; free-fall acceleration has no check kind. | Checks defined with existing/new kinds; free-fall acceleration explicitly report-only from `trace.csv`. |

Minor/nit fixes: `cadkit/cli.py` path; options lock copy; non-null scenario timestep;
coupled packet friction; pivot bore removed from 0.02 mm surfaces; crank/pusher guard stop
time constants.

## Round 3 — approve

Verdict: **approve**. R1–R4 and the minor/nit items were confirmed resolved. The reviewer
verified the tilt, per-packet translation, packet-10 origin z (48.286 mm), tops
(54.978 / 132.965 mm) and 25-rear −84.745 mm by hand. Three text fixes remained:

1. `relative_pose` was absolute at the boundary; `floor_world` frame was not stated; packet
   translation was called diagnostic while `maximum` is required.
2. `cad_probe.json` did not list every packet origin and used the pre-clearance z.
3. This review file did not exist yet.

Fixes applied in the plan/probe before submission:

- `relative_pose` is now the **change from the `initial` boundary**, expressed in `body_a`'s
  frame; `floor_world` is an identity frame with an offset collider; packet translation has a
  declared 20 mm non-binding diagnostic bound while rotation is the gate.
- `cad_probe.json` records all packet origins 02…25 after the 1 µm clearance.
- This file was written.

## Supervisor plan-review remediation — dec_0mvj09ctf3fb2adfee3afcedd

The supervisor reviewed the completed plan-only operation
`op_0mviyqlkz462e1d0a2dee9f1e` in `docs/mujoco-m5a-plan-supervisor-review.md`. It
independently verified the 99 source hashes, boundary inventory and the configured Opus
review transcript, then found three remaining plan defects. Planning was not approved and
no implementation was authorized. This section records the plan-only remediation; earlier
rounds above are preserved.

| Supervisor defect | Fix |
|---|---|
| Quarter button fractions were treated as linear pusher travel (12.5/37.5 mm); CAD gives 11.132495094/38.867504906 mm, a 1.3675 mm error above the 0.3 mm slot clearance. | §5.2 derives every reset from `phi_for_button_fraction`/`pose_at_phi`, lists the exact five-fraction table, and requires a compiled-transform cross-check at all five with linear and sign-flip negative tests. |
| `relative_pose` used `T_b·inverse(T_a)`, contradicting the body_a frame and changing under a common world transform. | §5.3 uses `inverse(T_a)·T_b`, `p_rel=R_aᵀ(p_b−p_a)`, `R_rel=R_aᵀR_b`, initial-frame Δp/ΔR, quaternion angle, the A/B yaw-90 counterexample, and common-world-transform plus true/no-motion tests. |
| A signed −0.4 mm fall would pass an upper-only drop bound. | `body_drop` is a world-z signed change with explicit lower/upper ±0.10 mm plus positive downward `max(0,−Δz)≤0.10 mm`; 0.4 mm fall and 0.4 mm lift both fail; upper-only signed predicates are forbidden. |
| Hold/replay sampling semantics were unstated. | §5.4 sets `sampling_interval_s = timestep_s` explicitly in every S0/P scenario (1 ms base, 0.5 ms half-dt), sizes budgets for every-step rows, uses `max_over_phase` for pose/drop/speed, per-step summed-force contact duration, and replay recomputation within one sample interval. |

Reviewer follow-up (same configured ordinary reviewer, no substitution): round 4 approved
items 1–3 and required the explicit sampling setting; round 5 approved after the
`sampling_interval_s = timestep_s` fix. Actual model remained
**`anthropic/claude-opus-5-5`** (`anthropic-messages`); the subagent transcript now has 197
records (SHA256 `47251a07e54e0c919ea6bb536f52b1ac43974c182eab11c4d3b2b37d41972a08`).
The reviewer edited nothing and ran no product command. Reviewer limitations: it re-read
only the changed sections, recomputed the numbers by hand, and ran no MuJoCo/CAD/product
command.

Prior review rounds, supervisor-authored review/orchestration documents and the supervisor
probe evidence are pre-existing and preserved. This plan still requires Codex approval and a
separate implementation authorization.

## Supervisor plan-review-2 correction — dec_0mvj0nmmf32ee59dd12743b88

The supervisor's second review, `docs/mujoco-m5a-plan-supervisor-review-2.md`, verified the
prior reset/drop/every-step-hold fixes and found one remaining mathematical defect: the plan
computed `Δp` by freezing `R_a(initial)` and subtracting world separation vectors. For an
exactly rigid pair rotating 90° together over time, that reports 1.414214 mm of drift.

Fix applied in §5.3:

```text
p_rel(t) = R_a(t)^T (p_b(t) - p_a(t))
Δp = p_rel(current) - p_rel(initial)
```

Components use body_a's attached local material axes at each time, so common physical rotation
leaves `p_rel` constant. The relative orientation `ΔR` and the separate signed world-z drop
with lower/upper bounds are retained. The numeric counterexample (A at origin, B at (1,0,0),
both rotate 90° about world Z to B at (0,1,0); true `Δp=0`; forbidden formula `(-1,1,0)`,
norm 1.414214 mm) is a planned regression. The plan now explicitly requires time-varying
common physical motion zero drift, superimposed true relative motion in body_a local axes,
fixed-coordinate transform invariance, and world drop sign cases. The optional hardening
recommended by the reviewer is included: `frame="world"` requires `axis="z"`.

Reviewer follow-up (same configured ordinary reviewer, no substitution): **approve**, with no
demonstrated defects remaining; only the optional world-axis hardening was suggested, and it
was applied. Actual model remained **`anthropic/claude-opus-5-5`**
(`anthropic-messages`); transcript 204 records, SHA256
`a0d58e2ed6e31a7532bad9c3ce01b9aff8391c7275136b678d829176addb8477`. The reviewer edited
nothing and ran no product/simulation command.

Prior review rounds and supervisor review/probe evidence are preserved. This correction is
still a planning artifact; Codex approval and a separate implementation authorization remain
required.

## Residual review limitations

- No simulation, export or test was run for the review; all checks were source/CAD hand
  calculations.
- Rounds 2–3 read only the changed plan sections and the probe block, not every source again.
- The reviewer did not verify physical measurements; none exist.
- The plan remains a planning artifact. Codex approval and a separate implementation
  authorization are still required; an approving review does not authorize implementation.

# M4c report: generic events, supported presentation and frozen criteria

**Status:** the bounded M4c packet is implemented, focused and full tests pass, and real
positive/negative/replay evidence is preserved. The configured ordinary reviewer completed
after the human updated the `slow` role: the actual reviewer subagent ran on
**anthropic/claude-opus-5-5** (verified in `M4cReview2.jsonl`, 52 session records; no
override), and found two major and four minor defects plus nits. Every demonstrated finding
was fixed and the focused/full suites were rerun. The earlier pre-change attempt on the old
`muse-code/muse-wonder-1.0` mapping returned 429 and is preserved as history. No substitute
model or role was used. M4 is **not claimed complete**; independent Codex acceptance remains
required.

**Follow-up repair:** the supervisor review at `docs/mujoco-m4c-supervisor-review.md`
identified two demonstrated defects in this increment. `docs/mujoco-m4c-repair-report.md`
records the bounded repair, its red/green evidence, the final test counts and the review.
The original M4c counts below are retained as the pre-repair increment history.

Scope boundaries held: no Pocky physics adapter, S0, product CAD edit, candidate redesign,
M5 work or physical trial. No scheduler, bridge verdict, self-renewal, model/provider/effort/
role/fallback change, or separate security-reviewer gate. M0–M3, M4a and M4b remain accepted.

## Native configured plan

The configured native plan role (`opencode-go/deepseek-v4.1-flash:max`, human-owned) was run
before any production edit:

1. Tool-enabled plan with the full packet prompt: exit 1 after **300 s**, empty stdout
   (`Deadline exceeded`). Raw: `/Users/daniel_l_newman/.omp-bridge/diagnostics/`
   `cadstudio-m4c-plan-20261021/plan.txt` and `plan.err`.
2. Retry with a shorter prompt and `--max-time 480`: exit 1 after **480 s**, empty stdout.
   Raw: the same directory, `plan2.txt` and `plan2.err`.
3. Retry with the same configured plan role and `--no-tools` so generation did not compete
   with tool exploration: exit 0 after **125.44 s**, **22,835 bytes** of substantive plan.
   Actual successful artifact:
   `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-plan-20261021/plan3.txt`.
   The failed tool attempts are in the same directory and are not the successful plan. This
   plan was executed; no custom planner was created.

The plan's numeric time-window sketch was adapted to the packet's required **named phase
windows**, and its optional `events.json` sidecar was replaced by bounded event evidence in
`summary.json`/`manifest.json`/`report.md` plus replay recomputation. Those are recorded
deviations, not scope changes.

## Implemented APIs and files

### `cadkit/physics/events.py` (new)

Pure, deterministic per-step tracker, independent of MuJoCo and projects:

- `EventTracker(events, gravity_m_s2=...)`, `begin_phase`, `end_phase`, `observe`,
  `finish`, `EventResult.to_dict`.
- `StepObservation(time_s, step_index, phase_name, phase_kind, ctrl_zero, bodies, contacts)`,
  `ObservedBody`, `ObservedContact`, `SupportMetrics`.
- `exit_crossing`: leading point of the declared rigid box, configured plane/direction,
  phase window, outward-velocity gate, touch-only, wrong-direction, initially-outside/
  initially-protruding suppression, one record per distinct body per cycle, re-crossing
  diagnostics.
- `supported_presentation`: protrusion beyond the outer plane and accessibility beyond the
  access/shelf plane; actual contact support load projected on gravity; projected COM inside
  the contact convex hull (1 mm margin) or within a declared 2 mm line-support degeneracy
  radius; a lone contact point is INCONCLUSIVE, not support evidence; continuous post-release dwell; bounded protrusion change; late/missed/support-loss/
  post-dwell-failure/out-of-bounds/uncontrolled-fallout diagnostics; INCONCLUSIVE for zero
  gravity, missing body, unobserved release, nonzero release input or truncated evidence.
- Crossing time is linearly interpolated between the two post-state samples; every other
  quantity belongs to the recorded post-state timestamp.

### `cadkit/physics/presentation_aperture.py` (new)

Independent non-Pocky fixture: fixed multipart housing (floor + two side walls + top) with a
true open mouth at `x = 0` and an 18 mm shelf ending at `x = 18 mm`; a free 100 × 36 × 8 mm
rigid box at 1.2 g/cm³; a bounded, damped 0.1 kg prismatic pusher driven by a real force
actuator (2 N requested, 3 N bound, 50 N·s/m damping, 65 mm stroke). Variants:
`presentation_aperture_blocked` (fixed wall 1 mm inside the mouth) and
`presentation_aperture_double` (two 17 mm packet identities side by side). Motion comes only
from the actuator, friction, contact and gravity; `qpos` is written only by the reset phase.

### Schema and integration

- `cadkit/physics/scenario.py`: `PlaneSpec`, `EventSpec`, acceptance `events`/`notes`,
  strict `event_count` and `event_verdict` checks, `acceptance_from_toml_text`/
  `load_acceptance_toml` using `tomllib`, and the three fixture ids. The schema version stays
  `m4a-1`; `events` is optional, so accepted M4a/M4b files load unchanged.
- `cadkit/physics/telemetry.py`: one event observation per real integration step from the
  coherent post-state scratch `MjData`; contact positions, world normals and forces are
  captured at the same state time. Sparse CSV remains display evidence only.
- `cadkit/physics/runner.py`: recorder wiring; `events` in `summary.json`, `manifest.json`
  and the Markdown report; failure summaries preserve partial event evidence.
- `cadkit/physics/evaluate.py`: event/body/support/phase reference and ordering validation;
  event checks use evidence-complete counts and verdicts, with INCONCLUSIVE when evidence is
  incomplete.
- `cadkit/physics/replay.py`: a fresh tracker is built from the hash-verified acceptance and
  fed by re-stepped states; recomputed event evidence is compared with the saved summary and
  the comparison is required for `reproduced`. Summary/manifest event evidence must agree.
  No saved event verdict is reused as the replay result.
- `cadkit/physics/schema.py`: nonzero gravity outside 1–100 m/s² is rejected as a unit-scale
  ERROR; zero gravity remains an explicit diagnostic scene.
- `cadkit/cli.py`: prints event status/code and replay event equivalence.
- Published schemas updated: `docs/physics-m4a-acceptance.schema.json` (events, plane/bounds
  definitions, two event checks) and `docs/physics-m4a-summary.schema.json` (`events`).

### Tolerances and rationale

| Constant | Value | Rationale |
|---|---:|---|
| crossing epsilon | 1 µm | above metre-scale float noise, far below the 0.8 mm minimum feature |
| outward velocity epsilon | 1 mm/s | rejects touch/rebound; commanded motion is tens of mm/s |
| support load fraction | 0.6 of body weight | tolerates one support edge unloading, rejects anything near half weight |
| support hull margin | 1 mm | contact-patch/sampling uncertainty; marginal hulls are INCONCLUSIVE |
| hull minimum area | 1e-5 m² | below this, use declared line support instead of a fake 2-D hull; a lone point is INCONCLUSIVE |
| degeneracy radius | 2 mm | a flat packet on a narrow shelf is legitimately line-supported |
| near-threshold bands | 5% support, 1% (min 0.1 mm) protrusion/accessibility, 1% dwell | near-threshold outcomes are INCONCLUSIVE, not PASS |
| dwell minimum | 0.5 s | frozen requirement; no grace steps |
| protrusion change | 1 mm | frozen requirement; also bounds creep |
| terminal speed (generic / Pocky) | 0.02 / 0.01 m/s | quiescent hold; generic fixture is not a product measurement |
| bounds / fallout drop | declared per event; 20 mm fallout | complete fallout must be distinguishable from contact settling |
| gravity plausibility | 1–100 m/s² unless exactly zero | catches mm/s²-vs-m/s² scale errors before simulation |

Near-threshold support load (within 5% of the fraction) or a marginal hull is INCONCLUSIVE,
not PASS.

## Synthetic failure and edge-case evidence

Scripted-sample tests are explicitly labelled `synthetic_`; the real MuJoCo fixture and replay
tests are separate.

| Case | Classification |
|---|---|
| no gravity | INCONCLUSIVE `gravity_absent` |
| wrong unit scale (`0.00980665 m/s²`) | ERROR before a run directory (`ValueError`) |
| blocked aperture | FAIL `zero_feed` |
| missing force (zero effort) | FAIL `zero_feed` |
| duplicate feed (two identities) | FAIL `double_feed`, count 2 |
| same identity re-crossing | one counted identity, `re_crossing` diagnostic |
| touch only / wrong direction / initially outside | no counted crossing, typed diagnostic |
| slow or rotational outward leading edge | counted from leading-edge displacement, no velocity gate |
| crossing before window / release timing | not counted / no pre-release dwell |
| dwell just below / at 0.5 s | FAIL / PASS |
| post-success drift > 1 mm | FAIL `post_dwell_failure`, success revoked |
| near-threshold support / protrusion | INCONCLUSIVE `support_uncertain` / `near_threshold` |
| pre-release fallout, non-Z gravity axis | FAIL `uncontrolled_fallout` on the configured axis |
| support lost midway / total fallout / out of bounds | FAIL with the named code |
| marginal, lone-point or coincident support | INCONCLUSIVE `support_uncertain` |
| tilted plane normal lock | canonical JSON round-trip keeps the acceptance hash |
| dwell window spanning a later actuate phase | config ERROR before a run |
| empty observation | INCONCLUSIVE, never PASS |
| malformed event schema | loader ERROR, distinct from a dynamics negative |

Synthetic detector tests: 28 passed. Real fixture/replay tests: 9 passed. Acceptance/schema
tests: 7 passed.

## Real MuJoCo and replay evidence

Pinned environment: MuJoCo 3.16.0, Python 3.12.15, NumPy 2.5.4, macOS arm64.

| Case | Run | Replay |
|---|---|---|
| positive partial presentation | PASS, 0 | PASS, reproduced, event comparison ok, max state diff 0.0 |
| blocked aperture | FAIL (1), `zero_feed` | FAIL (1), reproduced, event comparison ok, max diff 0.0 |
| missing force | FAIL (1), `zero_feed` | — |
| double feed | FAIL (1), `double_feed`, count 2 | — |
| no gravity | INCONCLUSIVE (2), `gravity_absent` | — |
| wrong unit scale | ERROR before run (typed API) | — |

Positive run facts: 4,401 archived state rows, 2,201 trace rows, 17,330 contact rows, no
solver warnings; crossing at 1.0552 s; final protrusion 45.128 mm; accessibility 27.128 mm
beyond the 18 mm shelf plane; sustained supported dwell 1.899 s (minimum 0.5 s) with
protrusion change 1.32e-9 m; minimum support fraction 0.9999999985; support hull `inside`;
dwell `uncertain=false`. Scene hash
`a5bfdc09db70a728bbdca3469460192acf2e09804ade2ef3776b7e23bb38dbd0`; acceptance semantic hash
`000d4dc1fa1de6d0067ecec9f13a96535a902f9668614362ddc3c6bbb1d2fa4c`.

## Frozen Pocky provisional criteria

Only `projects/pocky/physics/acceptance.toml` was added; no adapter or CAD. It is strict-TOML
loaded and canonical-JSON locked; its `notes` carry provenance and the M5a predicates that
this generic event schema cannot express.

- packet 165 × 55 × 5.2 mm; exactly one `packet` identity in the declared candidate set;
  M5a must bind every packet body that could escape to that list (or extend the frozen list
  before candidates); an undeclared second ID is a configuration error, not a pass;
- leading edge ≥ 30 mm beyond outer face x = 88 mm; 40 mm target recorded, never a threshold;
- ≥ 10 mm exposed beyond the 18 mm shelf ending at x = 106 mm (not the superseded 15 mm);
- continuous supported dwell ≥ 0.5 s after real zero input; protrusion change ≤ 1 mm;
- actual gravity-normal support ≥ 0.6 of weight with projected COM inside the hull;
- no uncontrolled fallout, no second packet, no support loss through the window;
- housing stability (S0) and pair-aware non-packet penetration ≤ 0.2 mm remain required M5a
  predicates; rigid-wrapper limitations remain.

Raw SHA-256: `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.
Semantic acceptance hash: `5109a0a4cb5ed70c3605ac9b1148eda58cae0a05ba18725807d645e474d216d3`.
The semantic hash is pinned by a test; changing a criterion requires review.

## Verification

```text
uv run pytest tests/test_cadkit_physics_m4c_events.py \
  tests/test_cadkit_physics_m4c_acceptance.py \
  tests/test_cadkit_physics_m4c_fixture.py \
  tests/test_cadkit_physics_scenario.py -q
69 passed in 16.72 s

uv run pytest tests/test_cadkit_physics_m4a.py tests/test_cadkit_physics_m4b_replay.py \
  tests/test_cadkit_physics_m4b_adversarial.py tests/test_cadkit_physics_m4b_typed.py -q
90 passed, 1 warning in 26.51 s

uv run pytest tests/test_cadkit_physics_mechanics.py tests/test_cadkit_physics_scene.py \
  tests/test_cadkit_physics_export_cli.py tests/test_cadkit_physics_optional.py \
  tests/test_cadkit_physics_units.py tests/test_cadkit_physics_gravity_drop.py \
  tests/test_cadkit_physics_hollow.py -q
231 passed in 69.65 s

PATH=/Users/daniel_l_newman/.local/bin:$PATH uv run pytest tests/ -q
614 passed, 1 warning in 409.50 s, exit 0
```

The one warning is the existing deliberate duplicate-ZIP-member test.

## Review

The configured ordinary reviewer (`reviewer` agent, model role `slow`) was invoked twice with
no task/CLI/env override:

1. Before the human updated the global mapping, the reviewer ran on
   `muse-code/muse-wonder-1.0:medium` and returned HTTP 429 subscription-quota exhaustion.
   That failure is preserved in `review-blocked.md`.
2. After the human changed `slow` to `anthropic/claude-opus-5-5:medium`, the completed
   `M4cReview2` subagent session records provider `anthropic`, model `claude-opus-5-5` (52
   session records). The parent log said it reused its model registry; the actual subagent
   session metadata is the authoritative record of the model that ran. No stale-config issue
   is claimed for this completed review, and no substitute model or role was used. The
   security-reviewer role remains disabled and no separate gate was requested.

The reviewer reported no release blocker but two majors and four minors, plus nits. All
demonstrated findings were fixed before the final suite:

- **Major 1 (post-success drift).** Once a dwell succeeded, a later drift over 1 mm restarted
  the dwell without revoking success, yielding PASS with a negative duration. Fixed: drift
  after success revokes it, records `post_dwell_failure` as fatal, and never restarts the
  dwell. Dwell evidence now reports the sustained end, not the first success instant.
- **Major 2 (near-threshold support).** A support fraction of 0.61 against 0.6 was marked
  uncertain but still allowed PASS. Fixed: `ok` excludes a near-threshold fraction, and a
  successful dwell records near-threshold protrusion/accessibility uncertainty and returns
  INCONCLUSIVE `near_threshold`; duration uncertainty is assessed from the sustained length.
- **m1 (velocity gate).** A slow or rotational outward leading edge was misclassified as
  `wrong_direction`. Fixed: crossing is judged by leading-edge displacement; inward crossing
  after an outward one remains `wrong_direction`.
- **m2 (`touch_only`).** It remained true after a real crossing. Fixed: cleared on crossing;
  tests cover the band-before-crossing sequence.
- **m3 (pre-release fallout/bounds, gravity axis).** Bounds/fallout were only checked after
  release, and fallout used world Z. Fixed: every in-window sample is checked, fallout uses
  the configured gravity axis, and pre-release fallout is reported as
  `uncontrolled_fallout` rather than hidden behind `zero_feed`.
- **m4 (tilted plane lock).** Normalizing at construction made tilted normals non-idempotent,
  so replay could reject its own canonical lock. Fixed: `PlaneSpec` stores the authored normal
  and exposes `unit_normal` for geometry; a tilted-normal canonical round-trip is tested.
- **m5 (dwell over actuation).** A dwell window could span a later actuate phase. Fixed:
  `resolve_references` rejects a dwell window that spans any actuate phase.
- **Nits.** Dwell duration no longer rounds up; the Pocky notes make the event `bodies` list
  the declared candidate identity set and require M5a to bind every escaping packet. The
  first-post-step seeding limitation remains: a body crossing within the very first step of a
  window can be labelled `initial_protruding`. That is a conservative false negative (never a
  false PASS) and is recorded here rather than hidden.

## Artifacts

All under `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-20261021/`:

- `prompt.md`, `prompt2.md`, `prompt3.md` in this directory; native plan outputs (failed
  `plan.txt`/`plan.err`, `plan2.*`; successful `plan3.txt`) are in
  `/Users/daniel_l_newman/.omp-bridge/diagnostics/cadstudio-m4c-plan-20261021/`;
- `positive-scenario.json`, `positive-acceptance.json`, `blocked-scenario.json`,
  `missing-force-scenario.json`, `double-scenario.json`, `double-acceptance.json`;
- `cli-run-positive/`, `cli-replay-positive/`, `cli-run-blocked/`, `cli-replay-blocked/`,
  `cli-run-missing-force/`, `cli-run-double/`, with `.stdout`/`.stderr`/`.exit`;
- `typed-synthetic-failures.txt` and `typed-run-no-gravity/`, `typed-run-wrong-unit/`;
- `full-suite.txt`, focused test outputs, `changed-files.sha256`, `final-hashes.sha256`,
  `evidence_summary.json`;
- `review-prompt.md`, `review.txt`/`review.err` (CLI alias attempt: `Model "@reviewer" not
  found`), `review-blocked.md` (pre-change muse 429), `review-completed.md` (Opus run and
  finding/fix map); reviewer session `.../M4cReview2.jsonl` records
  `anthropic/claude-opus-5-5`.

## Remaining uncertainty and limits

- The positive fixture is generic; it does not validate the Pocky dispenser. M5a/M5b, S0 and
  P0–P9 are not run, and physical M7 remains UNVERIFIED.
- The rigid packet proxy cannot predict wrapper folding, adhesion, candy fracture or measured
  friction. Pocky mass, friction and spring rate remain unmeasured.
- The support hull is a projected contact-point hull with declared degeneracy handling; it is
  not a deformable contact model. Marginal/near-threshold support is INCONCLUSIVE.
- Replay claims same-platform reproduction within pinned tolerances, not cross-platform bit
  equality. Contact forces are forward-evaluated at the recorded post-state.
- The configured Opus review completed and its demonstrated findings were fixed; independent
  Codex review is still required. M4 is not claimed complete.
- A body crossing within the very first post-step sample of an event window can be labelled
  `initial_protruding`; this is a conservative false negative, never a false PASS.

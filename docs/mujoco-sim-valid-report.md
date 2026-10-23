# MuJoCo simulation validity: root cause, valid S0, and S1 slow press

Scope: the Pocky no-packet housing (`pocky/prototype`) in MuJoCo. Evidence lives under `out/mujoco-sim-valid/` (git-ignored; regenerate with the commands in `s0/logs/*.cmd` and `s1/logs/s1_press.cmd`). Sources are cited per section. Every number below is copied from a cited file, or is stated arithmetic on cited numbers.

Status words are the evaluator's. FAIL on a valid run is a statement about this model with its assumed inputs, not about a printed part (section 9).

## 1. Headline

- **What is now valid.** All eight S0 cases and the S1 press run are numerically valid: `ok=True`, no validity reasons (`out/mujoco-sim-valid/s0/results.md` "Validity reasons"; `out/mujoco-sim-valid/s1/results.md` "Validity"). Peak penetration is at most 0.1032 mm (S0) and 0.1290 mm (S1) against the 0.2 mm bound.
- **What the valid S0 says.** Every case gives the evaluator status FAIL, not INCONCLUSIVE. The body drops 4.4711 to 4.6600 mm relative to the chassis and rotates 2.9598 to 3.0907 degrees, resting on the pusher carriage and the rod shaft. The pre-validity runs gave 4.253 to 4.665 mm and 2.959 to 3.237 degrees (`docs/mujoco-m5a-report.md` section 5). The structural verdict did not change; the load split between the supports did (section 5).
- **What the valid S1 says.** During a slow press the rod stops supporting the body, the pusher lifts it about 1.1 mm, and the button stalls at 59.1% of its stroke. After release the body sits 16.7 mm further along x than before the press (section 6).
- **Against the physical prototype.** The prototype observation is "the body is sitting on pegs, the body falls down when you press the button". At rest the sim agrees that the body sits on moving parts. During the press the sim only partly agrees (section 7). This is a partial reproduction.

## 2. Root cause of the old invalidity

Sources: `out/mujoco-sim-valid/forensics/forensics.json`, `supplement.json`, `pegs_hold.json`, `depth_vs_time.png`, and the scripts `analyze.py`, `supplement.py`, `extract.py` next to them. No `report.md` was written for the forensics; this section is the narrative.

### 2.1 The penetrations were impact transients

- The old runs used contact `solref` (0.002, 1.0) and `solimp` (0.95, 0.99, 0.001, 0.5, 2.0) (`forensics.json` `contact_model`).
- Within 0.1 s of start, each old case peaked between 0.3316 and 0.7909 mm. Peak times were between 0.003 s and 0.0445 s (`supplement.json` `windowed_all_cases`, "0-0.1s").
- After 0.1 s the peak fell. The maxima in the window from 0.1 s to the end of settle were 0.0068 to 0.0368 mm in six cases (f000, f025, f075, spring_low, spring_high, half_dt), 0.1313 mm in `s0_f050` (t = 0.342 s, crank `peg_pusher_head` vs body `floor_rear`) and 0.0896 mm in `s0_f100` (t = 0.111 s). All are under 0.2 mm.
- In the hold window (3.0 to 3.5 s) the maxima were 0.006485 to 0.007657 mm in all eight cases (`supplement.json`). `pegs_hold.json` gives 0.006487 to 0.007583 mm for its five cases.

| Old case | Peak in 0-0.1 s (mm) | Time (s) | Pair |
|---|---|---|---|
| s0_f000 | 0.3497 | 0.041 | body `floor_front` vs chassis `guide_north` |
| s0_f025 | 0.4465 | 0.044 | body `shim_04_a` vs lip `foot_n` |
| s0_f050 | 0.5919 | 0.004 | crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06` |
| s0_f075 | 0.6392 | 0.003 | crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06` |
| s0_f100 | 0.7909 | 0.011 | crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06` |
| s0_spring_low | 0.4062 | 0.041 | body `floor_front` vs chassis `guide_north` |
| s0_spring_high | 0.3316 | 0.044 | body `shim_04_a` vs lip `foot_n` |
| s0_half_dt | 0.4272 | 0.0445 | body `shim_04_a` vs lip `foot_n` |

Source: `supplement.json` `windowed_all_cases`.

### 2.2 What hit what

- **f = 0 body drop.** The body first touches the pusher `carriage_east` at t = 0.010 s after falling 0.4798 mm at vz = -0.0733 m/s. It reaches the main impact at t = 0.039 s, z = -4.6606 mm, vz = -0.2187 m/s before impact, with the body force peaking at 22.89 N (`forensics.json` `cases.s0_f000.body_motion`). The reset gap from the body to `carriage_east` is 0.4 mm (`supplement.json` `reset_gaps_to_supports_mm`).
- **Front-edge tip.** The body then tips its front edge onto chassis `guide_north` and rod `shaft`. The pre-contact normal speeds are 0.4533 and 0.4854 m/s (`supplement.json` `approach.s0_f000`, `row_onset_minus_1`).
- **Lip foot.** The lip foot corner hits the body shim. Pair `shim_04_a` vs `foot_n` peaks at 0.2677 mm in the forensics rerun of f000 and at 0.4465 mm in f025.
- **f > 0.** The pegs hit the slot walls at t = 0.003 to 0.011 s, with onset normal speeds of 0.6935 m/s (f050) and 0.7397 m/s (f100) (`forensics.json` `pairs[].episode.onset_normal_vel_m_s`). The slot clearance is 0.3 mm (`projects/pocky/docs/physics-m5a.md` "What was run"). The timing and speed are consistent with the preloaded spring releasing at t = 0.

### 2.3 Impact depth follows contact stiffness, not mass

- The soft-contact model predicts a critically damped impact peak of v / (omega e), ignoring mass, gravity and multi-contact coupling (`analyze.py:45-49`). With omega = 479.7980 rad/s (`forensics.json` `contact_model.omega_at_dmin_rad_s`), that is 0.767 mm per m/s. I computed this from `supplement.json` `soft_model_peak_from_pre_contact_speed_mm` divided by speed; it is the same value (0.76674 mm per m/s) for every pair except one `s0_half_dt` pair (0.8258).
- The approach speed that gives a 0.2 mm peak is 0.2608 m/s (`forensics.json` `contact_model.approach_speed_for_0.2mm_impact_m_s`). The observed impact speeds of 0.45 to 0.74 m/s (`supplement.json` pre-contact speeds, `forensics.json` onset speeds) therefore exceed it.
- Observed over predicted is 1.006 and 0.993 for the two largest f000 pairs. Across all pairs in `supplement.json` `approach` it ranges from 0.698 to 3.07, with larger outliers where the sampled speed one row before onset was near zero (26.3 for the f050 peg pairs). The model is a scale, not a fit.
- The hold depth is not a mystery either. For `floor_front` vs `guide_north` the terminal depth is 0.0016967 mm and the soft-equilibrium depth is 0.0016967 mm (`forensics.json` `cases.s0_f000.pairs[0].terminal`). The single-contact full-weight static depth is 0.0021300 mm (`contact_model.single_contact_static_depth_full_weight_mm`).

### 2.4 Why timestep alone did not help

- The old compliance had `tc` = 2 ms and the approved sensitivity halved `dt` from 1 ms to 0.5 ms while keeping `tc` = 2 ms. The peak went up: f000 0.3497 to 0.4272 mm (`out/mujoco-sim-valid/sweep/results.md` rows tc 2 / dt 1 and tc 2 / dt 0.5).
- Peak depth tracks `tc`. The sweep summary: f000 0.35-0.43 / 0.23 / 0.10-0.13 / 0.05-0.06 mm at tc = 2 / 1 / 0.5 / 0.25 ms (`sweep/results.md` "Summary", finding 1).

### 2.5 Checked and ruled out: overconstraint

For the five forensics cases (`s0_f000`, `f025`, `f050`, `f100`, `half_dt`), `solver_niter_max` is 9 to 12, `warnings` is 0, and `rows_with_opposed_deep_contacts` is 0 for both pegs (`forensics.json` `cases.*.peg_squeeze`). Peg squeeze between opposed walls is not the cause.

### 2.6 Model defects found

- **Duplicate overlapping wall colliders.** Pairs report identical depth at the same instant:
  - `pusher_cap_n_06` and `carriage_west` vs `peg_pusher_shaft`: 0.5918751 and 0.5918691 mm at f050; 0.7909118 and 0.7909055 mm at f100.
  - `cap_east_00` and `bar_south` vs `peg_button_shaft`: 0.4002337 and 0.4002325 mm at f050; 0.6465798 and 0.6465511 mm at f100 (`forensics.json` `cases.*.pairs`).
  - In the scene XML, `pusher_cap_n_06` (centre x -0.10765, y 0.043, half-extents 0.00235 by 0.003) and `pusher_cap_s_00` (centre y 0.0343013) sit inside the span of `carriage_west` (centre x -0.10815, y 0.021, half-extents 0.00285 by 0.029) (`out/mujoco-sim-valid/s0/runs/s0v_f000/scene.xml`). The crank `cap_east_00` / `bar_south` overlap was not geometrically re-checked here; the identical depths are the evidence.
- **Shim colliders thinner than the impact depth.** `shim_04_a` has z half-extent 0.0002 m, so it is 0.4 mm thick (`scene.xml`). The old peaks on shim pairs, 0.4465 mm (f025) and 0.4602 mm (f050), exceed that thickness (`forensics.json` pairs).
- **Reset gaps place the peg heads off the body.** Minimum geometric distance from the crank `peg_pusher_head` to the nearest body geom at reset is 4.5416 mm at f000 and 0.19 mm at f100 (`supplement.json` `reset_gaps_to_supports_mm`, computed with `mj_geomDistance` in `supplement.py:106-127`). Other reset gaps: `carriage_east` 0.4 mm, `hook_post_n/s` 0.3 mm, `hook_tooth_n/s` 0.05 mm, and `rod:peg_button_head` 2.2 mm.

## 3. Convergence study and chosen numerics

Sources: `out/mujoco-sim-valid/sweep/results.md`, `results.json`, `results.csv`, `sweep.py`.

### 3.1 Design

- 24 runs, none trimmed: contact and joint-stop time constant `tc` in {2, 1, 0.5, 0.25} ms; `dt` in {tc/2, tc/4}; cases s0_f000, s0_f025, s0_f100.
- Scene: `prototype_assembly` with `contact_timeconst_s` and every joint `stop_timeconst_s` set to `tc`. Only `timestep_s` and `sampling_interval_s` (1 ms) of the frozen scenarios were overridden.
- Peaks are tracked every integration step, not only on sampled rows (`sweep/results.md` header, citing `cadkit/physics/telemetry.py:1017-1021`).

### 3.2 Peak penetration (mm), whole run

| tc (ms) | dt (ms) | f000 | f025 | f100 |
|---|---|---|---|---|
| 2 | 1 | 0.3497 | 0.4465 | 0.7909 |
| 2 | 0.5 | 0.4272 | 0.4589 | 0.5214 |
| 1 | 0.5 | 0.2358 | 0.1951 | 0.3974 |
| 1 | 0.25 | 0.2259 | 0.2594 | 0.4361 |
| 0.5 | 0.25 | 0.1338 | 0.1242 | 0.1906 |
| 0.5 | 0.125 | 0.1047 | 0.1153 | 0.1862 |
| 0.25 | 0.125 | 0.0502 | 0.0650 | 0.1169 |
| 0.25 | 0.0625 | 0.0580 | 0.0707 | 0.0911 |

Source: `sweep/results.md` "Table". Hold-window maxima fall with `tc` from 0.0065 to 0.0076 mm at tc = 2 ms to 0.0001 mm at tc = 0.25 ms (same table).

### 3.3 Convergence findings

- **dt at fixed tc.** Drop and rotation change by at most 2.3% and 2.0% (f100, tc = 2 ms) and by 0.7% or less elsewhere. Nothing is flagged (`sweep/results.md` (2a)).
- **tc.** Drop changes by under 0.5% for f000 and f025 and up to 4.7% for f100 (-4.2530 mm at tc = 2 / dt 1 to -4.4539 mm at tc = 0.5 / dt 0.25). Nothing exceeds 10% ((2b), summary finding 2).
- **Support split.** The split between pusher, chassis and rod is flagged between tc = 2 and tc = 0.25 ms. Example f000 chassis share 36% to 8% and rod share 14% to 43% (rows tc 2 / dt 1 and tc 0.25 / dt 0.0625). Going from tc = 0.5 to tc = 0.25 it moves by at most 0.9 percentage points in any partner for either `dt` rule ((2c)). I read that as converged for tc <= 0.5 ms.
- **Pose and support set.** Drop spread across all 8 grid points is 0.1% (f000), 0.5% (f025) and 5.0% (f100) of the mean ((3), table). The pusher share (48, 49, 50 to 52%) and the lip share (about 2%) never move.
- **Verdicts.** Every grid point still fails `body_pose_retained`, `body_drop`, `body_on_pusher` and `body_on_rod`. The choice of numerics could not change a verdict (`sweep/results.md` finding 1 caveat).

### 3.4 Selection

- **Rule outcome.** The plan's coarsest-passing rule gives tc = 0.5 ms / dt = 0.125 ms: valid for all three cases (peaks 0.1047, 0.1153 and 0.1862 mm). Coarser points are rejected: tc = 0.5 / dt = 0.25 is INCONCLUSIVE for f100 (0.1906 mm, `chassis_grounded` lacks evidence) and tc = 1 ms fails the bound for f000 and f100.
- **Why not take it.** The f100 peak at tc = 0.5 / dt = 0.125 is 0.1862 mm. That is above 0.16 mm, 80% of the 0.2 mm bound, so it sits in the evaluator's 20% near-threshold band (`near_threshold_fraction` 0.2, `projects/pocky/physics/s1_acceptance.json`).
- **Chosen:** tc = 0.25 ms for contact and joint stops, dt = 0.0625 ms (tc/4). Peaks are 0.0580, 0.0707 and 0.0911 mm, so the margin to the bound is at least 2.2x (0.2 / 0.0911). It is inside the converged support-split regime. All three cases are valid (`sweep/results.md`, last three rows).
- **Cost.** Wall time at the chosen point was 86, 87 and 103 s per case (sweep) versus 51, 51 and 56 s at tc = 0.5 / dt = 0.125.
- **This was the orchestrator's decision, not the plan rule's output.** It could not alter any verdict (every grid point gives the same structural FAIL).

## 4. Code changes

All uncommitted in the working tree at the time of writing (`git diff HEAD`). The default scene hash is unchanged at `2c4bd425c55d9f56` (orchestrator-reported; not re-measured here). The committed M5a-1 scenarios, evidence and `s0_acceptance.json` are unchanged.

### 4.1 Generic engine (`cadkit/physics/`)

- **Schema.** New `AssemblySpec` fields `contact_solimp`, `contact_margin_m`, `contact_gap_m`, `noslip_iterations`, `impratio` (`schema.py:477-489`), and per-collider `solimp`, `solref`, `margin` (`schema.py:147-149`). Validators at `schema.py:29-59` and `schema.py:536-568`. A collider `solref` time constant under 2x the timestep is rejected.
- **Scene.** Options are emitted only when set, so existing XML is identical (`scene.py:513-534`, `scene.py:335-342`).
- **Runner.** Declared-vs-compiled checks cover the new solver options and every collider's solimp, solref, margin and gap (`runner.py:398-434`). Resolved inputs record them (`runner.py:239-285`).
- **Replay.** Compiled settings are compared when present in the record (`replay.py:570-600`).

### 4.2 Bug caught by the independent tests

The independent tests caught a defect for a collider with a 3-value `solimp` under a 5-value assembly default. MuJoCo fills the omitted midpoint and power from the inherited default geom, so the declared-vs-compiled check must expect the same tail. The fix takes the tail from the assembly default (`runner.py:349-372`, `_declared_contact_numerics`; the comment at `runner.py:360`). I did not run the failing case myself. The tests that found this are being written by another worker and are not described here.

### 4.3 Replay evidence caps

- The first `s0v_f000` replay attempt failed: `'contacts.csv' exceeds the 536870912-byte evidence budget`, exit 3 (`out/mujoco-sim-valid/s0/logs/replay_s0v_f000.first-attempt.log`). The file is 700,341,836 bytes (`s0/runs/s0v_f000/contacts.csv`).
- Per-file caps now derive from the run's own declared budgets, floored at the old cap and bounded by an 8 GiB ceiling `HARD_EVIDENCE_BYTES` (`replay.py:66-71`, `replay.py:133-158`, bootstrap at `replay.py:236-244`). The final source re-hash uses the same caps (`replay.py:1180-1188`).
- **Cost.** Replay of `s0v_f000` peaked at about 5.2 GiB resident (orchestrator-reported; no measurement file is in `out/mujoco-sim-valid/`).

### 4.4 Pocky (`projects/pocky/`)

- `projects/pocky/physics/options.py:23-33`, `128-149`: `timestep_s` now also allows 6.25e-5 and 3.125e-5 s; new `contact_timeconst_s` and `stop_timeconst_s`, each in {2e-3, 2.5e-4} and at least 2x the timestep; new `button_actuator` boolean. Compliance keys appear in the canonical document only when non-default.
- `projects/pocky/physics/assembly.py:71-75`, `154-156`, `311-316`: `prototype_assembly` takes `contact_timeconst_s`, `stop_timeconst_s`, `button_actuator`; constants `VALID_CONTACT_TIMECONST_S` (2.5e-4), `VALID_TIMESTEP_S` (6.25e-5), `BUTTON_MAX_EFFORT_N` (25.0). The actuator is a bounded force on the `rod_x` slide.
- `projects/pocky/__init__.py:41-42` passes the options through.
- The generic solimp, margin, gap, noslip and impratio knobs exist but no Pocky code sets them.
- **New files:** `projects/pocky/physics/options/s0v_{base,half_dt,spring_low,spring_high}.toml` and `s1_press.toml`; `scenarios/s0v_{f000,f025,f050,f075,f100,half_dt,spring_low,spring_high}.json` and `s1_press.json`; `s1_acceptance.json`. S0v scenarios sample every step (`sampling_interval_s` 6.25e-5). `s1_press.json` samples every 1 ms.

## 5. Valid S0 results

Sources: `out/mujoco-sim-valid/s0/results.md`, `results.json`; old values from `docs/mujoco-m5a-report.md` section 5 (all eight old cases INCONCLUSIVE, invalid). Command per case: `s0/logs/<case>.cmd`; scenario `s0v_*.json`, options `s0v_*.toml`, acceptance `s0_acceptance.json`.

### 5.1 Valid vs old

| Case | New status | New peak pen (mm) | New drop (mm) | Old drop (mm) | New rot (deg, term) | Old rot (deg) | New pose (mm) | Old pose (mm) | New on-pusher / on-rod (s) | Old on-pusher / on-rod (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| f000 | FAIL | 0.0580 | -4.6599 | -4.665 | 2.9600 | 2.959 | 4.76867 | 4.764 | 3.454 / 3.379 | 3.460 / 3.419 |
| f025 | FAIL | 0.0707 | -4.5918 | -4.582 | 3.0075 | 3.015 | 5.23812 | 5.745 | 3.454 / 3.324 | 3.448 / 3.420 |
| f050 | FAIL | 0.1031 | -4.5562 | -4.501 | 3.0322 | 3.074 | 6.06477 | 7.827 | 3.423 / 3.411 | 3.385 / 3.141 |
| f075 | FAIL | 0.1032 | -4.5461 | -4.499 | 3.0388 | 3.077 | 6.16096 | 8.086 | 3.418 / 3.406 | 3.414 / 3.388 |
| f100 | FAIL | 0.0911 | -4.4711 | -4.253 | 3.0907 | 3.237 | 8.67685 | 15.404 | 3.388 / 3.387 | 3.385 / 3.382 |
| spring_low | FAIL | 0.0500 | -4.6600 | -4.664 | 2.9601 | 2.959 | 4.76783 | 4.769 | 3.454 / 3.379 | 3.460 / 3.422 |
| spring_high | FAIL | 0.0518 | -4.6600 | -4.665 | 2.9602 | 2.959 | 4.76750 | 4.764 | 3.454 / 3.371 | 3.460 / 3.415 |
| half_dt | FAIL | 0.0566 | -4.6600 | -4.665 | 2.9598 | 2.959 | 4.76865 | 4.766 | 3.454 / 3.371 | 3.461 / 3.421 |

- New rows: `s0/results.md` (status, peak, hold z terminal, hold rot terminal, durations; pose is `body_pose_retained` converted from m to mm). Old rows: `docs/mujoco-m5a-report.md` section 5 table (peak pen was 0.332 to 0.791 mm, status INCONCLUSIVE, valid "no").
- I did not re-derive that the old "pose" and "rot" columns use the same definitions as the new ones.
- **Pose changed most at high fractions** (f100 15.404 to 8.67685 mm). Drop, rotation and contact durations moved little.

### 5.2 Checks (new)

- FAIL in all eight cases: `body_pose_retained`, `body_drop`, `body_on_pusher`, `body_on_rod`.
- FAIL in f100 only: `chassis_grounded` (0.00353071 rad; old report 0.0041 rad).
- PASS in all eight: `body_on_crank` (0.0145625 s at f100, 0 s elsewhere), `lip_on_pusher`, `lip_on_rod` (at most 0.0001875 s), `lip_on_crank`, `settled_body`, `settled_lip`, `penetration`. In the old table `penetration` was FAIL.

### 5.3 Terminal support forces on the body (N, at t = 3.5 s)

| Case | pusher | rod | chassis | lip | crank |
|---|---|---|---|---|---|
| f000 | 0.6831 | 0.6018 | 0.1065 | 0.0232 | - |
| f025 | 0.6931 | 0.6403 | 0.0567 | 0.0233 | - |
| f050 | 0.6983 | 0.6632 | 0.0289 | 0.0232 | - |
| f075 | 0.6998 | 0.6687 | 0.0220 | 0.0232 | - |
| f100 | 0.7336 | 0.6770 | - | 0.0259 | 0.0268 |
| spring_low | 0.6831 | 0.6016 | 0.1067 | 0.0232 | - |
| spring_high | 0.6831 | 0.6015 | 0.1068 | 0.0231 | - |
| half_dt | 0.6831 | 0.6020 | 0.1063 | 0.0231 | - |

Source: `s0/results.md` "Terminal support forces on body". Old f000 values: pusher 0.683, chassis 0.510, rod 0.198, lip 0.023 N (`docs/mujoco-m5a-report.md` section 5.3). The old chassis share depended on `tc` and had not converged (section 3.3); the valid chassis share is 0.1065 N at f000 and is absent at f100.

Main contacts at f000: pusher `carriage_east` vs body `floor_north_a` 0.6831 N, rod `shaft` vs `floor_front` 0.6018 N, chassis `guide_north` vs `floor_front` 0.1065 N, lip `foot_n` vs `shim_04_a` 0.0232 N.

### 5.4 Replay

`s0v_f000` replays with `reproduced: True`; full state 56001 rows and post-settle continuation 8001 rows both with max abs diff 0.0; events recomputed identically; evaluation differences `[]`; wall 99.799 s (`s0/replay_s0v_f000/replay_report.md`). Source and replay status are both FAIL. The first attempt failed on the evidence cap (section 4.3); the log is `s0/logs/replay_s0v_f000.first-attempt.log`.

## 6. S1 slow press

Sources: `out/mujoco-sim-valid/s1/results.md`, `results.json`, `s1_press.png`, `analyze.py`; run: `projects/pocky/physics/scenarios/s1_press.json` with `options/s1_press.toml` and `s1_acceptance.json`.

Timeline: settle 0-3 s; force ramp on the rod slide 3-5 s (0 to -25 N in 200 phases of 10 ms; negative presses in -X); pressed hold 5-6 s at -25 N; release 6-6.5 s at zero input; final hold 6.5-8 s. Evaluator status FAIL (exit 1); validity `ok=True`; peak penetration 0.1290 mm (every step; crank `peg_pusher_shaft` vs pusher `pusher_cap_n_06`).

### 6.1 Phase table (mean of last 100 ms of each phase)

| phase | rod_x (mm) | pusher_x (mm) | body z rel chassis (mm) | body x rel chassis (mm) | tilt (deg) | total normal on body (N) |
|---|---|---|---|---|---|---|
| settle | 0.101 | -0.500 | -4.660 | -1.007 | 2.960 | 1.415 |
| press | -13.559 | 28.959 | -3.563 | -4.662 | 3.716 | 17.371 |
| press_hold | -13.652 | 29.190 | -3.551 | -4.686 | 3.747 | 24.120 |
| release | 0.101 | 0.670 | -4.132 | -17.732 | 3.335 | 1.410 |
| final_hold | 0.101 | 0.658 | -4.132 | -17.732 | 3.335 | 1.410 |

### 6.2 Normal force on body by partner (N, mean of last 100 ms)

| partner | settle | press | press_hold | release | final_hold |
|---|---|---|---|---|---|
| pusher.carriage | 0.683 | 5.892 | 9.196 | 0.761 | 0.761 |
| pusher.other | 0.000 | 5.789 | 9.085 | 0.000 | 0.000 |
| rod.shaft | 0.602 | 0.000 | 0.000 | 0.000 | 0.000 |
| chassis.guide | 0.106 | 0.000 | 0.000 | 0.627 | 0.628 |
| lip | 0.023 | 5.689 | 5.839 | 0.022 | 0.022 |

The crank and the other rod and chassis groups carry 0.000 N in every phase. Largest geoms at the end of the pressed hold: `pusher/carriage_east` 9.196, `pusher/bullnose` 7.928, `lip/shelf` 4.099, `pusher/neck_south` 1.157 N.

### 6.3 Answers

The three questions are my framing of what S1 was meant to show. `s1_acceptance.json` does not state them.

**(a) Does the rod stop supporting the body once the button moves?** Yes. `rod.shaft` goes from 0.602 N at settle to 0.000 N in the press, and stays 0.000 N through release (`results.md` partner table). The first sample where the body rises more than 0.1 mm is at t = 3.462 s, with the rod at -4.85 mm, 21.0% of full stroke.

**(b) Does the body drop further during the press?** No. The body does not drop more than 0.1 mm below its end-of-settle height at any time (`z_drop_gt_0.1mm: never`). It rises: z goes from -4.660 mm at settle to -3.551 mm in the pressed hold (peak -3.550 mm), a rise of 1.10969 mm (`body_drop_extra_press_hold`). The pusher bullnose and neck drive under the body and the tilt grows from 2.960 to 3.749 deg (maximum at t = 6.000 s). The body x extremes during 3-6 s are -4.687 and 4.235 mm (relative to the chassis; reset pose). The body shifts in x from the first samples (x shift above 0.5 mm at t = 3.277 s, rod at -1.70 mm, 7.3% of stroke).

**(c) What stops the button, and where does the body end up?** The rod stalls at -13.657 mm, 59.1% of the 23.094 mm stroke, with the full 25 N applied (`rod_full_stroke` FAIL, value -0.013657 m). The contacts on the rod in the pressed hold are (N, mean of last 100 ms):

- `rod/peg_button_shaft` from `crank/bar_north`: 6.236
- `rod/peg_button_shaft` from `crank/cap_east_06`: 5.663
- `rod/head_lower` from `lip/nose`: 4.807

The rod spring at that displacement is 500 N/m x (13.657 + 3) mm = 8.33 N (stiffness and 3 mm installed preload from `projects/pocky/physics/assembly.py:271`; the arithmetic is mine). After release the rod returns to within 0.100668 mm (`rod_returned` PASS). The body stays displaced: 16.725 mm further in x than at settle (-1.007 to -17.732 mm), 0.528 mm higher (`body_drop_extra_final` 0.000528259 m, z -4.132 mm) and tilted 3.335 deg. In the final hold it rests on the pusher carriage 0.761 N, chassis `guide_north` 0.628 N and the lip 0.022 N. The lip sits at [-17.788, -1.024, -9.239] mm in chassis axes, against [-0.689, 0.468, -9.234] mm at settle and [-4.916, -0.034, -2.487] mm at the end of the pressed hold.

### 6.4 Evaluator checks (S1)

FAIL: `rod_full_stroke`, `body_drop_total_press_end`, `body_drop_total_press_hold`, `body_drop_extra_press_hold`, `body_drop_total_final`, `body_drop_extra_final`, `body_pose_press_hold` (0.00588434 m), `body_pose_final_hold` (0.0182346 m), `body_on_pusher`, `body_on_rod`. PASS: `rod_returned`, `body_on_crank`, `settled_body`, `effort_bound`, `penetration`. The `body_drop_*` checks use a +/-0.1 mm bound about the initial or settle pose (`s1_acceptance.json`), so a 1.1 mm rise registers as FAIL.

## 7. Simulation vs prototype

The prototype observation, from the user: "the body is sitting on pegs, the body falls down when you press the button."

| Stage | Prototype | Simulation | Verdict |
|---|---|---|---|
| At rest | Body sits on pegs | Body sits on moving parts, not the chassis: pusher carriage 0.6831 N and rod shaft 0.6018 N at f000; the crank peg head carries it only at f100 (0.0268 N) | Agrees in kind |
| During press | Body falls down | Rod support vanishes (0.602 to 0.000 N), but the pusher bullnose and neck drive under the body and lift it about 1.1 mm. No fall below the settle height. The button stalls at 59.1% of stroke | Partly disagrees |
| After release | Not reported | Body is 16.7 mm further along x, 0.528 mm higher, tilted 3.335 deg | No comparison |

Notes on "at rest":

- The sim supports the body on moving parts rather than the chassis, which is the same qualitative state as sitting on pegs. The pegs themselves are not the load path in the sim. At reset the peg heads are 4.5416 mm (f000) to 0.19 mm (f100) below the body (section 2.6; minimum geometric distance, `supplement.json`). Print tolerance on the real part could close that gap, so the sim does not rule out the pegs carrying load on a printed part.
- The sim does lose rod support in the press. That removes one of the two main supports, which is a direction consistent with the prototype's sag, but in the sim the pusher takes over.

Notes on "during press":

- The sim body does not fall further. The button stops at 59.1% stroke, held by `lip/nose` on the rod head (4.807 N), the spring (8.33 N, section 6.3) and the crank reaction on the button peg (6.236 + 5.663 N).
- **This is a partial reproduction.** No parameter was tuned toward the observed failure.

Candidate model gaps (not tested individually):

1. The lip and the body are free bodies with no clip preload.
2. Colliders are rigid and exact, whereas the printed parts have tolerance and flex.
3. Mechanism-to-chassis contacts are filtered by the parent-child relationship, so some contacts a real part would make are not simulated.
4. Friction (`PETG_FRICTION`, 0.4 0.005 0.0001 in the scene XML) and spring values (500 N/m with 3 mm preload) are assumed, not measured.
5. The button is a pure force on the rod slide, not a finger with contact and compliance.

## 8. Design hypotheses (not verified)

These are hypotheses for a design revision. None has been tested in the sim or on a printed part.

1. **The root problem is that nothing seats the body downward on the chassis.** In the valid S0 the chassis guide carries 0.1065 N at f000 and no listed force at f100, so the moving parts carry the body. In S1 at settle the chassis guide carries 0.106 N of 1.415 N total normal force on the body.
2. **The sag puts the lip in the button path.** In the S1 hold the lip nose loads the rod head at 4.807 N and the lip carries 5.839 N of the body force, while the lip sits at [-4.916, -0.034, -2.487] mm in chassis axes. In the final hold it is displaced to [-17.788, -1.024, -9.239] mm.
3. A downward seat or ledge on the chassis, or a retained lip, would be the natural thing to test next. The sim could evaluate that after the geometry is changed.

## 9. Limits and open items

- Physical inputs remain unmeasured: friction, spring rate and preload, damping, clip preload, wrapper behaviour, print tolerance and infill (`projects/pocky/docs/physics-m5a.md` "What this does not say"). FAIL statuses are for this model with assumed inputs.
- The configured OMP reviewer (`docs/mujoco-reviewer-policy.md`) has not reviewed any of this work.
- Plan stages P0 to P3 (single packet to 25 packets, `docs/mujoco-m5a-plan.md` section 5) have not been run. Nothing here says anything about packets.
- The validated numerics are for the no-packet housing. Convergence was run on f000, f025 and f100 only; f050 and f075 ran at the chosen point (S0v) but not across the grid.
- Replay of a validated run needs about 5.2 GiB resident (orchestrator-reported) and the contacts file is 700,341,836 bytes (`s0/runs/s0v_f000/contacts.csv`). The 8 GiB per-file ceiling is a hard-coded constant.
- Contact numerics are validated against penetration, not against measured stiffness. The model is critically damped by construction.
- Evidence directories are git-ignored; nothing here has been committed.
- The tests for the new configurable contact numerics are being written separately and are not covered by this report.

## 10. Evidence index

| Item | Path |
|---|---|
| Forensics data and scripts | `out/mujoco-sim-valid/forensics/` |
| Convergence sweep | `out/mujoco-sim-valid/sweep/results.md`, `results.json`, `results.csv` |
| Valid S0 | `out/mujoco-sim-valid/s0/results.md`, `results.json`, `runs/`, `logs/` |
| S0 replay | `out/mujoco-sim-valid/s0/replay_s0v_f000/` |
| S1 press | `out/mujoco-sim-valid/s1/results.md`, `results.json`, `s1_press.png`, `run/` |
| Old invalid S0 | `docs/mujoco-m5a-report.md` section 5 |
| Project summary | `projects/pocky/docs/physics-m5a.md` |

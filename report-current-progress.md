# Current progress

Date: 2026-10-18. Project: Pocky packet dispenser, inside cadstudio. The plan for the next print is `plan-first-prototype.md`. The older milestone plan is `plan-pockey-dispenser.md`. Where they disagree about the spring and the cycle counts, the first-prototype plan is the one in force.

Nothing has been printed. The CAD for the 10-packet PETG prototype is done and is clear to slice. Packet measurements, the print, the dry cycle, and the bench are not done.

## Where the work stands

| Stage | State | Evidence |
|---|---|---|
| M0 — inputs and mechanism study | Done | `projects/pocky/docs/m0-report.md` |
| M1 — motion proof | Done. Gate A passed | `out/pocky/linkage_motion/gate_a.json` |
| First prototype, step 1 — model | Done. Check report has no FAIL. Sweep passed | `out/pocky/prototype/report.md`, `out/pocky/prototype/gate_a.json` |
| First prototype, step 0 — packet measurements | Not done | Does not block the model. The bench cannot close acceptance criterion 9 without them |
| First prototype, steps 2–4 — print, dry cycle, bench | Not started | No `projects/pocky/docs/prototype-log.md`. That file waits until a print exists |
| Final step — ejection animation | Script written. Every pose passed. Not played here | `projects/pocky/docs/prototype_animation.py`. The OCP CAD Viewer was not running |

## M0

Recorded in `projects/pocky/docs/m0-report.md`. Each item in plan §9 passed there.

- Tooling and the `projects/pocky/` skeleton are in place. The rigid packet is 165 × 55 × 5.2 mm in `projects/pocky/params.toml`.
- The reference linkage is written up in `projects/pocky/docs/reference-notes.md`, with `kinematic-diagram.png`. Meshes from `~/Downloads` are not in the repo.
- The original mechanism is `projects/pocky/docs/mechanism-proposal.md`, checked by `proposal_sweep.py` and drawn in `proposal-diagram.png`.
- `pocky/packet_dummy` builds clean: 5 pass, 0 fail, 0 warn (`out/pocky/packet_dummy/report.md`).

`params.toml` has not been given linkage keys. The crank numbers live next to the model.

## M1

`projects/pocky/geometry/linkage.py` and `projects/pocky/models/linkage_motion.py`. Those files were not edited for the prototype.

The mechanism is a straight pusher driven by a 180° reversing crank. Stroke 50 mm on the face, 23.09 mm on the button, pivot (−78, −8), face 40 × 4.2 mm. `POCKY_POSE` selects 0, 25, 50, 75, or 100 percent of button travel.

Gate A (`projects/pocky/docs/m1_sweep.py`) sampled 21 button positions on the way out and the same 21 on the way back. All 42 passed. Checked builds, both `--render --check --views standard`: 28 pass, 0 fail, 2 warn, 6 info, at pose 0 and at pose 100. The two warns were overhangs in the assembly pose: the rod at 2138.8 mm² and the pusher at 118.5 mm². The prototype print poses are below.

## First prototype, step 1

`projects/pocky/models/prototype.py` builds the body, chassis, lip, two 0.4 mm shims, the spare 0.8 mm shim, the variant-B spring seat, crank, pusher, rod, spring, three pegs, and one dummy. Variants A and C are seat-offset numbers only. They are not solids. One dummy solid is in the model; extra dummies are a slicer count, as is the spare spring.

`UV_NO_SYNC=1 uv run cad build pocky/prototype --render --check --views standard` wrote `out/pocky/prototype/`. Summary: 69 pass, 0 fail, 6 warn, 15 info. Every part is one solid, fits the 360 mm bed, and sits on z = 0 in its print pose. Renders: `out/pocky/prototype/renders/iso.png` and `front.png`.

`projects/pocky/docs/prototype_sweep.py` wrote `out/pocky/prototype/gate_a.json` with status pass. 21 button fractions forward and return, plus the neck sample at φ = 109.5°. Gate B at gaps 5.35, 5.75, 6.15, and 6.55: a 5.2 mm packet misses the lip (overlap 0) and a second packet hits it (about 256 mm³).

`tests/test_pocky_prototype.py`: 4 passed. The spring solid length is 20.4 mm, free length 53.4 mm, installed 50.4 mm. Seat-face offsets are A +2.4, B 0, C −4.8. Peg clearances are 0.6 mm on the sliding slots and 0.4 mm on the pivot bore. The full suite after that was `UV_NO_SYNC=1 uv run pytest tests -q`: 224 passed in 300 s.

The six warns, from `report.md`:

| Part | Warn | What it is |
|---|---|---|
| body | min_wall, minimum ray 0.56 mm, 1st percentile 2.40 mm | The exit wall and the back-notch ceiling are chamfered at 45° so the packet path does not need a support bridge. A few rays at that chamfer are short. The 1st percentile passes. |
| body | overhangs 193.6 mm² | Most of this is the shim ledges, outside the bore. A thin land remains on the exit underside and the notch ceiling. |
| chassis | overhangs 56.8 mm² | About 16 mm² is the two hook catch faces, which are square to −Z. About 41 mm² is the pivot-head seat inside the counterbore. The chassis stays open-top-up. The pivot stays at (−78, −8). |
| lip | overhangs 331.6 mm² | Printed on the separator edge. The remaining area is the shelf and the hook rails, off that edge. Do not file the edge that was on the bed. |
| rod | overhangs 414.1 mm² | Was 2138.8 mm² in the M1 assembly pose. Printed on the shaft's +Y face, long axis on the bed. What remains is the thumb-pad steps. |
| pusher | overhangs 118.5 mm² | The return chamfer, same area as in M1. Bullnose up. |

`min_wall` does not FAIL on any part. The spring's required wall is its 1.2 mm beam. The shim plates are required at 0.4 mm and 0.8 mm. Every other part is required at 2.4 mm. Peg heads are 2.4 mm thick so they pass that check. The plan's 2.0 mm head would sit under 95% of 2.4 mm.

### Geometry that the housing drawing had to absorb

These are in `projects/pocky/geometry/prototype.py`. `linkage.py` is unchanged.

- The button head is full width only below z = −2.6. Above that, the thumb pad stops at y = −36.8, so the exit ledge, the shim, the shelf, and the −Y bar stay clear for the whole stroke.
- The lip shelf stays at z = 0 for every shim. Only the blade and the feet follow the gap. The blade is a 2.4 mm plate whose underside is the gap, with an R0.8 round on the packet-facing corner. The front wall starts at z = 9.20, above the tallest blade.
- The spring pad stays south of the forward lug. A web at rest x [8.456, 12.456] joins the pad to the shaft, 0.4 mm clear of the lug. The south guide is open over that web's travel. Without this, the pad hit the lug around 30% of the stroke.
- The chassis bed is at z = −19.2 so the spring-pocket floor is 2.4 mm thick. The pivot counterbore is open through that bed. The pivot head still seats on the boss.
- The free spring in the assembly render runs 3 mm into the seat. That is the preload, drawn on the free part. The STL is the free spring, 53.4 × 14 × 5 mm. The sweep uses the compressed length, 50.4 mm at rest and about 27.3 mm at full stroke, 6.9 mm above the solid length.
- Peg tips are a 0.5 mm × 45° chamfer cut on the tip edge. Sliding slots are 4.6 mm. The pivot bore is Ø5.4. Grip holes stay at the peg diameter.

## Decided since M1

- The first article is printed PETG only. No steel dowel, heat-set insert, stainless shim, or purchased spring.
- `Resorte.stl` is the reference dispenser's printed serpentine. Its dimensions are not reused. This print uses variant B: 12 beams, 1.2 mm thick, 3.0 mm gap, 53.4 mm free.
- There is no coupon print and no linkage fixture. Spring rate and peg fit are first seen on this unit.
- Dispense stays +X. Stick direction is still unmeasured. If the bench breaks sticks, the next study is +Y.
- Presentation stays 40 mm. The button stays at y = −28.
- The separator target stays 5.75 mm, one 0.4 mm shim on a 5.35 mm ledge.

## Not done

- No STL has been sliced or printed.
- Packet thickness at the centre and at the end seals has not been measured. Neither has fin length or stick direction. Do not change `packet.height` in `params.toml` from a seal measurement.
- `projects/pocky/docs/prototype-log.md` does not exist.
- The ejection cycle is scripted for the OCP CAD Viewer in `projects/pocky/docs/prototype_animation.py`. The pose check passed (`out/pocky/prototype/animation/simulation.json`, 132 frames). The viewer was not running in this session, so the animation has not been played. It is a geometry record. It does not accept the prototype, and it does not count toward the 10 cycles.
- The 25-packet tube, the metal spring, and Gate D (50 and 100 cycles) have not been started.

## Environment

`uv run cad` without `UV_NO_SYNC=1` fails in this environment: uv tries to rebuild the project and cannot resolve hatchling from `https://pypi.apple.com/simple`. `UV_NO_SYNC=1 uv run cad` and `.venv/bin/cad` both run. The documented command is still `uv run cad`. Tests were not changed to hide that.

## Next step

Print the parts in `plan-first-prototype.md` step 2, from `out/pocky/prototype/`. Measure the spring's free length before assembly and confirm 53.4 mm within 0.5 mm. Packet measurements can happen on the bench day. Do not start the dry cycle until the unit is assembled, and do not start the bench until the dry cycle passes.

# M5a plan repair review: one remaining relative-translation defect

Reviewed completed op_0mvj09ue77e6b9f512686938c, turn2, authorized by
dec_0mvj09ctf3fb2adfee3afcedd, run_0mviyq59q90622f804e919ceb.

Independently verified: only the two authorized plan/review documents changed,
no added/removed files or stale hashes;99accepted source hashes remain exact.
Actual configured Opus reviewer follow-ups inspected, transcript hash verified.
Quarter-fraction resets match source; drop lower/upper bounds and explicit every-step
hold/replay recording resolve prior findings. No simulation/tests ran. Durable checks:
out/mujoco-m5a-supervisor-planning/remediation1-boundary.json.

## Remaining demonstrated defect

The revised plan correctly defines instantaneous relative transform inverse(T_a)*T_b,
but its translation CHANGE discards that transform and subtracts WORLD separation
vectors before multiplying by the INITIAL R_a transpose. That is a different metric.
It reports drift for an exactly rigid pair physically rotating together over time.

Counterexample (mm): initially R_a=I, p_a=(0,0,0), p_b=(1,0,0). Both bodies then
physically rotate90deg about world Z, giving R_a=R_z90, p_b=(0,1,0), p_a unchanged.
The true p_rel=R_a^T(p_b-p_a) is (1,0,0) at BOTH times. True relative translation
change is ZERO; the revised plan gives(-1,1,0)mm, norm1.414214mm. A fixed change
of coordinates G applied to the entire trajectory is a different invariance test
and does not catch this time-varying common physical motion.
Raw out/mujoco-m5a-supervisor-planning/rigid-pair-rotation-probe.json.

Correct specification for relative_pose / frame=body_a:

    p_rel(t)=R_a(t)^T*(p_b(t)-p_a(t))
    delta_p=p_rel(current)-p_rel(initial)
    R_rel(t)=R_a(t)^T*R_b(t)

The components use body_a's attached local axes at each time. Local material axes
retain their identity as body_a rotates; freezing its world rotation is incorrect.
The existing orientation-angle metric is acceptable. Keep world-axis drop
separately defined as signed world relative-z change with lower/upper bounds.

## Next bounded plan-only correction

Correct this equation, corresponding frame prose/API semantics, and planned tests.
Explicitly require: (1) common physical translation/rotation varying over time
with constant T_rel produces zero relative_pose drift, (2) superimposed REAL
relative displacement is detected in body_a local axes, (3) fixed coordinate
transform of the whole trajectory leaves relative metrics invariant, and
(4) world-z drop retains its explicit world/gravity semantics and sign cases.
Use the numeric rigid-pair counterexample as a planned regression, not only
a text claim. Obtain configured ordinary reviewer follow-up on THIS formula
and example; retain prior successful fixes and review history.

Only docs/mujoco-m5a-plan.md, docs/mujoco-m5a-plan-review.md and evidence under
out/mujoco-m5a-planning/ may change. No implementation or product/test/harness/
CAD/config/service edits. Return to Codex for approval and separate implementation
admission. No separate planner/model changes/substitution/security-reviewer gate.

Before decision:successor4 uses2/10ops,1/2remediations; cumulative21submitted
ops/8remediations. One REMEDIATE will use second cycle; deadline1792667380525
unchanged. This is concrete progress on a bounded mathematical defect, no renewal.

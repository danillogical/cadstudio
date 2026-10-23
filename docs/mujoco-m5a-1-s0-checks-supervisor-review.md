# Independent S0-check review: corrections required

Operation `op_0mvj62z0p3dcdad31cbfa078c`, successor5
`run_0mvj62atk8b61da9fe2edf2ea`, turn 1. The operation is terminal completed;
this review does **not** accept its implementation yet. Scope remains the
generic S0-check packet, not the Pocky adapter or a product gate.

## Verified progress and boundaries

- Independently ran `uv run --frozen --extra physics pytest
  tests/test_cadkit_physics_*.py -q`: **529 passed, 1 warning in 125.62 s**,
  exit 0. The duplicate `time.npy` warning is the existing adversarial case.
  Supervisor log: `out/mujoco-m5a-supervisor-resume/s0-physics-regressions.log`.
  Full CAD suite remains deferred until final shared M5a-1 changes.
- Inspected all six modified tracked files and the new tests/report. The
  acceptance JSON-schema update is a necessary documentation conformance change
  for the new kinds; it does not change the frozen project criteria. Fresh hash
  comparison of the after-manifest's 204 files has zero mismatches. The six
  differences against its before-manifest are the five authorized physics
  modules plus that schema. No existing test, CAD, params, dependency or project
  physics file changed. The two Supervisor documents were preserved.
- Frozen presentation criteria raw SHA256 remains
  `518a45ffc4592ca602be4c33c59681038e43dedaa15b688312202c3a57ff6ca2`.
- Direct native transcript inspection verifies 59 reviewer assistant messages
  all attributed to `anthropic/claude-opus-5-5`, including final visible approval
  after five earlier fixes. Reviewer transcript SHA256:
  `3a89d4c9953edf2e70096394c65e7a6f168dc518909b7f8e4f72aeff419368ef`.
  This is stronger evidence than the report's configuration-only attribution.
  Separate test-worker transcript has 84 assistant messages, all configured
  `opencode-go/deepseek-v4.1-flash`; hash
  `f8fc9c4bf0034e6131e4e028f70e26b9ad90f5533eb1878b59559adb529b4200`.
  Visible reviewer final text and metadata are retained without internal reasoning
  in `out/mujoco-m5a-supervisor-resume/reviewer-verification.json`.
- Read current human-owned model configuration; it matches prior settings. No
  model/provider/effort/role/fallback mutation or reviewer substitution occurred.
- Independently exercised a real `drop_box` with every-step pose/speed/contact
  watches and replay. Untampered control is PASS, reproduced true. The geometry
  equations and summed-contact implementation have meaningful live coverage;
  exact common-rotation counterexamples remain synthetic in this increment.

## Demonstrated defects

Reproducer: `out/mujoco-m5a-supervisor-resume/probe_s0_checks.py`, run with
`PYTHONPATH=. .venv/bin/python out/mujoco-m5a-supervisor-resume/probe_s0_checks.py`.
Raw source/replay artifacts and `results.json` are under
`out/mujoco-m5a-supervisor-resume/s0-probes/`. Exit 0, all observations below
come from actual generic fixture runs and replay, not prediction.

### R1 — P2: overflowed recorded metrics falsely reproduce as PASS

`cadkit/physics/replay.py:805` compares numeric watch values using
`abs(left-right) > atol + rtol*abs(left)` without a finite-value guard.
An overflowing JSON number `1e999` parses to infinity without invoking the
JSON literal `parse_constant` rejection. With source infinity, both sides of
that comparison become infinity, so it detects no difference from a finite
recomputation.

Copied the valid source, replaced `pose.value` and
`pose.evidence.translation_m` with literal `1e999`, and refreshed only the
manifest's summary byte count/hash using the existing tamper-test pattern.
Replay returns **PASS, reproduced=true, evaluation_comparison.ok=true, no
differences**, despite the recorded infinite measurements. This violates the
explicit fail-closed replay and finite-evidence contracts.

Required repair: reject non-finite watch numbers before tolerance arithmetic,
including exponent overflow, in all relevant derived fields and times. Malformed
recorded or recomputed evidence must never reproduce as PASS. Preserve legitimate
finite value/time tolerances. Add live tampered-record regression coverage for
positive/negative overflow and direct non-finite comparison inputs as appropriate.

### R2 — P2: opt-in threshold band ignores S0 speed/contact gates

`cadkit/physics/evaluate.py:772–819` never applies
`near_threshold_fraction` to contact-duration or max-over-phase body-speed
checks. The implementation/report silently narrows the acceptance-level feature
to relative-pose/translation. The approved plan §5.4 and packet require
near-threshold handling of relevant S0 bounds using worst-over-phase evidence.

Real fixture observations with `near_threshold_fraction=0.2`:

- Speed `0.8825985 m/s`, maximum `0.980665 m/s`: 10% below its limit,
  still **PASS**.
- Summed contact duration `0.290000000 s`, maximum `0.322222222 s`: 10%
  below its limit, still **PASS**.
- The overall run is **PASS**. Both otherwise passing measurements should be
  INCONCLUSIVE under the declared 20% band.

Required repair: consistently apply the opt-in band to S0's body-speed and
contact-duration maxima, with truthful structured bound/band evidence and replay
recomputation. Preserve default-off M4 behavior, zero-bound semantics and true
out-of-bound failure handling. Test enabled and disabled bands on live runs,
including replay of the INCONCLUSIVE result. Do not change numeric product
criteria or introduce an adapter-specific status sidecar.

### R3 — P2: public typed execution writes PASS locks its loader rejects

The file loader rejects prohibited combinations, but the typed path admits them:
`CheckSpec.__post_init__` and `resolve_references` do not enforce all new
kind-specific constraints, and `_select_document_text` emits a canonical document
without checking that its loader accepts it.

Two independent real runs write **PASS** summaries:

1. `relative_translation(frame="world", axis="x")`.
2. `contact_duration(window="max_over_phase")`.

Their same-runtime replay raises `ReplayError` because the saved acceptance lock
rejects respectively world x and the forbidden contact window. Saved summaries
and locks are preserved in `s0-probes/typed-world-x/` and
`s0-probes/typed-contact-window/`. This is a public execution/evidence defect,
not merely an optional constructor nicety.

Required repair: validate typed criteria against the same strict semantics as
loaded criteria before claiming an output directory or writing evidence; either
constructor or execution-boundary enforcement is acceptable. Cover these two
examples and malformed new fields/bounds/units/non-finite values. Valid typed
defaults must still round-trip with identical hashes and replay. Do not rewrite
old tests or weaken document loading to accept forbidden combinations.

## Bounded correction and limits

Authorize ONE remediation of R1–R3 within the original generic packet's file
surface, necessary schema/docs and new independent tests. Reuse configured
ordinary reviewer for follow-up; it must inspect these concrete probes and
repairs, and preserve actual transcript/model evidence. No manual model override
or substitute; required role failure blocks the gate. Run focused tests and
physics regressions, retain negative/control evidence and after-manifest, and
correct the packet report's claims. Do not start the adapter or product runs.

Before decision: successor5 used 1 operation / 0 remediations of 6 / 2,
5 operations / 2 cycles remain, deadline `1792679704903` unchanged. Cumulative
23 submitted bridge operations / 9 remediation cycles. REMEDIATE spends one
cycle, making cumulative remediation usage 10; the next admission will make
submitted operation usage 24. No renewal, no human model/config changes,
no full-plan or physical acceptance.

Recorded exactly one review decision for turn 1 through the bridge:
`REMEDIATE dec_0mvj93wc4ee431c23c04f7fb2`, idempotency key
`cadstudio-m5a1-s0-review-remediate-1`. It authorizes one repair operation;
successor5 now 1 operation / 1 remediation used, 5 operations / 1 cycle remain.
Host was independently ready with no active operation; exact current-chat
bounded-autonomy wakeup binding was reaffirmed. Next request id is
`cadstudio-m5a1-s0-checks-repair-01a1624d-1`. Its operation id and consumption
remain in the bridge for reconciliation on completion. No limits renewed.

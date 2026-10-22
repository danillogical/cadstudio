# M0 supervisor review

Operation: `op_0mvhxylus1ca1c69ec253e707`; supervision run: `run_0mvhxwg5l2aa1ba8e92d0c92f`.

Outcome: architecture inventory accepted after explicit supervisor corrections in architecture review §21. No physical acceptance is claimed. Next authorized increment is M1 only.

Independent evidence: all 69 baseline manifest entries unchanged/missing=0; direct inspection of chassis hooks confirms tooth underside at z +0.05 mm above rib z 0, retaining against lift rather than providing a downward bearing seat. Independent CAD volume/mass probe gives body 0.139432325 kg and chassis 0.102566947 kg. Independently reran the 53 relevant baseline tests with PATH fixed: **53 passed in 20.95 s**. No feature source was edited by M0. Current primary MuJoCo docs confirm assets dictionaries deprecated in favor of MjVfs, headless stepping, and macOS mjpython requirement; uv docs confirm standard PyPI is supported/default. Citations: https://mujoco.readthedocs.io/en/stable/python.html and https://docs.astral.sh/uv/concepts/indexes/.

Found and corrected a material documentary defect: mass formula in review §6 was off by 1000. Actual M0 evidence code and mass table were correct. Corrected canonical design formula and rigid-spring geometry claims; §21 resolves setup, thresholds, fixture distinction, rigid-clip limitations, support-candidate authorization and initial-state handling. Historical packet report hashes refer to the pre-supervisor document revision; new canonical hash follows below.

M0 elapsed ~45 minutes vs requested 20; the run itself remained within its 240-minute ceiling. Next packet must keep tighter implementation/reporting focus and avoid extended exploratory probe proliferation. Do not repeat the entire geometry inventory.

M1 scope: optional solver extra + minimal headless primitive drop, correct units/mass, reproducible scene/report and meaningful negative cases; project index repair and clean no-extra CAD import/CLI verification. No Pocky CAD changes, no speculative full framework, no GUI. Work toward M7 remains active; missing physical trials do not stop independent software progress.

Canonical architecture SHA256 after supervisor correction: `84f826146d4033073087da26ef0bf72f7ab7108d92077fc42e2d05928c46b111`.

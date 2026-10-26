---
name: connect-ide
description: Open cadstudio artifacts (verdicts, reports, renders, physics videos, source lines) in the VS Code window the user is working in, using the `code` CLI. Use when the user asks to show, open, or view something "in VS Code" / "in the editor" / "in the IDE", or after producing a verdict, render or video they will want to look at. Covers where each artifact lives and how to render a run to video first.
---

# connect-ide

Opens files in the user's VS Code window from Claude's shell, with `code -r` (reuse the
current window) and `code -g FILE:LINE` (go to a line).

## Requirements

- `code` must be on the ACC tool allowlist (`~/.claude/apple/tool_allowlist.csv`). Inside the
  ACC process sandbox `code` cannot reach VS Code's main socket: it starts a separate instance
  that quits at once and still exits 0. If the user reports that nothing opened, check that
  `code` is listed. Do not edit the allowlist without the user's explicit go-ahead.
- `VSCODE_IPC_HOOK_CLI` is not needed. Claude's shell does not inherit it, and `code` reaches
  the running app through its main socket instead.
- Detect VS Code with `TERM_PROGRAM=vscode`. If it is not VS Code, print the paths instead of
  calling `code`.

## Commands

Run from the repo root and use repo-relative paths.

```
code -r out/mujoco-syringe/verdict.md                      # open a file in this window
code -g projects/pocky/geometry/syringe.py:250             # jump to a line
code -r out/pocky/syringe/renders/iso.png                  # image preview
code -r out/mujoco-syringe/syringe_top.mp4                 # built-in video player
code -r --diff a.json b.json                               # side-by-side diff
```

`code` exits 0 even when nothing opened, so a zero exit is not confirmation. Say what you opened
and let the user say if it did not appear.

## Where things are

| What | Path |
|---|---|
| CAD check report | `out/pocky/<model>/report.md` |
| CAD renders | `out/pocky/<model>/renders/{iso,front,top,back}.png`, `<part>_print.png` |
| Physics run summary / report | `<run>/summary.json`, `<run>/report.md` |
| Dispense verdicts | `out/mujoco-dispense*/verdict.md`, `out/mujoco-syringe/verdict.md` |
| Physics videos | next to the run, e.g. `out/mujoco-syringe/*.mp4` |
| Validity / numerics write-up | `docs/mujoco-sim-valid-report.md` |
| Redesign mockups | `projects/pocky/docs/mockups/README.md`, `*.png` |
| Pass/fail commands | `projects/pocky/README.md` ("Dispense pass/fail") |

A run directory is anything containing `summary.json` and `states.npz`. Find recent ones with
`ls -td out/*/run* out/*/runs/* 2>/dev/null | head`.

## Showing a physics run

Default to the interactive viewer, not video; the user prefers it. Launch it yourself as a
background command (it re-execs under mjpython and opens a native window on the user's
screen; it runs until they close the window):

```
uv run --frozen --extra physics python projects/pocky/preview.py RUN_DIR --transparent housing
```

Keys: space pause, left/right step while paused, `[` / `]` speed, `r` restart.

Render a video only when asked for one, for example to share. Render it, then open it:

```
uv run --frozen --extra physics python projects/pocky/preview.py RUN_DIR \
  --video RUN_DIR/../preview.mp4 --start 2.9 --end 8.0 --transparent housing --force-scale 0.3
code -r RUN_DIR/../preview.mp4
```

- `--video` refuses paths inside the run dir, so write it next to the run.
- `--transparent body,lip` is for the prototype; use `--transparent housing` for the syringe.
- Add `--elevation -70 --azimuth 90` for a top view.

## Later: the cadstudio extension

When the cadstudio VS Code extension exists, prefer its URI routes so the GUI panels open:

```
code --open-url "vscode://danillogical.cadstudio/viewer?run=out/mujoco-syringe/run_clamped"
```

Until that extension is installed these URLs do nothing, so use the file commands above.

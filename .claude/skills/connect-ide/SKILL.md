---
name: connect-ide
description: Open cadstudio artifacts (verdicts, reports, renders, physics videos, source lines) in the VS Code window the user is working in, using the `code` CLI. Use when the user asks to show, open, or view something "in VS Code" / "in the editor" / "in the IDE", or after producing a verdict, render or video they will want to look at. Covers where each artifact lives and how to render a run to video first.
---

# connect-ide

Opens files in the user's VS Code window from an agent's shell, with `code -r` (reuse the
current window) and `code -g FILE:LINE` (go to a line).

To show a **model or a physics run**, prefer the GUI:
`uv run --frozen --extra physics cad gui open <project>/<model>` or
`... cad gui open --run RUN_DIR` (the `cadstudio` skill covers it, its JSON and exit codes).
It opens the CADStudio panel in this window, or falls back to a browser and says why.
Use the `code` commands below for files: reports, verdicts, renders, videos and source lines.

## Requirements

- `code` must be reachable from your shell sandbox (on your sandbox's tool allowlist, if it has one).
  Inside a restrictive sandbox `code` cannot reach VS Code's main socket: it starts a separate
  instance that quits at once and still exits 0. If the user reports that nothing opened, check
  that `code` is allowed. Do not change sandbox or allowlist settings without the user's explicit go-ahead.
- `VSCODE_IPC_HOOK_CLI` is not needed. An agent's shell may not inherit it, and `code` reaches
  the running app through its main socket instead.
- Detect VS Code with `TERM_PROGRAM=vscode`. If it is not VS Code, print the paths instead of
  calling `code`.

## Commands

Run from the repo root and use repo-relative paths.

```
code -r out/starter/box/report.md                          # open a file in this window
code -g projects/starter/models/box.py:20                  # jump to a line
code -r out/starter/box/renders/iso.png                    # image preview
code -r out/<run>/preview.mp4                              # built-in video player
code -r --diff a.json b.json                               # side-by-side diff
```

`code` exits 0 even when nothing opened, so a zero exit is not confirmation. Say what you opened
and let the user say if it did not appear.

## Where things are

| What | Path |
|---|---|
| CAD check report | `out/<project>/<model>/report.md` |
| CAD renders | `out/<project>/<model>/renders/{iso,front,top,back}.png`, `<part>_print.png` |
| Physics run summary / report | `<run>/summary.json`, `<run>/report.md` |
| Physics videos | next to the run, e.g. `out/<run>/*.mp4` |
| Project docs and pass/fail commands | `projects/<project>/README.md`, if the project has one |

A run directory is anything containing `summary.json` and `states.npz`. Find recent ones with
`ls -td out/*/run* out/*/runs/* 2>/dev/null | head`.

## Showing a physics run

Prefer `cad gui open --run RUN_DIR` (above). When a project ships its own native MuJoCo viewer or
video renderer (check `projects/<project>/README.md`), use that when the user asks for it or the GUI
cannot open. Launch an interactive viewer as a background command so it does not block. Render a
video only when asked for one, and write it next to the run, not inside it, then open it with
`code -r`.

## The cadstudio extension

Don't call `code --open-url "vscode://danillogical.cadstudio/..."` by hand. `cad gui open`
builds that URI with a one-time request id and waits for the extension's acknowledgement,
which is the only reliable sign that the panel opened.

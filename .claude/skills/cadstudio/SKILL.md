---
name: cadstudio
description: Drive the cadstudio GUI through the `cad` CLI. Open a model or a physics run in the CADStudio VS Code panel (or a browser), list models, check the toolchain, export a run's trajectory. Use when the user asks to open, show or view a model, assembly or physics run "in the GUI" or "in CADStudio", e.g. "open the GUI for pocky/syringe".
---

# cadstudio

Everything goes through the `cad` CLI, run from the repo root. For opening report, render or video files instead, use the `connect-ide` skill.

## Commands

```
uv run --frozen cad doctor --json                     # toolchain, ui/dist and extension build present
uv run --frozen cad list --json                       # projects and <project>/<model> names
uv run --frozen --extra physics cad gui open pocky/syringe --json
uv run --frozen --extra physics cad gui open --run out/mujoco-two-cycle/wedge_clamped --json
uv run --frozen --extra physics cad gui trajectory RUN_DIR --json   # export <run>.gui/ for playback
```

- `cad gui open [<model> | --run RUN_DIR] [--editor auto|vscode|browser] [--no-open] [--json]`.
- With `--editor auto` (the default), VS Code is used when the command runs in its terminal (`TERM_PROGRAM=vscode`) and `code` is on PATH. Otherwise, or with no acknowledgement within 10 s, the browser opens instead.
- `--no-open` opens nothing and only prints the URL.
- If no GUI service is running, the command starts one and leaves it running. Its log is `out/.gui/service.log`.

## Reading the result

The JSON has `opened` (`"vscode"`, `"browser"` or `null`), `reason` (why it fell back or failed), `requestId`, `service` and `url`.

The `url` holds the session token, so don't paste it into chat unless the user asks for it.

Report what `opened` says. Say "opened in VS Code" only when `opened` is `"vscode"`. With `"browser"`, also quote `reason`.

| Exit | Meaning |
|---|---|
| 0 | Opened: VS Code acknowledged, the browser launched, or `--no-open` |
| 1 | The GUI service failed to start or answer (stderr has the log tail) |
| 2 | Bad arguments, an unknown model, or not a run directory |
| 3 | Not opened: no acknowledgement from VS Code with `--editor vscode` (extension missing, untrusted workspace, or another window got it), or the browser launch failed |

## Sandbox (Claude Code)

- Starting the service binds a loopback port, which the ACC sandbox blocks. The error ends in `PermissionError: [Errno 1] Operation not permitted`. After one such failure, rerun the same command with `dangerouslyDisableSandbox: true`, or ask the user to run it in their terminal. Later opens reuse the running service.
- `code` must be on the ACC tool allowlist (`~/.claude/apple/tool_allowlist.csv`). Without it, `code --open-url` reaches no window, so the command ends in exit 3 or a browser fallback. Do not edit the allowlist without the user's go-ahead.

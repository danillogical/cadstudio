---
name: cadstudio
description: Build, check, render and view CAD models and physics runs in cadstudio with the `cad` CLI. Use when the user asks to build, check, render, tweak or open a model or assembly (e.g. "build starter/box", "does it pass the checks", "show it in the GUI"), run or view a physics simulation, or diagnose the cadstudio toolchain.
---

# cadstudio

Everything goes through the `cad` CLI (`uv run cad ...`), run from the workspace root: the directory that holds `projects/`. Model outputs land in `<workspace>/projects/<project>/out/<model>/`, and physics runs in `projects/<project>/out/<model>/runs/`. For opening report, render or video files instead, use the `connect-ide` skill. `AGENTS.md` has the full command list and check definitions.

## Build, check, render

```
uv run --frozen cad list --json                                   # <project>/<model> names
uv run --frozen cad build starter/box --render --check --views standard
uv run --frozen cad check starter/hinge                           # checks only; exit 1 on FAIL
uv run --frozen cad build starter/box --check --set box.wall=3 --out /tmp/box-try   # scratch experiment
```

1. Edit `projects/<project>/params.toml` or `projects/<project>/models/*.py`.
2. Build with `--render --check --views standard` (the default `--views all` is slow).
3. Read `projects/<project>/out/<model>/report.md` (FAIL/WARN rows first), then the PNGs in `projects/<project>/out/<model>/renders/`: `iso.png`, `front.png`, `back.png`, `top.png` and `<part>_print.png`.
4. Renders in `projects/<project>/out/<model>/renders/` are not cleared between runs; check `ls -lt` timestamps before trusting a `section_*` or `detail_*` file.
5. Never say a geometry change works without having read the report and at least one render.

`--part NAME --check` overwrites `report.md` with a one-part report, so pair `--part` with `--out`.

## Open in the GUI

```
uv run --frozen --extra physics cad gui open starter/hinge --json
uv run --frozen --extra physics cad gui open --run projects/starter/out/hinge/runs/<run> --json
```

- `cad gui open [<model> | --run RUN_DIR] [--editor auto|vscode|browser] [--no-open] [--json]`.
- `--run` takes a run dir relative to the cwd or the workspace, inside `projects/*/out/` or `.cadstudio/fixtures/`.
- With `--editor auto` (the default), VS Code is used when the command runs in its terminal (`TERM_PROGRAM=vscode`) and `code` is on PATH. Otherwise, or with no acknowledgement within 10 s, the browser opens instead.
- `--no-open` opens nothing and only prints the URL.
- If no GUI service is running, the command starts one and leaves it running. Its log is `.cadstudio/gui/service.log`.

### Reading the result

The JSON has `opened` (`"vscode"`, `"browser"` or `null`), `reason` (why it fell back or failed), `requestId`, `service` and `url`.

The `url` holds the session token, so don't paste it into chat unless the user asks for it.

Report what `opened` says. Say "opened in VS Code" only when `opened` is `"vscode"`. With `"browser"`, also quote `reason`.

| Exit | Meaning |
|---|---|
| 0 | Opened: VS Code acknowledged, the browser launched, or `--no-open` |
| 1 | The GUI service failed to start or answer (stderr has the log tail) |
| 2 | Bad arguments, an unknown model, or not a run directory |
| 3 | Not opened: no acknowledgement from VS Code with `--editor vscode` (extension missing, untrusted workspace, or another window got it), or the browser launch failed |

## Live monitoring

Open the panel once with `cad gui open <model>`. After that, run builds and sims as usual: with Follow on (the default), the panel follows them. Build with `--scene` so a scene is written (`cad build starter/hinge --check --scene`); edits to the model's sources rebuild it, and a `cad physics run` streams into the panel while it steps (`--no-live` skips the stream).

Don't re-run `cad gui open` for each change. Each call reveals the panel again.

## Physics runs

Physics is an optional extra, so pass `--extra physics`:

```
uv run --frozen --extra physics cad physics smoke
uv run --frozen --extra physics cad physics run <project>/<model> --scenario S --acceptance A
uv run --frozen --extra physics cad gui trajectory RUN_DIR --json   # export <run>.gui/ for playback
```

A run directory holds `summary.json` and `report.md`. Read the summary and report before claiming a result. Exit codes of `cad physics`: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 ERROR (usage errors included). Scenarios and acceptance files come from the project that defines them.

## Toolchain

```
uv run --frozen cad doctor --json   # Python, uv, build123d, MuJoCo, node/npm, out dir, ui/dist and extension builds
```

If a command fails oddly, run `doctor` first, then `./setup.sh` from the engine checkout.

## Sandboxes

A sandboxed shell may block binding or connecting to loopback ports. If starting the service fails with `Operation not permitted`, rerun the command once outside the sandbox (or ask the user to run it). Later opens reuse the running service. `code` must also be reachable from the sandbox, or `code --open-url` reaches no window and the command ends in exit 3 or a browser fallback. Don't change sandbox or allowlist settings without the user's go-ahead.

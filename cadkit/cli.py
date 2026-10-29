"""``cad`` command line: list / build / render / check / doctor / gui ``<project>/<model>``."""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
from pathlib import Path

from .checks import format_report, has_failures, run_checks, write_report
from .export import export_assembly, export_part
from .params import override
from .project import Project, all_models, discover, list_models, load_model, resolve
from .workspace import WorkspaceError, default_run_dir, fixtures_root, model_out


# Local copy so the argparse hook can use it without importing the physics package.
EXIT_CODES_PHYSICS = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "ERROR": 3}

VIEW_SETS = ("standard", "detail", "sections", "all")  # mirrors cadkit.render; render is imported lazily


def _parse_sets(items: list[str] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items or []:
        key, eq, val = item.partition("=")
        if not eq:
            raise SystemExit(f"--set expects key=value, got {item!r}")
        try:
            out[key] = float(val)
        except ValueError:
            out[key] = val  # type: ignore[assignment]  # string fields, e.g. material.name
    return out


def _resolve(args) -> tuple[Project, str]:
    try:
        return resolve(args.model)
    except KeyError as e:
        raise SystemExit(str(e.args[0]))


def _load(args, project: Project):
    p = project.load_params(Path(args.params) if args.params else project.params_path)
    sets = _parse_sets(args.set)
    if sets:
        try:
            p = override(p, sets)
        except KeyError as e:
            raise SystemExit(f"unknown parameter {e}")
    return p


def _build_parts(args, project: Project, model: str, p):
    parts = load_model(project, model).build(p)
    part_name = getattr(args, "part", None)
    if part_name:
        if part_name not in parts:
            raise SystemExit(f"no part {part_name!r}; parts: {', '.join(parts)}")
        parts = {part_name: parts[part_name]}
    return parts


def _outdir(args, project: Project, model: str) -> Path:
    return Path(args.out) if args.out else model_out(project.name, model)


@contextlib.contextmanager
def _stdout_to_stderr():
    """JSON mode: send all progress (Python and native, e.g. OCCT) to stderr so stdout is one document."""
    sys.stdout.flush()
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


def _finite(value: float | None) -> float | None:
    """Coerce to a JSON-safe float; NaN and infinities are not valid JSON, so report null."""
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _emit_json(doc) -> None:
    """Print the one JSON document on stdout; call only with the stdout guard released."""
    print(json.dumps(doc, indent=2, allow_nan=False))


def _run_and_report(parts, p, project: Project, outdir) -> tuple[dict, dict[str, Path]]:
    results = {n: run_checks(n, mp, p, project) for n, mp in parts.items()}
    report = write_report(results, outdir)
    print(format_report(results))
    return results, report


def _checks_json(results: dict) -> dict:
    return {n: [{"name": r.name, "status": r.status, "detail": r.detail, "value": _finite(r.value)}
                for r in rs] for n, rs in results.items()}


def _do_checks(parts, p, project: Project, outdir) -> int:
    results, _ = _run_and_report(parts, p, project, outdir)
    return 1 if has_failures(results) else 0


def _do_render(parts, p, project: Project, outdir, views: str = "all") -> list[Path]:
    from .render import render_model, render_part
    written = render_model(parts, p, outdir, project, views)
    if views in ("standard", "all"):
        for n, mp in parts.items():
            written[f"{n}_print.png"] = render_part(n, mp, outdir)
    for path in written.values():
        print(f"wrote {path}")
    return list(written.values())


def cmd_list(args) -> int:
    if not args.json:
        for name in all_models():
            print(name)
        return 0
    with _stdout_to_stderr():
        projects = [{"name": proj.name, "params_path": str(proj.params_path),
                     "models": list_models(proj)} for proj in discover().values()]
        models = all_models()
    _emit_json({"projects": projects, "models": models})
    return 0


def _build(args) -> dict:
    """Resolve, export, and optionally render/check one model, printing progress as it goes."""
    project, model = _resolve(args)
    p = _load(args, project)
    parts = _build_parts(args, project, model, p)
    outdir = _outdir(args, project, model)
    written: list[Path] = []
    for n, mp in parts.items():
        for path in export_part(n, mp, outdir).values():
            written.append(path)
            print(f"wrote {path}")
    assembly = export_assembly(parts, outdir)
    written.append(assembly)
    print(f"wrote {assembly}")
    if args.render:
        written.extend(_do_render(parts, p, project, outdir, args.views))
    results, report = _run_and_report(parts, p, project, outdir) if args.check else (None, None)
    scene = None
    if args.scene and not (results is not None and has_failures(results)):
        scene = _write_build_scene(args, project, model, outdir)
    return {"project": project, "model": model, "outdir": outdir, "written": written,
            "results": results, "report": report, "scene": scene}


def _write_build_scene(args, project: Project, model: str, outdir: Path) -> Path:
    """Write the GUI scene to ``<outdir>/scene`` for ``cad build --scene``."""
    # Function-local import: cadkit core must not import cadkit.gui at module load.
    from .gui.scene import SceneError, write_scene

    try:
        state = write_scene(f"{project.name}/{model}", params_path=args.params,
                            sets=_parse_sets(args.set), out=outdir / "scene")
    except (SceneError, OSError) as exc:
        raise SystemExit(f"scene export failed: {exc}") from None
    print(f"wrote {state['scene']}")
    return Path(state["scene"])


def cmd_build(args) -> int:
    try:
        if args.json:
            with _stdout_to_stderr():
                state = _build(args)
        else:
            state = _build(args)
    except SystemExit as exc:
        if not args.json or not isinstance(exc.code, str):
            raise
        print(exc.code, file=sys.stderr)
        _emit_json({"model": args.model, "error": exc.code, "exit_code": 1})
        return 1

    results = state["results"]
    code = 1 if results is not None and has_failures(results) else 0
    if not args.json:
        return code
    _emit_json({
        "model": f"{state['project'].name}/{state['model']}",
        "outdir": str(state["outdir"]),
        "written": [str(path) for path in state["written"]],
        "checks": _checks_json(results) if results is not None else None,
        "report": {k: str(v) for k, v in state["report"].items()} if state["report"] else None,
        "scene": str(state["scene"]) if state["scene"] else None,
        "exit_code": code,
    })
    return code


def cmd_render(args) -> int:
    project, model = _resolve(args)
    p = _load(args, project)
    _do_render(_build_parts(args, project, model, p), p, project, _outdir(args, project, model), args.views)
    return 0


def cmd_check(args) -> int:
    project, model = _resolve(args)
    p = _load(args, project)
    return _do_checks(_build_parts(args, project, model, p), p, project, _outdir(args, project, model))


def cmd_doctor(args) -> int:
    """``cad doctor``: report the local toolchain; imports lazily to keep the CLI light."""
    from .doctor import collect, format_text

    if args.json:
        with _stdout_to_stderr():
            report = collect()
        _emit_json(report)
    else:
        report = collect()
        print(format_text(report))
    return 0 if report["ok"] else 1


def _gui_scene(args) -> int:
    # Function-local import: cadkit core must not import cadkit.gui at module load.
    from .gui.scene import SceneError, write_scene

    try:
        sets = _parse_sets(args.set)
        if args.json:
            with _stdout_to_stderr():
                state = write_scene(args.model, params_path=args.params, sets=sets, out=args.out)
        else:
            state = write_scene(args.model, params_path=args.params, sets=sets, out=args.out)
    except (SceneError, OSError, SystemExit) as exc:
        msg = str(exc.code) if isinstance(exc, SystemExit) else str(exc)
        print(msg, file=sys.stderr)
        if args.json:
            _emit_json({"model": args.model, "error": msg, "exit_code": 1})
        return 1

    if not args.json:
        for path in state["written"]:
            print(f"wrote {path}")
        return 0
    _emit_json({
        "model": f"{state['project']}/{state['model']}",
        "outdir": str(state["outdir"]),
        "scene": str(state["scene"]),
        "parts": state["parts"],
        "written": [str(path) for path in state["written"]],
        "exit_code": 0,
    })
    return 0


def _gui_trajectory(args) -> int:
    # Function-local imports: cadkit core must not import cadkit.gui or mujoco at module load.
    from .gui.trajectory import write_trajectory
    from .physics import PhysicsUnavailable

    try:
        if args.json:
            with _stdout_to_stderr():
                state = write_trajectory(args.run_dir, fps=args.fps, contacts=args.contacts)
        else:
            state = write_trajectory(args.run_dir, fps=args.fps, contacts=args.contacts)
    except (ValueError, OSError, PhysicsUnavailable) as exc:
        msg = str(exc)
        print(msg, file=sys.stderr)
        if args.json:
            _emit_json({"run": args.run_dir, "error": msg, "exit_code": 1})
        return 1

    if not args.json:
        for path in state["written"]:
            print(f"wrote {path}")
        return 0
    _emit_json({
        "run": state["run"],
        "outdir": str(state["outdir"]),
        "trajectory": str(state["trajectory"]),
        "frameCount": state["frameCount"],
        "bodies": state["bodies"],
        "written": [str(path) for path in state["written"]],
        "exit_code": 0,
    })
    return 0


def cmd_gui(args) -> int:
    """``cad gui <verb>``: artifacts for the browser UI; imports are lazy."""
    if args.verb == "scene":
        return _gui_scene(args)
    if args.verb == "trajectory":
        return _gui_trajectory(args)
    if args.verb == "serve":
        # Function-local import: cadkit core must not import http.server at module load.
        from .gui.server import run

        return run(port=args.port, open_browser=not args.no_browser, as_json=args.json)
    if args.verb == "open":
        from .gui import opener

        return opener.run(model=args.model, run_dir=args.run_dir, editor=args.editor,
                          no_open=args.no_open, as_json=args.json)
    raise SystemExit(f"unknown gui verb {args.verb!r}")


def cmd_physics(args) -> int:
    """``cad physics <verb>``. Imports are lazy so CAD commands never need MuJoCo."""
    from .physics import EXIT_CODES, PhysicsUnavailable

    if args.verb == "smoke":
        from pathlib import Path

        from .physics.gravity_drop import DropSpec
        from .physics.run import run_smoke

        try:
            spec = DropSpec(
                edge_mm=args.edge_mm,
                density_g_cm3=args.density,
                clearance_mm=args.clearance,
                timestep_s=args.timestep,
                duration_s=args.duration,
                gravity_m_s2=args.gravity,
            )
            result = run_smoke(Path(args.out) if args.out else None, spec)
        except ValueError as exc:
            print(f"physics smoke: invalid input: {exc}", file=sys.stderr)
            print(json_status("ERROR", "gravity_drop", f"invalid input: {exc}"))
            return EXIT_CODES["ERROR"]
        except PhysicsUnavailable as exc:
            print(f"physics smoke: {exc}", file=sys.stderr)
            print(json_status("ERROR", "gravity_drop", str(exc)))
            return EXIT_CODES["ERROR"]
        except OSError as exc:
            # Unwritable --out, full disk, permission denied: still machine-readable.
            print(f"physics smoke: could not write artifacts: {exc}", file=sys.stderr)
            print(json_status("ERROR", "gravity_drop", f"could not write artifacts: {exc}"))
            return EXIT_CODES["ERROR"]
        if result.status == "ERROR" and result.detail:
            # Actionable message on stderr; the machine-readable status goes to stdout.
            print(f"physics smoke: {result.detail}", file=sys.stderr)
        print(json_status(result.status, result.scenario, result.detail))
        for name, path in result.artifacts.items():
            print(f"wrote {name}: {path}")
        return result.exit_code

    if args.verb == "export":
        return _physics_export(args)

    if args.verb == "fixture":
        return _physics_fixture(args)

    if args.verb == "channel":
        return _physics_channel(args)

    if args.verb == "mechanics":
        return _physics_mechanics(args)

    if args.verb == "scenario":
        return _physics_scenario(args)

    if args.verb == "replay":
        return _physics_replay(args)

    if args.verb == "run":
        return _physics_run(args)

    print(f"physics: unknown verb {args.verb!r}", file=sys.stderr)
    print(json_status("ERROR", "cli", f"unknown physics verb {args.verb!r}"))
    return EXIT_CODES["ERROR"]


def _physics_export(args) -> int:
    """``cad physics export <project>/<model>``: emit and compile a model's scene."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.scene import SceneInvalid, export_scene

    scenario = getattr(args, "model", None) or "export"
    try:
        project, model = _resolve(args)
        p = _load(args, project)
        hook = getattr(project, "physics", None)
        if hook is None:
            detail = (
                f"project {project.name!r} has no physics assembly; declare "
                f"Project.physics(model_name, params) in projects/{project.name}/__init__.py"
            )
            print(f"physics export: {detail}", file=sys.stderr)
            print(json_status("ERROR", scenario, detail))
            return EXIT_CODES["ERROR"]
        spec = hook(model, p)
        if spec is None:
            detail = (f"model {project.name}/{model} has no physics assembly; the project's "
                      f"physics hook returned None for this model")
            print(f"physics export: {detail}", file=sys.stderr)
            print(json_status("ERROR", scenario, detail))
            return EXIT_CODES["ERROR"]
        outdir = Path(args.out) if args.out else _physics_outdir(project, model)
        result = export_scene(spec, outdir)
    except KeyError as exc:
        print(f"physics export: {exc.args[0]}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc.args[0])))
        return EXIT_CODES["ERROR"]
    except SystemExit:
        # _resolve raises SystemExit for an unknown model; that is a usage/selection error.
        print(json_status("ERROR", scenario, "unknown project or model"))
        return EXIT_CODES["ERROR"]
    except SceneInvalid as exc:
        print(f"physics export: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc)))
        return EXIT_CODES["ERROR"]
    except ValueError as exc:
        print(f"physics export: invalid scene: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, f"invalid scene: {exc}"))
        return EXIT_CODES["ERROR"]
    except PhysicsUnavailable as exc:
        print(f"physics export: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc)))
        return EXIT_CODES["ERROR"]
    except OSError as exc:
        print(f"physics export: could not write artifacts: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, f"could not write artifacts: {exc}"))
        return EXIT_CODES["ERROR"]

    print(json_status("PASS", spec.name, f"scene {result.scene_hash[:16]}"))
    print(f"wrote scene: {result.scene_xml}")
    if result.report_json is not None:
        print(f"wrote report: {result.report_json}")
    for name in sorted(result.asset_hashes):
        print(f"wrote asset: {result.outdir / name}")
    return EXIT_CODES["PASS"]


def _physics_fixture(args) -> int:
    """``cad physics fixture``: export the built-in generic asymmetric assembly."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.fixtures import fixture_assembly
    from .physics.scene import SceneInvalid, export_scene

    try:
        spec = fixture_assembly()
        outdir = Path(args.out) if args.out else _fixture_outdir()
        result = export_scene(spec, outdir)
    except (SceneInvalid, ValueError, OSError) as exc:
        print(f"physics fixture: {exc}", file=sys.stderr)
        print(json_status("ERROR", "m2a_asymmetric_fixture", str(exc)))
        return EXIT_CODES["ERROR"]
    except PhysicsUnavailable as exc:
        print(f"physics fixture: {exc}", file=sys.stderr)
        print(json_status("ERROR", "m2a_asymmetric_fixture", str(exc)))
        return EXIT_CODES["ERROR"]

    print(json_status("PASS", spec.name, f"scene {result.scene_hash[:16]}"))
    print(f"wrote scene: {result.scene_xml}")
    if result.report_json is not None:
        print(f"wrote report: {result.report_json}")
    for body in result.bodies:
        print(f"body {body.body_id}: mass {body.mass_kg:.6g} kg, "
              f"colliders {body.n_colliders}, visuals {body.n_visual_meshes}")
    return EXIT_CODES["PASS"]


def _physics_channel(args) -> int:
    """``cad physics channel``: hollow-channel fidelity evidence (validation + live passage)."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.hollow_run import run_channel_evidence
    from .physics.scene import SceneInvalid

    scenario = "m2b_channel_passage"
    try:
        outdir = Path(args.out) if args.out else None  # runner mints a run-id directory
        summary = run_channel_evidence(outdir)
    except SceneInvalid as exc:
        print(f"physics channel: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc)))
        return EXIT_CODES["ERROR"]
    except PhysicsUnavailable as exc:
        print(f"physics channel: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc)))
        return EXIT_CODES["ERROR"]
    except (ValueError, OSError) as exc:
        print(f"physics channel: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc)))
        return EXIT_CODES["ERROR"]

    status = summary["status"]
    outdir = Path(summary["run_dir"])
    print(json_status(status, scenario, f"scene {summary['scene_hash'][:16]}"))
    pos, neg = summary["positive"], summary["negative_mesh_diagnostic"]
    crit = summary["criterion"]
    print(f"positive: crossed exit at x {crit['exit_plane_x_mm']:.1f} mm "
          f"(max x {pos['max_x_mm']:.1f}), z dev {pos['height_deviation_mm']}, "
          f"contact depth {pos['max_contact_depth_mm']:.3f} mm")
    print(f"concave-mesh diagnostic: initial penetration "
          f"{neg['initial_penetration_mm']:.3f} mm, z dev {neg['height_deviation_mm']}, "
          f"passed {neg['passed']}")
    for name, rel in summary["artifacts"].items():
        print(f"wrote {name}: {outdir / rel}")
    return EXIT_CODES[status]


def _physics_mechanics(args) -> int:
    """``cad physics mechanics``: loaded-spring return and hinge-period evidence."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.mechanics_run import run_mechanics
    from .physics.scene import SceneInvalid

    scenario = "m3_mechanics"
    try:
        outdir = Path(args.out) if args.out else None  # the runner mints a run-id directory
        summary = run_mechanics(outdir, timestep_s=args.timestep)
    except (SceneInvalid, PhysicsUnavailable, ValueError, OSError) as exc:
        print(f"physics mechanics: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario, str(exc)))
        return EXIT_CODES["ERROR"]

    status = summary["status"]
    outdir = Path(summary["run_dir"])
    solver = summary["solver"]
    print(json_status(status, scenario,
                      f"base step {solver['base_timestep_s']:g} s, "
                      f"half step {solver['half_timestep_s']:g} s"))
    # Keyed by set, so an operator can tell a base line from a half line: the trial names are
    # identical between the two sets.
    for name, trial in {**summary["trials"], **summary["half_trials"],
                        **summary["negative_trials"]}.items():
        failed = [c["name"] for c in trial["checks"] if not c["ok"]]
        print(f"{name}: valid {trial['valid']}, "
              f"{len(trial['checks']) - len(failed)}/{len(trial['checks'])} checks pass"
              + (f", failed {', '.join(failed)}" if failed else ""))
        if not trial["valid"]:
            print(f"  invalid: {'; '.join(trial['invalid_reasons'])}")
    for name, entry in summary["negatives"].items():
        print(f"negative {name}: {'correctly failed its named check' if entry['ok'] else 'DID NOT FAIL'}")
    gating = summary["gating"]
    print(f"gated {len(gating['positive_trials_gated'])} positive trials "
          f"(base and half); base invalid {gating['base_invalid'] or 'none'}, "
          f"half invalid {gating['half_invalid'] or 'none'}")
    conv = summary["convergence"]
    print(f"convergence base vs half dt: {'ok' if conv['ok'] else 'FAILED'}")
    for name, rel in summary["artifacts"].items():
        print(f"wrote {name}: {outdir / rel}")
    return EXIT_CODES[status]


def _physics_scenario(args) -> int:
    """``cad physics scenario``: strict JSON generic scenario through the M4a runner."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.runner import run_scenario_files
    from .physics.scenario import ScenarioError
    from .physics.scene import SceneInvalid

    scenario_name = Path(args.scenario).stem
    try:
        summary = run_scenario_files(args.scenario, args.acceptance,
                                     Path(args.out) if args.out else None)
    except (ScenarioError, SceneInvalid, PhysicsUnavailable, OSError, ValueError,
            ArithmeticError, RecursionError, TypeError, KeyError, StopIteration,
            IndexError) as exc:
        # A loader/usage failure happens before admission: no run directory is created.
        print(f"physics scenario: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario_name, str(exc)))
        return EXIT_CODES["ERROR"]

    status = summary["status"]
    if status == "ERROR":
        print(f"physics scenario: {summary.get('detail', 'run failed')}", file=sys.stderr)
    detail = summary.get("detail") or (
        f"{summary.get('fixture', '?')}, seed {summary.get('seed', '?')}, "
        f"{len(summary.get('checks', []))} checks")
    print(json_status(status, scenario_name, detail))
    for phase in summary.get("phases", []):
        print(f"phase {phase['name']}: {phase['kind']}, requested "
              f"{phase['requested_steps']} steps, actual {phase['actual_steps']}, "
              f"complete {phase['complete']}")
    for check in summary.get("checks", []):
        print(f"check {check['name']}: {check['status']} - {check['detail']}")
    for event in summary.get("events", []):
        print(f"event {event['name']}: {event['status']} {event['verdict_code']} - "
              f"{event['detail']}")
    for reason in summary.get("validity", {}).get("reasons", []):
        print(f"invalid [{reason['stage']}]: {reason['reason']}")
    outdir = Path(summary["run_dir"])
    for name, rel in summary.get("artifacts", {}).items():
        print(f"wrote {name}: {outdir / rel}")
    return EXIT_CODES[status]


MAX_OPTIONS_BYTES = 64 * 1024
EMPTY_OPTIONS_LOCK = "# assembly options: none\n"


def _read_options(path: str) -> tuple[str, dict]:
    """Strict bounded options TOML: a top-level table of scalars and flat scalar arrays."""
    import tomllib

    with open(path, "rb") as fh:
        raw = fh.read(MAX_OPTIONS_BYTES + 1)
    if len(raw) > MAX_OPTIONS_BYTES:
        raise ValueError(f"options file {path} exceeds {MAX_OPTIONS_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
        parsed = tomllib.loads(text)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"options file {path} is not valid TOML: {exc}") from exc

    def scalar(v) -> bool:
        return isinstance(v, (bool, int, float, str))

    for key, value in parsed.items():
        if scalar(value):
            continue
        if isinstance(value, list) and all(scalar(v) for v in value):
            continue
        raise ValueError(f"options key {key!r} must be a scalar or an array of scalars")
    return text, parsed


def _fresh_run_dir(project, model, scenario_id: str):
    return default_run_dir(project.name, model, scenario_id)


def _physics_run(args) -> int:
    """``cad physics run <project>/<model>``: run a project assembly through the generic runner."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.runner import run_assembly
    from .physics.scenario import ScenarioError, load_acceptance, load_scenario
    from .physics.scene import SceneInvalid

    label = getattr(args, "model", None) or "run"

    def fail(detail: str) -> int:
        print(f"physics run: {detail}", file=sys.stderr)
        print(json_status("ERROR", label, detail))
        return EXIT_CODES["ERROR"]

    try:
        project, model = _resolve(args)
        p = _load(args, project)
        scenario = load_scenario(Path(args.scenario))
        acceptance = load_acceptance(Path(args.acceptance))
        label = scenario.scenario_id
        if args.options:
            options_text, options = _read_options(args.options)
            hook = getattr(project, "physics_with_options", None)
            if hook is None:
                return fail(f"project {project.name!r} has no physics_with_options hook but "
                            f"--options was given")
            spec = hook(model, p, options)
        else:
            options_text, options = EMPTY_OPTIONS_LOCK, {}
            hook = getattr(project, "physics_with_options", None)
            if hook is not None:
                spec = hook(model, p, options)
            else:
                hook = getattr(project, "physics", None)
                if hook is None:
                    return fail(f"project {project.name!r} has no physics assembly; declare "
                                f"Project.physics(model_name, params)")
                spec = hook(model, p)
        if spec is None:
            return fail(f"model {project.name}/{model} has no physics assembly; the project's "
                        f"physics hook returned None for this model")
        outdir = Path(args.out) if args.out else _fresh_run_dir(project, model, scenario.scenario_id)
        live = None
        if getattr(args, "live", True):
            from .physics.live import DEFAULT_FPS, LiveWriter

            live_fps = getattr(args, "live_fps", None)
            live = LiveWriter(fps=DEFAULT_FPS if live_fps is None else live_fps)
        summary = run_assembly(spec, scenario, acceptance, outdir,
                               scenario_text=scenario.source_text,
                               acceptance_text=acceptance.source_text,
                               fixture_label=f"{project.name}/{model}",
                               options_text=options_text, require_scenario_timestep=True,
                               live=live)
    except SystemExit:
        return fail("unknown project or model")
    except (ScenarioError, SceneInvalid, PhysicsUnavailable, OSError, ValueError,
            ArithmeticError, RecursionError, TypeError, KeyError, StopIteration,
            IndexError) as exc:
        return fail(str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc))

    status = summary["status"]
    if status == "ERROR":
        print(f"physics run: {summary.get('detail', 'run failed')}", file=sys.stderr)
    detail = summary.get("detail") or (
        f"{summary.get('fixture', '?')}, seed {summary.get('seed', '?')}, "
        f"{len(summary.get('checks', []))} checks")
    print(json_status(status, label, detail))
    for check in summary.get("checks", []):
        print(f"check {check['name']}: {check['status']} - {check['detail']}")
    for event in summary.get("events", []):
        print(f"event {event['name']}: {event['status']} {event['verdict_code']} - "
              f"{event['detail']}")
    for reason in summary.get("validity", {}).get("reasons", []):
        print(f"invalid [{reason['stage']}]: {reason['reason']}")
    if "assembly_options_sha256" in summary:
        print(f"assembly options sha256: {summary['assembly_options_sha256']}")
    outdir = Path(summary["run_dir"])
    for name, rel in summary.get("artifacts", {}).items():
        print(f"wrote {name}: {outdir / rel}")
    return EXIT_CODES[status]


def _physics_replay(args) -> int:
    """``cad physics replay <run-dir> --out <fresh-dir>``: verify and replay saved evidence."""
    from pathlib import Path

    from .physics import EXIT_CODES, PhysicsUnavailable
    from .physics.evidence import EvidenceError
    from .physics.replay import ReplayError, replay_run
    from .physics.state_archive import ArchiveError

    source = Path(args.run_dir)
    scenario_name = source.name or "replay"
    try:
        result = replay_run(source, Path(args.out))
    except (ReplayError, EvidenceError, ArchiveError, PhysicsUnavailable, OSError,
            ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"physics replay: {exc}", file=sys.stderr)
        print(json_status("ERROR", scenario_name, str(exc)))
        return EXIT_CODES["ERROR"]

    status = result["status"]
    print(json_status(status, scenario_name,
                      f"source {result['source_status']}, reproduced "
                      f"{result['reproduced']}"))
    print(f"full state: ok {result['state_comparison']['ok']}, "
          f"max abs diff {result['state_comparison'].get('max_abs_diff')}")
    print(f"post-settle continuation: ok {result['post_settle_continuation']['ok']}")
    print(f"events recomputed identically: ok "
          f"{result.get('event_comparison', {}).get('ok')}")
    if result["evaluation_comparison"]["differences"]:
        for difference in result["evaluation_comparison"]["differences"]:
            print(f"difference: {difference}")
    out = Path(args.out)
    print(f"wrote replay: {out / 'replay.json'}")
    print(f"wrote replayed states: {out / 'replayed_states.npz'}")
    return EXIT_CODES[status]


def _fixture_outdir():
    return fixtures_root() / "m2a_asymmetric" / "physics" / "export"


def _physics_outdir(project, model):
    return model_out(project.name, model) / "physics" / "export"


def json_status(status: str, scenario: str, detail: str = "") -> str:
    """Machine-readable status line, always emitted, including on the error path."""
    import json as _json

    return _json.dumps({"status": status, "scenario": scenario, "detail": detail})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cad", description="build123d CAD workflow tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    listp = sub.add_parser("list", help="list models as <project>/<model>")
    listp.add_argument("--json", action="store_true", help="print one JSON document on stdout")
    listp.set_defaults(fn=cmd_list)
    for name, fn, helptext in (("build", cmd_build, "build, export (and optionally render/check)"),
                               ("render", cmd_render, "render PNGs"),
                               ("check", cmd_check, "run checks")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("model", help="<project>/<model>, or a bare <model> unique across projects")
        sp.add_argument("--part", help="only this part")
        sp.add_argument("--params", help="params TOML (default: the project's params file)")
        sp.add_argument("--set", nargs="+", action="extend", metavar="KEY=VAL",
                        help="override params, e.g. structure.min_wall=2.0")
        sp.add_argument("--out", help="output dir (default projects/<project>/out/<model>)")
        if name in ("build", "render"):
            sp.add_argument("--views", choices=VIEW_SETS, default="all",
                            help="render set: standard (iso/front/back/top), detail, sections or all")
        if name == "build":
            sp.add_argument("--render", action="store_true")
            sp.add_argument("--check", action="store_true")
            sp.add_argument("--scene", action="store_true",
                            help="also write the GUI scene to <out>/scene (skipped if a check FAILs)")
            sp.add_argument("--json", action="store_true", help="print one JSON document on stdout")
        sp.set_defaults(fn=fn)

    doctor = sub.add_parser("doctor", help="check the local toolchain")
    doctor.add_argument("--json", action="store_true", help="print one JSON document on stdout")
    doctor.set_defaults(fn=cmd_doctor)

    gui = sub.add_parser("gui", help="GUI artifacts and service")
    gui_sub = gui.add_subparsers(dest="verb", required=True)
    scene = gui_sub.add_parser("scene", help="export scene.json and parts/<id>.glb (assembly coords, mm)")
    scene.add_argument("model", help="<project>/<model>, or a bare <model> unique across projects")
    scene.add_argument("--params", help="params TOML (default: the project's params file)")
    scene.add_argument("--set", nargs="+", action="extend", metavar="KEY=VAL",
                       help="override params, e.g. structure.min_wall=2.0")
    scene.add_argument("--out", help="scene dir (default projects/<project>/out/<model>/scene)")
    scene.add_argument("--json", action="store_true", help="print one JSON document on stdout")
    scene.set_defaults(fn=cmd_gui)

    trajectory = gui_sub.add_parser(
        "trajectory",
        help="export <run>.gui/ (trajectory.json, poses.bin, meshes/*.glb; mm)")
    trajectory.add_argument("run_dir", help="a `cad physics run` output directory")
    trajectory.add_argument("--fps", type=float, default=60.0,
                            help="sim frames per second (default 60)")
    trajectory.add_argument("--contacts", action="store_true",
                            help="also write contacts.bin (points and normal forces)")
    trajectory.add_argument("--json", action="store_true", help="print one JSON document on stdout")
    trajectory.set_defaults(fn=cmd_gui)

    serve = gui_sub.add_parser("serve", help="run the local GUI service (127.0.0.1)")
    serve.add_argument("--port", type=int, default=0, help="TCP port on 127.0.0.1 (default 0: pick one)")
    serve.add_argument("--no-browser", action="store_true", help="do not open a browser")
    serve.add_argument("--json", action="store_true", help="print one JSON document on stdout")
    serve.set_defaults(fn=cmd_gui)

    gui_open = gui_sub.add_parser(
        "open", help="open the GUI on a model or run in VS Code (acknowledged) or a browser")
    gui_open.add_argument("model", nargs="?",
                          help="<project>/<model>, or a bare <model> unique across projects")
    gui_open.add_argument("--run", dest="run_dir", metavar="RUN_DIR",
                          help="a `cad physics run` directory under projects/<project>/out/ or "
                               ".cadstudio/fixtures/ (absolute, cwd- or workspace-relative)")
    gui_open.add_argument("--editor", choices=("auto", "vscode", "browser"), default="auto",
                          help="auto (default): VS Code from its terminal, else the browser")
    gui_open.add_argument("--no-open", action="store_true",
                          help="open nothing; print the tokened URL")
    gui_open.add_argument("--json", action="store_true", help="print one JSON document on stdout")
    gui_open.set_defaults(fn=cmd_gui)

    phys = sub.add_parser("physics", help="optional rigid-body physics (needs --extra physics)")
    phys_sub = phys.add_subparsers(dest="verb", required=True)
    smoke = phys_sub.add_parser("smoke", help="headless primitive gravity drop/settle fixture")
    smoke.add_argument("--out", help="output dir (default .cadstudio/fixtures/gravity_drop/physics/<run-id>)")
    smoke.add_argument("--edge-mm", type=float, default=20.0, help="box edge, mm (default 20)")
    smoke.add_argument("--density", type=float, default=1.27, help="g/cm3 (default 1.27)")
    smoke.add_argument("--clearance", type=float, default=100.0,
                       help="initial gap between box bottom and floor, mm (default 100)")
    smoke.add_argument("--timestep", type=float, default=1.0e-3, help="s (default 0.001)")
    smoke.add_argument("--duration", type=float, default=0.6, help="s (default 0.6)")
    smoke.add_argument("--gravity", type=float, default=9.80665,
                       help="m/s2 (default 9.80665; 0 is a negative test)")
    smoke.set_defaults(fn=cmd_physics)

    export = phys_sub.add_parser("export", help="emit and compile a model's physics scene")
    export.add_argument("model", help="<project>/<model>, or a bare <model> unique across projects")
    export.add_argument("--params", help="params TOML (default: the project's params file)")
    export.add_argument("--set", nargs="+", action="extend", metavar="KEY=VAL",
                        help="override params, e.g. structure.min_wall=2.0")
    export.add_argument("--out", help="output dir (default projects/<project>/out/<model>/physics/export)")
    export.set_defaults(fn=cmd_physics)

    fixture = phys_sub.add_parser(
        "fixture", help="export the built-in generic asymmetric CAD assembly")
    fixture.add_argument("--out", help="output dir (default .cadstudio/fixtures/m2a_asymmetric/physics/export)")
    fixture.set_defaults(fn=cmd_physics)

    channel = phys_sub.add_parser(
        "channel", help="hollow-channel collider-fidelity evidence (validation + live passage)")
    channel.add_argument("--out", help="output dir (default .cadstudio/fixtures/m2b_u_channel/physics/<run-id>)")
    channel.set_defaults(fn=cmd_physics)

    mechanics = phys_sub.add_parser(
        "mechanics", help="loaded-spring return and hinge-oscillator period evidence")
    mechanics.add_argument("--out", help="output dir (default .cadstudio/fixtures/m3_mechanics/physics/<run-id>)")
    mechanics.add_argument("--timestep", type=float, default=1.0e-3, help="s (default 0.001)")
    mechanics.set_defaults(fn=cmd_physics)

    scenario = phys_sub.add_parser(
        "scenario", help="run a strict JSON generic scenario through the M4a phase runner")
    scenario.add_argument("scenario", help="scenario JSON path")
    scenario.add_argument("--acceptance", required=True, help="frozen acceptance JSON path")
    scenario.add_argument("--out", help="run directory (default .cadstudio/fixtures/m4a/"
                                        "<scenario>/physics/<run-id>)")
    scenario.set_defaults(fn=cmd_physics)

    run = phys_sub.add_parser(
        "run", help="run a project model's physics assembly against a scenario and acceptance")
    run.add_argument("model", help="<project>/<model>")
    run.add_argument("--scenario", required=True, help="scenario JSON path")
    run.add_argument("--acceptance", required=True, help="frozen acceptance JSON path")
    run.add_argument("--options", help="strict TOML assembly options (scalars/arrays, <=64 KiB)")
    run.add_argument("--params", help="params TOML (default: the project's)")
    run.add_argument("--set", action="append", metavar="KEY=VAL", help="override a parameter")
    run.add_argument("--out", help="run directory, must not exist (default projects/<project>/"
                                   "out/<model>/runs/<scenario_id>-<UTC stamp>)")
    run.add_argument("--no-live", dest="live", action="store_false",
                     help="do not stream poses to the <run>.live/ sidecar while running")
    run.add_argument("--live-fps", type=float, default=None, metavar="N",
                     help="live sidecar sample rate in sim frames per second (default 30)")
    run.set_defaults(fn=cmd_physics)

    replay = phys_sub.add_parser(
        "replay", help="verify and deterministically replay a saved M4a run directory")
    replay.add_argument("run_dir", help="source run directory")
    replay.add_argument("--out", required=True, help="fresh output directory for replay evidence")
    replay.set_defaults(fn=cmd_physics)

    words = list(sys.argv[1:] if argv is None else argv)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on a usage error, which collides with INCONCLUSIVE. A typo must
        # never look like a physics verdict, so the physics verb reports ERROR instead.
        if exc.code == 2 and words[:1] == ["physics"]:
            print(json_status("ERROR", "cli", "usage error"))
            raise SystemExit(EXIT_CODES_PHYSICS["ERROR"]) from None
        raise
    try:
        code = args.fn(args)
    except WorkspaceError as exc:
        code = _workspace_failure(args, words, exc)
    sys.exit(code)


def _workspace_failure(args, words: list[str], exc: WorkspaceError) -> int:
    """No workspace: a one-line error on stderr, and the command's usual JSON shape if any."""
    msg = f"cad: {exc}"
    print(msg, file=sys.stderr)
    if words[:1] == ["physics"]:
        print(json_status("ERROR", "cli", str(exc)))
        return EXIT_CODES_PHYSICS["ERROR"]
    if getattr(args, "json", False):
        _emit_json({"error": str(exc), "exit_code": 1})
    return 1


if __name__ == "__main__":
    main()

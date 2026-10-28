"""Lay every syringe part out on one Prusa XL plate and write a PrusaSlicer 3MF project.

Run `uv run cad build pocky/<model> --check --views standard` first; this reads the print-pose
STLs from out/pocky/<model>/ and writes out/pocky/<model>/<model>_plate.3mf.
Pick the model with `--model syringe|syringe3` (default syringe). `--skip NAME` (repeatable) leaves out
parts that are already printed, e.g. `--skip handle`, and writes <model>_plate_without_<names>.3mf.
Needs `prusa-slicer` on PATH (a link to PrusaSlicer.app/Contents/MacOS/PrusaSlicer).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import trimesh

MODELS = ("syringe", "syringe3")
OUT_ROOT = Path(__file__).resolve().parents[3] / "out" / "pocky"
PROFILES = [
    "--printer-profile", "Original Prusa XL - 2T Input Shaper 0.4 nozzle",
    "--print-profile", "0.20mm STRUCTURAL @XLIS 0.4",
    "--material-profile", "Generic PETG @XL",
]
BED = 360.0
GAP = 15.0
# Rows of parts per model, front to back; each row is laid left to right.
ROWS = {
    "syringe": [["slider"], ["housing", "handle", "leg_1", "leg_2"], ["leg_3", "leg_4", "spring"]],
    "syringe3": [["slider"], ["housing", "clip_n", "clip_s"], ["handle", "leg_1", "leg_2", "leg_3", "leg_4"],
                 ["spring"]],
}


def layout(meshes: dict[str, trimesh.Trimesh], rows: list[list[str]]) -> dict[str, tuple[float, float]]:
    """XY offset that moves each part's footprint into its row, with the whole layout centred on the bed."""
    spots, y = {}, 0.0
    for row in rows:
        x, depth = 0.0, 0.0
        for name in row:
            (x0, y0, _), (x1, y1, _) = meshes[name].bounds
            spots[name] = (x - x0, y - y0)
            x += (x1 - x0) + GAP
            depth = max(depth, y1 - y0)
        y += depth + GAP
    placed = {n: meshes[n].bounds[:, :2] + spots[n] for n in spots}
    lo = min(b[0][0] for b in placed.values()), min(b[0][1] for b in placed.values())
    hi = max(b[1][0] for b in placed.values()), max(b[1][1] for b in placed.values())
    if hi[0] - lo[0] > BED or hi[1] - lo[1] > BED:
        sys.exit(f"layout {hi[0] - lo[0]:.0f} x {hi[1] - lo[1]:.0f} mm does not fit the {BED:.0f} mm bed")
    shift = (BED - (hi[0] + lo[0])) / 2, (BED - (hi[1] + lo[1])) / 2
    return {n: (dx + shift[0], dy + shift[1]) for n, (dx, dy) in spots.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Lay one pocky syringe model out on a Prusa XL plate.")
    parser.add_argument("--model", choices=MODELS, default="syringe", help="model whose STLs to lay out")
    parser.add_argument("--skip", action="append", default=[], metavar="NAME",
                        help="part to leave off the plate (repeatable), e.g. one already printed")
    args = parser.parse_args()
    model = args.model
    out = OUT_ROOT / model
    known = {n for row in ROWS[model] for n in row}
    unknown = sorted(set(args.skip) - known)
    if unknown:
        sys.exit(f"unknown part(s) for {model}: {', '.join(unknown)}; parts: {', '.join(sorted(known))}")
    rows = [kept for row in ROWS[model] if (kept := [n for n in row if n not in args.skip])]
    names = [n for row in rows for n in row]
    meshes = {n: trimesh.load(out / f"{n}.stl") for n in names}
    for n, m in meshes.items():
        if abs(m.bounds[0][2]) > 1e-3:
            sys.exit(f"{n}.stl is not resting on z=0; rebuild pocky/{model}")
    suffix = f"_without_{'_'.join(sorted(set(args.skip)))}" if args.skip else ""
    target = out / f"{model}_plate{suffix}.3mf"
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for n, (dx, dy) in layout(meshes, rows).items():
            path = Path(tmp) / f"{n}.stl"
            meshes[n].copy().apply_translation((dx, dy, 0.0)).export(path)
            paths.append(str(path))
        config = Path(tmp) / "config.ini"
        subprocess.run(["prusa-slicer", *PROFILES, "--save", str(config)], check=True, capture_output=True)
        subprocess.run(["prusa-slicer", "--export-3mf", "--merge", "--dont-arrange", *PROFILES,
                        "--output", str(target), *paths], check=True, capture_output=True)
        # The CLI leaves the settings out of an exported 3MF; this is where the GUI stores a project's settings.
        with zipfile.ZipFile(target, "a") as z:
            z.writestr("Metadata/Slic3r_PE.config", config.read_text())
    print(target)


if __name__ == "__main__":
    main()

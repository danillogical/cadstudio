"""Regenerate the tiny two-box scene fixture; no project geometry is involved.

Run from the repo root: ``uv run --frozen python ui/test/fixtures/generate.py``.
The GLBs use the same trimesh exporter as ``cadkit/gui/scene.py`` so the fixture
matches production encoding (assembly coordinates, Z up, millimetres).
"""
from __future__ import annotations

import json
from pathlib import Path

import trimesh

HERE = Path(__file__).resolve().parent
PARTS = HERE / "parts"

# Row-major 4x4: -90 deg about X then translate z by 2 mm.
PRINT_POSE = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 2.0],
    [0.0, 0.0, 0.0, 1.0],
]


def _box(extents: list[float], lo: list[float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation([lo[i] + extents[i] / 2 for i in range(3)])
    return mesh


def main() -> None:
    base = _box([40.0, 20.0, 5.0], [0.0, 0.0, 0.0])
    pin = _box([4.0, 4.0, 30.0], [18.0, 8.0, 5.0])

    PARTS.mkdir(parents=True, exist_ok=True)
    for part_id, mesh in (("base", base), ("pin", pin)):
        (PARTS / f"{part_id}.glb").write_bytes(mesh.export(file_type="glb"))

    doc = {
        "schemaVersion": 1,
        "project": "fixture",
        "model": "two_box",
        "units": "mm",
        "provenance": {
            "commit": "0" * 40,
            "dirty": False,
            "paramsPath": "fixture/params.toml",
            "paramsSha256": "1" * 64,
            "overrides": {},
            "builtAt": "2024-01-02T03:04:05Z",
        },
        "parts": [
            {
                "id": "base",
                "name": "base",
                "mesh": "parts/base.glb",
                "bbox": {"min": [0.0, 0.0, 0.0], "max": [40.0, 20.0, 5.0]},
                "volume": 4000.0,
                "color": "#6f9a86",
            },
            {
                "id": "pin",
                "name": "pin",
                "mesh": "parts/pin.glb",
                "bbox": {"min": [18.0, 8.0, 5.0], "max": [22.0, 12.0, 35.0]},
                "volume": 480.0,
                "color": "#a58f6e",
                "printPose": PRINT_POSE,
            },
        ],
    }
    (HERE / "scene.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

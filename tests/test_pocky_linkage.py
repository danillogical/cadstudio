"""Locks the M1 linkage closed form. Does not shell out to ``uv run cad``."""
import importlib.util
import math
from pathlib import Path

import pytest

from cadkit.checks import overlap_volume
from projects.pocky.geometry.linkage import (
    button_slot_radii,
    floor_slot_bounds,
    linkage_from,
    phi_for_button_fraction,
    pin_solids,
    pose_at_phi,
    pusher_slot_ends,
    slot_end_clearance,
)
from projects.pocky.models.linkage_motion import build
from projects.pocky.params import load_params

# Button-travel checkpoints from the M1 review. Printed to 4 decimals.
BUTTON_TABLE = (
    # fraction, phi deg, travel, face x, pin y, slot r, shift, protrusion
    (0.00, 120.000, 0.0000, -87.0000, 35.3013, 23.0940, 0.0000, -5.5000),
    (0.25, 106.102, 5.7735, -75.8675, 40.0384, 20.8167, 6.6325, 1.1325),
    (0.50, 90.000, 11.5470, -62.0000, 42.0000, 20.0000, 20.5000, 15.0000),
    (0.75, 73.898, 17.3205, -48.1325, 40.0384, 20.8167, 34.3675, 28.8675),
    (1.00, 60.000, 23.0940, -37.0000, 35.3013, 23.0940, 45.5000, 40.0000),
)


@pytest.fixture(scope="module")
def params():
    return load_params()


@pytest.fixture(scope="module")
def link(params):
    return linkage_from(params)


def _proposal_sweep():
    path = Path(__file__).resolve().parents[1] / "projects" / "pocky" / "docs" / "proposal_sweep.py"
    spec = importlib.util.spec_from_file_location("pocky_proposal_sweep", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_derivation(link):
    assert link.stroke == pytest.approx(50.0, abs=1e-9)
    assert link.radius == pytest.approx(50.0, abs=1e-9)
    assert (link.pivot_x, link.pivot_y) == pytest.approx((-78.0, -8.0), abs=1e-9)
    assert link.button_stroke == pytest.approx(40.0 / math.sqrt(3.0), abs=1e-9)
    assert link.face0 == pytest.approx(-87.0, abs=1e-9)
    assert (link.rod_z0, link.rod_z1) == pytest.approx((-15.6, -11.6), abs=1e-9)
    assert (link.crank_z0, link.crank_z1) == pytest.approx((-11.2, -7.2), abs=1e-9)
    assert (link.carriage_z0, link.carriage_z1) == pytest.approx((-6.8, -2.8), abs=1e-9)
    assert (link.floor_z0, link.floor_z1) == pytest.approx((-2.4, 0.0), abs=1e-9)
    assert floor_slot_bounds(link) == pytest.approx((-93.1, -35.1, -3.5, 3.5), abs=1e-9)
    assert button_slot_radii(link)[0] == pytest.approx(19.0, abs=1e-9)
    assert button_slot_radii(link)[1] == pytest.approx(24.0940107676, abs=1e-9)
    assert pusher_slot_ends(link) == pytest.approx((34.3012701892, 43.0), abs=1e-9)


def test_stroke_follows_packet_length(params):
    shorter = linkage_from(params.override({"packet.length": 160.0}))
    assert shorter.stroke == pytest.approx(55.0, abs=1e-9)
    assert shorter.radius == pytest.approx(55.0, abs=1e-9)
    assert shorter.button_stroke == pytest.approx(40.0 / math.sqrt(3.0), abs=1e-9)


def test_button_travel_table(link):
    for fraction, phi_deg, travel, face, pin_y, slot_r, shift, protrusion in BUTTON_TABLE:
        pose = pose_at_phi(link, phi_for_button_fraction(link, fraction))
        assert math.degrees(pose.phi) == pytest.approx(phi_deg, abs=5e-3)
        assert pose.button_travel == pytest.approx(travel, abs=5e-4)
        assert pose.face_x == pytest.approx(face, abs=5e-4)
        assert pose.pusher_pin_y == pytest.approx(pin_y, abs=5e-4)
        assert pose.slot_radius == pytest.approx(slot_r, abs=5e-4)
        assert pose.packet_shift == pytest.approx(shift, abs=5e-4)
        assert pose.protrusion == pytest.approx(protrusion, abs=5e-4)
        assert pose.button_y == pytest.approx(-28.0, abs=1e-9)
        assert pose.speed_ratio == pytest.approx(2.5 * math.sin(pose.phi) ** 3, abs=1e-9)
        button_clear, pusher_clear = slot_end_clearance(link, pose)
        assert button_clear >= 1.0 - 1e-9
        assert pusher_clear >= 1.0 - 1e-9


def test_closed_form_at_rest(link):
    phi = math.radians(120.0)
    pose = pose_at_phi(link, phi)
    assert pose.face_x == pytest.approx(-78.0 + 50.0 * math.cos(phi) + 16.0, abs=1e-9)
    cot = lambda a: math.cos(a) / math.sin(a)
    assert pose.button_travel == pytest.approx(20.0 * (cot(phi) - cot(math.radians(120.0))), abs=1e-9)
    assert pose.slot_radius == pytest.approx(20.0 / math.sin(phi), abs=1e-9)


def test_matches_proposal_sweep_angle_poses(link):
    sweep = _proposal_sweep().sweep(201)
    n = len(sweep["phi"])
    for i in range(5):
        idx = int(round(i * (n - 1) / 4))
        pose = pose_at_phi(link, float(sweep["phi"][idx]))
        assert pose.face_x == pytest.approx(float(sweep["face_x"][idx]), abs=1e-6)
        assert pose.pusher_pin_y == pytest.approx(float(sweep["pusher_pin_y"][idx]), abs=1e-6)
        assert pose.slot_radius == pytest.approx(float(sweep["slot_radius"][idx]), abs=1e-6)
        assert pose.button_travel == pytest.approx(float(sweep["button_travel"][idx]), abs=1e-6)
        assert pose.packet_shift == pytest.approx(float(sweep["packet_shift"][idx]), abs=1e-6)
        assert pose.protrusion == pytest.approx(float(sweep["protrusion"][idx]), abs=1e-6)
        assert pose.button_y == pytest.approx(float(sweep["button_y"][idx]), abs=1e-6)


def test_bad_pose_rejected(params, monkeypatch):
    monkeypatch.setenv("POCKY_POSE", "10")
    with pytest.raises(ValueError, match="POCKY_POSE"):
        build(params)


@pytest.mark.parametrize("pose_name", ["0", "100"])
def test_pose_solids(params, monkeypatch, pose_name):
    monkeypatch.setenv("POCKY_POSE", pose_name)
    parts = build(params)
    assert set(parts) == {"floor", "crank", "rod", "pusher", "home_stop", "forward_stop"}
    for mp in parts.values():
        assert mp.shape.is_valid
        assert len(mp.shape.solids()) == 1
        zmin = mp.shape.moved(mp.print_location).bounding_box().min.Z
        assert zmin == pytest.approx(0.0, abs=1e-6)
    link = linkage_from(params)
    phi = phi_for_button_fraction(link, int(pose_name) / 100.0)
    pins = pin_solids(params, phi)
    assert overlap_volume(parts["crank"].shape, parts["pusher"].shape) <= 1e-3
    for pin in pins.values():
        for mp in parts.values():
            assert overlap_volume(pin, mp.shape) <= 1e-3

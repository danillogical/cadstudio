"""Independent generic presentation-aperture fixture (M4c).

This is deliberately **not** the Pocky dispenser. It is a small, physically driven fixture
that exercises the generic presentation events end to end:

* a fixed housing made of separate floor, side-wall and top-wall colliders, leaving a true
  open aperture at +X and an 18 mm shelf beyond it;
* one free rigid box on the floor inside the channel;
* a bounded, damped prismatic pusher driven by a real force actuator;
* variants with a blocked mouth and with two packet identities.

The box is pushed part-way out, released to zero input, and must remain supported by actual
floor/shelf contacts for a continuous dwell. Motion comes from the pusher, friction, contact
and gravity; no ``qpos`` is written after reset. Geometry is authored in millimetres and
converted exactly once by the scene exporter.
"""
from __future__ import annotations

from build123d import Box, Pos
from dataclasses import replace

from .schema import (
    ActuatorSpec,
    AssemblySpec,
    BodySpec,
    ColliderSpec,
    Frame,
    JointSpec,
    PartSpec,
    Source,
)
from .units import mass_kg

# ---- fixed generic geometry, mm -----------------------------------------------------------
PACKET_LENGTH_MM = 100.0
PACKET_WIDTH_MM = 36.0
PACKET_HEIGHT_MM = 8.0
PACKET_DENSITY_G_CM3 = 1.2

#: Mouth (outer face) at x = 0; the shelf ends 18 mm beyond it.
MOUTH_X_MM = 0.0
SHELF_END_X_MM = 18.0
SHELF_LENGTH_MM = 18.0
FLOOR_REAR_X_MM = -130.0
FLOOR_LENGTH_MM = 148.0  # -130 .. +18
FLOOR_CENTRE_X_MM = -56.0
FLOOR_HALF_WIDTH_MM = 24.25
FLOOR_THICKNESS_MM = 6.0
WALL_THICKNESS_MM = 3.0
CAVITY_HALF_WIDTH_MM = 18.25
CAVITY_HEIGHT_MM = 8.5
WALL_HEIGHT_MM = 8.5
TOP_THICKNESS_MM = 3.0

#: Packet starts 20 mm inside the mouth and is pushed 65 mm.
PACKET_START_X_MM = -70.0
PACKET_START_Z_MM = PACKET_HEIGHT_MM / 2.0
PUSH_STROKE_MM = 65.0
PUSHER_THICKNESS_MM = 6.0
PUSHER_CENTRE_X_MM = PACKET_START_X_MM - PACKET_LENGTH_MM / 2.0 - PUSHER_THICKNESS_MM / 2.0
PUSHER_START_X_MM = PUSHER_CENTRE_X_MM
PUSHER_HALF_WIDTH_MM = PACKET_WIDTH_MM / 2.0
PUSHER_DAMPING_NS_M = 50.0
PUSHER_MASS_KG = 0.1
PUSHER_MAX_EFFORT_N = 3.0
PUSHER_EFFORT_N = 2.0

#: Blocked variant: a fixed wall just inside the mouth, so the leading edge cannot reach the
#: exit plane even under numerical contact penetration.
BLOCKER_REAR_X_MM = -1.0
BLOCKER_LENGTH_MM = 5.0
BLOCKER_CENTRE_X_MM = BLOCKER_REAR_X_MM + BLOCKER_LENGTH_MM / 2.0
BLOCKER_HALF_WIDTH_MM = 19.0
BLOCKER_HEIGHT_MM = 11.5

#: Two-packet variant: two narrower boxes side by side, both pushed.
DOUBLE_PACKET_WIDTH_MM = 17.0
DOUBLE_PACKET_OFFSET_Y_MM = 8.75

DENSITY_G_CM3 = 1.24
CONTACT_TIMECONST_S = 2.0e-3
CONTACT_DAMPRATIO = 1.0
STOP_TIMECONST_S = 2.0e-3
FRICTION = (0.5, 0.005, 0.0001)
TIMESTEP_S = 1.0e-3


def _part(part_id: str, size_mm, pos_mm, half_mm, *, role: str = "structure",
          density: float = DENSITY_G_CM3, source_note: str = "declared box") -> PartSpec:
    """A box part whose shape is in assembly mm and whose collider is body-local."""
    return PartSpec(
        part_id,
        Pos(*pos_mm) * Box(*size_mm),
        colliders=(ColliderSpec(f"{part_id}_col", "box", tuple(half_mm),
                                pos_mm=tuple(pos_mm), role=role,
                                source=Source("derived", f"{part_id} half-extents")),),
        density_g_cm3=density,
        role=role,
        source=Source("derived", source_note),
    )


def _housing_parts() -> tuple[PartSpec, ...]:
    floor = _part(
        "floor", (FLOOR_LENGTH_MM, 2.0 * FLOOR_HALF_WIDTH_MM, FLOOR_THICKNESS_MM),
        (FLOOR_CENTRE_X_MM, 0.0, -FLOOR_THICKNESS_MM / 2.0),
        (FLOOR_LENGTH_MM / 2.0, FLOOR_HALF_WIDTH_MM, FLOOR_THICKNESS_MM / 2.0),
        source_note="fixed channel floor and 18 mm shelf")
    wall_y = CAVITY_HALF_WIDTH_MM + WALL_THICKNESS_MM / 2.0
    wall_x = (FLOOR_REAR_X_MM + MOUTH_X_MM) / 2.0
    wall_length = MOUTH_X_MM - FLOOR_REAR_X_MM
    side_pos = _part(
        "wall_pos", (wall_length, WALL_THICKNESS_MM, WALL_HEIGHT_MM),
        (wall_x, wall_y, WALL_HEIGHT_MM / 2.0),
        (wall_length / 2.0, WALL_THICKNESS_MM / 2.0, WALL_HEIGHT_MM / 2.0),
        source_note="fixed +Y channel wall")
    side_neg = _part(
        "wall_neg", (wall_length, WALL_THICKNESS_MM, WALL_HEIGHT_MM),
        (wall_x, -wall_y, WALL_HEIGHT_MM / 2.0),
        (wall_length / 2.0, WALL_THICKNESS_MM / 2.0, WALL_HEIGHT_MM / 2.0),
        source_note="fixed -Y channel wall")
    top = _part(
        "top", (wall_length, 2.0 * FLOOR_HALF_WIDTH_MM, TOP_THICKNESS_MM),
        (wall_x, 0.0, CAVITY_HEIGHT_MM + TOP_THICKNESS_MM / 2.0),
        (wall_length / 2.0, FLOOR_HALF_WIDTH_MM, TOP_THICKNESS_MM / 2.0),
        source_note="fixed channel top; mouth is open at +X")
    return (floor, side_pos, side_neg, top)


def _housing_body() -> BodySpec:
    return BodySpec(
        body_id="housing",
        parts=_housing_parts(),
        fixed_to_world=True,
        fixture="analytic_fixture",
        source=Source("derived", "fixed multipart presentation aperture fixture"),
    )


def _packet_body(body_id: str, y_mm: float = 0.0,
                 width_mm: float = PACKET_WIDTH_MM) -> BodySpec:
    volume_mm3 = PACKET_LENGTH_MM * width_mm * PACKET_HEIGHT_MM
    return BodySpec(
        body_id=body_id,
        parts=(PartSpec(
            f"{body_id}_shell",
            Pos(PACKET_START_X_MM, y_mm, PACKET_START_Z_MM)
            * Box(PACKET_LENGTH_MM, width_mm, PACKET_HEIGHT_MM),
            colliders=(ColliderSpec(
                f"{body_id}_col", "box",
                (PACKET_LENGTH_MM / 2.0, width_mm / 2.0, PACKET_HEIGHT_MM / 2.0),
                pos_mm=(0.0, 0.0, 0.0), role="packet",
                source=Source("derived", f"{body_id} rigid proxy half-extents")),),
            mass_kg=mass_kg(volume_mm3, PACKET_DENSITY_G_CM3),
            role="packet",
            source=Source("assumed", "generic rigid packet proxy at 1.2 g/cm3"),
        ),),
        frame=Frame(pos_mm=(PACKET_START_X_MM, y_mm, PACKET_START_Z_MM)),
        source=Source("derived", "free rigid packet on the channel floor"),
    )


def _pusher_body() -> BodySpec:
    return BodySpec(
        body_id="pusher",
        parts=(PartSpec(
            "pusher_plate",
            Pos(PUSHER_START_X_MM, 0.0, PACKET_START_Z_MM)
            * Box(PUSHER_THICKNESS_MM, PACKET_WIDTH_MM, PACKET_HEIGHT_MM),
            colliders=(ColliderSpec(
                "pusher_col", "box",
                (PUSHER_THICKNESS_MM / 2.0, PUSHER_HALF_WIDTH_MM,
                 PACKET_HEIGHT_MM / 2.0),
                pos_mm=(0.0, 0.0, 0.0), role="mechanism",
                source=Source("derived", "pusher plate half-extents")),),
            mass_kg=PUSHER_MASS_KG,
            density_g_cm3=None,
            role="mechanism",
            source=Source("assumed", "declared 0.1 kg pusher mass for contact stability"),
        ),),
        frame=Frame(pos_mm=(PUSHER_START_X_MM, 0.0, PACKET_START_Z_MM)),
        parent="housing",
        joint=JointSpec(
            joint_id="pusher_slide",
            body_id="pusher",
            kind="slide",
            axis=(1.0, 0.0, 0.0),
            anchor_mm=(0.0, 0.0, 0.0),
            limits=(0.0, PUSH_STROKE_MM * 1e-3),
            damping=PUSHER_DAMPING_NS_M,
            stop_timeconst_s=STOP_TIMECONST_S,
            stop_dampratio=1.0,
            source=Source("assumed", "bounded damped pusher; not a product mechanism"),
        ),
        source=Source("derived", "prismatic pusher mounted in the fixed housing"),
    )


def _blocker_body() -> BodySpec:
    return BodySpec(
        body_id="blocker",
        parts=(PartSpec(
            "blocker_wall",
            Pos(BLOCKER_CENTRE_X_MM, 0.0, BLOCKER_HEIGHT_MM / 2.0)
            * Box(BLOCKER_LENGTH_MM, 2.0 * BLOCKER_HALF_WIDTH_MM, BLOCKER_HEIGHT_MM),
            colliders=(ColliderSpec(
                "blocker_col", "box",
                (BLOCKER_LENGTH_MM / 2.0, BLOCKER_HALF_WIDTH_MM,
                 BLOCKER_HEIGHT_MM / 2.0),
                pos_mm=(BLOCKER_CENTRE_X_MM, 0.0, BLOCKER_HEIGHT_MM / 2.0),
                role="structure",
                source=Source("derived", "blocked-aperture diagnostic wall")),),
            density_g_cm3=DENSITY_G_CM3,
            role="structure",
            source=Source("derived", "fixed blocked-mouth diagnostic"),
        ),),
        fixed_to_world=True,
        fixture="analytic_fixture",
        source=Source("derived", "deliberately blocked aperture, dynamics negative"),
    )


def _actuator() -> ActuatorSpec:
    return ActuatorSpec(
        "push", "pusher_slide", "force", PUSHER_MAX_EFFORT_N,
        source=Source("assumed", "bounded mechanical input, not a product actuator"),
    )


def presentation_aperture_spec(*, timestep_s: float = TIMESTEP_S) -> AssemblySpec:
    """The positive/zero-feed fixture: one free packet, open aperture."""
    return AssemblySpec(
        name="m4c_presentation_aperture",
        bodies=(_housing_body(), _packet_body("packet"), _pusher_body()),
        actuators=(_actuator(),),
        gravity_m_s2=(0.0, 0.0, -9.80665),
        timestep_s=timestep_s,
        contact_timeconst_s=CONTACT_TIMECONST_S,
        contact_dampratio=CONTACT_DAMPRATIO,
        friction=FRICTION,
        source=Source("derived", "generic supported partial-presentation fixture"),
    )


def blocked_presentation_aperture_spec(*, timestep_s: float = TIMESTEP_S) -> AssemblySpec:
    """Same fixture with a fixed wall just inside the mouth: a blocked-aperture negative."""
    positive = presentation_aperture_spec(timestep_s=timestep_s)
    return replace(
        positive,
        name="m4c_presentation_aperture_blocked",
        bodies=(*positive.bodies, _blocker_body()),
        source=Source("derived", "blocked-aperture dynamics negative"),
    )


def double_presentation_aperture_spec(*, timestep_s: float = TIMESTEP_S) -> AssemblySpec:
    """Two distinct free packet identities side by side: a real double-feed negative."""
    positive = presentation_aperture_spec(timestep_s=timestep_s)
    return replace(
        positive,
        name="m4c_presentation_aperture_double",
        bodies=(_housing_body(),
                _packet_body("packet_a", -DOUBLE_PACKET_OFFSET_Y_MM,
                             DOUBLE_PACKET_WIDTH_MM),
                _packet_body("packet_b", DOUBLE_PACKET_OFFSET_Y_MM,
                             DOUBLE_PACKET_WIDTH_MM),
                _pusher_body()),
        source=Source("derived", "two distinct packet identities, double-feed negative"),
    )

"""An independently authored asymmetric multi-part CAD assembly, for scene-adapter validation.

This is deliberately **not** a Pocky stand-in. It exists to exercise the things a real model
will need and a symmetric box cannot test:

* unequal dimensions on all three axes;
* a non-trivial rotation (about Z) and a translation, so a frame applied twice or not at all
  is visible;
* an **offset centre of mass**, because one part is much denser in volume than the other;
* two parts welded into one rigid body, so the parallel-axis theorem is exercised;
* a second, separate free body so body counting and world poses are checked.

The two parts are authored in assembly coordinates, as the contract requires.
"""
from __future__ import annotations

from build123d import Box, Pos, Rot

from .schema import AssemblySpec, BodySpec, ColliderSpec, Frame, PartSpec, Source

#: Density of the fixture material, g/cm3. Deliberately not PETG so a stray hard-coded
#: default cannot pass unnoticed.
FIXTURE_DENSITY_G_CM3 = 1.24

#: The body frame: translated and rotated 90 degrees about Z.
FIXTURE_FRAME = Frame(pos_mm=(100.0, -50.0, 20.0), rot_deg=(0.0, 0.0, 90.0))

#: Part geometry in *design* coordinates, before the frame is applied. The specs below place
#: the resulting solids in assembly coordinates, which is what PartSpec.shape must contain.
ARM_DESIGN = (Pos(10.0, 0.0, 0.0) * Box(40.0, 10.0, 6.0))
TAB_DESIGN = (Pos(-8.0, 4.0, 0.0) * Rot(0.0, 0.0, 25.0) * Box(12.0, 30.0, 10.0))
PEG_DESIGN = (Pos(0.0, 0.0, 0.0) * Box(8.0, 8.0, 24.0))


def _to_assembly(shape):
    """Move a design-coordinate solid into assembly coordinates with the fixture frame."""
    return FIXTURE_FRAME.location() * shape


def fixture_assembly() -> AssemblySpec:
    """The two-body asymmetric fixture used by the M2a tests and `cad physics export`."""
    return AssemblySpec(
        name="m2a_asymmetric_fixture",
        bodies=(
            BodySpec(
                body_id="link_ab",
                parts=(
                    PartSpec(
                        part_id="arm",
                        shape=_to_assembly(ARM_DESIGN),
                        colliders=(ColliderSpec(
                            collider_id="arm_col", kind="box",
                            size_mm=(20.0, 5.0, 3.0), pos_mm=(10.0, 0.0, 0.0),
                            source=Source("derived", "arm half-extents"),
                        ),),
                        density_g_cm3=FIXTURE_DENSITY_G_CM3,
                    ),
                    PartSpec(
                        part_id="tab",
                        shape=_to_assembly(TAB_DESIGN),
                        colliders=(ColliderSpec(
                            collider_id="tab_col", kind="box",
                            size_mm=(6.0, 15.0, 5.0), pos_mm=(-8.0, 4.0, 0.0),
                            rot_deg=(0.0, 0.0, 25.0),
                            source=Source("derived", "tab half-extents, 25 deg about Z"),
                        ),),
                        density_g_cm3=FIXTURE_DENSITY_G_CM3,
                    ),
                ),
                frame=FIXTURE_FRAME,
                fixture="analytic_fixture",
                source=Source("derived", "two parts welded into one rigid link"),
            ),
            BodySpec(
                body_id="post_free",
                parts=(
                    PartSpec(
                        part_id="post",
                        shape=_to_assembly(Pos(40.0, 30.0, 0.0) * PEG_DESIGN),
                        colliders=(ColliderSpec(
                            collider_id="post_col", kind="box",
                            size_mm=(4.0, 4.0, 12.0), pos_mm=(40.0, 30.0, 0.0),
                            source=Source("derived", "post half-extents at its body-local centre"),
                        ),),
                        density_g_cm3=FIXTURE_DENSITY_G_CM3,
                    ),
                ),
                frame=Frame(pos_mm=(100.0, -50.0, 20.0), rot_deg=(0.0, 0.0, 90.0)),
                source=Source("derived", "separate free body"),
            ),
        ),
        source=Source("derived", "M2a asymmetric fixture"),
    )

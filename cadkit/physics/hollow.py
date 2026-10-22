"""The M2b hollow-channel fixture: a U-channel that must stay open.

Independently authored from primitives — **not** a Pocky stand-in. It is a U-channel: three
connected walls (floor + two sides) with a cavity running the full length and open at both
ends, plus a drop-in mouth so a free object can fall into it.

```
        z
        ^        open top
        |
   +---------+  <- side wall top
   |  |   |  |
   |  |   |  |   cavity: length along X, width along Y, open at +/-X
   |  |   |  |
   +--+---+--+  <- floor
      y ->
```

Two recipes are provided on purpose:

* :func:`u_channel_spec` — the **correct** recipe: five boxes (floor, two sides, two end
  returns) that leave the cavity and both mouths empty. It has a declared fidelity contract,
  so export refuses to proceed if a collider intrudes into the void.
* :func:`u_channel_spec_bad_recipe` — a deliberately wrong recipe: one box spanning the whole
  bounding volume. It compiles fine and MuJoCo would happily collide with it; only the
  fidelity contract can tell it is wrong.

:func:`convex_hull_scene_xml` builds a **test-only diagnostic** MJCF that collides with the
channel's convex hull, reproducing the failure MuJoCo would apply to a single concave mesh.
It is never a design of record and is never exported by the CLI.
"""
from __future__ import annotations

from dataclasses import replace

from build123d import Box, Pos

from .collision import FidelitySpec, ProbeSpec, TransitSpec
from .units import mm_to_m
from .schema import AssemblySpec, BodySpec, ColliderSpec, Frame, PartSpec, Source

# ---- fixed acceptance geometry, mm -------------------------------------------------------
CHANNEL_LENGTH_MM = 120.0     # along X; the passage direction
CHANNEL_WIDTH_MM = 40.0       # outside, along Y
CHANNEL_HEIGHT_MM = 40.0      # outside, along Z
WALL_MM = 5.0                 # floor and both side walls
#: How far the floor runs past the walled section at each end, mm. Fixture lead-in/lead-out.
FLOOR_OVERRUN_MM = 30.0

CAVITY_WIDTH_MM = CHANNEL_WIDTH_MM - 2.0 * WALL_MM      # 30
CAVITY_HEIGHT_MM = CHANNEL_HEIGHT_MM - WALL_MM          # 35
CAVITY_HALF_WIDTH_MM = CAVITY_WIDTH_MM / 2.0            # 15

#: Radius of the test object that must pass through, mm.
PROBE_RADIUS_MM = 6.0
#: The through-path probe starts this far outside the -X mouth, on the cavity axis, mm.
LAUNCH_GAP_MM = 15.0
#: Declared initial +X speed for the through-path trial, m/s. A recorded fixture input, not a
#: per-step write: it is applied once at t=0 and gravity/contact do the rest.
#:
#: The probe rides ON the floor, so the floor supports it and gravity does not convert the
#: transit into a free fall. The run from the start (-81 mm) to the exit plane (66 mm) is
#: 147 mm; the declared friction 0.4 gives a = mu*g = 3.9 m/s^2, so a friction-only stop needs
#: sqrt(2*3.9*0.147) = 1.07 m/s. This speed is ~2x that, which covers the extra loss from the
#: stiffer declared contact model without relying on a scripted push.
LAUNCH_SPEED_M_S = 2.2
#: Contact model time constant, in **absolute seconds**, and damping ratio. Fixed in SI so a
#: timestep-refinement comparison changes integration resolution only, never contact
#: compliance. At the default 1 ms step this is 2 steps, MuJoCo's recommended minimum.
CONTACT_TIMECONST_S = 2.0e-3
CONTACT_DAMPRATIO = 1.0
#: Solver impedance parameters, emitted alongside solref.
CONTACT_SOLIMP = "0.95 0.99 0.001"
#: The passage line: through the cavity, along X, at the height a probe resting on the floor
#: occupies. The static transit check uses a 2 mm lift so it clears the floor by construction.
TRANSIT_Z_MM = WALL_MM + PROBE_RADIUS_MM + 2.0          # 13
#: Height of a probe resting on the floor, mm.
RESTING_Z_MM = WALL_MM + PROBE_RADIUS_MM                # 11
TRANSIT_START_MM = (-CHANNEL_LENGTH_MM / 2.0 - 20.0, 0.0, TRANSIT_Z_MM)
TRANSIT_END_MM = (CHANNEL_LENGTH_MM / 2.0 + 20.0, 0.0, TRANSIT_Z_MM)

DENSITY_G_CM3 = 1.24


def channel_solid():
    """The U-channel as one solid: floor plus two side walls, open top and both ends.

    The **floor** runs ``FLOOR_OVERRUN_MM`` past the walled section at each end. That is the
    fixture's lead-in and lead-out: without it a probe launched outside the mouth would be in
    free fall and would strike the floor's leading edge, which is a corner impact rather than
    a transit. The walls still span exactly ``CHANNEL_LENGTH_MM``, so the cavity is open at
    both ends and the exit plane is unchanged.
    """
    lx, wy, hz, wall = CHANNEL_LENGTH_MM, CHANNEL_WIDTH_MM, CHANNEL_HEIGHT_MM, WALL_MM
    floor_len = lx + 2.0 * FLOOR_OVERRUN_MM
    floor = Pos(0.0, 0.0, wall / 2.0) * Box(floor_len, wy, wall)
    side_pos = Pos(0.0, (wy - wall) / 2.0, hz / 2.0) * Box(lx, wall, hz)
    side_neg = Pos(0.0, -(wy - wall) / 2.0, hz / 2.0) * Box(lx, wall, hz)
    return (floor + side_pos + side_neg).solid()


def channel_colliders() -> tuple[ColliderSpec, ...]:
    """Correct recipe: three walls, no box spanning the cavity."""
    lx, wy, hz, wall = CHANNEL_LENGTH_MM, CHANNEL_WIDTH_MM, CHANNEL_HEIGHT_MM, WALL_MM
    floor_len = lx + 2.0 * FLOOR_OVERRUN_MM
    return (
        ColliderSpec("u_floor", "box", (floor_len / 2.0, wy / 2.0, wall / 2.0),
                     pos_mm=(0.0, 0.0, wall / 2.0),
                     source=Source("derived", "floor, full width, with lead-in/out")),
        ColliderSpec("u_side_pos", "box", (lx / 2.0, wall / 2.0, hz / 2.0),
                     pos_mm=(0.0, (wy - wall) / 2.0, hz / 2.0),
                     source=Source("derived", "positive-Y side wall")),
        ColliderSpec("u_side_neg", "box", (lx / 2.0, wall / 2.0, hz / 2.0),
                     pos_mm=(0.0, -(wy - wall) / 2.0, hz / 2.0),
                     source=Source("derived", "negative-Y side wall")),
    )


def channel_fidelity() -> FidelitySpec:
    """The declared contract: cavity probes along X, a through-transit, wall surfaces."""
    z_mid = WALL_MM + CAVITY_HEIGHT_MM / 2.0
    probes = (
        ProbeSpec(
            "cavity_axis",
            tuple((-CHANNEL_LENGTH_MM / 2.0 + i * CHANNEL_LENGTH_MM / 4.0, 0.0, z_mid)
                  for i in range(5)),
            note="cavity centre line along the passage",
        ),
        ProbeSpec(
            "cavity_mouth_neg_x",
            ((0.0, 0.0, TRANSIT_Z_MM), (0.0, 0.0, z_mid)),
            note="near the -X mouth",
        ),
        ProbeSpec(
            "cavity_mouth_pos_x",
            ((0.0, 0.0, TRANSIT_Z_MM), (0.0, 0.0, z_mid)),
            note="near the +X mouth",
        ),
    )
    transits = (
        TransitSpec("through_channel", TRANSIT_START_MM, TRANSIT_END_MM, PROBE_RADIUS_MM,
                    samples=400),
    )
    # A few points on the inner face of each side wall and on the floor top: the collider must
    # sit on the CAD surface, not float off it or intrude into the cavity.
    # Points ON the CAD surfaces, not inside the cavity: the metric is "how far is the
    # nearest collider boundary from this surface", so a sample must sit on the surface for a
    # buried-surface intrusion to register.
    critical = []
    for x in (-40.0, 0.0, 40.0):
        critical.append((x, CAVITY_HALF_WIDTH_MM, WALL_MM + CAVITY_HEIGHT_MM / 2.0))
        critical.append((x, -CAVITY_HALF_WIDTH_MM, WALL_MM + CAVITY_HEIGHT_MM / 2.0))
        critical.append((x, 0.0, WALL_MM))
        critical.append((x, CAVITY_HALF_WIDTH_MM / 2.0, WALL_MM))
    return FidelitySpec(
        probes=probes,
        transits=transits,
        critical_surfaces_mm=tuple(critical),
        max_surface_deviation_mm=1.0,
        max_coverage_gap_mm=1.0,
    )


def through_path_probe_centre() -> tuple[float, float, float]:
    """Initial probe centre: outside the -X mouth, resting on the floor inside the channel.

    Height is ``wall + half-edge`` so the probe starts in contact with the floor rather than
    falling: the trial is a transit, not a drop.
    """
    return (-CHANNEL_LENGTH_MM / 2.0 - LAUNCH_GAP_MM - PROBE_RADIUS_MM, 0.0,
            WALL_MM + PROBE_RADIUS_MM)


def u_channel_spec(through_path: bool = False,
                   timestep_s: float = 1.0e-3) -> AssemblySpec:
    """The correct assembly: a fixed channel plus one free probe object.

    ``through_path=False`` drops the probe vertically into the cavity (a top-entry diagnostic).
    ``through_path=True`` starts it outside the -X mouth on the cavity axis, so a successful
    trial means the object travelled the full open length and left past the +X exit plane.

    ``timestep_s`` is propagated into the emitted solver options, so the compiled model always
    runs at the step the caller asked for. The contact time constant stays absolute, so
    refining the step does not also stiffen the contact.
    """
    return AssemblySpec(
        name="m2b_u_channel",
        bodies=(
            BodySpec(
                body_id="channel",
                parts=(PartSpec("u_channel", channel_solid(), colliders=channel_colliders(),
                                density_g_cm3=DENSITY_G_CM3,
                                source=Source("derived", "U-channel CAD")),),
                fixed_to_world=True,
                fixture="analytic_fixture",
                fidelity=channel_fidelity(),
                source=Source("derived", "fixed analytic channel fixture"),
            ),
            BodySpec(
                body_id="probe",
                parts=(PartSpec(
                    "probe",
                    Pos(*_probe_start(through_path))
                    * Box(2 * PROBE_RADIUS_MM, 2 * PROBE_RADIUS_MM, 2 * PROBE_RADIUS_MM),
                    colliders=(ColliderSpec(
                        "probe_col", "box",
                        (PROBE_RADIUS_MM, PROBE_RADIUS_MM, PROBE_RADIUS_MM),
                        pos_mm=_probe_start(through_path),
                        role="packet",
                        source=Source("derived", "cubic probe, same half-extent as the radius"),
                    ),),
                    density_g_cm3=DENSITY_G_CM3,
                    role="packet",
                    source=Source("derived", "free probe object"),
                ),),
                source=Source("derived", "free probe body"),
            ),
        ),
        timestep_s=timestep_s,
        contact_timeconst_s=CONTACT_TIMECONST_S,
        contact_dampratio=CONTACT_DAMPRATIO,
        source=Source("derived", "M2b hollow-channel fixture"),
    )


def _probe_start(through_path: bool) -> tuple[float, float, float]:
    if through_path:
        return through_path_probe_centre()
    return (0.0, 0.0, CHANNEL_HEIGHT_MM + 30.0)


def u_channel_spec_bad_recipe() -> AssemblySpec:
    """The same CAD with a deliberately wrong recipe: one box over the whole envelope."""
    good = u_channel_spec()
    channel = good.bodies[0]
    bad_part = replace(
        channel.parts[0],
        colliders=(ColliderSpec(
            "u_spanning_block", "box",
            (CHANNEL_LENGTH_MM / 2.0, CHANNEL_WIDTH_MM / 2.0, CHANNEL_HEIGHT_MM / 2.0),
            pos_mm=(0.0, 0.0, CHANNEL_HEIGHT_MM / 2.0),
            source=Source("derived", "DELIBERATELY WRONG: single box over the cavity"),
        ),),
    )
    return replace(good, bodies=(replace(channel, parts=(bad_part,)), *good.bodies[1:]))


def rotated_u_channel_spec() -> AssemblySpec:
    """The correct assembly with the channel rotated, so local/world confusion fails."""
    good = u_channel_spec()
    frame = Frame(pos_mm=(250.0, -120.0, 60.0), rot_deg=(0.0, 0.0, 37.0))
    channel = good.bodies[0]
    moved_parts = []
    for part in channel.parts:
        moved_parts.append(replace(part, shape=frame.location() * part.shape))
    return replace(
        good,
        bodies=(
            replace(channel, parts=tuple(moved_parts), frame=frame),
            good.bodies[1],
        ),
    )


def write_channel_stl(path) -> "object":
    """Write the original U-channel as a binary STL in **millimetres** (the CAD's own unit)."""
    from pathlib import Path

    from build123d import export_stl

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    export_stl(channel_solid(), str(path), tolerance=0.02, angular_tolerance=0.1,
               ascii_format=False)
    return path


def concave_mesh_diagnostic_xml(mesh_file: str = "u_channel.stl",
                                through_path: bool = True,
                                timestep_s: float = 1.0e-3) -> str:
    """TEST-ONLY diagnostic MJCF: collide the real U-channel **mesh** as MuJoCo does.

    This is the actual failure mode: a single concave mesh used as a collision geom is
    replaced by its convex hull, sealing the cavity. The scene references the original CAD STL
    with the same ``scale`` the production exporter uses, and the same probe and contact
    settings as the correct recipe, so the two trials differ only in the collider.

    It is produced only by the M2b evidence runner and the tests; ``cadkit.physics.scene``
    never emits a mesh collision geom, and no CLI path can select this scene.
    """
    from .hollow_run import probe_start_mm

    start = probe_start_mm(through_path)
    r = PROBE_RADIUS_MM / 1000.0
    edge_mm = 2.0 * PROBE_RADIUS_MM
    mass_kg = edge_mm ** 3 * DENSITY_G_CM3 * 1e-6
    inertia = mass_kg * (edge_mm / 1000.0) ** 2 / 6.0
    scale = mm_to_m(1.0)
    return f"""<mujoco model="m2b_concave_mesh_diagnostic">
  <!-- TEST-ONLY DIAGNOSTIC. Not a design of record, not reachable from the CLI.
       Collides the ORIGINAL U-channel STL as type="mesh"; MuJoCo replaces it with its
       convex hull, which seals the cavity. Produced by cadkit.physics.hollow_run only. -->
  <compiler angle="degree" coordinate="local"/>
  <option timestep="{timestep_s:.9g}" integrator="RK4" cone="elliptic" solver="Newton"
          iterations="100" gravity="0 0 -9.80665"/>
  <default>
    <geom condim="3" solref="{CONTACT_TIMECONST_S:.9g} {CONTACT_DAMPRATIO:.9g}"
          solimp="0.95 0.99 0.001" friction="0.4 0.005 0.0001"/>
  </default>
  <asset>
    <mesh name="u_channel_mesh" file="{mesh_file}"
          scale="{scale:.9g} {scale:.9g} {scale:.9g}"/>
  </asset>
  <worldbody>
    <geom name="u_channel_hull" type="mesh" mesh="u_channel_mesh"
          contype="1" conaffinity="1" condim="3"/>
    <body name="probe" pos="{start[0] / 1000.0:.9g} {start[1] / 1000.0:.9g} {start[2] / 1000.0:.9g}">
      <freejoint name="probe_free"/>
      <inertial pos="0 0 0" mass="{mass_kg:.9g}"
                diaginertia="{inertia:.9g} {inertia:.9g} {inertia:.9g}"/>
      <geom name="probe_geom" type="box" size="{r:.9g} {r:.9g} {r:.9g}"
            contype="1" conaffinity="1" condim="3"/>
    </body>
  </worldbody>
</mujoco>
"""

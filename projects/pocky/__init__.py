"""Pocky packet dispenser: a manual spring-return mechanism that ejects one packet from a stack."""
from __future__ import annotations

from cadkit.project import Project

from . import models
from .params import DEFAULT_PARAMS_PATH, load_params


def _ghost_meshes(p):
    from cadkit.mesh import shape_to_mesh

    from .geometry.linkage import ghost_packet_shapes

    bottom, second = ghost_packet_shapes(p)
    return [
        (shape_to_mesh(bottom), "#1f4e79", 0.35),
        (shape_to_mesh(second), "#c45911", 0.28),
    ]


def _physics(model_name, p):
    """Lazy physics assembly: the ``prototype``, ``syringe`` and ``syringe3`` models have one."""
    if model_name == "syringe":
        from .physics.syringe_assembly import syringe_assembly

        return syringe_assembly(p)
    if model_name == "syringe3":
        from .physics.syringe3_assembly import syringe_assembly

        return syringe_assembly(p)
    if model_name != "prototype":
        return None
    from .physics.assembly import prototype_assembly

    return prototype_assembly(p)


def _physics_with_options(model_name, p, options):
    """Strict option path for ``cad physics run``; unsupported options are rejected.

    The ``syringe`` model reuses the prototype's option keys: ``button_actuator`` enables its
    ``pull`` actuator and ``chassis_clamped`` clamps its housing. ``separator`` is for the syringe models only (``syringe``, ``syringe3``).
    """
    if model_name not in ("prototype", "syringe", "syringe3"):
        return None
    from .physics.options import load_options

    opts = load_options(options)
    if model_name in ("syringe", "syringe3"):
        if model_name == "syringe3":
            from .physics.syringe3_assembly import syringe_assembly
        else:
            from .physics.syringe_assembly import syringe_assembly

        return syringe_assembly(
            p, spring_stiffness_n_m=opts.spring_stiffness_n_m, timestep_s=opts.timestep_s,
            contact_timeconst_s=opts.contact_timeconst_s, stop_timeconst_s=opts.stop_timeconst_s,
            pull_actuator=opts.button_actuator, packets=opts.packets,
            packet_mass_kg=opts.packet_mass_kg, housing_clamped=opts.chassis_clamped,
            separator=opts.separator,
        )
    if options is not None and "separator" in options:
        raise ValueError(
            "assembly option 'separator' applies to the syringe model only; the prototype's "
            "separator is its fixed lip blade"
        )
    from .physics.assembly import prototype_assembly

    return prototype_assembly(
        p, spring_stiffness_n_m=opts.spring_stiffness_n_m, timestep_s=opts.timestep_s,
        contact_timeconst_s=opts.contact_timeconst_s, stop_timeconst_s=opts.stop_timeconst_s,
        button_actuator=opts.button_actuator, packets=opts.packets,
        packet_mass_kg=opts.packet_mass_kg, chassis_clamped=opts.chassis_clamped,
    )


PROJECT = Project(
    name="pocky",
    params_path=DEFAULT_PARAMS_PATH,
    load_params=load_params,
    models=models,
    ghost_meshes=_ghost_meshes,
    physics=_physics,
    physics_with_options=_physics_with_options,
)

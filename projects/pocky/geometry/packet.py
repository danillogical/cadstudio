"""Rigid packet envelope solids (not a foil simulation)."""
from __future__ import annotations

from build123d import Align, Box, Pos, Solid

from projects.pocky.params import Params


def packet(p: Params) -> Solid:
    """One packet box, centred in X and Y, spanning ``z = 0 .. packet.height``."""
    k = p.packet
    return Box(k.length, k.width, k.height, align=(Align.CENTER, Align.CENTER, Align.MIN)).solid()


def packet_stack(p: Params, n: int, gap: float = 0.0) -> list[Solid]:
    """``n`` separate packets; packet i spans ``z = i*(height+gap) .. i*(height+gap)+height``."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if gap < 0:
        raise ValueError(f"gap must be >= 0, got {gap}")
    pitch = p.packet.height + gap
    base = packet(p)
    return [Pos(0, 0, i * pitch) * base for i in range(n)]

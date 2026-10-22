"""Analytic sweep of the proposed Pocky ejector linkage.

Standalone: numpy and matplotlib only. From the repo root:

    .venv/bin/python projects/pocky/docs/proposal_sweep.py

Writes proposal-diagram.png next to this file and prints the pose table.
The constants are the M0 proposal (see mechanism-proposal.md). They are not
in params.toml. The packet frame matches geometry/packet.py: origin at the
packet centre, +X toward the exit, Z up.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

# Existing params.toml values used here. Do not change that file from this script.
PACKET_L = 165.0
PACKET_W = 55.0
PACKET_H = 5.2
MAG_L = 170.0
MAG_W = 60.0
SEPARATOR_GAP = 5.75

# Proposed for M1. See mechanism-proposal.md for the derivation.
PRESENTATION = 40.0
EXIT_WALL = 3.0
POCKET_SETBACK = 2.0
LIP = 18.0
PUSHER_STROKE = PRESENTATION + EXIT_WALL + (MAG_L - PACKET_L) + POCKET_SETBACK  # 50
CRANK_R = 50.0
HALF_DEG = 30.0
INCLUDED_DEG = 180.0
BUTTON_OFFSET = -20.0  # slider line minus pivot, mm
BUTTON_Y = -28.0
PIVOT_Y = BUTTON_Y - BUTTON_OFFSET  # -8
FACE_LEAD = 16.0
FACE_W = 40.0
FACE_H = 4.2
SHIM = 0.20
SHIM_COUNT = 2
GAP_NO_SHIM = SEPARATOR_GAP - SHIM_COUNT * SHIM  # 5.35

PHI0 = np.deg2rad(90.0 + HALF_DEG)  # 120 deg, pusher retracted
PHI1 = np.deg2rad(90.0 - HALF_DEG)  # 60 deg, pusher extended
FACE0 = -MAG_L / 2.0 - POCKET_SETBACK  # -87
PIVOT_X = FACE0 - FACE_LEAD - CRANK_R * np.cos(PHI0)  # -78

OUTER_X = MAG_L / 2.0 + EXIT_WALL  # 88
PACKET_BACK = -PACKET_L / 2.0  # -82.5
HERE = Path(__file__).resolve().parent


def sweep(n: int = 201) -> dict[str, np.ndarray]:
    """Sample the press from rest to the forward stop. Button travel increases."""
    phi = np.linspace(PHI0, PHI1, n)
    pusher_pin_x = PIVOT_X + CRANK_R * np.cos(phi)
    pusher_pin_y = PIVOT_Y + CRANK_R * np.sin(phi)
    face_x = pusher_pin_x + FACE_LEAD
    theta = phi + np.deg2rad(INCLUDED_DEG)
    radius = BUTTON_OFFSET / np.sin(theta)
    button_x = PIVOT_X + radius * np.cos(theta)
    button_y = PIVOT_Y + radius * np.sin(theta)
    button_travel = button_x[0] - button_x
    crank_deg = np.rad2deg(PHI0 - phi)
    # Packet back stays put until the face reaches it, then moves with the face.
    packet_shift = np.maximum(0.0, face_x - PACKET_BACK)
    protrusion = PACKET_BACK + packet_shift + PACKET_L - OUTER_X
    d_face = np.diff(face_x)
    d_button = -np.diff(button_x)
    speed_ratio = d_face / d_button
    return {
        "phi": phi,
        "pusher_pin_x": pusher_pin_x,
        "pusher_pin_y": pusher_pin_y,
        "face_x": face_x,
        "slot_radius": radius,
        "button_x": button_x,
        "button_y": button_y,
        "button_travel": button_travel,
        "crank_deg": crank_deg,
        "packet_shift": packet_shift,
        "protrusion": protrusion,
        "speed_ratio": speed_ratio,
        "ratio_button": button_travel[:-1] + 0.5 * np.diff(button_travel),
    }


def check(s: dict[str, np.ndarray]) -> None:
    """Lock the design constraints. A failed assert means a constant drifted."""
    stroke_button = 2.0 * abs(BUTTON_OFFSET) * np.tan(np.deg2rad(HALF_DEG))
    assert abs(PUSHER_STROKE - 50.0) < 1e-9
    assert abs(s["face_x"][-1] - s["face_x"][0] - PUSHER_STROKE) < 1e-6
    assert abs(s["button_travel"][-1] - stroke_button) < 1e-6
    assert np.all(np.diff(s["face_x"]) > 0)
    assert np.all(np.diff(s["button_x"]) < 0)
    assert np.allclose(s["button_y"], BUTTON_Y)
    # No dead point: both slots stay at least 30 deg off the slider axis.
    assert np.min(np.abs(np.sin(s["phi"]))) > 0.85
    assert np.min(np.abs(s["pusher_pin_y"] - PIVOT_Y)) > 40.0
    ratio = s["speed_ratio"]
    assert ratio.min() > 1.6 and ratio.max() < 2.51
    # Pins never need the ends of their slots. Margins are applied in the drawing.
    assert s["slot_radius"].max() - s["slot_radius"].min() < 3.2
    assert s["pusher_pin_y"].max() - s["pusher_pin_y"].min() < 7.0
    assert abs(s["protrusion"][-1] - PRESENTATION) < 1e-6
    # At rest the face is behind the packet; at the stop the packet is presented.
    assert s["face_x"][0] < PACKET_BACK
    assert s["packet_shift"][0] == 0.0


def _pose_indices(n: int) -> list[int]:
    return [int(round(i * (n - 1) / 4)) for i in range(5)]


def _draw(s: dict[str, np.ndarray], path: Path) -> None:
    plt.rcParams.update({
        "font.size": 8.5,
        "axes.titlesize": 10,
        "axes.labelsize": 8.5,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })
    colors = ["#1f4e79", "#2e75b6", "#7faddb", "#ed7d31", "#c45911"]
    idx = _pose_indices(len(s["phi"]))
    fig = plt.figure(figsize=(15.2, 9.0))
    grid = fig.add_gridspec(3, 2, height_ratios=[1.15, 1.05, 1.05], width_ratios=[1.45, 1.0], wspace=0.28, hspace=0.42)
    ax = fig.add_subplot(grid[0:2, 0])
    ax_ang = fig.add_subplot(grid[0, 1])
    ax_ratio = fig.add_subplot(grid[1, 1])
    ax_side = fig.add_subplot(grid[2, :])

    # --- plan view ---
    mag = Rectangle((-MAG_L / 2, -MAG_W / 2), MAG_L, MAG_W, facecolor="#f2f2f2", edgecolor="#666666", lw=1.0, zorder=0)
    ax.add_patch(mag)
    wall = Rectangle((MAG_L / 2, -MAG_W / 2), EXIT_WALL, MAG_W, facecolor="#d9d9d9", edgecolor="#666666", lw=0.8, zorder=1)
    ax.add_patch(wall)
    lip = Rectangle((OUTER_X, -29), LIP, 58, facecolor="#e7f0e7", edgecolor="#548235", lw=0.8, zorder=1)
    ax.add_patch(lip)
    slot = Rectangle((-96, -3.5), 62, 7.0, facecolor="none", edgecolor="#888888", lw=0.7, ls="--", zorder=2)
    ax.add_patch(slot)

    def packet_rect(shift: float, face: str, edge: str, alpha: float) -> None:
        ax.add_patch(Rectangle(
            (PACKET_BACK + shift, -PACKET_W / 2), PACKET_L, PACKET_W,
            facecolor=face, edgecolor=edge, lw=1.0, alpha=alpha, zorder=3,
        ))

    packet_rect(float(s["packet_shift"][-1]), "#fde4d4", "#c45911", 0.55)
    packet_rect(0.0, "#d6e6f5", "#1f4e79", 0.35)

    stroke = float(s["button_travel"][-1])
    for k, i in enumerate(idx):
        c = colors[k]
        ax.plot(
            [PIVOT_X, s["pusher_pin_x"][i]], [PIVOT_Y, s["pusher_pin_y"][i]],
            color=c, lw=1.3, ls="--", zorder=4,
        )
        ax.plot(
            [PIVOT_X, s["button_x"][i]], [PIVOT_Y, BUTTON_Y],
            color=c, lw=1.1, ls="--", zorder=4,
        )
        ax.plot(s["pusher_pin_x"][i], s["pusher_pin_y"][i], "o", color=c, ms=4.5, zorder=5)
        ax.plot(s["button_x"][i], BUTTON_Y, "o", color=c, ms=4.0, zorder=5)
        y0 = -FACE_W / 2
        ax.plot([s["face_x"][i], s["face_x"][i]], [y0, -y0], color=c, lw=3.2, solid_capstyle="round", zorder=6)
        travel = float(s["button_travel"][i])
        head_in = OUTER_X + 3.0 + (stroke - travel)
        ax.plot([s["button_x"][i], head_in], [BUTTON_Y, BUTTON_Y], color=c, lw=1.0, ls="--", zorder=4)
        if k in (0, 4):
            ax.add_patch(FancyBboxPatch(
                (head_in, BUTTON_Y - 6.5), 14, 13,
                boxstyle="round,pad=0,rounding_size=2",
                facecolor=c, edgecolor="none", alpha=0.95, zorder=6,
            ))
            ax.plot([s["button_x"][i], head_in], [BUTTON_Y, BUTTON_Y], color=c, lw=1.3, zorder=4)

    ax.plot(PIVOT_X, PIVOT_Y, "o", color="black", ms=7, zorder=7)
    ax.annotate(
        "pivot",
        (PIVOT_X, PIVOT_Y),
        xytext=(-114, 6),
        fontsize=8,
        color="black",
        arrowprops={"arrowstyle": "->", "lw": 0.6, "color": "black"},
    )
    ax.annotate(
        "press (−X)",
        (OUTER_X + 32, BUTTON_Y + 6),
        xytext=(OUTER_X + 32, BUTTON_Y - 14),
        fontsize=8, color="#c45911", ha="center",
        arrowprops={"arrowstyle": "->", "color": "#c45911", "lw": 0.8},
    )
    ax.text(OUTER_X + 2, 22, "exit +X", fontsize=8, color="#548235")
    ax.text(-58, 46, "40 mm faces, straight path", fontsize=7.5, color="#1f4e79", ha="center")
    ax.text(float(s["face_x"][idx[0]]), -40, "0%", fontsize=7.5, color=colors[0], ha="center")
    ax.text(float(s["face_x"][idx[-1]]), -40, "100%", fontsize=7.5, color=colors[-1], ha="center")
    ax.set_aspect("equal")
    ax.set_xlim(-118, 155)
    ax.set_ylim(-50, 52)
    ax.set_xlabel("X (mm). Dashed: below the floor. Solid bars: pusher face. Blue outline at rest, orange presented.")
    ax.set_ylabel("Y (mm)")
    ax.set_title("Plan view — poses at 0 / 25 / 50 / 75 / 100% of the button stroke")

    # --- crank angle ---
    ax_ang.plot(s["button_travel"], s["crank_deg"], color="#1f4e79", lw=1.8)
    ax_ang.set_xlabel("button travel (mm)")
    ax_ang.set_ylabel("crank rotation (deg)")
    ax_ang.set_title("Crank rotation vs button travel")
    ax_ang.set_xlim(0, float(s["button_travel"][-1]) + 0.5)
    ax_ang.set_ylim(0, 70)
    ax_ang.grid(True, lw=0.4, alpha=0.6)
    ax_ang.axvline(float(s["button_travel"][-1]), color="#999999", lw=0.6, ls=":")

    # --- speed ratio ---
    ax_ratio.plot(s["ratio_button"], s["speed_ratio"], color="#c45911", lw=1.8)
    overall = PUSHER_STROKE / float(s["button_travel"][-1])
    ax_ratio.axhline(overall, color="#1f4e79", lw=0.8, ls="--", label=f"overall {overall:.2f}")
    ax_ratio.set_xlabel("button travel (mm)")
    ax_ratio.set_ylabel("pusher speed / button speed")
    ax_ratio.set_title("Speed ratio (ideal, no friction)")
    ax_ratio.set_xlim(0, float(s["button_travel"][-1]) + 0.5)
    ax_ratio.set_ylim(1.2, 2.8)
    ax_ratio.grid(True, lw=0.4, alpha=0.6)
    ax_ratio.legend(fontsize=7.5, loc="upper right")

    # --- side section ---
    def packet_side(shift: float, z0: float, face: str, edge: str, alpha: float) -> None:
        ax_side.add_patch(Rectangle(
            (PACKET_BACK + shift, z0), PACKET_L, PACKET_H,
            facecolor=face, edgecolor=edge, lw=0.8, alpha=alpha,
        ))

    ax_side.plot([-100, OUTER_X + LIP], [0, 0], color="#666666", lw=1.2)
    ax_side.plot([OUTER_X, OUTER_X + LIP], [0, 0], color="#548235", lw=3.0, solid_capstyle="butt")
    packet_side(0.0, 0.0, "#d6e6f5", "#1f4e79", 0.95)
    packet_side(0.0, PACKET_H, "#eeeeee", "#888888", 0.95)
    shift_end = float(s["packet_shift"][-1])
    ax_side.add_patch(Rectangle(
        (PACKET_BACK + shift_end, 0.0), PACKET_L, PACKET_H,
        facecolor="none", edgecolor="#c45911", lw=1.2, ls="--",
    ))
    ax_side.text(0, PACKET_H + 1.5, "next packet", fontsize=7.5, color="#666666", ha="center")
    ax_side.text(PACKET_BACK + shift_end + PACKET_L - 8, PACKET_H + 1.5, "presented", fontsize=7.5, color="#c45911", ha="right")
    # Separator lip: underside at separator.gap, held by two 0.20 mm shims above a 5.35 mm ledge.
    ax_side.add_patch(Rectangle((82, GAP_NO_SHIM), 8, 8, facecolor="#f4b183", edgecolor="#c45911", lw=0.7))
    ax_side.plot([82, 90], [SEPARATOR_GAP, SEPARATOR_GAP], color="#c45911", lw=1.0)
    # Pusher heads: bullnose, rest and full stroke.
    for i, c in ((idx[0], colors[0]), (idx[-1], colors[-1])):
        cx = float(s["face_x"][i]) - FACE_H / 2.0
        circle = plt.Circle((cx, FACE_H / 2.0), FACE_H / 2.0, facecolor=c, edgecolor="none", alpha=0.9)
        ax_side.add_patch(circle)
    ax_side.annotate("separator 5.75", (90, SEPARATOR_GAP), xytext=(108, 12.5), fontsize=7.5, arrowprops={"arrowstyle": "->", "lw": 0.5})
    ax_side.annotate("pusher rest", (float(s["face_x"][idx[0]]) - FACE_H / 2, FACE_H / 2), xytext=(-112, 10), fontsize=7.5, color=colors[0], arrowprops={"arrowstyle": "->", "lw": 0.5, "color": colors[0]})
    ax_side.annotate("pusher 100%", (float(s["face_x"][idx[-1]]) - FACE_H / 2, FACE_H / 2), xytext=(-20, 12.5), fontsize=7.5, color=colors[-1], arrowprops={"arrowstyle": "->", "lw": 0.5, "color": colors[-1]})
    ax_side.text(OUTER_X + LIP / 2, 2.2, "lip", fontsize=7.5, color="#548235", ha="center")
    ax_side.set_xlim(-120, 155)
    ax_side.set_ylim(-3, 18)
    ax_side.set_xlabel("X (mm)")
    ax_side.set_ylabel("Z (mm, exaggerated)")
    ax_side.set_title("Side section on Y = 0. Z is stretched so the 5.2 mm packet and the 5.75 mm gap are visible.")

    fig.suptitle("Pocky dispenser mechanism proposal (original linkage, not the reference)", fontsize=12, y=0.98)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    s = sweep()
    check(s)
    out = HERE / "proposal-diagram.png"
    _draw(s, out)
    stroke_button = float(s["button_travel"][-1])
    idx = _pose_indices(len(s["phi"]))
    print(f"pusher_stroke {PUSHER_STROKE:.4f}")
    print(f"button_stroke {stroke_button:.4f}")
    print(f"overall_ratio {PUSHER_STROKE / stroke_button:.4f}")
    print(f"speed_ratio_min {s['speed_ratio'].min():.4f}")
    print(f"speed_ratio_max {s['speed_ratio'].max():.4f}")
    print(f"pivot {PIVOT_X:.4f} {PIVOT_Y:.4f}")
    print(f"slot_radius {s['slot_radius'].min():.4f} {s['slot_radius'].max():.4f}")
    print(f"pusher_pin_y {s['pusher_pin_y'].min():.4f} {s['pusher_pin_y'].max():.4f}")
    print(f"button_x {s['button_x'][0]:.4f} {s['button_x'][-1]:.4f}")
    print(f"face_x {s['face_x'][0]:.4f} {s['face_x'][-1]:.4f}")
    print(f"approach {PACKET_BACK - s['face_x'][0]:.4f}")
    print(f"png {out}")
    print("pct button crank face_x pin_y slot_r packet_shift protrusion")
    for k, i in enumerate(idx):
        # Instantaneous ratio is between samples; report the neighbour after this pose.
        j = min(i, len(s["speed_ratio"]) - 1)
        print(
            f"{25 * k:3d} {s['button_travel'][i]:7.3f} {s['crank_deg'][i]:6.2f} "
            f"{s['face_x'][i]:8.3f} {s['pusher_pin_y'][i]:7.3f} {s['slot_radius'][i]:7.3f} "
            f"{s['packet_shift'][i]:7.3f} {s['protrusion'][i]:7.3f} ratio {s['speed_ratio'][j]:.3f}"
        )


if __name__ == "__main__":
    main()

"""Visual audit of the same five P1 trucks used by the AC power-flow run."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from p1_multibus_dispatch import InjectionHour, TruckHour


def save_fleet_timeline(
    trucks: tuple[TruckHour, ...],
    injections: tuple[InjectionHour, ...],
    output_dir: Path,
) -> None:
    """Color shows modeled bus; a black dot shows actual HFC/ESS dispatch."""
    if len(trucks) != 168 * 5 or len(injections) != 168:
        raise ValueError("Timeline requires the complete 168-hour, five-truck P1 path")
    alpha = injections[0].alpha
    locations = np.zeros((5, 168), dtype=int)
    active_t: list[int] = []
    active_truck: list[int] = []
    for row in trucks:
        if row.alpha != alpha or row.bus not in (18, 33):
            raise ValueError("Truck rows differ from the selected P1 scenario")
        locations[row.truck, row.t] = 0 if row.bus == 18 else 1
        ess_active = row.truck == 0 and injections[row.t].ess18_kwh > 0
        if row.hfc_kwh > 0 or ess_active:
            active_t.append(row.t)
            active_truck.append(row.truck)

    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.weight": "bold",
            "axes.titlesize": 18,
            "axes.titleweight": "bold",
            "axes.labelsize": 18,
            "axes.labelweight": "bold",
            "xtick.labelsize": 16,
            "ytick.labelsize": 16,
            "legend.fontsize": 12,
        }
    )
    fig, axis = plt.subplots(figsize=(15, 5), dpi=220)
    axis.imshow(
        locations,
        aspect="auto",
        interpolation="nearest",
        origin="upper",
        extent=(-0.5, 167.5, 4.5, -0.5),
        cmap=ListedColormap(("#2574ac", "#32b16d")),
        vmin=-0.5,
        vmax=1.5,
    )
    axis.scatter(active_t, active_truck, color="black", marker="o", s=18, zorder=3)
    axis.set_yticks(range(5), ["Main truck", "Aux 1", "Aux 2", "Aux 3", "Aux 4"])
    axis.set_xticks(np.arange(0, 169, 24))
    axis.set_xlabel("Hour of 168-hour P1 simulation")
    axis.set_ylabel("Vehicle")
    axis.set_title(
        f"P1 multi-truck deployment for IEEE 33-bus power flow (α={alpha:.1f})"
    )
    axis.grid(axis="x", color="white", alpha=0.45)
    axis.legend(
        handles=[
            Patch(color="#2574ac", label="Bus 18"),
            Patch(color="#32b16d", label="Bus 33"),
            Line2D(
                [],
                [],
                color="black",
                marker="o",
                linestyle="None",
                label="HFC or ESS active",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout()
    output_dir.mkdir(exist_ok=True)
    for extension in ("png", "pdf"):
        fig.savefig(
            output_dir / f"figure_16_p1_multitruck_deployment.{extension}",
            bbox_inches="tight",
        )
    plt.close(fig)

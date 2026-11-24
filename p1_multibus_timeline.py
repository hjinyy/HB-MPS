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

from paper_figure_style import apply_paper_typography, normalize_figure_text
from p1_multibus_dispatch import InjectionHour, TruckHour


def save_fleet_timeline(
    trucks: tuple[TruckHour, ...],
    injections: tuple[InjectionHour, ...],
    output_dir: Path,
) -> None:
    """Color shows modeled bus; an orange dot shows actual HFC/ESS dispatch."""
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

    apply_paper_typography()
    fig, axis = plt.subplots(figsize=(18, 8), dpi=220)
    axis.imshow(
        locations,
        aspect="auto",
        interpolation="nearest",
        origin="upper",
        extent=(0, 168, 4.5, -0.5),
        cmap=ListedColormap(("#2574ac", "#32b16d")),
        vmin=-0.5,
        vmax=1.5,
    )
    axis.scatter(np.array(active_t) + 0.5, active_truck, color="#ff7f0e", marker="o", s=24, zorder=3)
    for boundary in (0.5, 1.5, 2.5, 3.5):
        axis.axhline(boundary, color="white", linewidth=1.5, zorder=2)
    axis.set_yticks(range(5), ["Main\ntruck", "Aux 1", "Aux 2", "Aux 3", "Aux 4"])
    axis.set_xticks(np.arange(0, 169, 24))
    axis.set_xlim(0, 168)
    axis.set_xlabel("Time (h)")
    axis.set_ylabel("Vehicle")
    axis.grid(axis="x", color="white", alpha=0.45)
    fig.legend(
        handles=[
            Patch(color="#2574ac", label="Bus 18"),
            Patch(color="#32b16d", label="Bus 33"),
            Line2D(
                [],
                [],
                color="#ff7f0e",
                marker="o",
                linestyle="None",
                label="HFC or ESS active",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    normalize_figure_text(fig)
    output_dir.mkdir(exist_ok=True)
    for extension in ("png", "pdf"):
        fig.savefig(
            output_dir / f"fig17_hourly_deployment_of_the_main_ess_hfc_truck_and_four_auxiliary_hfc_trucks.{extension}",
            bbox_inches="tight",
        )
    plt.close(fig)

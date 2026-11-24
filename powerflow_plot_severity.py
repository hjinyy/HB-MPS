"""Load, voltage, and operation panels for the separate Figure 15 experiment."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from powerflow_validation_severity import SeverityResult


def _intervals(mask: np.ndarray) -> list[tuple[int, int]]:
    """Convert consecutive active hours into horizontal timeline spans."""
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return list(
        zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True)
    )


def _style_time_axis(axis: Axes, *, show_ticks: bool) -> None:
    axis.set_xlim(0, 168)
    axis.set_xticks(np.arange(0, 169, 24))
    axis.grid(axis="x", color="#d7d7d7", linewidth=0.6)
    axis.tick_params(axis="x", labelbottom=show_ticks)


def save_severity_figure(result: SeverityResult, output_path: Path) -> None:
    """Save the two-panel validation figure without changing the original Fig. 15."""
    with plt.rc_context(
        {
            "font.family": "Times New Roman",
            "font.weight": "normal",
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 9,
            "pdf.fonttype": 42,
        }
    ):
        fig = plt.figure(figsize=(15.2, 7.0), dpi=220)
        grid = fig.add_gridspec(1, 2, width_ratios=(1.32, 1.0), wspace=0.30)
        left = grid[0].subgridspec(3, 1, height_ratios=(1.05, 2.15, 0.9), hspace=0.29)
        load_axis = fig.add_subplot(left[0])
        voltage_axis = fig.add_subplot(left[1], sharex=load_axis)
        timeline_axis = fig.add_subplot(left[2], sharex=load_axis)
        nodal_axis = fig.add_subplot(grid[1])
        hours = np.arange(len(result.hourly)) + 0.5

        industrial = result.buses.loc[result.buses.bus_type.eq("Industrial")]
        capacity = float(industrial.loc[industrial.t.eq(0), "threshold_mw"].sum())
        industrial_load = result.hourly.industrial_load_mw.to_numpy(dtype=float)
        load_axis.plot(
            hours,
            industrial_load,
            color="#1f77b4",
            linewidth=1.7,
            label="Industrial load",
        )
        load_axis.axhline(
            capacity,
            color="#333333",
            linewidth=1.2,
            linestyle="--",
            label="Grid supply capacity",
        )
        load_axis.fill_between(
            hours,
            capacity,
            industrial_load,
            where=industrial_load > capacity,
            color="#ff7f0e",
            alpha=0.28,
        )
        load_axis.set_ylabel("Power (MW)")
        load_axis.set_ylim(bottom=0)
        _style_time_axis(load_axis, show_ticks=False)
        load_axis.legend(
            loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2, frameon=False
        )

        minimum_bus = int(np.argmin(np.mean(result.baseline_profiles, axis=0)))
        for bus in range(result.baseline_profiles.shape[1]):
            if bus != minimum_bus:
                voltage_axis.plot(
                    hours,
                    result.baseline_profiles[:, bus],
                    color="#c6382b",
                    alpha=0.10,
                    linewidth=0.55,
                    label="Other bus voltages" if bus == 0 else "_nolegend_",
                )
        voltage_axis.plot(
            hours,
            result.baseline_minimum,
            color="#d62728",
            linewidth=2.2,
            label="Minimum voltage (Baseline)",
        )
        voltage_axis.plot(
            hours,
            result.supported_minimum,
            color="#1f77b4",
            linewidth=1.5,
            label="Minimum voltage (HB-MPS)",
        )
        voltage_axis.axhline(
            0.95,
            color="#222222",
            linewidth=1.0,
            linestyle="--",
            label="Voltage limit",
        )
        voltage_axis.set_ylim(0.915, 1.005)
        voltage_axis.set_yticks((0.92, 0.94, 0.96, 0.98, 1.00))
        voltage_axis.set_ylabel("Voltage (p.u.)")
        _style_time_axis(voltage_axis, show_ticks=False)
        voltage_axis.grid(axis="y", color="#dedede", linewidth=0.6)
        voltage_axis.legend(
            loc="lower left",
            bbox_to_anchor=(0, 1.01),
            ncol=2,
            frameon=False,
            columnspacing=1.3,
            handlelength=1.6,
        )

        hourly = result.hourly
        timeline = (
            (
                "Economic supply (Mode 1)",
                hourly.mode1_active.to_numpy(dtype=bool),
                "#9467bd",
            ),
            (
                "Emergency supply (Mode 2)",
                hourly.supply_active.to_numpy(dtype=bool),
                "#ff7f0e",
            ),
            (
                "Requested but unavailable",
                (hourly.mode2_trigger & ~hourly.supply_active).to_numpy(dtype=bool),
                "#777777",
            ),
        )
        for row, (_, mask, color) in enumerate(timeline):
            timeline_axis.broken_barh(
                [(start, stop - start) for start, stop in _intervals(mask)],
                (row - 0.32, 0.64),
                facecolors=color,
                edgecolors="none",
            )
        timeline_axis.set_yticks(
            range(len(timeline)), [label for label, _, _ in timeline]
        )
        timeline_axis.set_ylim(len(timeline) - 0.5, -0.5)
        timeline_axis.tick_params(axis="y", length=0)
        timeline_axis.set_xlabel("Time (h)\n(a)")
        _style_time_axis(timeline_axis, show_ticks=True)

        worst = result.worst_hour
        buses = np.arange(1, result.baseline_profiles.shape[1] + 1)
        for low, high in ((14, 18), (30, 33)):
            nodal_axis.axvspan(low - 0.45, high + 0.45, color="#ff7f0e", alpha=0.07)
        nodal_axis.plot(
            buses,
            result.baseline_profiles[worst],
            "o-",
            color="#d62728",
            linewidth=2.2,
            markersize=2.7,
            label="Baseline",
        )
        nodal_axis.plot(
            buses,
            result.supported_profiles[worst],
            "s-",
            color="#1f77b4",
            linewidth=1.5,
            markersize=2.7,
            label="With HB-MPS",
        )
        selected = np.array(sorted(set(result.injection_buses[worst])), dtype=int)
        if selected.size:
            nodal_axis.scatter(
                selected,
                result.supported_profiles[worst, selected - 1],
                color="#ff7f0e",
                edgecolor="#222222",
                linewidth=0.4,
                s=47,
                marker="^",
                zorder=5,
            )
            nodal_axis.annotate(
                "HB-MPS connection",
                xy=(selected[0], result.supported_profiles[worst, selected[0] - 1]),
                xytext=(0.03, 0.08),
                textcoords="axes fraction",
                fontsize=9,
                arrowprops={"arrowstyle": "-", "color": "#555555", "lw": 0.7},
            )
        else:
            nodal_axis.text(
                0.03,
                0.07,
                "No HB-MPS connection at this hour",
                transform=nodal_axis.transAxes,
                fontsize=9,
            )
        nodal_axis.axhline(0.95, color="#222222", linewidth=1.0, linestyle="--")
        nodal_axis.set_xlim(1, 33)
        nodal_axis.set_xticks((1, 5, 10, 15, 20, 25, 30, 33))
        nodal_axis.set_ylim(0.915, 1.005)
        nodal_axis.set_yticks((0.92, 0.94, 0.96, 0.98, 1.00))
        nodal_axis.set_xlabel("IEEE bus number\n(b)")
        nodal_axis.set_ylabel("Voltage (p.u.)")
        nodal_axis.grid(color="#dedede", linewidth=0.6)
        nodal_axis.legend(
            loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2, frameon=False
        )
        fig.subplots_adjust(left=0.15, right=0.985, bottom=0.11, top=0.90)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)

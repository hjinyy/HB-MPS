"""Load, voltage, and operation panels for the separate Figure 13 experiment."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
import numpy as np
from matplotlib.colors import TwoSlopeNorm

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


def save_severity_figure(
    result: SeverityResult, output_path: Path, *, final: bool = False
) -> None:
    """Save a six-panel validation figure, with an optional legacy layout."""
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
        if final:
            fig = plt.figure(figsize=(16.4, 10.8), dpi=220)
            grid = fig.add_gridspec(
                3,
                2,
                width_ratios=(1.22, 1.0),
                height_ratios=(1.3, 1.8, 1.05),
                hspace=0.50,
                wspace=0.33,
            )
            load_axis = fig.add_subplot(grid[0, 0])
            voltage_axis = fig.add_subplot(grid[1, 0], sharex=load_axis)
            timeline_axis = fig.add_subplot(grid[2, 0], sharex=load_axis)
            nodal_axis = fig.add_subplot(grid[0, 1])
            gain_axis = fig.add_subplot(grid[1, 1])
            deployment_axis = fig.add_subplot(grid[2, 1])
        else:
            fig = plt.figure(figsize=(15.2, 7.0), dpi=220)
            grid = fig.add_gridspec(1, 2, width_ratios=(1.32, 1.0), wspace=0.30)
            left = grid[0].subgridspec(
                3, 1, height_ratios=(1.05, 2.15, 0.9), hspace=0.29
            )
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
        _style_time_axis(load_axis, show_ticks=final)
        if final:
            load_axis.set_xlabel("Time (h)\n(a)")
        load_axis.legend(
            loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2,
            frameon=True, fancybox=False, edgecolor="black",
            facecolor="white", framealpha=1.0,
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
        _style_time_axis(voltage_axis, show_ticks=final)
        if final:
            voltage_axis.set_xlabel("Time (h)\n(c)")
        voltage_axis.grid(axis="y", color="#dedede", linewidth=0.6)
        voltage_axis.legend(
            loc="lower left",
            bbox_to_anchor=(0, 1.01),
            ncol=4,
            frameon=True,
            fancybox=False,
            edgecolor="black",
            facecolor="white",
            framealpha=1.0,
            columnspacing=1.3,
            handlelength=1.6,
        )

        hourly = result.hourly
        timeline = (
            (
                "Economic supply\n(Mode 1)",
                hourly.mode1_active.to_numpy(dtype=bool),
                "#9467bd",
            ),
            (
                "Emergency supply\n(Mode 2)",
                hourly.supply_active.to_numpy(dtype=bool),
                "#ff7f0e",
            ),
            (
                "Requested\nbut unavailable",
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
        timeline_axis.set_ylabel("Operation" if final else "")
        timeline_axis.set_xlabel("Time (h)\n(e)" if final else "Time (h)\n(a)")
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
                label="HB-MPS connection",
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
            loc="lower left", bbox_to_anchor=(0, 1.01), ncol=3,
            frameon=True, fancybox=False, edgecolor="black",
            facecolor="white", framealpha=1.0,
        )
        if final:
            gain = (result.supported_profiles - result.baseline_profiles).T
            limit = max(float(np.abs(gain).max()), 1e-8)
            image = gain_axis.imshow(
                gain,
                aspect="auto",
                origin="lower",
                interpolation="nearest",
                extent=(0, 168, 0.5, 33.5),
                cmap="RdBu_r",
                norm=TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit),
            )
            gain_axis.set_xlim(0, 168)
            gain_axis.set_xticks(np.arange(0, 169, 24))
            gain_axis.set_yticks((1, 9, 18, 25, 33))
            gain_axis.set_xlabel("Time (h)\n(d)")
            gain_axis.set_ylabel("Bus number")
            fig.colorbar(image, ax=gain_axis, pad=0.015, fraction=0.055).set_label(
                "Nodal voltage difference (p.u.)"
            )

            deployed = result.trucks.loc[
                result.trucks["mode"].isin(("Mode 1", "Mode 2"))
                & result.trucks.bus.notna()
            ]
            bus_palette = (
                "#9467bd",
                "#ff7f0e",
                "#d62728",
                "#2ca02c",
                "#17becf",
                "#1f77b4",
                "#8c564b",
                "#bcbd22",
                "#7f7f7f",
                "#e377c2",
            )
            for index, bus in enumerate(sorted(deployed.bus.astype(int).unique())):
                rows = deployed.loc[deployed.bus.eq(bus)]
                deployment_axis.scatter(
                    rows.t.to_numpy(dtype=float) + 0.5,
                    rows.truck.to_numpy(dtype=int),
                    s=38,
                    marker="s",
                    color=bus_palette[index],
                    edgecolors="#252525",
                    linewidths=0.35,
                    label=f"Bus {bus}",
                )
            for boundary in (0.5, 1.5, 2.5, 3.5):
                deployment_axis.axhline(
                    boundary, color="#dddddd", linewidth=0.7, zorder=0
                )
            deployment_axis.set_xlim(0, 168)
            deployment_axis.set_xticks(np.arange(0, 169, 24))
            deployment_axis.set_ylim(4.5, -0.5)
            deployment_axis.set_yticks(
                range(5), ("Main\ntruck", "Aux 1", "Aux 2", "Aux 3", "Aux 4")
            )
            deployment_axis.set_xlabel("Time (h)\n(f)")
            deployment_axis.set_ylabel("Vehicle")
            deployment_axis.grid(axis="x", color="#dedede", linewidth=0.6)
            deployment_axis.legend(
                loc="lower left",
                bbox_to_anchor=(0, 1.01),
                ncol=max(1, len(deployed.bus.unique())),
                frameon=True,
                fancybox=False,
                edgecolor="black",
                facecolor="white",
                framealpha=1.0,
                columnspacing=0.8,
            )
            fig.subplots_adjust(left=0.17, right=0.965, bottom=0.08, top=0.91)
        else:
            fig.subplots_adjust(left=0.15, right=0.985, bottom=0.11, top=0.90)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)

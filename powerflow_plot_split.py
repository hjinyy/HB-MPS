"""Three-panel operation and voltage figures from the dynamic IEEE 33-bus run."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
import numpy as np
from matplotlib.colors import TwoSlopeNorm

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from powerflow_plot_severity import _intervals, _style_time_axis

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from powerflow_validation_severity import SeverityResult


_STYLE = {
    "font.family": "Times New Roman",
    "font.weight": "normal",
    "axes.labelsize": 26,
    "xtick.labelsize": 22,
    "ytick.labelsize": 22,
    "legend.fontsize": 20,
    "pdf.fonttype": 42,
}
_LEGEND = {
    "loc": "lower left",
    "bbox_to_anchor": (0, 1.015),
    "frameon": True,
    "fancybox": False,
    "edgecolor": "black",
    "facecolor": "white",
    "framealpha": 1.0,
}


def _draw_industrial_load(axis: Axes, result: SeverityResult) -> None:
    hours = np.arange(len(result.hourly)) + 0.5
    industrial = result.buses.loc[result.buses.bus_type.eq("Industrial")]
    capacity = float(industrial.loc[industrial.t.eq(0), "threshold_mw"].sum())
    load = result.hourly.industrial_load_mw.to_numpy(dtype=float)
    axis.plot(hours, load, color="#1f77b4", linewidth=1.7, label="Industrial load")
    axis.axhline(
        capacity,
        color="#333333",
        linewidth=1.2,
        linestyle="--",
        label="Grid supply capacity",
    )
    axis.fill_between(
        hours, capacity, load, where=load > capacity, color="#ff7f0e", alpha=0.28
    )
    axis.set_ylim(bottom=0)
    axis.set_ylabel("Power (MW)")
    axis.set_xlabel("Time (h)\n(a)")
    _style_time_axis(axis, show_ticks=True)
    axis.legend(ncol=2, **_LEGEND)


def _draw_operation_timeline(axis: Axes, result: SeverityResult) -> None:
    hourly = result.hourly
    states = (
        (
            "Mode 1",
            hourly.mode1_active.to_numpy(dtype=bool),
            "#9467bd",
        ),
        (
            "Mode 2",
            hourly.supply_active.to_numpy(dtype=bool),
            "#ff7f0e",
        ),
        (
            "unserved\nenergy",
            (hourly.mode2_trigger & ~hourly.supply_active).to_numpy(dtype=bool),
            "#777777",
        ),
    )
    for row, (_, mask, color) in enumerate(states):
        axis.broken_barh(
            [(start, stop - start) for start, stop in _intervals(mask)],
            (row - 0.32, 0.64),
            facecolors=color,
            edgecolors="none",
        )
    axis.set_yticks(range(len(states)), [label for label, _, _ in states])
    axis.set_ylim(len(states) - 0.5, -0.5)
    axis.tick_params(axis="y", length=0)
    axis.set_ylabel("Operation")
    axis.set_xlabel("Time (h)\n(b)")
    _style_time_axis(axis, show_ticks=True)


def _draw_truck_deployment(axis: Axes, result: SeverityResult) -> None:
    deployed = result.trucks.loc[
        result.trucks["mode"].isin(("Mode 1", "Mode 2"))
        & result.trucks.bus.notna()
    ]
    palette = (
        "#9467bd", "#ff7f0e", "#d62728", "#2ca02c", "#17becf",
        "#1f77b4", "#8c564b", "#bcbd22", "#7f7f7f", "#e377c2",
    )
    for index, bus in enumerate(sorted(deployed.bus.astype(int).unique())):
        rows = deployed.loc[deployed.bus.eq(bus)]
        axis.scatter(
            rows.t.to_numpy(dtype=float) + 0.5,
            rows.truck.to_numpy(dtype=int),
            s=38,
            marker="s",
            color=palette[index],
            edgecolors="#252525",
            linewidths=0.35,
            label=f"Bus {bus}",
        )
    for boundary in (0.5, 1.5, 2.5, 3.5):
        axis.axhline(boundary, color="#dddddd", linewidth=0.7, zorder=0)
    axis.set_xlim(0, 168)
    axis.set_xticks(np.arange(0, 169, 24))
    axis.set_ylim(4.5, -0.5)
    axis.set_yticks(range(5), ("Main\ntruck", "Aux 1", "Aux 2", "Aux 3", "Aux 4"))
    axis.set_xlabel("Time (h)\n(c)")
    axis.set_ylabel("Vehicle")
    axis.grid(axis="x", color="#dedede", linewidth=0.6)
    if not deployed.empty:
        axis.legend(ncol=max(1, len(deployed.bus.unique())), columnspacing=0.8, **_LEGEND)


def save_operation_figure(result: SeverityResult, output_path: Path) -> None:
    """Save load trigger, operation timeline, and truck locations as Fig. 13."""
    with plt.rc_context(_STYLE):
        fig = plt.figure(figsize=(13.5, 12), dpi=220)
        grid = fig.add_gridspec(3, 1, height_ratios=(1.15, 0.95, 1.15), hspace=1.0)
        load_axis = fig.add_subplot(grid[0])
        timeline_axis = fig.add_subplot(grid[1])
        deployment_axis = fig.add_subplot(grid[2])
        _draw_industrial_load(load_axis, result)
        _draw_operation_timeline(timeline_axis, result)
        _draw_truck_deployment(deployment_axis, result)
        fig.subplots_adjust(left=0.19, right=0.965, bottom=0.07, top=0.91)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)


def _draw_nodal_profile(axis: Axes, result: SeverityResult) -> None:
    worst = result.worst_hour
    buses = np.arange(1, result.baseline_profiles.shape[1] + 1)
    for low, high in ((14, 18), (30, 33)):
        axis.axvspan(low - 0.45, high + 0.45, color="#ff7f0e", alpha=0.07)
    axis.plot(
        buses,
        result.baseline_profiles[worst],
        "o-",
        color="#d62728",
        linewidth=2.2,
        markersize=2.7,
        label="Baseline",
    )
    axis.plot(
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
        axis.scatter(
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
        axis.text(
            0.03, 0.07, "No HB-MPS connection at this hour",
            transform=axis.transAxes, fontsize=18,
        )
    axis.axhline(0.95, color="#222222", linewidth=1.0, linestyle="--")
    axis.set_xlim(1, 33)
    axis.set_xticks((1, 5, 10, 15, 20, 25, 30, 33))
    axis.set_ylim(0.915, 1.005)
    axis.set_yticks((0.92, 0.94, 0.96, 0.98, 1.00))
    axis.set_xlabel("IEEE bus number\n(a)")
    axis.set_ylabel("Voltage (p.u.)")
    axis.grid(color="#dedede", linewidth=0.6)
    axis.legend(ncol=3, **_LEGEND)


def _draw_minimum_voltage(axis: Axes, result: SeverityResult) -> None:
    hours = np.arange(len(result.hourly)) + 0.5
    minimum_bus = int(np.argmin(np.mean(result.baseline_profiles, axis=0)))
    for bus in range(result.baseline_profiles.shape[1]):
        if bus != minimum_bus:
            axis.plot(
                hours,
                result.baseline_profiles[:, bus],
                color="#c6382b",
                alpha=0.10,
                linewidth=0.55,
                label="Other bus voltages" if bus == 0 else "_nolegend_",
            )
    axis.plot(
        hours,
        result.baseline_minimum,
        color="#d62728",
        linewidth=2.2,
        label="Minimum voltage (Baseline)",
    )
    axis.plot(
        hours,
        result.supported_minimum,
        color="#1f77b4",
        linewidth=1.5,
        label="Minimum voltage (HB-MPS)",
    )
    axis.axhline(
        0.95, color="#222222", linewidth=1.0, linestyle="--", label="Voltage limit"
    )
    axis.set_ylim(0.915, 1.005)
    axis.set_yticks((0.92, 0.94, 0.96, 0.98, 1.00))
    axis.set_ylabel("Voltage (p.u.)")
    axis.set_xlabel("Time (h)\n(b)")
    _style_time_axis(axis, show_ticks=True)
    axis.grid(axis="y", color="#dedede", linewidth=0.6)
    axis.legend(ncol=2, columnspacing=1.3, handlelength=1.6, **_LEGEND)


def save_voltage_figure(result: SeverityResult, output_path: Path) -> None:
    """Save nodal, temporal, and spatiotemporal voltage effects as Fig. 14."""
    with plt.rc_context(_STYLE):
        fig = plt.figure(figsize=(13.5, 13.5), dpi=220)
        grid = fig.add_gridspec(3, 1, height_ratios=(1.15, 1.45, 1.35), hspace=1.1)
        nodal_axis = fig.add_subplot(grid[0])
        minimum_axis = fig.add_subplot(grid[1])
        gain_axis = fig.add_subplot(grid[2])
        _draw_nodal_profile(nodal_axis, result)
        _draw_minimum_voltage(minimum_axis, result)
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
        gain_axis.set_xlabel("Time (h)\n(c)")
        gain_axis.set_ylabel("Bus number")
        fig.colorbar(image, ax=gain_axis, pad=0.015, fraction=0.035).set_label(
            "Nodal voltage difference (p.u.)"
        )
        fig.subplots_adjust(left=0.12, right=0.94, bottom=0.07, top=0.91)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)

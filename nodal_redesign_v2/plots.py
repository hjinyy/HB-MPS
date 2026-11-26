"""Paper-style, case-specific IEEE 33-bus Figs. 12–14."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandapower.networks as nw
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from powerflow_plot_split import (
    _LEGEND,
    _STYLE,
    _align_panel_gaps,
    _draw_industrial_load,
    _draw_minimum_voltage,
)
from powerflow_plot_severity import _intervals, _style_time_axis

from .experiment import CaseRun, GRID_CHARGE_BUS


def _save(fig: plt.Figure, directory: Path, stem: str) -> None:
    fig.savefig(directory / f"{stem}.png", dpi=220, bbox_inches="tight")
    fig.savefig(
        directory / f"{stem}.pdf", bbox_inches="tight",
        metadata={"CreationDate": None},
    )
    plt.close(fig)


def _positions() -> dict[int, tuple[float, float]]:
    positions = {bus: (float(bus - 1), 0.0) for bus in range(1, 19)}
    positions.update({bus: (float(bus - 17), 2.0) for bus in range(19, 23)})
    positions.update({bus: (float(bus - 20), -1.8) for bus in range(23, 26)})
    positions.update({bus: (float(bus - 20), -3.6) for bus in range(26, 34)})
    return positions


def save_configuration(run: CaseRun, directory: Path) -> None:
    """Show preserved topology, load types and dynamic connection candidates."""
    net = nw.case33bw()
    positions = _positions()
    open_lines = set(
        int(element) for element in net.switch.loc[
            net.switch.et.eq("l") & ~net.switch.closed, "element"
        ]
    )
    with plt.rc_context({**_STYLE, "font.size": 15, "legend.fontsize": 14}):
        fig, axis = plt.subplots(figsize=(16, 8.1), dpi=220)
        for index, line in net.line.iterrows():
            start, end = positions[int(line.from_bus) + 1], positions[int(line.to_bus) + 1]
            is_open = index in open_lines or not line.in_service
            axis.plot(
                (start[0], end[0]), (start[1], end[1]),
                color="#b6bdc6" if is_open else "#596579",
                linestyle="--" if is_open else "-",
                linewidth=1.0 if is_open else 1.8,
                zorder=1,
            )
        industrial = set(run.case.industrial_buses)
        for bus in range(1, 34):
            x, y = positions[bus]
            color = "#374151" if bus == 1 else "#ff7f0e" if bus in industrial else "#1f77b4"
            axis.scatter(x, y, s=275, color=color, edgecolor="black", linewidth=0.7, zorder=3)
            axis.text(x, y, str(bus), ha="center", va="center", color="white", fontsize=12, zorder=4)
        for bus, marker, color in ((7, "^", "#2ca02c"), (GRID_CHARGE_BUS, "s", "#9467bd")):
            x, y = positions[bus]
            axis.plot((x, x), (y + 0.2, y + 0.55), color=color, linewidth=1.2)
            axis.scatter(x, y + 0.68, s=180, marker=marker, color=color,
                         edgecolor="black", linewidth=0.6, zorder=5)
        axis.set_xlim(-0.7, 17.7)
        axis.set_ylim(-4.5, 3.1)
        axis.set_aspect("equal")
        axis.axis("off")
        handles = [
            Line2D([], [], color="none", marker="o", markerfacecolor="#374151", markeredgecolor="black", markersize=10, label="Slack bus"),
            Line2D([], [], color="none", marker="o", markerfacecolor="#1f77b4", markeredgecolor="black", markersize=10, label="Residential (Mode 1)"),
            Line2D([], [], color="none", marker="o", markerfacecolor="#ff7f0e", markeredgecolor="black", markersize=10, label="Industrial (dynamic Mode 2 connection)"),
            Line2D([], [], color="none", marker="^", markerfacecolor="#2ca02c", markeredgecolor="black", markersize=10, label="Bus 7: PV, ESS charging, P2G"),
            Line2D([], [], color="none", marker="s", markerfacecolor="#9467bd", markeredgecolor="black", markersize=10, label="Bus 9: Grid ESS charging"),
            Line2D([], [], color="#b6bdc6", linestyle="--", linewidth=1.0, label="Normally open tie"),
        ]
        axis.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.01),
                    ncol=3, frameon=True, fancybox=False, edgecolor="black",
                    facecolor="white", framealpha=1.0)
        _save(fig, directory, "fig12_ieee_33_bus_configuration")


def _draw_deployment(axis: plt.Axes, run: CaseRun) -> None:
    deployed = run.result.trucks.loc[
        run.result.trucks["mode"].isin(("Mode 1", "Mode 2"))
        & run.result.trucks.bus.notna()
    ]
    buses = sorted(deployed.bus.astype(int).unique())
    colors = plt.get_cmap("tab20", max(len(buses), 1))
    for index, bus in enumerate(buses):
        rows = deployed.loc[deployed.bus.eq(bus)]
        axis.scatter(
            rows.t.to_numpy(dtype=float) + 0.5,
            rows.truck.to_numpy(dtype=int),
            s=38, marker="s", color=colors(index), edgecolors="#252525",
            linewidths=0.35, label=f"Bus {bus}",
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
    if buses:
        axis.legend(ncol=(len(buses) + 1) // 2, columnspacing=0.8, **_LEGEND)


def _draw_operation_timeline(axis: plt.Axes, run: CaseRun) -> None:
    hourly = run.result.hourly
    states = [
        ("Mode 1", hourly.mode1_active.to_numpy(dtype=bool), "#9467bd"),
        ("Mode 2", hourly.supply_active.to_numpy(dtype=bool), "#ff7f0e"),
    ]
    unavailable = (hourly.mode2_trigger & ~hourly.supply_active).to_numpy(dtype=bool)
    if unavailable.any():
        states.append(("No supply", unavailable, "#777777"))
    for row, (_, mask, color) in enumerate(states):
        axis.broken_barh(
            [(start, stop - start) for start, stop in _intervals(mask)],
            (row - 0.32, 0.64), facecolors=color, edgecolors="none",
        )
    axis.set_yticks(range(len(states)), [label for label, _, _ in states])
    axis.set_ylim(len(states) - 0.5, -0.5)
    axis.tick_params(axis="y", length=0)
    axis.set_ylabel("Operation")
    axis.set_xlabel("Time (h)\n(b)")
    _style_time_axis(axis, show_ticks=True)


def save_operation(run: CaseRun, directory: Path) -> None:
    """Fig. 13: why, when and where the fleet supplies the network."""
    with plt.rc_context(_STYLE):
        fig = plt.figure(figsize=(13.5, 12), dpi=220)
        grid = fig.add_gridspec(3, 1, height_ratios=(1.15, 0.95, 1.15), hspace=1.0)
        load_axis, timeline_axis, deployment_axis = (
            fig.add_subplot(grid[index]) for index in range(3)
        )
        _draw_industrial_load(load_axis, run.result)
        _draw_operation_timeline(timeline_axis, run)
        _draw_deployment(deployment_axis, run)
        fig.subplots_adjust(left=0.19, right=0.965, bottom=0.07, top=0.91)
        _align_panel_gaps(fig, load_axis, timeline_axis, deployment_axis)
        _save(fig, directory, "fig13_operation_and_nodal_deployment")


def _ranges(buses: tuple[int, ...]) -> list[tuple[int, int]]:
    ordered = sorted(buses)
    ranges: list[tuple[int, int]] = []
    start = end = ordered[0]
    for bus in ordered[1:]:
        if bus == end + 1:
            end = bus
        else:
            ranges.append((start, end))
            start = end = bus
    ranges.append((start, end))
    return ranges


def _draw_nodal_profile(axis: plt.Axes, run: CaseRun) -> None:
    result = run.result
    worst = result.worst_hour
    buses = np.arange(1, 34)
    for low, high in _ranges(run.case.industrial_buses):
        axis.axvspan(low - 0.45, high + 0.45, color="#ff7f0e", alpha=0.07)
    axis.plot(buses, result.baseline_profiles[worst], "o-", color="#d62728",
              linewidth=2.2, markersize=2.7, label="Baseline")
    axis.plot(buses, result.supported_profiles[worst], "s-", color="#1f77b4",
              linewidth=1.5, markersize=2.7, label="With HB-MPS")
    selected = np.array(sorted(set(result.injection_buses[worst])), dtype=int)
    if selected.size:
        axis.scatter(selected, result.supported_profiles[worst, selected - 1],
                     color="#ff7f0e", edgecolor="#222222", linewidth=0.4,
                     s=47, marker="^", zorder=5, label="HB-MPS connection")
    axis.axhline(0.95, color="#222222", linewidth=1.0, linestyle="--")
    axis.set_xlim(1, 33)
    axis.set_xticks((1, 5, 10, 15, 20, 25, 30, 33))
    voltage_floor = min(float(result.baseline_profiles[worst].min()),
                        float(result.supported_profiles[worst].min()))
    axis.set_ylim(min(0.915, voltage_floor - 0.005), 1.005)
    if "pv_potential_mw" in result.hourly:
        axis.set_ylim(
            min(0.915, voltage_floor - 0.005),
            max(1.005, float(result.baseline_profiles[worst].max()) + 0.005,
                float(result.supported_profiles[worst].max()) + 0.005),
        )
    axis.set_xlabel("IEEE bus number\n(a)")
    axis.set_ylabel("Voltage (p.u.)")
    axis.grid(color="#dedede", linewidth=0.6)
    axis.legend(ncol=3, **_LEGEND)


def save_voltage(run: CaseRun, directory: Path) -> None:
    """Fig. 14: spatial, temporal and spatiotemporal AC voltage changes."""
    result = run.result
    with plt.rc_context(_STYLE):
        fig = plt.figure(figsize=(13.5, 13.5), dpi=220)
        grid = fig.add_gridspec(3, 1, height_ratios=(1.45, 1.45, 1.35), hspace=1.1)
        nodal_axis, minimum_axis, gain_axis = (
            fig.add_subplot(grid[index]) for index in range(3)
        )
        _draw_nodal_profile(nodal_axis, run)
        _draw_minimum_voltage(minimum_axis, result)
        voltage_floor = min(0.915, float(result.baseline_profiles.min()) - 0.005)
        if "pv_potential_mw" in result.hourly:
            voltage_ceiling = max(
                1.055, float(result.baseline_profiles.max()) + 0.005,
                float(result.supported_profiles.max()) + 0.005,
            )
            minimum_axis.set_ylim(voltage_floor, voltage_ceiling)
            minimum_axis.set_yticks((0.92, 0.95, 1.00, 1.05))
            minimum_axis.axhline(1.05, color="#228b22", linestyle=":",
                                 linewidth=1.1)
            minimum_axis.text(
                166, 1.0505, "PV ceiling", ha="right", va="bottom",
                color="#228b22", fontsize=18,
            )
        else:
            minimum_axis.set_ylim(voltage_floor, 1.005)
        gain = (result.supported_profiles - result.baseline_profiles).T
        limit = max(float(np.abs(gain).max()), 1e-8)
        image = gain_axis.imshow(
            gain, aspect="auto", origin="lower", interpolation="nearest",
            extent=(0, 168, 0.5, 33.5), cmap="RdBu_r",
            norm=TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit),
        )
        gain_axis.set_xlim(0, 168)
        gain_axis.set_xticks(np.arange(0, 169, 24))
        gain_axis.set_yticks((1, 9, 18, 25, 33))
        gain_axis.set_xlabel("Time (h)\n(c)")
        gain_axis.set_ylabel("Bus number")
        colorbar = fig.colorbar(image, ax=gain_axis, pad=0.015, fraction=0.035)
        colorbar.set_label(
            "Voltage difference (p.u.)"
        )
        fig.subplots_adjust(left=0.12, right=0.94, bottom=0.07, top=0.91)
        _align_panel_gaps(fig, nodal_axis, minimum_axis, gain_axis)
        fig.canvas.draw()
        right_edge = colorbar.ax.get_tightbbox(fig.canvas.get_renderer()).x1 / fig.bbox.width
        for axis in (nodal_axis, minimum_axis):
            position = axis.get_position()
            axis.set_position((position.x0, position.y0, right_edge - position.x0, position.height))
        _save(fig, directory, "fig14_nodal_voltage_analysis")


def save_figures(run: CaseRun, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    save_configuration(run, directory)
    save_operation(run, directory)
    save_voltage(run, directory)

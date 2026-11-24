"""Separate two-panel presentation for severity-ranked power-flow validation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from powerflow_validation_severity import SeverityResult


def save_severity_figure(result: SeverityResult, output_path: Path) -> None:
    """Save 168-hour and worst-hour voltage comparisons without changing Fig. 15."""
    with plt.rc_context({
        "font.family": "Times New Roman",
        "font.weight": "normal",
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 10,
        "pdf.fonttype": 42,
    }):
        fig, (time_axis_plot, nodal_plot) = plt.subplots(
            1, 2, figsize=(13.0, 4.4), dpi=220,
            gridspec_kw={"width_ratios": [1.12, 1.0]},
        )
        hours = np.arange(1, len(result.active_hours) + 1)
        bus_numbers = np.arange(1, result.baseline_profiles.shape[1] + 1)
        minimum_bus = int(np.argmin(np.mean(result.baseline_profiles, axis=0)))
        for bus in range(result.baseline_profiles.shape[1]):
            if bus != minimum_bus:
                time_axis_plot.plot(
                    hours, result.baseline_profiles[:, bus],
                    color="#c6382b", alpha=0.11, linewidth=0.55,
                    label="Other buses" if bus == 0 or (bus == 1 and minimum_bus == 0) else "_nolegend_",
                )
        time_axis_plot.plot(
            hours, result.baseline_minimum,
            color="#d62728", linewidth=2.2, label="Baseline minimum",
        )
        time_axis_plot.plot(
            hours, result.supported_minimum,
            color="#1f77b4", linewidth=1.4, label="HB-MPS minimum",
        )
        time_axis_plot.axhline(
            0.95, color="#222222", linewidth=1.0, linestyle="--",
            label="0.95 p.u. limit",
        )
        time_axis_plot.scatter(
            hours[result.active_hours],
            np.full(int(result.active_hours.sum()), 0.025),
            transform=time_axis_plot.get_xaxis_transform(),
            color="#ff7f0e", s=9, marker="|", linewidths=1.5,
            label="Emergency dispatch", zorder=5,
        )
        time_axis_plot.set_xlim(0, 168)
        time_axis_plot.set_xticks(np.arange(0, 169, 24))
        time_axis_plot.set_ylim(0.915, 1.005)
        time_axis_plot.set_yticks((0.92, 0.94, 0.96, 0.98, 1.00))
        time_axis_plot.set_xlabel("Time (h)\n(a)")
        time_axis_plot.set_ylabel("Voltage (p.u.)")
        time_axis_plot.grid(alpha=0.23)
        time_axis_plot.legend(
            loc="lower center", bbox_to_anchor=(0.5, 1.02),
            ncol=3, frameon=False, columnspacing=0.8, handlelength=1.3,
        )

        worst = result.worst_hour
        nodal_plot.plot(
            bus_numbers, result.baseline_profiles[worst], "o-",
            color="#d62728", linewidth=2.2, markersize=2.7,
            label="Baseline",
        )
        nodal_plot.plot(
            bus_numbers, result.supported_profiles[worst], "s-",
            color="#1f77b4", linewidth=1.4, markersize=2.7,
            label="Severity dispatch",
        )
        selected = np.array(sorted(set(result.injection_buses[worst])), dtype=int)
        if selected.size:
            nodal_plot.scatter(
                selected, result.supported_profiles[worst, selected - 1],
                color="#ff7f0e", edgecolor="#222222", linewidth=0.4,
                s=46, marker="^", zorder=5, label="Injection bus",
            )
        nodal_plot.axhline(
            0.95, color="#222222", linewidth=1.0, linestyle="--",
            label="0.95 p.u. limit",
        )
        nodal_plot.set_xlim(1, 33)
        nodal_plot.set_xticks((1, 5, 10, 15, 20, 25, 30, 33))
        nodal_plot.set_ylim(0.915, 1.005)
        nodal_plot.set_yticks((0.92, 0.94, 0.96, 0.98, 1.00))
        nodal_plot.set_xlabel("IEEE bus number\n(b)")
        nodal_plot.set_ylabel("Voltage (p.u.)")
        nodal_plot.grid(alpha=0.23)
        nodal_plot.legend(
            loc="lower center", bbox_to_anchor=(0.5, 1.02),
            ncol=2, frameon=False, columnspacing=0.9, handlelength=1.3,
        )
        fig.subplots_adjust(left=0.075, right=0.985, bottom=0.17, top=0.77, wspace=0.27)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)

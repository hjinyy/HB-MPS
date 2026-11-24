from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.weight": "normal",
        "axes.titlesize": 18,
        "axes.titleweight": "normal",
        "axes.labelsize": 18,
        "axes.labelweight": "normal",
        "xtick.labelsize": 18,
        "ytick.labelsize": 18,
        "legend.fontsize": 12,
    }
)

if TYPE_CHECKING:
    from powerflow_validation import ScenarioResult


def save_figure(
    results: list[ScenarioResult],
    output_path: Path,
    hb_bus_number: int,
) -> None:
    """Save time-series and nodal-voltage comparisons for all scenarios."""
    fig, axes = plt.subplots(3, 2, figsize=(16, 10), dpi=220)
    bus_numbers = np.arange(1, 34)
    for row, result in enumerate(results):
        records = result.records
        time_axis = np.arange(1, len(records) + 1)
        left, right = axes[row]
        minimum_bus = int(records["vminbus_base"].mode().iloc[0]) - 1
        first_other_bus = True
        for bus in range(result.base_voltage_profiles.shape[0]):
            if bus != minimum_bus:
                left.plot(
                    time_axis, result.base_voltage_profiles[bus],
                    color="#c6382b", alpha=0.12, linewidth=0.6,
                    label="Other buses" if first_other_bus else "_nolegend_",
                )
                first_other_bus = False
        left.plot(
            time_axis, records["vmin_base"], color="#d62728",
            linewidth=2.4, label="Baseline minimum",
        )
        left.plot(
            time_axis, records["vmin_hbmps"], color="#1f77b4",
            linewidth=1.2, label="HB-MPS minimum",
        )
        active = records["mode2"].eq(1)
        left.scatter(
            time_axis[active.to_numpy()],
            records.loc[active, "vmin_base"],
            color="#2ca02c",
            s=8,
            label="Mode 2 active",
            zorder=4,
        )
        load_axis = left.twinx()
        load_axis.plot(
            time_axis, result.industrial_load_mwh,
            color="#6b7280", alpha=0.35, linewidth=1.0,
            label="Industrial load",
        )
        # Mode 2 is triggered by industrial load, not by bus voltage.
        load_axis.axhline(
            result.mode2_trigger_mwh, color="#2ca02c",
            linestyle="--", linewidth=1.2, label="Mode 2 trigger",
        )
        load_axis.set_ylim(0, 25)
        load_axis.set_yticks((0, 10, 20))
        load_axis.set_ylabel("Industrial load (MWh)")
        left.set_ylabel("Voltage (p.u.)")
        left.set_yticks(
            (0.92, 0.94, 0.96, 0.98, 1.00),
            labels=("0.92", "0.94", "0.96", "0.98", "1.00"),
        )
        left.set_xlim(0, 168)
        left.set_xticks(range(0, 169, 24))
        left.set_xlabel(f"Time (h)\n({'abcdef'[2 * row]})")
        left.grid(alpha=0.3)
        handles, labels = left.get_legend_handles_labels()
        load_handles, load_labels = load_axis.get_legend_handles_labels()
        left.legend(
            handles + load_handles, labels + load_labels,
            loc="lower center", bbox_to_anchor=(0.5, 1.02),
            ncol=3, frameon=True, fancybox=False, edgecolor="black",
            facecolor="white", framealpha=1.0, fontsize=10,
        )

        right.plot(
            bus_numbers, result.base_voltages, "o-", color="#d62728",
            linewidth=2.4, markersize=2.5, label="Baseline",
        )
        right.plot(
            bus_numbers, result.hbmps_voltages, "s-", color="#1f77b4",
            linewidth=1.2, markersize=2.5, label="HB-MPS",
        )
        right.axvline(hb_bus_number, color="#2ca02c", linestyle=":", linewidth=1.4)
        right.set_ylabel("Voltage (p.u.)")
        right.set_yticks(
            (0.92, 0.94, 0.96, 0.98, 1.00),
            labels=("0.92", "0.94", "0.96", "0.98", "1.00"),
        )
        right.grid(alpha=0.3)
        right.legend(
            loc="lower center", bbox_to_anchor=(0.5, 1.02),
            ncol=2, frameon=True, fancybox=False, edgecolor="black",
            facecolor="white", framealpha=1.0,
        )
        right.set_xlabel(f"IEEE bus number\n({'abcdef'[2 * row + 1]})")

    fig.tight_layout(h_pad=5.0, w_pad=4.0)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

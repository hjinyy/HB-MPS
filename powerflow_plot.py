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
    minimum_voltage_pu: float,
    hb_bus_number: int,
) -> None:
    """Save time-series and nodal-voltage comparisons for all scenarios."""
    fig, axes = plt.subplots(3, 2, figsize=(16, 13), dpi=220)
    bus_numbers = np.arange(1, 34)
    for row, result in enumerate(results):
        records = result.records
        time_axis = np.arange(1, len(records) + 1)
        left, right = axes[row]
        left.plot(time_axis, records["vmin_base"], color="#c6382b", label="Baseline")
        left.plot(time_axis, records["vmin_hbmps"], color="#2574ac", label="HB-MPS")
        active = records["mode2"].eq(1)
        left.scatter(
            time_axis[active.to_numpy()],
            records.loc[active, "vmin_base"],
            color="#e68127",
            s=18,
            label="Mode 2",
            zorder=4,
        )
        left.axhline(minimum_voltage_pu, color="black", linestyle="--", linewidth=1.2)
        left.set_ylabel("Voltage (pu)")
        left.set_yticks(
            (0.93, 0.94, 0.95, 0.96),
            labels=("0.93", "0.94", "0.95", "0.96"),
        )
        left.set_xlim(0, 168)
        left.set_xticks(range(0, 169, 24))
        left.set_xlabel(f"Time[h]\n({'abcdef'[2 * row]})")
        left.grid(alpha=0.3)
        left.legend(loc="best")

        right.plot(bus_numbers, result.base_voltages, "o-", color="#c6382b", label="Baseline")
        right.plot(
            bus_numbers, result.hbmps_voltages, "s-", color="#2574ac", label="HB-MPS"
        )
        right.axhline(minimum_voltage_pu, color="black", linestyle="--", linewidth=1.2)
        right.axvline(hb_bus_number, color="#32b16d", linestyle=":", linewidth=1.4)
        right.set_ylabel("Voltage (pu)")
        right.set_yticks(
            (0.92, 0.94, 0.96, 0.98, 1.00),
            labels=("0.92", "0.94", "0.96", "0.98", "1.00"),
        )
        right.grid(alpha=0.3)
        right.legend(loc="best")
        right.set_xlabel(f"IEEE bus number\n({'abcdef'[2 * row + 1]})")

    fig.tight_layout(h_pad=2.5, w_pad=2.0)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "Times New Roman"})

if TYPE_CHECKING:
    from powerflow_validation import ScenarioResult


def save_figure(
    results: list[ScenarioResult],
    output_path: Path,
    minimum_voltage_pu: float,
    hb_bus_number: int,
) -> None:
    """Save time-series and nodal-voltage comparisons for all scenarios."""
    fig, axes = plt.subplots(3, 2, figsize=(15, 14), dpi=220)
    bus_numbers = np.arange(1, 34)
    for row, result in enumerate(results):
        records = result.records
        time_axis = pd.to_datetime(records["timestamp"])
        left, right = axes[row]
        left.plot(time_axis, records["vmin_base"], color="#c6382b", label="Baseline")
        left.plot(time_axis, records["vmin_hbmps"], color="#2574ac", label="HB-MPS")
        active = records["mode2"].eq(1)
        left.scatter(
            time_axis[active],
            records.loc[active, "vmin_base"],
            color="#e68127",
            s=18,
            label="Mode 2",
            zorder=4,
        )
        left.axhline(minimum_voltage_pu, color="black", linestyle="--", linewidth=1.2)
        left.set_title(f"Minimum bus voltage (α={result.alpha})", fontweight="bold")
        left.set_ylabel("Voltage (pu)")
        left.grid(alpha=0.3)
        left.legend(loc="best")

        right.plot(bus_numbers, result.base_voltages, "o-", color="#c6382b", label="Baseline")
        right.plot(
            bus_numbers, result.hbmps_voltages, "s-", color="#2574ac", label="HB-MPS"
        )
        right.axhline(minimum_voltage_pu, color="black", linestyle="--", linewidth=1.2)
        right.axvline(hb_bus_number, color="#32b16d", linestyle=":", linewidth=1.4)
        right.set_title(
            f"Nodal profile at worst baseline hour t={result.worst_hour}",
            fontweight="bold",
        )
        right.set_ylabel("Voltage (pu)")
        right.grid(alpha=0.3)
        right.legend(loc="best")

    axes[-1, 0].set_xlabel("Time")
    axes[-1, 1].set_xlabel("IEEE bus number")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

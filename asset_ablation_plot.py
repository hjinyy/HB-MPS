"""Publication figures for the ESS/HFC configuration experiment."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT: Final = Path(__file__).resolve().parent / "results"


def plot_results(summaries: list[dict[str, str | float]]) -> None:
    """Save energy-balance and operating-value comparisons at both capacity bases."""
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 13})
    names = [str(row["configuration"]) for row in summaries[:3]]
    x = np.arange(3)
    colors = ("#3E7CB1", "#DE8F43", "#8F9BA8")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=200, sharey=True)
    for ax, group in zip(axes, (summaries[:3], summaries[3:]), strict=True):
        bottom = np.zeros(3)
        for field, label, color in zip(
            ("ess_supply_kwh", "hfc_supply_kwh", "unserved_kwh"),
            ("ESS supplied", "HFC supplied", "Unserved"),
            colors,
            strict=True,
        ):
            values = np.array([float(row[field]) / 1000 for row in group])
            ax.bar(x, values, bottom=bottom, width=0.58, label=label, color=color)
            bottom += values
        ax.set_xticks(x, names)
        ax.set_title(str(group[0]["comparison"]))
        ax.set_ylim(0, bottom.max() * 1.07)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Energy over 168 h (MWh)")
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
    )
    fig.suptitle("Single-truck asset ablation: supplied and unserved energy")
    fig.subplots_adjust(bottom=0.23, wspace=0.15)
    fig.tight_layout()
    fig.savefig(OUT / "figure_10_asset_ablation_energy.png", bbox_inches="tight")
    fig.savefig(OUT / "figure_10_asset_ablation_energy.pdf", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=200, sharey=True)
    for ax, group in zip(axes, (summaries[:3], summaries[3:]), strict=True):
        for offset, field, label, color in zip(
            (-0.25, 0.0, 0.25),
            ("operating_net_krw", "avoided_outage_krw", "total_value_krw"),
            ("Operating net", "Avoided outage value", "Total value"),
            ("#3E7CB1", "#DE8F43", "#498F72"),
            strict=True,
        ):
            ax.bar(
                x + offset,
                [float(row[field]) / 1e6 for row in group],
                width=0.23,
                label=label,
                color=color,
            )
        ax.set_xticks(x, names)
        ax.set_title(str(group[0]["comparison"]))
        ax.axhline(0, color="black", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("168-hour value (million KRW)")
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
    )
    fig.suptitle("Operating plus avoided-outage value (excluding capex)")
    fig.subplots_adjust(bottom=0.23, wspace=0.15)
    fig.tight_layout()
    fig.savefig(OUT / "figure_11_asset_ablation_value.png", bbox_inches="tight")
    fig.savefig(OUT / "figure_11_asset_ablation_value.pdf", bbox_inches="tight")
    plt.close(fig)

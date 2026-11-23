"""Publication figures for the ESS/HFC configuration experiment."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from paper_figure_style import apply_paper_typography, normalize_figure_text

OUT: Final = Path(__file__).resolve().parent / "results"


def plot_results(summaries: list[dict[str, str | float]]) -> None:
    """Compare original component ratings and equal 3 MWh total storage."""
    apply_paper_typography()
    original_ratings = [
        row for row in summaries
        if row["comparison"] == "Original component ratings"
    ]
    equal_capacity = [
        row for row in summaries
        if row["comparison"] == "Equal total storage (3 MWh)"
    ]
    if len(original_ratings) != 3 or len(equal_capacity) != 3:
        raise ValueError("Expected three configurations for each comparison basis")
    groups = (original_ratings, equal_capacity)
    x = np.arange(3) * 0.55
    colors = ("#3E7CB1", "#DE8F43", "#8F9BA8")
    fig, axes = plt.subplots(1, 2, figsize=(19.2, 8), dpi=200, sharey=True)
    for ax, group, letter in zip(axes, groups, "ab", strict=True):
        bottom = np.zeros(3)
        for field, label, color in zip(
            ("ess_supply_kwh", "hfc_supply_kwh", "unserved_kwh"),
            ("ESS supplied", "HFC supplied", "Unserved"),
            colors,
            strict=True,
        ):
            values = np.array([float(row[field]) / 1000 for row in group])
            ax.bar(x, values, bottom=bottom, width=0.39, label=label, color=color)
            bottom += values
        names = [str(row["configuration"]).replace("Hybrid ESS–HFC", "Hybrid\nESS–HFC") for row in group]
        ax.set_xticks(x, names)
        ax.set_ylim(0, bottom.max() * 1.07)
        ax.set_xlim(-0.45, 1.55)
        ax.set_xlabel(f"({letter})")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Energy over 168 h (MWh)")
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.tight_layout(rect=(0, 0.15, 1, 1), w_pad=1.0)
    normalize_figure_text(fig)
    fig.savefig(OUT / "fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand.png", bbox_inches="tight")
    fig.savefig(OUT / "fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand.pdf", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(19.2, 8), dpi=200, sharey=True)
    for ax, group, letter in zip(axes, groups, "ab", strict=True):
        for offset, field, label, color in zip(
            (-0.16, 0.0, 0.16),
            ("operating_net_krw", "avoided_outage_krw", "total_value_krw"),
            ("Operating net benefit", "Avoided interruption benefit", "Net societal benefit"),
            ("#3E7CB1", "#DE8F43", "#498F72"),
            strict=True,
        ):
            ax.bar(x + offset, [float(row[field]) / 1e6 for row in group],
                   width=0.15, label=label, color=color)
        names = [str(row["configuration"]).replace("Hybrid ESS–HFC", "Hybrid\nESS–HFC") for row in group]
        ax.set_xticks(x, names)
        ax.set_xlim(-0.45, 1.55)
        ax.set_xlabel(f"({letter})")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("168-hour value (M KRW)")
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.tight_layout(rect=(0, 0.15, 1, 1), w_pad=1.0)
    normalize_figure_text(fig)
    fig.savefig(OUT / "fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit.png", bbox_inches="tight")
    fig.savefig(OUT / "fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit.pdf", bbox_inches="tight")
    plt.close(fig)

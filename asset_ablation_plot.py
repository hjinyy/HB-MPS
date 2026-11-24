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
    names = ("ESS-only", "HFC-only", "Proposed")
    supply_colors = ("#1f77b4", "#ff7f0e")
    fig, axes = plt.subplots(1, 2, figsize=(17.6, 8), dpi=200, sharey=True)
    for ax, group, letter in zip(axes, groups, "ab", strict=True):
        bottom = np.zeros(3)
        for field, label, color in zip(
            ("ess_supply_kwh", "hfc_supply_kwh"),
            ("ESS supplied", "HFC supplied"),
            supply_colors,
            strict=True,
        ):
            values = np.array([float(row[field]) / 1000 for row in group])
            hatch = r"\\" if field == "hfc_supply_kwh" else None
            visible = values > 0
            ax.bar(
                x[visible], values[visible], bottom=bottom[visible], width=0.39,
                label=label, facecolor=color,
                edgecolor="black", linewidth=1.2,
                hatch=hatch, hatchcolor="white",
            )
            for x_position, start, value in zip(x, bottom, values, strict=True):
                if value > 0:
                    ax.text(
                        x_position, start + value / 2, f"{value:.1f}",
                        ha="center", va="center",
                        color="white",
                    )
            bottom += values
        ax.set_xticks(x, names)
        ax.set_ylim(0, bottom.max() * 1.12)
        ax.set_xlim(-0.3225, 1.4225)
        ax.set_xlabel(f"Configuration\n({letter})")
        ax.set_ylabel("Energy (MWh)")
        ax.tick_params(axis="y", labelleft=True)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        frameon=True,
        fancybox=False,
        edgecolor="black",
        facecolor="white",
        framealpha=1.0,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93), w_pad=1.5)
    normalize_figure_text(fig)
    fig.savefig(OUT / "fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand.png", bbox_inches="tight")
    fig.savefig(OUT / "fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand.pdf", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(17.6, 8), dpi=200, sharey=True)
    for ax, group, letter in zip(axes, groups, "ab", strict=True):
        for offset, field, label, color, hatch in zip(
            (-0.16, 0.0, 0.16),
            ("operating_net_krw", "avoided_outage_krw", "total_value_krw"),
            ("Operating net benefit", "Avoided interruption benefit", "Net societal benefit"),
            ("#1f77b4", "#ff7f0e", "#2ca02c"),
            (None, r"\\", "xx"),
            strict=True,
        ):
            ax.bar(x + offset, [float(row[field]) / 1e6 for row in group],
                   width=0.15, label=label,
                   facecolor=color,
                   edgecolor="black", linewidth=1.2,
                   hatch=hatch, hatchcolor="white")
        ax.set_xticks(x, names)
        ax.set_xlim(-0.3425, 1.4425)
        ax.set_xlabel(f"Configuration\n({letter})")
        ax.set_ylabel("Value (M KRW)")
        ax.tick_params(axis="y", labelleft=True)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        frameon=True,
        fancybox=False,
        edgecolor="black",
        facecolor="white",
        framealpha=1.0,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93), w_pad=1.5)
    normalize_figure_text(fig)
    fig.savefig(OUT / "fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit.png", bbox_inches="tight")
    fig.savefig(OUT / "fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit.pdf", bbox_inches="tight")
    plt.close(fig)

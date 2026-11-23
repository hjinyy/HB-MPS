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
    """Save equal-capacity energy and value comparisons for the manuscript."""
    apply_paper_typography()
    equal_capacity = [
        row for row in summaries
        if row["comparison"] == "Equal total storage (3 MWh)"
    ]
    if len(equal_capacity) != 3:
        raise ValueError("Expected ESS-only, HFC-only, and hybrid 3 MWh configurations")
    names = [
        str(row["configuration"]).replace("Hybrid ESS–HFC", "Hybrid\nESS–HFC")
        for row in equal_capacity
    ]
    x = np.arange(3)
    colors = ("#3E7CB1", "#DE8F43", "#8F9BA8")
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    bottom = np.zeros(3)
    for field, label, color in zip(
        ("ess_supply_kwh", "hfc_supply_kwh", "unserved_kwh"),
        ("ESS supplied", "HFC supplied", "Unserved"),
        colors,
        strict=True,
    ):
        values = np.array([float(row[field]) / 1000 for row in equal_capacity])
        ax.bar(x, values, bottom=bottom, width=0.58, label=label, color=color)
        bottom += values
    ax.set_xticks(x, names)
    ax.set_ylim(0, bottom.max() * 1.07)
    ax.set_ylabel("Energy over 168 h (MWh)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *ax.get_legend_handles_labels(),
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    normalize_figure_text(fig)
    fig.savefig(OUT / "fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand.png", bbox_inches="tight")
    fig.savefig(OUT / "fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand.pdf", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(17, 9), dpi=200)
    for offset, field, label, color in zip(
        (-0.25, 0.0, 0.25),
        ("operating_net_krw", "avoided_outage_krw", "total_value_krw"),
        ("Operating net benefit", "Avoided interruption benefit", "Net societal benefit"),
        ("#3E7CB1", "#DE8F43", "#498F72"),
        strict=True,
    ):
        ax.bar(
            x + offset,
            [float(row[field]) / 1e6 for row in equal_capacity],
            width=0.23,
            label=label,
            color=color,
        )
    ax.set_xticks(x, names)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel("168-hour value (million KRW)")
    fig.legend(
        *ax.get_legend_handles_labels(),
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    normalize_figure_text(fig)
    fig.savefig(OUT / "fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit.png", bbox_inches="tight")
    fig.savefig(OUT / "fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit.pdf", bbox_inches="tight")
    plt.close(fig)

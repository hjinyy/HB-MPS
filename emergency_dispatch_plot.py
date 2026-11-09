"""Paper-style figures for the finite-truck emergency dispatch experiment.

Run: ``uv run --with numpy --with matplotlib emergency_dispatch_experiment.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


class SummaryView(Protocol):
    alpha: float
    strategy: str
    available_trucks: int
    reserve_soc: float | None
    ess_emergency_supply_kwh: float
    hfc_supply_kwh: float
    residual_unserved_kwh: float
    operating_net_krw: float
    avoided_interruption_krw: float
    net_societal_benefit_krw: float


def pick(
    rows: Sequence[SummaryView],
    alpha: float,
    trucks: int,
    strategy: str,
    reserve: float | None = None,
) -> SummaryView:
    """Pick a preregistered result for one panel."""
    return next(
        row
        for row in rows
        if row.alpha == alpha
        and row.available_trucks == trucks
        and row.strategy == strategy
        and row.reserve_soc == reserve
    )


def save(fig: plt.Figure, path: Path) -> None:
    """Export both raster and vector versions with stable PDF metadata."""
    fig.savefig(path.with_suffix(".png"), dpi=220, bbox_inches="tight")
    fig.savefig(
        path.with_suffix(".pdf"), bbox_inches="tight", metadata={"CreationDate": None}
    )
    plt.close(fig)


def make_figures(rows: Sequence[SummaryView], out: Path) -> None:
    """Plot energy balance, benefits, and reserve sensitivity for all truck limits."""
    plt.rcParams.update(
        {"font.family": "Times New Roman", "font.size": 12, "axes.titleweight": "bold"}
    )
    labels = ("P0", "P1", "P2 (0.3)")
    selection = (("P0", None), ("P1", None), ("P2", 0.3))
    colors = ("#326FA8", "#D78C44", "#9CA6B0")

    fig, axes = plt.subplots(
        2, 3, figsize=(15, 9), sharey=True, constrained_layout=True
    )
    for axis, alpha, trucks in (
        (axes[ai, ti], alpha, trucks)
        for ai, alpha in enumerate((1.3, 1.5))
        for ti, trucks in enumerate((1, 2, 5))
    ):
        panel = [
            pick(rows, alpha, trucks, strategy, reserve)
            for strategy, reserve in selection
        ]
        bottom = np.zeros(3)
        for field, label, color in zip(
            ("hfc_supply_kwh", "ess_emergency_supply_kwh", "residual_unserved_kwh"),
            ("HFC supplied", "ESS emergency supplied", "Residual unserved"),
            colors,
            strict=True,
        ):
            values = np.array([getattr(row, field) / 1000 for row in panel])
            axis.bar(
                labels, values, bottom=bottom, color=color, width=0.65, label=label
            )
            bottom += values
        axis.set_title(f"α = {alpha}, {trucks} truck{'s' if trucks > 1 else ''}")
        axis.set_ylabel("Energy over 168 h (MWh)")
        axis.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *axes[0, 0].get_legend_handles_labels(),
        loc="outside lower center",
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "Emergency supply and residual load under finite truck availability",
        fontweight="bold",
    )
    save(fig, out / "emergency_figure_A_dispatch_energy")

    fig, axes = plt.subplots(
        2, 3, figsize=(15, 9), sharey=True, constrained_layout=True
    )
    for axis, alpha, trucks in (
        (axes[ai, ti], alpha, trucks)
        for ai, alpha in enumerate((1.3, 1.5))
        for ti, trucks in enumerate((1, 2, 5))
    ):
        panel = [
            pick(rows, alpha, trucks, strategy, reserve)
            for strategy, reserve in selection
        ]
        for offset, field, label, color in zip(
            (-0.24, 0.0, 0.24),
            (
                "operating_net_krw",
                "avoided_interruption_krw",
                "net_societal_benefit_krw",
            ),
            ("Operating net", "Avoided interruption", "Net societal"),
            ("#326FA8", "#D78C44", "#4F9272"),
            strict=True,
        ):
            axis.bar(
                np.arange(3) + offset,
                [getattr(row, field) / 1e6 for row in panel],
                width=0.22,
                color=color,
                label=label,
            )
        axis.set_xticks(range(3), labels)
        axis.set_title(f"α = {alpha}, {trucks} truck{'s' if trucks > 1 else ''}")
        axis.set_ylabel("168-hour value (million KRW)")
        axis.axhline(0, color="black", linewidth=0.7)
        axis.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *axes[0, 0].get_legend_handles_labels(),
        loc="outside lower center",
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "Emergency dispatch: operating cost and avoided interruption value",
        fontweight="bold",
    )
    save(fig, out / "emergency_figure_B_economic_resilience")

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    for column, trucks in enumerate((1, 2, 5)):
        for alpha, color in ((1.3, "#326FA8"), (1.5, "#D78C44")):
            panel = [
                pick(rows, alpha, trucks, "P2", reserve)
                for reserve in (0.2, 0.3, 0.4, 0.5)
            ]
            x = [row.reserve_soc for row in panel]
            axes[0, column].plot(
                x,
                [row.residual_unserved_kwh / 1000 for row in panel],
                marker="o",
                color=color,
                label=f"α = {alpha}",
            )
            axes[1, column].plot(
                x,
                [row.net_societal_benefit_krw / 1e6 for row in panel],
                marker="o",
                color=color,
                label=f"α = {alpha}",
            )
        axes[0, column].set_title(f"{trucks} truck{'s' if trucks > 1 else ''}")
        axes[0, column].set_ylabel("Residual unserved (MWh)")
        axes[1, column].set_ylabel("Net societal (million KRW)")
        axes[1, column].set_xlabel("Emergency reserve SOC")
        for axis in axes[:, column]:
            axis.set_xticks((0.2, 0.3, 0.4, 0.5))
            axis.grid(alpha=0.25)
            axis.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *axes[0, 0].get_legend_handles_labels(),
        loc="outside lower center",
        ncol=2,
        frameon=False,
    )
    fig.suptitle(
        "Reserve matters at α = 1.3; all α = 1.5 cases coincide",
        fontweight="bold",
    )
    save(fig, out / "emergency_figure_C_reserve_sensitivity")

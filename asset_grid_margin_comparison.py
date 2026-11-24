# /// script
# requires-python = ">=3.14"
# dependencies = ["matplotlib", "numpy"]
# ///
# How to run: uv run --offline asset_grid_margin_comparison.py
"""Compare equal-3-MWh asset configurations across grid margin factors."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from asset_ablation import CONFIGURATIONS, INPUT, load_hours, run_configuration
from paper_figure_style import apply_paper_typography, normalize_figure_text

OUT: Final = Path(__file__).resolve().parent / "results"
FIGURE_STEM: Final = (
    "fig10_1_asset_configuration_performance_across_grid_margin_factors"
)
ALPHAS: Final = (1.3, 1.5, 1.8)
CONFIGURATION_NAMES: Final = ("ESS-only", "HFC-only", "Hybrid")
COLORS: Final = ("#1f77b4", "#ff7f0e", "#2ca02c")
MARKERS: Final = ("o", "s", "^")


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    alpha: float
    configuration: str
    ess_capacity_mwh: float
    hfc_capacity_mwh: float
    emergency_energy_mwh: float
    operating_net_benefit_mkrw: float
    avoided_interruption_benefit_mkrw: float
    net_societal_benefit_mkrw: float


def calculate_results() -> list[ComparisonResult]:
    """Run the Figure 9–10 P1 model with one truck and equal total storage."""
    hours = load_hours(INPUT)
    configurations = CONFIGURATIONS[3:]
    results: list[ComparisonResult] = []
    for alpha in ALPHAS:
        for configuration, name in zip(
            configurations, CONFIGURATION_NAMES, strict=True
        ):
            _, summary = run_configuration(hours, configuration, alpha=alpha)
            ess_mwh = configuration.ess_capacity / 1000
            hfc_mwh = configuration.hfc_capacity / 1000
            results.append(
                ComparisonResult(
                    alpha=alpha,
                    configuration=name,
                    ess_capacity_mwh=ess_mwh,
                    hfc_capacity_mwh=hfc_mwh,
                    emergency_energy_mwh=(
                        float(summary["ess_supply_kwh"])
                        + float(summary["hfc_supply_kwh"])
                    )
                    / 1000,
                    operating_net_benefit_mkrw=float(summary["operating_net_krw"])
                    / 1e6,
                    avoided_interruption_benefit_mkrw=float(
                        summary["avoided_outage_krw"]
                    )
                    / 1e6,
                    net_societal_benefit_mkrw=float(summary["total_value_krw"]) / 1e6,
                )
            )
    return results


def plot_results(results: list[ComparisonResult]) -> None:
    """Draw three comparisons with the same asset colors in every panel."""
    apply_paper_typography(text_scale=0.8)
    fig, axes = plt.subplots(1, 3, figsize=(26, 8), dpi=200)
    panels = (
        ("emergency_energy_mwh", "Emergency energy supply (MWh)"),
        ("operating_net_benefit_mkrw", "Operating net benefit (M KRW)"),
        ("net_societal_benefit_mkrw", "Net societal benefit (M KRW)"),
    )
    for ax, (field, ylabel), letter in zip(axes, panels, "abc", strict=True):
        for name, color, marker in zip(
            CONFIGURATION_NAMES, COLORS, MARKERS, strict=True
        ):
            series = [row for row in results if row.configuration == name]
            ax.plot(
                [row.alpha for row in series],
                [getattr(row, field) for row in series],
                color=color,
                marker=marker,
                markersize=11,
                linewidth=2.8,
                label=name,
            )
        ax.set_xticks(ALPHAS)
        ax.set_xlim(1.25, 1.85)
        ax.set_xlabel(f"Grid margin factor (α)\n({letter})")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.99),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88), w_pad=2.0)
    normalize_figure_text(fig)
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / f"{FIGURE_STEM}.{suffix}", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Save the nine auditable experiment results and Figure 10_1."""
    results = calculate_results()
    OUT.mkdir(exist_ok=True)
    with (OUT / f"{FIGURE_STEM}.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(
            target, fieldnames=list(asdict(results[0])), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(asdict(row) for row in results)
    plot_results(results)
    for row in results:
        print(row)


if __name__ == "__main__":
    main()

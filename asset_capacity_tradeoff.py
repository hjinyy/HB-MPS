# /// script
# requires-python = ">=3.14"
# dependencies = ["matplotlib", "numpy"]
# ///
# How to run: uv run --offline asset_capacity_tradeoff.py
"""Compare eleven ESS/HFC allocations at 3 MWh and grid margin α=1.3."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emergency_dispatch import (
    ESS_EFFICIENCY,
    ESS_WEAR_KRW_PER_KWH,
    TRAVEL_H2_KG,
    run_scenario,
)
from emergency_dispatch_model import Scenario, Strategy
from emergency_validation import validate_run
from hb_inputs import INPUT, load_hours
from paper_figure_style import apply_paper_typography, normalize_figure_text

OUT: Final = Path(__file__).resolve().parent / "results"
FIGURE_STEM: Final = (
    "fig9_1_economic_resilience_trade_off_by_ess_hfc_capacity_allocation"
)
TOTAL_CAPACITY_KWH: Final = 3000.0
ALPHA: Final = 1.3


@dataclass(frozen=True, slots=True)
class AllocationResult:
    ess_share_percent: int
    ess_capacity_mwh: float
    hfc_capacity_mwh: float
    emergency_energy_mwh: float
    hfc_emergency_mwh: float
    ess_emergency_mwh: float
    mode1_energy_mwh: float
    operating_net_benefit_mkrw: float
    mode1_revenue_mkrw: float
    mode1_direct_margin_mkrw: float
    mode1_net_after_charging_mkrw: float
    mode2_resource_cost_mkrw: float
    hydrogen_purchase_cost_mkrw: float
    grid_purchase_cost_mkrw: float
    charging_wear_cost_mkrw: float
    terminal_inventory_change_mkrw: float


def calculate_results() -> list[AllocationResult]:
    """Run each capacity split through the unchanged single-truck P1 rules."""
    hours = load_hours(INPUT)
    results: list[AllocationResult] = []
    for share in range(11):
        ess_capacity = 300.0 * share
        hfc_capacity = TOTAL_CAPACITY_KWH - ess_capacity
        run = run_scenario(
            hours,
            Scenario(
                ALPHA,
                1,
                Strategy.P1,
                ess_capacity_kwh=ess_capacity,
                hfc_capacity_kwh=hfc_capacity,
            ),
        )
        validate_run(run)
        mode1_wear = sum(
            step.phase1_ess_kwh / ESS_EFFICIENCY * ESS_WEAR_KRW_PER_KWH
            for step in run.steps
        )
        mode2_wear = sum(
            step.ess_emergency_kwh / ESS_EFFICIENCY * ESS_WEAR_KRW_PER_KWH
            for step in run.steps
        )
        charging_wear = run.total("ess_wear_krw") - mode1_wear - mode2_wear
        mode1_travel_cost = sum(
            TRAVEL_H2_KG * step.h2_price_krw_per_kg
            for step in run.steps
            if step.phase1_ess_kwh > 0
        )
        mode1_revenue = run.total("revenue_krw")
        mode1_direct_margin = mode1_revenue - mode1_wear - mode1_travel_cost
        mode2_hydrogen_use_cost = sum(
            step.consumed_h2_kg * step.h2_price_krw_per_kg
            for step in run.steps
            if step.mode2
        )
        grid_purchase = run.total("grid_purchase_krw")
        results.append(
            AllocationResult(
                ess_share_percent=share * 10,
                ess_capacity_mwh=ess_capacity / 1000,
                hfc_capacity_mwh=hfc_capacity / 1000,
                emergency_energy_mwh=(
                    run.total("hfc_kwh") + run.total("ess_emergency_kwh")
                )
                / 1000,
                hfc_emergency_mwh=run.total("hfc_kwh") / 1000,
                ess_emergency_mwh=run.total("ess_emergency_kwh") / 1000,
                mode1_energy_mwh=run.total("phase1_ess_kwh") / 1000,
                operating_net_benefit_mkrw=sum(
                    step.operating_net_krw for step in run.steps
                )
                / 1e6,
                mode1_revenue_mkrw=mode1_revenue / 1e6,
                mode1_direct_margin_mkrw=mode1_direct_margin / 1e6,
                mode1_net_after_charging_mkrw=(
                    mode1_direct_margin - grid_purchase - charging_wear
                )
                / 1e6,
                mode2_resource_cost_mkrw=(mode2_hydrogen_use_cost + mode2_wear) / 1e6,
                hydrogen_purchase_cost_mkrw=run.total("h2_purchase_krw") / 1e6,
                grid_purchase_cost_mkrw=grid_purchase / 1e6,
                charging_wear_cost_mkrw=charging_wear / 1e6,
                terminal_inventory_change_mkrw=(
                    run.terminal_inventory_change_krw / 1e6
                ),
            )
        )
    return results


def is_non_dominated(row: AllocationResult, results: list[AllocationResult]) -> bool:
    """Check the two maximized objectives among the simulated allocations."""
    return not any(
        other.operating_net_benefit_mkrw >= row.operating_net_benefit_mkrw
        and other.emergency_energy_mwh >= row.emergency_energy_mwh
        and (
            other.operating_net_benefit_mkrw > row.operating_net_benefit_mkrw
            or other.emergency_energy_mwh > row.emergency_energy_mwh
        )
        for other in results
    )


def plot_results(results: list[AllocationResult]) -> None:
    """Show allocation sensitivity and the observed economic–resilience plane."""
    apply_paper_typography(text_scale=0.78 * 1.3, legend_scale=1.3)
    fig, (allocation_ax, tradeoff_ax) = plt.subplots(1, 2, figsize=(20, 8), dpi=220)
    shares = [row.ess_share_percent for row in results]
    operating = [row.operating_net_benefit_mkrw for row in results]
    emergency = [row.emergency_energy_mwh for row in results]
    supply_ax = allocation_ax.twinx()
    operating_line = allocation_ax.plot(
        shares,
        operating,
        color="#1f77b4",
        marker="o",
        linewidth=2.5,
        markersize=8,
        label="Operating net benefit",
    )[0]
    supply_line = supply_ax.plot(
        shares,
        emergency,
        color="#ff7f0e",
        marker="s",
        linewidth=2.5,
        markersize=8,
        label="Emergency energy supply",
    )[0]
    allocation_ax.set_xticks(range(0, 101, 20))
    allocation_ax.set_xlim(-3, 103)
    allocation_ax.set_xlabel("ESS share (%)\n(a)")
    allocation_ax.set_ylabel(r"$\Pi_{\mathrm{op}}$ (M KRW)")
    supply_ax.set_ylabel(r"$E_{\mathrm{emg}}$ (MWh)")
    allocation_ax.grid(alpha=0.25)
    allocation_ax.spines["top"].set_visible(False)
    supply_ax.spines["top"].set_visible(False)
    allocation_ax.legend(
        handles=(operating_line, supply_line),
        loc="upper center",
        bbox_to_anchor=(0.5, 1.17),
        ncol=2,
        frameon=True,
        fancybox=False,
        edgecolor="black",
        facecolor="white",
        framealpha=1.0,
    )

    tradeoff_ax.plot(operating, emergency, color="0.65", linestyle="--", linewidth=1.6)
    scatter = tradeoff_ax.scatter(
        operating,
        emergency,
        c=shares,
        cmap="viridis",
        vmin=0,
        vmax=100,
        s=105,
        edgecolors="black",
        linewidths=0.6,
        zorder=3,
    )
    for share, offset in ((0, (-12, 10)), (50, (9, 10)), (100, (-10, 10))):
        row = results[share // 10]
        tradeoff_ax.annotate(
            f"{share}%" + (" Hybrid" if share == 50 else ""),
            (row.operating_net_benefit_mkrw, row.emergency_energy_mwh),
            xytext=offset,
            textcoords="offset points",
            ha="right" if share in (0, 100) else "left",
        )
    tradeoff_ax.set_xlabel("$\\Pi_{\\mathrm{op}}$ (M KRW)\n(b)")
    tradeoff_ax.set_ylabel(r"$E_{\mathrm{emg}}$ (MWh)")
    tradeoff_ax.grid(alpha=0.25)
    tradeoff_ax.spines[["top", "right"]].set_visible(False)
    colorbar = fig.colorbar(scatter, ax=tradeoff_ax, pad=0.02, shrink=0.82)
    colorbar.set_label("ESS share (%)")
    fig.tight_layout(w_pad=2.2)
    normalize_figure_text(fig)
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / f"{FIGURE_STEM}.{suffix}", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Save audited metrics and Figure 9_1 for all eleven allocations."""
    results = calculate_results()
    OUT.mkdir(exist_ok=True)
    rows = [
        asdict(row) | {"non_dominated": is_non_dominated(row, results)}
        for row in results
    ]
    with (OUT / f"{FIGURE_STEM}.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    plot_results(results)
    for row in results:
        print(
            row.ess_share_percent,
            row.emergency_energy_mwh,
            row.operating_net_benefit_mkrw,
            is_non_dominated(row, results),
        )


if __name__ == "__main__":
    main()

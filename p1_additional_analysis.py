"""VOLL, ESS opportunity, and fleet checks for the adopted P1 main strategy.

Run: ``uv run --with numpy --with matplotlib p1_additional_analysis.py``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emergency_dispatch import H2_KWH_PER_KG, VOLL_KRW_PER_KWH, run_scenario
from emergency_dispatch_model import Run, Scenario, Strategy
from emergency_validation import validate_run
from hb_inputs import INPUT, load_hours
from paper_figure_style import (
    ANNOTATION_SIZE,
    TICK_SIZE,
    apply_paper_typography,
    normalize_figure_text,
    scale_figure_text,
)

OUT: Final = Path(__file__).resolve().parent / "results"
MULTIPLIERS: Final = (0.0, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0)


def write_rows(name: str, rows: list[dict[str, str | float | int]]) -> None:
    """Persist the numerical source for each plotted comparison."""
    with (OUT / name).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def save(fig: plt.Figure, name: str) -> None:
    """Export both paper-ready figure formats with stable PDF metadata."""
    normalize_figure_text(fig)
    fig.savefig(OUT / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(
        OUT / f"{name}.pdf", bbox_inches="tight", metadata={"CreationDate": None}
    )
    plt.close(fig)


def societal(run: Run, voll: float) -> float:
    """Revalue fixed dispatch without changing any physical action."""
    return (
        sum(step.operating_net_krw for step in run.steps)
        + (run.total("hfc_kwh") + run.total("ess_emergency_kwh")) * voll
    )


def main() -> None:
    """Run finite-fleet paths, revalue VOLL, and decompose ESS opportunity cost."""
    hours = load_hours(INPUT)
    OUT.mkdir(exist_ok=True)
    runs = {
        (alpha, trucks, strategy): run_scenario(
            hours,
            Scenario(alpha, trucks, strategy, 0.3 if strategy is Strategy.P2 else None),
        )
        for alpha in (1.3, 1.5, 1.8)
        for trucks in (1, 2, 5)
        for strategy in (Strategy.P0, Strategy.P1, Strategy.P2)
    }
    for run in runs.values():
        validate_run(run)

    fleet = []
    for alpha in (1.3, 1.5, 1.8):
        for trucks in (1, 2, 5):
            run = runs[alpha, trucks, Strategy.P1]
            operating = sum(step.operating_net_krw for step in run.steps)
            avoided = (
                run.total("hfc_kwh") + run.total("ess_emergency_kwh")
            ) * VOLL_KRW_PER_KWH
            fleet.append(
                {
                    "alpha": alpha,
                    "available_trucks": trucks,
                    "hfc_supply_kwh": run.total("hfc_kwh"),
                    "ess_emergency_supply_kwh": run.total("ess_emergency_kwh"),
                    "ess_mode1_supply_kwh": run.total("phase1_ess_kwh"),
                    "unserved_kwh": run.total("unserved_kwh"),
                    "operating_net_krw": operating,
                    "avoided_interruption_krw": avoided,
                    "net_societal_krw": operating + avoided,
                    "final_soc": run.terminal_soc,
                    "final_main_loh": run.steps[-1].main_h2_end_kg
                    / (1500.0 / H2_KWH_PER_KG),
                    "required_trucks_max": max(
                        step.required_hfc_trucks for step in run.steps
                    ),
                    "dispatched_trucks_max": max(
                        step.hfc_trucks_dispatched for step in run.steps
                    ),
                }
            )
    write_rows("p1_fleet_summary.csv", fleet)

    sensitivity = []
    break_even_rows = []
    apply_paper_typography()
    fig, axes = plt.subplots(
        1, 3, figsize=(28, 9.5), sharey=True
    )
    for axis, trucks, letter in zip(axes, (1, 2, 5), "abc", strict=True):
        p0 = runs[1.3, trucks, Strategy.P0]
        proposed = runs[1.3, trucks, Strategy.P1]
        op0 = sum(step.operating_net_krw for step in p0.steps)
        op_proposed = sum(step.operating_net_krw for step in proposed.steps)
        extra_supply = (
            proposed.total("hfc_kwh")
            + proposed.total("ess_emergency_kwh")
            - p0.total("hfc_kwh")
        )
        break_even = (op0 - op_proposed) / extra_supply
        break_even_rows.append(
            {
                "alpha": 1.3,
                "available_trucks": trucks,
                "break_even_voll_krw_per_kwh": break_even,
            }
        )
        # Manuscript P1 is the former P2; proposed P2 is the former P1.
        for label, strategy, color, marker, linestyle in (
            ("P0", Strategy.P0, "#6C7890", "o", "-"),
            ("P1", Strategy.P2, "#2775B6", "^", "--"),
            ("P2", Strategy.P1, "#D9904A", "s", ":"),
        ):
            run = runs[1.3, trucks, strategy]
            x = np.array(MULTIPLIERS) * VOLL_KRW_PER_KWH
            y = np.array([societal(run, voll) / 1e6 for voll in x])
            axis.plot(x, y, color=color, marker=marker, linestyle=linestyle,
                      linewidth=3.5, label=label)
            for multiple, voll, value in zip(MULTIPLIERS, x, y, strict=True):
                sensitivity.append(
                    {
                        "alpha": 1.3,
                        "available_trucks": trucks,
                        "strategy": label,
                        "voll_multiplier": multiple,
                        "voll_krw_per_kwh": voll,
                        "net_societal_million_krw": value,
                    }
                )
        axis.axvline(break_even, color="black", linestyle=":", linewidth=1.3)
        axis.axvline(VOLL_KRW_PER_KWH, color="firebrick", linestyle="--", linewidth=1.3)
        axis.set_xlabel(f"VOLL (KRW/kWh)\n({letter})")
        axis.set_ylabel(r"$V_{\mathrm{societal}}$ (M KRW)")
        axis.tick_params(axis="y", labelleft=True)
        axis.set_box_aspect(1)
        axis.set_xticks((0, 5000, 10000))
        axis.grid(alpha=0.2)
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.94),
        ncol=3,
        frameon=True,
        fancybox=False,
        edgecolor="black",
        facecolor="white",
        framealpha=1.0,
        prop={"size": TICK_SIZE},
    )
    scale_figure_text(fig, 1.2)
    fig.tight_layout(rect=(0, 0, 1, 0.76), w_pad=2.0)
    positions = [axis.get_position() for axis in axes]
    reduced_gap = (positions[1].x0 - positions[0].x1) * 0.75
    left = (1 - sum(position.width for position in positions) - 2 * reduced_gap) / 2
    for axis, position in zip(axes, positions, strict=True):
        axis.set_position((left, position.y0, position.width, position.height))
        left += position.width + reduced_gap
    save(fig, "fig11_voll_sensitivity_of_net_societal_benefit")
    write_rows("p1_voll_sensitivity.csv", sensitivity)
    write_rows("p1_voll_break_even.csv", break_even_rows)

    p0 = runs[1.3, 1, Strategy.P0]
    p1 = runs[1.3, 1, Strategy.P1]
    difference = lambda field: p1.total(field) - p0.total(field)
    components = [
        ("Internal valuation benefit", difference("revenue_krw")),
        ("Grid electricity purchase cost", -difference("grid_purchase_krw")),
        ("Battery degradation cost", -difference("ess_wear_krw")),
        ("Hydrogen purchase cost", -difference("h2_purchase_krw")),
        ("Avoided interruption benefit", difference("avoided_interruption_krw")),
    ]
    net_change = societal(p1, VOLL_KRW_PER_KWH) - societal(p0, VOLL_KRW_PER_KWH)
    if abs(sum(value for _, value in components) - net_change) > 1e-5:
        raise AssertionError("Opportunity-cost components do not close to net benefit")
    write_rows(
        "p1_opportunity_components.csv",
        [
            {"component": label, "delta_krw": value}
            for label, value in (*components, ("Net societal benefit", net_change))
        ],
    )
    labels = [label for label, _ in components] + ["Net societal benefit"]
    values = [value / 1e6 for _, value in components] + [net_change / 1e6]
    colors = ["#B85C5C" if value < 0 else "#4F9272" for value in values]
    apply_paper_typography()
    plot_labels = {
        "Internal valuation benefit": "Internal valuation\nbenefit",
        "Grid electricity purchase cost": "Grid electricity\npurchase cost",
        "Battery degradation cost": "Battery\ndegradation cost",
        "Hydrogen purchase cost": "Hydrogen\npurchase cost",
        "Avoided interruption benefit": "Avoided\ninterruption benefit",
    }
    fig, axis = plt.subplots(figsize=(17, 10.5), constrained_layout=True)
    axis.barh([plot_labels.get(label, label) for label in labels[::-1]], values[::-1],
              color=colors[::-1])
    axis.set_xlim(min(values) - 1.5, max(values) + 3.5)
    for position, value in enumerate(values[::-1]):
        display_value = 0.0 if abs(value) < 0.0005 else value
        axis.text(
            max(value + 0.2, 1.0),
            position,
            f"{display_value:+.3f}",
            va="center",
            ha="left",
            fontsize=ANNOTATION_SIZE,
        )
    axis.axvline(0, color="black", linewidth=0.9)
    axis.set_xlabel("Difference between P1 and P0 (M KRW)")
    axis.grid(axis="x", alpha=0.2)
    save(fig, "fig12_decomposition_of_economic_opportunity_costs_and_avoided_interruption_benefits")
    print(
        f"Fleet rows={len(fleet)}; break-even VOLL={[round(row['break_even_voll_krw_per_kwh'], 2) for row in break_even_rows]}"
    )


if __name__ == "__main__":
    main()

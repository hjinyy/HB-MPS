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
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 12})
    fig, axes = plt.subplots(
        1, 3, figsize=(15, 5), sharey=True, constrained_layout=True
    )
    for axis, trucks in zip(axes, (1, 2, 5), strict=True):
        p0 = runs[1.3, trucks, Strategy.P0]
        p1 = runs[1.3, trucks, Strategy.P1]
        op0 = sum(step.operating_net_krw for step in p0.steps)
        op1 = sum(step.operating_net_krw for step in p1.steps)
        extra_supply = (
            p1.total("hfc_kwh") + p1.total("ess_emergency_kwh") - p0.total("hfc_kwh")
        )
        break_even = (op0 - op1) / extra_supply
        break_even_rows.append(
            {
                "alpha": 1.3,
                "available_trucks": trucks,
                "break_even_voll_krw_per_kwh": break_even,
            }
        )
        for strategy, color in (
            (Strategy.P0, "#6C7890"),
            (Strategy.P1, "#2775B6"),
            (Strategy.P2, "#D9904A"),
        ):
            run = runs[1.3, trucks, strategy]
            x = np.array(MULTIPLIERS) * VOLL_KRW_PER_KWH
            y = np.array([societal(run, voll) / 1e6 for voll in x])
            axis.plot(x, y, color=color, marker="o", linewidth=2, label=strategy.value)
            for multiple, voll, value in zip(MULTIPLIERS, x, y, strict=True):
                sensitivity.append(
                    {
                        "alpha": 1.3,
                        "available_trucks": trucks,
                        "strategy": strategy.value,
                        "voll_multiplier": multiple,
                        "voll_krw_per_kwh": voll,
                        "net_societal_million_krw": value,
                    }
                )
        axis.axvline(break_even, color="black", linestyle=":", linewidth=1.3)
        axis.axvline(VOLL_KRW_PER_KWH, color="firebrick", linestyle="--", linewidth=1.3)
        axis.text(
            break_even + 150,
            axis.get_ylim()[0] * 0.85,
            f"BE {break_even:.0f}",
            rotation=90,
            fontsize=10,
        )
        axis.set_title(f"{trucks} truck{'s' if trucks > 1 else ''}", fontweight="bold")
        axis.set_xlabel("VOLL (KRW/kWh)")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Net societal benefit (million KRW)")
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        loc="outside lower center",
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "Figure 14. VOLL revalues fixed P0, P1 and P2 dispatch (α = 1.3)",
        fontweight="bold",
    )
    save(fig, "figure_14_voll_sensitivity")
    write_rows("p1_voll_sensitivity.csv", sensitivity)
    write_rows("p1_voll_break_even.csv", break_even_rows)

    p0 = runs[1.3, 1, Strategy.P0]
    p1 = runs[1.3, 1, Strategy.P1]
    difference = lambda field: p1.total(field) - p0.total(field)
    components = [
        ("Lost Mode 1 revenue", difference("revenue_krw")),
        ("Additional grid purchase", -difference("grid_purchase_krw")),
        ("Additional ESS wear", -difference("ess_wear_krw")),
        ("External H2 purchase change", -difference("h2_purchase_krw")),
        ("Additional avoided interruption", difference("avoided_interruption_krw")),
    ]
    net_change = societal(p1, VOLL_KRW_PER_KWH) - societal(p0, VOLL_KRW_PER_KWH)
    if abs(sum(value for _, value in components) - net_change) > 1e-5:
        raise AssertionError("Opportunity-cost components do not close to net benefit")
    write_rows(
        "p1_opportunity_components.csv",
        [
            {"component": label, "delta_krw": value}
            for label, value in (*components, ("Net societal change", net_change))
        ],
    )
    labels = [label for label, _ in components] + ["Net societal change"]
    values = [value / 1e6 for _, value in components] + [net_change / 1e6]
    colors = ["#B85C5C" if value < 0 else "#4F9272" for value in values]
    fig, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
    axis.barh(labels[::-1], values[::-1], color=colors[::-1])
    axis.set_xlim(-2.0, 24.5)
    for position, value in enumerate(values[::-1]):
        display_value = 0.0 if abs(value) < 0.0005 else value
        axis.text(
            value + (0.2 if display_value >= 0 else -0.2),
            position,
            f"{display_value:+.3f}",
            va="center",
            ha="left" if display_value >= 0 else "right",
        )
    axis.axvline(0, color="black", linewidth=0.9)
    axis.set_xlabel("P1 − P0 (million KRW over 168 hours)")
    axis.set_title(
        "Figure 15. ESS backup opportunity cost versus avoided interruption (α = 1.3, 1 truck)",
        fontweight="bold",
    )
    axis.grid(axis="x", alpha=0.2)
    save(fig, "figure_15_ess_opportunity_cost")
    print(
        f"Fleet rows={len(fleet)}; break-even VOLL={[round(row['break_even_voll_krw_per_kwh'], 2) for row in break_even_rows]}"
    )


if __name__ == "__main__":
    main()

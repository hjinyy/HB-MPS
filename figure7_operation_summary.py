# /// script
# requires-python = ">=3.14"
# dependencies = ["matplotlib", "numpy"]
# ///
# How to run: uv run --offline figure7_operation_summary.py
"""Mode distribution and ten action-use rates for the 168-hour P1 cases."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emergency_dispatch import H2_CAPACITY_KG, H2_INITIAL_LOH, run_scenario
from emergency_dispatch_model import Scenario, Step, Strategy
from emergency_validation import validate_run
from hb_inputs import INPUT, load_hours
from paper_figure_style import apply_paper_typography, normalize_figure_text

OUT: Final = Path(__file__).resolve().parent / "results"
FIGURE_STEM: Final = "fig7_distribution_of_hb_mps_operating_modes"
SCENARIOS: Final = ((1.3, "Tight"), (1.5, "Standard"), (1.8, "Robust"))
ACTIONS: Final = (
    "ESS economic discharging",
    "Surplus PV charging",
    "P2G hydrogen production",
    "Grid charging",
    "Main-truck hydrogen refueling",
    "Auxiliary-truck hydrogen refueling",
    "Standby",
    "Main-truck HFC power supply",
    "Auxiliary-truck HFC power supply",
    "ESS emergency backup",
)
MODE_NAMES: Final = ("Mode 1", "Mode 2", "Standby")
MODE_COLORS: Final = ("#1f77b4", "#ff7f0e", "#b3b3b3")


@dataclass(frozen=True, slots=True)
class ScenarioUsage:
    alpha: float
    condition: str
    hours: int
    mode_hours: tuple[int, int, int]
    action_hours: tuple[int, ...]


def action_flags(step: Step, previous_main_h2_kg: float) -> tuple[bool, ...]:
    """Identify concurrent actions from physical flows, including auxiliary use."""
    # During Mode 2, only main-truck HFC dispatch can lower its H2 inventory.
    main_hfc = step.mode2 and previous_main_h2_kg - step.main_h2_end_kg > 1e-9
    auxiliary_hfc = step.mode2 and step.hfc_trucks_dispatched > int(main_hfc)
    non_emergency = (
        step.phase1_ess_kwh > 0,
        step.pv_ess_charge_kwh > 0,
        step.pv_p2g_kwh > 0,
        step.grid_ess_charge_kwh > 0,
        step.main_h2_refill_kg > 1e-9,
        step.external_h2_kg - step.main_h2_refill_kg > 1e-9 and not step.mode2,
    )
    standby = not step.mode2 and not any(non_emergency)
    return (
        *non_emergency,
        standby,
        main_hfc,
        auxiliary_hfc,
        step.mode2 and step.ess_emergency_kwh > 0,
    )


def calculate_usage() -> tuple[ScenarioUsage, ...]:
    """Run each α with the same five-truck P1 dispatch as the main figures."""
    hours = load_hours(INPUT)
    summaries: list[ScenarioUsage] = []
    for alpha, condition in SCENARIOS:
        run = run_scenario(hours, Scenario(alpha, 5, Strategy.P1))
        validate_run(run)
        action_counts = [0] * len(ACTIONS)
        mode_counts = [0, 0, 0]
        previous_main_h2_kg = H2_INITIAL_LOH * H2_CAPACITY_KG
        for step in run.steps:
            flags = action_flags(step, previous_main_h2_kg)
            for index, active in enumerate(flags):
                action_counts[index] += int(active)
            if step.mode2:
                mode_counts[1] += 1
            elif flags[6]:
                mode_counts[2] += 1
            else:
                mode_counts[0] += 1
            previous_main_h2_kg = step.main_h2_end_kg
        summaries.append(
            ScenarioUsage(
                alpha,
                condition,
                len(run.steps),
                tuple(mode_counts),
                tuple(action_counts),
            )
        )
    return tuple(summaries)


def save_usage(summaries: tuple[ScenarioUsage, ...]) -> None:
    """Write counts and denominators for every plotted percentage."""
    with (OUT / "fig7_operating_modes_and_actions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(
            (
                "alpha",
                "grid_condition",
                "classification",
                "label",
                "hours",
                "share_percent",
            )
        )
        for summary in summaries:
            for classification, names, counts in (
                ("mode", MODE_NAMES, summary.mode_hours),
                ("action", ACTIONS, summary.action_hours),
            ):
                for name, count in zip(names, counts, strict=True):
                    writer.writerow(
                        (
                            summary.alpha,
                            summary.condition,
                            classification,
                            name,
                            count,
                            count / summary.hours * 100,
                        )
                    )


def plot_usage(summaries: tuple[ScenarioUsage, ...]) -> None:
    """Draw (a) mutually exclusive modes and (b) overlapping actions."""
    apply_paper_typography(text_scale=0.78)
    fig, (mode_ax, action_ax) = plt.subplots(
        1, 2, figsize=(25, 10), dpi=220, gridspec_kw={"width_ratios": (1, 1.6)}
    )
    x = np.arange(len(summaries))
    bottom = np.zeros(len(summaries))
    for index, (name, color) in enumerate(zip(MODE_NAMES, MODE_COLORS, strict=True)):
        values = np.array(
            [summary.mode_hours[index] / summary.hours * 100 for summary in summaries]
        )
        mode_ax.bar(
            x,
            values,
            bottom=bottom,
            width=0.62,
            color=color,
            edgecolor="black",
            linewidth=0.8,
            label=name,
        )
        for position, start, value in zip(x, bottom, values, strict=True):
            if value >= 4:
                mode_ax.text(
                    position,
                    start + value / 2,
                    f"{value:.1f}%",
                    ha="center",
                    va="center",
                    color="white" if index < 2 else "black",
                    fontsize=20,
                )
        bottom += values
    labels = [f"{summary.condition}\n(α = {summary.alpha})" for summary in summaries]
    mode_ax.set_xticks(x, labels)
    mode_ax.set_ylim(0, 103)
    mode_ax.set_ylabel("Time share (%)")
    mode_ax.set_xlabel("Grid condition\n(a)")
    mode_ax.grid(axis="y", alpha=0.2)
    mode_ax.set_axisbelow(True)
    mode_ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.13),
        ncol=3,
        frameon=True,
        fontsize=19,
    )

    values = np.array(
        [
            [summary.action_hours[index] / summary.hours * 100 for summary in summaries]
            for index in range(len(ACTIONS))
        ]
    )
    image = action_ax.imshow(
        values, cmap="Blues", vmin=0, vmax=max(45, values.max()), aspect="auto"
    )
    action_ax.set_xticks(range(len(summaries)), labels)
    action_ax.set_yticks(range(len(ACTIONS)), ACTIONS)
    action_ax.set_xlabel("Grid condition\n(b)")
    action_ax.set_xticks(np.arange(-0.5, len(summaries), 1), minor=True)
    action_ax.set_yticks(np.arange(-0.5, len(ACTIONS), 1), minor=True)
    action_ax.grid(which="minor", color="white", linewidth=1.5)
    action_ax.tick_params(which="minor", bottom=False, left=False)
    action_ax.axhline(6.5, color="black", linewidth=1.5)
    for row, column in np.ndindex(values.shape):
        value = values[row, column]
        action_ax.text(
            column,
            row,
            f"{value:.1f}%",
            ha="center",
            va="center",
            color="white" if value > image.norm.vmax * 0.6 else "black",
            fontsize=19,
        )
    colorbar = fig.colorbar(image, ax=action_ax, pad=0.02, shrink=0.8)
    colorbar.set_label("Time share (%)")
    fig.tight_layout(rect=(0, 0, 1, 0.92), w_pad=2.8)
    normalize_figure_text(fig)
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / f"{FIGURE_STEM}.{suffix}", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Generate Fig. 7 and its source counts without touching other figures."""
    summaries = calculate_usage()
    OUT.mkdir(exist_ok=True)
    save_usage(summaries)
    plot_usage(summaries)


if __name__ == "__main__":
    main()

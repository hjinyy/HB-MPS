# /// script
# requires-python = ">=3.14"
# dependencies = ["matplotlib", "numpy"]
# ///
# How to run: uv run --offline figure7_operation_summary.py
"""Show Mode 1, Mode 2, and standby shares in the 168-hour P1 cases."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emergency_dispatch import run_scenario
from emergency_dispatch_model import Scenario, Step, Strategy
from emergency_validation import validate_run
from hb_inputs import INPUT, load_hours
from paper_figure_style import apply_paper_typography, normalize_figure_text

OUT: Final = Path(__file__).resolve().parent / "results"
FIGURE_STEM: Final = "fig7_distribution_of_hb_mps_operating_modes"
SCENARIOS: Final = ((1.3, "Tight"), (1.5, "Standard"), (1.8, "Robust"))
MODE_NAMES: Final = ("Mode 1", "Mode 2", "Standby")
MODE_COLORS: Final = ("#1f77b4", "#ff7f0e", "#808080")
MODE_HATCHES: Final = (None, r"\\", "//")


@dataclass(frozen=True, slots=True)
class ScenarioModeSummary:
    alpha: float
    condition: str
    hours: int
    mode_hours: tuple[int, int, int]


def is_standby(step: Step) -> bool:
    """Count an hour as standby only when no fleet operation occurs."""
    return not step.mode2 and not any(
        (
            step.phase1_ess_kwh > 0,
            step.pv_ess_charge_kwh > 0,
            step.pv_p2g_kwh > 0,
            step.grid_ess_charge_kwh > 0,
            step.external_h2_kg > 0,
        )
    )


def calculate_usage() -> tuple[ScenarioModeSummary, ...]:
    """Use the original five-truck P1 dispatch and exclusive mode categories."""
    hours = load_hours(INPUT)
    summaries: list[ScenarioModeSummary] = []
    for alpha, condition in SCENARIOS:
        run = run_scenario(hours, Scenario(alpha, 5, Strategy.P1))
        validate_run(run)
        mode_counts = [0, 0, 0]
        for step in run.steps:
            if step.mode2:
                mode_counts[1] += 1
            elif is_standby(step):
                mode_counts[2] += 1
            else:
                mode_counts[0] += 1
        summaries.append(
            ScenarioModeSummary(alpha, condition, len(run.steps), tuple(mode_counts))
        )
    return tuple(summaries)


def save_usage(summaries: tuple[ScenarioModeSummary, ...]) -> None:
    """Save the exact hours and rates used in the stacked bars."""
    with (OUT / "fig7_operating_mode_distribution.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(("alpha", "grid_condition", "mode", "hours", "share_percent"))
        for summary in summaries:
            for name, count in zip(MODE_NAMES, summary.mode_hours, strict=True):
                writer.writerow(
                    (
                        summary.alpha,
                        summary.condition,
                        name,
                        count,
                        count / summary.hours * 100,
                    )
                )


def plot_usage(summaries: tuple[ScenarioModeSummary, ...]) -> None:
    """Draw one stacked bar chart for the three grid conditions."""
    apply_paper_typography(text_scale=0.78)
    fig, axis = plt.subplots(figsize=(12, 8), dpi=220)
    x = np.arange(len(summaries))
    bottom = np.zeros(len(summaries))
    for index, (name, color, hatch) in enumerate(
        zip(MODE_NAMES, MODE_COLORS, MODE_HATCHES, strict=True)
    ):
        values = np.array(
            [summary.mode_hours[index] / summary.hours * 100 for summary in summaries]
        )
        axis.bar(
            x,
            values,
            bottom=bottom,
            width=0.62,
            facecolor=color,
            edgecolor="black",
            linewidth=0.8,
            hatch=hatch,
            hatchcolor="white",
            label=name,
        )
        for position, start, value in zip(x, bottom, values, strict=True):
            if value >= 4:
                axis.text(
                    position,
                    start + value / 2,
                    f"{value:.1f}%",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=20,
                )
        bottom += values
    labels = [f"{summary.condition}\n(α = {summary.alpha})" for summary in summaries]
    axis.set_xticks(x, labels)
    axis.set_ylim(0, 103)
    axis.set_ylabel("Time share (%)")
    axis.set_xlabel("Grid condition\n(a)")
    axis.grid(axis="y", alpha=0.2)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.15),
        ncol=3,
        frameon=True,
        fancybox=False,
        edgecolor="black",
        facecolor="white",
        framealpha=1.0,
        fontsize=19,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    normalize_figure_text(fig)
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / f"{FIGURE_STEM}.{suffix}", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Regenerate Figure 7 and its nine source mode rates only."""
    summaries = calculate_usage()
    OUT.mkdir(exist_ok=True)
    save_usage(summaries)
    plot_usage(summaries)


if __name__ == "__main__":
    main()

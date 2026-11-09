"""Reproduce finite-truck P0/P1/P2 experiments from the repository's CSV.

Run: ``uv run --with numpy --with matplotlib emergency_dispatch_experiment.py``.
Outputs are prefixed ``emergency_`` so Figures 5–13 are untouched.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from emergency_dispatch import (
    run_scenario,
)
from emergency_dispatch_model import Run, Scenario, Strategy
from emergency_dispatch_plot import make_figures
from emergency_validation import validate_run
from hb_inputs import INPUT, load_hours

OUT: Final = Path(__file__).resolve().parent / "results"
RESERVES: Final = (0.2, 0.3, 0.4, 0.5)


@dataclass(frozen=True, slots=True)
class Summary:
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
    phase1_ess_supply_kwh: float
    phase1_revenue_krw: float
    grid_charge_kwh: float
    grid_purchase_krw: float
    pv_ess_charge_kwh: float
    pv_p2g_kwh: float
    external_h2_refill_kg: float
    h2_purchase_krw: float
    h2_consumed_kg: float
    ess_wear_krw: float
    terminal_soc: float
    terminal_h2_kg: float
    terminal_inventory_change_krw: float
    inventory_adjusted_societal_krw: float


def scenarios() -> tuple[Scenario, ...]:
    """Enumerate every preregistered scenario; no result-driven tuning."""
    return tuple(
        scenario
        for alpha in (1.3, 1.5)
        for trucks in (1, 2, 5)
        for scenario in (
            Scenario(alpha, trucks, Strategy.P0),
            Scenario(alpha, trucks, Strategy.P1),
            *(Scenario(alpha, trucks, Strategy.P2, reserve) for reserve in RESERVES),
        )
    )


def summarize(run: Run) -> Summary:
    """Use the original paper's operating and avoided-interruption definitions."""
    operating = sum(step.operating_net_krw for step in run.steps)
    avoided = run.total("avoided_interruption_krw")
    societal = operating + avoided
    return Summary(
        run.scenario.alpha,
        run.scenario.strategy.value,
        run.scenario.trucks,
        run.scenario.reserve_soc,
        run.total("ess_emergency_kwh"),
        run.total("hfc_kwh"),
        run.total("unserved_kwh"),
        operating,
        avoided,
        societal,
        run.total("phase1_ess_kwh"),
        run.total("revenue_krw"),
        run.total("grid_ess_charge_kwh"),
        run.total("grid_purchase_krw"),
        run.total("pv_ess_charge_kwh"),
        run.total("pv_p2g_kwh"),
        run.total("external_h2_kg"),
        run.total("h2_purchase_krw"),
        run.total("consumed_h2_kg"),
        run.total("ess_wear_krw"),
        run.terminal_soc,
        run.terminal_h2_kg,
        run.terminal_inventory_change_krw,
        societal + run.terminal_inventory_change_krw,
    )


def write_csv(
    path: Path, rows: list[dict[str, str | float | int | bool | None]]
) -> None:
    """Write comparable, machine-readable results with stable LF endings."""
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Execute and validate all 36 paths, then create tables and figures."""
    hours = load_hours(INPUT)
    runs = [run_scenario(hours, scenario) for scenario in scenarios()]
    for run in runs:
        validate_run(run)
    summaries = [summarize(run) for run in runs]
    OUT.mkdir(exist_ok=True)
    write_csv(
        OUT / "emergency_dispatch_summary.csv", [asdict(row) for row in summaries]
    )
    hourly = [
        {
            "alpha": run.scenario.alpha,
            "strategy": run.scenario.strategy.value,
            "available_trucks": run.scenario.trucks,
            "reserve_soc": run.scenario.reserve_soc,
            "hour_index": index,
            **asdict(step),
            "operating_net_krw": step.operating_net_krw,
        }
        for run in runs
        for index, step in enumerate(run.steps)
    ]
    write_csv(OUT / "emergency_dispatch_hourly.csv", hourly)
    make_figures(summaries, OUT)
    print(f"Validated {len(runs)} scenarios × {len(hours)} hours; output: {OUT}")


if __name__ == "__main__":
    main()

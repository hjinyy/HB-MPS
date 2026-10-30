"""Reproduce finite-truck P0/P1/P2 experiments from the repository's CSV.

Run: ``uv run --with numpy --with matplotlib emergency_dispatch_experiment.py``.
Outputs are prefixed ``emergency_`` so Figures 5–13 are untouched.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from asset_ablation import INPUT, load_hours
from emergency_dispatch import (
    ESS_CAPACITY,
    ESS_EFFICIENCY,
    ESS_MAX_SOC,
    ESS_MIN_SOC,
    ESS_WEAR_KRW_PER_KWH,
    ESS_WITHDRAWAL_KWH,
    H2_CAPACITY_KG,
    HFC_OUTPUT_KWH,
    P2G_KWH_PER_KG,
    run_scenario,
)
from emergency_dispatch_model import Run, Scenario, Strategy
from emergency_dispatch_plot import make_figures

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


def validate_run(run: Run) -> None:
    """Reject energy, output, inventory, and accounting inconsistencies."""
    tolerance = 1e-6
    for step in run.steps:
        if not math.isclose(
            step.demand_kwh,
            step.hfc_kwh + step.ess_emergency_kwh + step.unserved_kwh,
            abs_tol=tolerance,
        ):
            raise AssertionError((run.scenario, step.timestamp, "supply balance"))
        if not ESS_MIN_SOC - tolerance <= step.soc_end <= ESS_MAX_SOC + tolerance:
            raise AssertionError((run.scenario, step.timestamp, "SOC bound"))
        if (
            not -tolerance
            <= step.h2_end_kg
            <= run.scenario.trucks * H2_CAPACITY_KG + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "H2 inventory bound"))
        if not (
            -tolerance
            <= step.h2_min_truck_kg
            <= step.h2_max_truck_kg
            <= H2_CAPACITY_KG + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "per-truck H2 bound"))
        if (
            not 0
            <= step.hfc_kwh
            <= step.hfc_trucks_dispatched * HFC_OUTPUT_KWH + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "HFC rating"))
        if (
            not 0
            <= step.ess_emergency_kwh
            <= ESS_WITHDRAWAL_KWH * ESS_EFFICIENCY + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "ESS rating"))
        if step.hfc_trucks_dispatched > run.scenario.trucks:
            raise AssertionError((run.scenario, step.timestamp, "truck availability"))
        expected_h2_end = (
            step.h2_start_kg
            + step.external_h2_kg
            + step.pv_p2g_kwh / P2G_KWH_PER_KG
            - step.consumed_h2_kg
        )
        if not math.isclose(step.h2_end_kg, expected_h2_end, abs_tol=tolerance):
            raise AssertionError((run.scenario, step.timestamp, "H2 balance"))
        expected_soc_end = (
            step.soc_start
            + (
                (step.pv_ess_charge_kwh + step.grid_ess_charge_kwh) * ESS_EFFICIENCY
                - (step.ess_emergency_kwh + step.phase1_ess_kwh) / ESS_EFFICIENCY
            )
            / ESS_CAPACITY
        )
        if not math.isclose(step.soc_end, expected_soc_end, abs_tol=tolerance):
            raise AssertionError((run.scenario, step.timestamp, "ESS balance"))
        if (
            step.h2_purchase_krw < 0
            or step.grid_purchase_krw < 0
            or step.ess_wear_krw < 0
        ):
            raise AssertionError((run.scenario, step.timestamp, "negative cost"))
        if not math.isclose(
            step.h2_purchase_krw,
            step.external_h2_kg * step.h2_price_krw_per_kg,
            abs_tol=tolerance,
        ):
            raise AssertionError(
                (run.scenario, step.timestamp, "H2 purchase accounting")
            )
        if not math.isclose(
            step.grid_purchase_krw,
            step.grid_ess_charge_kwh * step.smp_krw_per_kwh,
            abs_tol=tolerance,
        ):
            raise AssertionError(
                (run.scenario, step.timestamp, "grid purchase accounting")
            )
        if not math.isclose(
            step.revenue_krw,
            step.phase1_ess_kwh * step.lcoe_krw_per_kwh,
            abs_tol=tolerance,
        ):
            raise AssertionError(
                (run.scenario, step.timestamp, "Mode 1 revenue accounting")
            )
        wear_throughput = (
            (step.ess_emergency_kwh + step.phase1_ess_kwh) / ESS_EFFICIENCY
            + step.pv_ess_charge_kwh
            + step.grid_ess_charge_kwh
        )
        if not math.isclose(
            step.ess_wear_krw, wear_throughput * ESS_WEAR_KRW_PER_KWH, abs_tol=tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "ESS wear accounting"))
    if run.scenario.strategy is Strategy.P0 and run.total("ess_emergency_kwh") != 0:
        raise AssertionError((run.scenario, "P0 ESS emergency supply"))
    if run.scenario.strategy is Strategy.P2 and run.terminal_soc < ESS_MIN_SOC:
        raise AssertionError((run.scenario, "P2 terminal SOC"))
    if run.scenario.strategy is Strategy.P2:
        for step in run.steps:
            if (
                step.ess_emergency_kwh > 0
                and step.soc_end < (run.scenario.reserve_soc or 0.0) - tolerance
            ):
                raise AssertionError(
                    (run.scenario, step.timestamp, "emergency reserve")
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

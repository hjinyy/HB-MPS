"""Reproducible single-truck ESS/HFC ablation using the repository's hourly inputs.

Mode 2 supply is bounded by onboard energy and output ratings. No auxiliary
truck or capital expenditure is assumed; all configurations face identical
industrial demand, prices, vehicle travel cost, and hourly time steps.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from asset_ablation_plot import plot_results
from emergency_dispatch import run_scenario
from emergency_dispatch_model import Scenario, Strategy
from hb_inputs import INPUT, Hour, load_hours

ROOT: Final = Path(__file__).resolve().parent
OUT: Final = ROOT / "results"
ALPHA: Final = 1.3


@dataclass(frozen=True, slots=True)
class Configuration:
    comparison: str
    name: str
    ess_capacity: float
    hfc_capacity: float


@dataclass(frozen=True, slots=True)
class Policy:
    phase1_soc_threshold: float = 0.3
    phase1_lcoe_quantile: float = 0.6


DEFAULT_POLICY: Final = Policy()


CONFIGURATIONS: Final = (
    Configuration("Original component ratings", "ESS-only", 1500.0, 0.0),
    Configuration("Original component ratings", "HFC-only", 0.0, 1500.0),
    Configuration("Original component ratings", "Hybrid ESS–HFC", 1500.0, 1500.0),
    Configuration("Equal total storage (3 MWh)", "ESS-only", 3000.0, 0.0),
    Configuration("Equal total storage (3 MWh)", "HFC-only", 0.0, 3000.0),
    Configuration("Equal total storage (3 MWh)", "Hybrid ESS–HFC", 1500.0, 1500.0),
)


def run_configuration(
    hours: list[Hour], configuration: Configuration, policy: Policy = DEFAULT_POLICY
) -> tuple[list[dict[str, str | float]], dict[str, str | float]]:
    """Use the same P1 state transition and purchase accounting as the main case."""
    scenario = Scenario(
        ALPHA,
        1,
        Strategy.P1,
        phase1_soc_gate=policy.phase1_soc_threshold,
        phase1_lcoe_quantile=policy.phase1_lcoe_quantile,
        ess_capacity_kwh=configuration.ess_capacity,
        hfc_capacity_kwh=configuration.hfc_capacity,
    )
    run = run_scenario(hours, scenario)
    from emergency_validation import validate_run

    validate_run(run)
    records = [
        {
            "configuration": configuration.name,
            "comparison": configuration.comparison,
            "timestamp": step.timestamp,
            "demand_kwh": step.demand_kwh,
            "ess_supply_kwh": step.ess_emergency_kwh,
            "hfc_supply_kwh": step.hfc_kwh,
            "unserved_kwh": step.unserved_kwh,
            "operating_net_krw": step.operating_net_krw,
            "avoided_outage_krw": step.avoided_interruption_krw,
        }
        for step in run.steps
    ]
    totals: dict[str, str | float] = {
        "configuration": configuration.name,
        "comparison": configuration.comparison,
        "ess_capacity_kwh": configuration.ess_capacity,
        "hfc_capacity_kwh": configuration.hfc_capacity,
    }
    for field in (
        "demand_kwh",
        "ess_supply_kwh",
        "hfc_supply_kwh",
        "unserved_kwh",
        "operating_net_krw",
        "avoided_outage_krw",
    ):
        totals[field] = sum(float(record[field]) for record in records)
    totals["total_value_krw"] = float(totals["operating_net_krw"]) + float(
        totals["avoided_outage_krw"]
    )
    return records, totals


def main() -> None:
    """Run all single-truck ablations and save their hourly and aggregate results."""
    hours = load_hours(INPUT)
    outcomes = [run_configuration(hours, config) for config in CONFIGURATIONS]
    OUT.mkdir(exist_ok=True)
    for filename, rows in (
        (
            "asset_ablation_hourly.csv",
            [row for records, _ in outcomes for row in records],
        ),
        ("asset_ablation_summary.csv", [summary for _, summary in outcomes]),
    ):
        with (OUT / filename).open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target, fieldnames=list(rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
    summaries = [summary for _, summary in outcomes]
    plot_results(summaries)
    for row in summaries:
        print(row)


if __name__ == "__main__":
    main()

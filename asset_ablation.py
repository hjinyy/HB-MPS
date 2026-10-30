"""Reproducible single-truck ESS/HFC ablation using the repository's hourly inputs.

Mode 2 supply is bounded by onboard energy and output ratings. No auxiliary
truck or capital expenditure is assumed; all configurations face identical
industrial demand, prices, vehicle travel cost, and hourly time steps.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from asset_ablation_plot import plot_results

ROOT: Final = Path(__file__).resolve().parent
INPUT: Final = ROOT / "Data file" / "data_file.csv"
OUT: Final = ROOT / "results"
ALPHA: Final = 1.3
HFC_RATING: Final = 500.0
ESS_RATING: Final = 700.0
ESS_EFFICIENCY: Final = 0.95
H2_KWH_PER_KG: Final = 16.65
TRAVEL_H2_KG: Final = 0.08 * 1.7
ESS_WEAR_KRW_PER_KWH: Final = 50.0


@dataclass(frozen=True, slots=True)
class Hour:
    timestamp: str
    residential: float
    industrial: float
    solar: float
    lcoe: float
    smp: float
    h2_price: float


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


def load_hours(path: Path) -> list[Hour]:
    """Parse the measured 168-hour profile and its economic input columns."""
    hours: list[Hour] = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if not row["산업용 전력사용량(kWh)"]:
                continue
            hours.append(
                Hour(
                    timestamp=f"{row['날짜']}-{int(row['시간']):02d}",
                    residential=float(row["주택용 전력사용량(kWh)"]),
                    industrial=float(row["산업용 전력사용량(kWh)"]),
                    solar=float(row["E: 태양광 발전량(kWh)"]),
                    lcoe=float(row["LCOE=SMP+REC(원/kWh)"]),
                    smp=float(row["SMP(원/kWh)"]),
                    h2_price=float(row["수소 외부계통 충전 비용(원/kg)"]),
                )
            )
    if len(hours) != 168:
        raise ValueError(f"Expected 168 valid hourly records, found {len(hours)}")
    return hours


def run_configuration(
    hours: list[Hour], configuration: Configuration, policy: Policy = DEFAULT_POLICY
) -> tuple[list[dict[str, str | float]], dict[str, str | float]]:
    """Dispatch bounded onboard assets under the published mode priorities."""
    threshold = ALPHA * float(np.mean([hour.industrial for hour in hours]))
    high_lcoe = float(
        np.quantile([hour.lcoe for hour in hours], policy.phase1_lcoe_quantile)
    )
    low_smp = float(np.quantile([hour.smp for hour in hours], 0.25))
    voll = math.exp(-0.0000206 * 60**2 + 0.0227011 * 60 + 0.3018905) * 1000
    ess_capacity = configuration.ess_capacity
    h2_capacity = configuration.hfc_capacity / H2_KWH_PER_KG
    ess_min = 0.1 * ess_capacity
    ess_max = 0.9 * ess_capacity
    ess = 0.4 * ess_capacity
    h2 = 0.8 * h2_capacity
    records: list[dict[str, str | float]] = []

    for hour in hours:
        demand = max(hour.industrial - threshold, 0.0)
        ess_supply = 0.0
        hfc_supply = 0.0
        revenue = 0.0
        cost = 0.0

        if demand > 0:
            if h2_capacity > 0 and h2 > TRAVEL_H2_KG:
                hfc_supply = min(
                    demand, HFC_RATING, (h2 - TRAVEL_H2_KG) * H2_KWH_PER_KG
                )
                h2 -= hfc_supply / H2_KWH_PER_KG + TRAVEL_H2_KG
                cost += (hfc_supply / H2_KWH_PER_KG + TRAVEL_H2_KG) * hour.h2_price
            if ess_capacity > 0:
                ess_supply = min(
                    demand - hfc_supply,
                    ESS_RATING,
                    max(ess - ess_min, 0.0) * ESS_EFFICIENCY,
                )
                withdrawn = ess_supply / ESS_EFFICIENCY
                ess -= withdrawn
                cost += withdrawn * ESS_WEAR_KRW_PER_KWH
            if ess_supply > 0 and hfc_supply == 0:
                cost += TRAVEL_H2_KG * hour.h2_price
        elif h2_capacity > 0 and h2 / h2_capacity < 0.6:
            # Same off-event refill rule as the main model; fuel is costed at use.
            h2 = 0.9 * h2_capacity
        elif (
            ess_capacity > 0
            and hour.lcoe >= high_lcoe
            and ess / ess_capacity >= policy.phase1_soc_threshold
        ):
            withdrawn = min(ESS_RATING, max(ess - ess_min, 0.0))
            ess -= withdrawn
            revenue += withdrawn * ESS_EFFICIENCY * hour.lcoe
            cost += withdrawn * ESS_WEAR_KRW_PER_KWH + TRAVEL_H2_KG * hour.h2_price
        else:
            surplus = max(hour.solar - hour.residential - hour.industrial, 0.0)
            if surplus > 0:
                if ess_capacity > 0:
                    charged = min(
                        surplus, 300.0, max(ess_max - ess, 0.0) / ESS_EFFICIENCY
                    )
                    ess += charged * ESS_EFFICIENCY
                    surplus -= charged
                    cost += charged * ESS_WEAR_KRW_PER_KWH
                if h2_capacity > 0:
                    h2 += min(surplus / 55.0, h2_capacity - h2)
            elif ess_capacity > 0 and hour.smp <= low_smp:
                charged = min(300.0, max(ess_max - ess, 0.0) / ESS_EFFICIENCY)
                ess += charged * ESS_EFFICIENCY
                cost += charged * (hour.smp + ESS_WEAR_KRW_PER_KWH)

        records.append(
            {
                "configuration": configuration.name,
                "comparison": configuration.comparison,
                "timestamp": hour.timestamp,
                "demand_kwh": demand,
                "ess_supply_kwh": ess_supply,
                "hfc_supply_kwh": hfc_supply,
                "unserved_kwh": max(demand - ess_supply - hfc_supply, 0.0),
                "operating_net_krw": revenue - cost,
                "avoided_outage_krw": (ess_supply + hfc_supply) * voll,
            }
        )

    totals: dict[str, str | float] = {
        "configuration": configuration.name,
        "comparison": configuration.comparison,
        "ess_capacity_kwh": ess_capacity,
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
            writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    summaries = [summary for _, summary in outcomes]
    plot_results(summaries)
    for row in summaries:
        print(row)


if __name__ == "__main__":
    main()

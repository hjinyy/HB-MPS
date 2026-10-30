"""Shared hourly CSV input boundary for the operational simulations."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent
INPUT: Final = ROOT / "Data file" / "data_file.csv"


@dataclass(frozen=True, slots=True)
class Hour:
    timestamp: str
    residential: float
    industrial: float
    solar: float
    lcoe: float
    smp: float
    h2_price: float


def load_hours(path: Path) -> list[Hour]:
    """Parse the same valid 168 hourly rows used by the original main model."""
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

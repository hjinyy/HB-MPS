"""Build manuscript Table III from the unchanged emergency-dispatch results.

Code P2 (30% reserve) is manuscript P1; code P1 is proposed manuscript P2.
"""

from __future__ import annotations

import csv
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
SOURCE = RESULTS / "emergency_dispatch_summary.csv"
OUTPUT_CSV = RESULTS / "table_iii_emergency_dispatch_comparison.csv"
OUTPUT_MD = RESULTS / "table_iii_emergency_dispatch_comparison.md"

PAPER_TO_CODE = (
    ("P0", "P0", None),
    ("P1", "P2", 0.3),
    ("P2", "P1", None),
)
INDICATORS = (
    ("HFC supply (MWh)", "hfc_supply_kwh", 1_000),
    ("ESS emergency supply (MWh)", "ess_emergency_supply_kwh", 1_000),
    ("Residual unserved (MWh)", "residual_unserved_kwh", 1_000),
    ("Operating net benefit (M KRW)", "operating_net_krw", 1_000_000),
    ("Avoided interruption benefit (M KRW)", "avoided_interruption_krw", 1_000_000),
    ("Net societal benefit (M KRW)", "net_societal_benefit_krw", 1_000_000),
)


def table_rows() -> list[dict[str, str]]:
    with SOURCE.open(newline="", encoding="utf-8") as source:
        source_rows = list(csv.DictReader(source))

    selected = {}
    for paper, code, reserve in PAPER_TO_CODE:
        matches = [
            row
            for row in source_rows
            if float(row["alpha"]) == 1.3
            and int(row["available_trucks"]) == 1
            and row["strategy"] == code
            and (float(row["reserve_soc"]) if row["reserve_soc"] else None) == reserve
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one source run for manuscript {paper}, found {len(matches)}")
        selected[paper] = matches[0]

    rows = [{"Indicator": "Emergency SOC floor", "P0": "-", "P1": "0.3", "P2": "0.1"}]
    for indicator, field, divisor in INDICATORS:
        values = {}
        for paper in ("P0", "P1", "P2"):
            value = float(selected[paper][field]) / divisor
            values[paper] = "0" if value == 0 else f"{value:.3f}"
        rows.append({"Indicator": indicator, **values})
    return rows


def main() -> None:
    rows = table_rows()
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=("Indicator", "P0", "P1", "P2"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Table III. Comparison of emergency dispatch strategies under tight grid conditions",
        "",
        "Grid margin factor α = 1.3; one HB-MPS truck. P0: HFC-only emergency dispatch; "
        "P1: reserve-protected ESS backup (30% SOC floor); "
        "P2: proposed HFC-first dispatch with ESS backup.",
        "",
        "| Indicator | P0 | P1 | P2 |",
        "| --- | ---: | ---: | ---: |",
        *(f"| {row['Indicator']} | {row['P0']} | {row['P1']} | {row['P2']} |" for row in rows),
        "",
        "Paper labels map to code results as P0 → P0, P1 → P2 (reserve SOC 0.3), "
        "and P2 → P1. The source simulation data and code strategy identifiers are unchanged.",
        "",
    ]
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

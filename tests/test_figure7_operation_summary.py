"""Check the three exclusive mode shares against the saved P1 week."""

from __future__ import annotations

import csv
from pathlib import Path

from figure7_operation_summary import calculate_usage

RESULTS = Path(__file__).resolve().parents[1] / "results"


def test_operating_modes_partition_each_168_hour_scenario() -> None:
    # Given the existing P1 hourly results used by the manuscript figures.
    with (RESULTS / "p1_main_hourly.csv").open(newline="", encoding="utf-8") as source:
        saved = list(csv.DictReader(source))

    # When Figure 7 recomputes each scenario's mode distribution.
    summaries = calculate_usage()

    # Then its three mutually exclusive modes match the saved week.
    assert len(summaries) == 3
    for summary in summaries:
        rows = [row for row in saved if float(row["Alpha"]) == summary.alpha]
        assert len(rows) == summary.hours == 168
        assert sum(summary.mode_hours) == 168
        assert summary.mode_hours[1] == sum(row["Mode"] == "PHASE 2" for row in rows)
        assert summary.mode_hours[2] == sum(row["Mode"] == "STANDBY" for row in rows)

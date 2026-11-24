"""Check that the new mode and action counts follow the saved P1 week."""

from __future__ import annotations

import csv
from pathlib import Path

from figure7_operation_summary import ACTIONS, calculate_usage

RESULTS = Path(__file__).resolve().parents[1] / "results"


def test_operating_modes_partition_each_168_hour_scenario() -> None:
    # Given the same stored P1 runs used by the manuscript's main figures.
    with (RESULTS / "p1_main_hourly.csv").open(newline="", encoding="utf-8") as source:
        saved = list(csv.DictReader(source))

    # When physical action flags are counted for Figure 7.
    summaries = calculate_usage()

    # Then each mode is exclusive and agrees with the existing hourly results.
    assert len(summaries) == 3
    assert len(ACTIONS) == 10
    for summary in summaries:
        rows = [row for row in saved if float(row["Alpha"]) == summary.alpha]
        assert len(rows) == summary.hours == 168
        assert sum(summary.mode_hours) == 168
        assert summary.mode_hours[1] == sum(row["Mode"] == "PHASE 2" for row in rows)
        assert summary.mode_hours[2] == sum(row["Mode"] == "STANDBY" for row in rows)
        assert summary.action_hours[6] == summary.mode_hours[2]
        assert len(summary.action_hours) == 10
        assert all(0 <= count <= 168 for count in summary.action_hours)


def test_auxiliary_actions_and_overlap_are_counted_separately() -> None:
    # Given the tight-grid P1 run, where auxiliary HFCs and refills operate.
    tight = calculate_usage()[0]

    # When auxiliary action hours are examined separately from main-truck hours.
    main_hfc_hours = tight.action_hours[7]
    auxiliary_hfc_hours = tight.action_hours[8]

    # Then the counts reflect actual truck use and concurrent actions.
    assert tight.action_hours[5] == 4
    assert main_hfc_hours == 12
    assert auxiliary_hfc_hours == 20
    assert tight.action_hours[2] > 0
    assert tight.action_hours[1] > 0

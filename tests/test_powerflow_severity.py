"""Severity ranking and fleet placement without changing the P1 energy path."""

from __future__ import annotations

import numpy as np

from powerflow_validation_severity import place_trucks, severity_scores


def test_weaker_voltage_wins_when_local_emergency_demands_are_equal() -> None:
    # Given two industrial buses with the same positive excess demand.
    demand = np.zeros(9)
    demand[:2] = 0.1
    voltage = np.full(9, 0.98)
    voltage[0] = 0.94
    voltage[1] = 0.92

    # When the documented half-demand, half-voltage severity is calculated.
    scores = severity_scores(demand, voltage)

    # Then the weaker bus ranks first, while voltage alone creates no supply.
    assert scores[1] > scores[0] > scores[2]


def test_each_truck_uses_one_bus_and_all_p1_supply_is_preserved() -> None:
    # Given a top-priority bus with less demand than the main truck can supply.
    demand = np.zeros(9)
    demand[:2] = (0.02, 0.2)
    scores = np.zeros(9)
    scores[:2] = (1.0, 0.8)
    truck_hfc = np.array((0.03, 0.1, 0.0, 0.0, 0.0))

    # When the main HFC plus ESS and one auxiliary HFC truck are placed.
    injection, main_bus, buses = place_trucks(demand, scores, truck_hfc, 0.01)

    # Then the next truck moves to the next unmet bus; no output is lost.
    assert main_bus == 18
    assert buses == (18, 17)
    assert np.isclose(injection[0], 0.04)
    assert np.isclose(injection[1], 0.1)
    assert np.isclose(injection.sum(), truck_hfc.sum() + 0.01)

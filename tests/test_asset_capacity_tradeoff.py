"""Reproduce the existing Fig. 8–9 anchors in the 11-case capacity sweep."""

from __future__ import annotations

import math

from asset_ablation import CONFIGURATIONS, run_configuration
from asset_capacity_tradeoff import calculate_results, is_non_dominated
from emergency_dispatch_model import InvalidScenario, Scenario, Strategy
from hb_inputs import INPUT, load_hours


def test_capacity_sweep_recovers_existing_asset_comparisons() -> None:
    # Given the original 168-hour inputs and equal-3-MWh anchor configurations.
    hours = load_hours(INPUT)
    expected = [run_configuration(hours, config)[1] for config in CONFIGURATIONS[3:]]

    # When the full 0–100% ESS sweep is simulated at α=1.3.
    results = calculate_results()

    # Then its original endpoint and 50:50 results match Fig. 8–9 exactly.
    for index, summary in ((0, expected[1]), (5, expected[2]), (10, expected[0])):
        row = results[index]
        assert math.isclose(row.ess_capacity_mwh + row.hfc_capacity_mwh, 3.0)
        assert math.isclose(
            row.emergency_energy_mwh,
            (float(summary["ess_supply_kwh"]) + float(summary["hfc_supply_kwh"]))
            / 1000,
        )
        assert math.isclose(
            row.operating_net_benefit_mkrw,
            float(summary["operating_net_krw"]) / 1e6,
        )
    assert len(results) == 11
    assert all(is_non_dominated(row, results) for row in results)


def test_scenario_rejects_unrequested_capacity_increment() -> None:
    # Given a capacity outside the 0.3 MWh sweep resolution.
    # When the experiment tries to construct that scenario.
    try:
        Scenario(1.3, 1, Strategy.P1, ess_capacity_kwh=450.0, hfc_capacity_kwh=2550.0)
    except InvalidScenario:
        # Then the model refuses to silently mix capacity grids.
        return
    raise AssertionError("The unsupported capacity increment was accepted")

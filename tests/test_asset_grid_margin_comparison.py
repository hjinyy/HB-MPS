"""Check that the equal-storage comparison actually varies grid margin."""

from __future__ import annotations

from asset_ablation import CONFIGURATIONS, run_configuration
from hb_inputs import INPUT, load_hours


def test_asset_comparison_changes_emergency_demand_with_alpha() -> None:
    # Given the same measured week and the same 3 MWh hybrid asset.
    hours = load_hours(INPUT)
    hybrid = CONFIGURATIONS[5]

    # When only the grid margin factor changes.
    _, tight = run_configuration(hours, hybrid, alpha=1.3)
    _, loose = run_configuration(hours, hybrid, alpha=1.8)

    # Then the loose grid has no emergency demand or supply in this dataset.
    assert float(tight["demand_kwh"]) > 0
    assert float(loose["demand_kwh"]) == 0
    assert float(loose["ess_supply_kwh"]) + float(loose["hfc_supply_kwh"]) == 0

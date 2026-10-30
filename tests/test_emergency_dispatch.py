"""Behavior checks for finite fuel, emergency reserve, and purchase accounting."""

from __future__ import annotations

import math

from asset_ablation import Hour
from emergency_dispatch import (
    ESS_CAPACITY,
    ESS_MIN_SOC,
    H2_CAPACITY_KG,
    HFC_OUTPUT_KWH,
    run_scenario,
)
from emergency_dispatch_experiment import validate_run
from emergency_dispatch_model import Scenario, Strategy


def hour(index: int, industrial: float, price: float = 100.0) -> Hour:
    """Build a physically simple hour with no charging surplus."""
    return Hour(str(index), 0.0, industrial, 0.0, 300.0, price, 1000.0)


def test_ess_backup_reduces_unserved_when_hfc_rating_binds() -> None:
    # Given a spike whose residual demand exceeds one HFC's hourly rating.
    hours = [hour(0, 1000.0), hour(1, 0.0), hour(2, 0.0)]

    # When the same path is run under all three dispatch rules.
    p0 = run_scenario(hours, Scenario(1.3, 1, Strategy.P0))
    p1 = run_scenario(hours, Scenario(1.3, 1, Strategy.P1))
    p2 = run_scenario(hours, Scenario(1.3, 1, Strategy.P2, 0.4))

    # Then unrestricted ESS covers the shortfall while a 0.4 reserve blocks it.
    assert p0.steps[0].hfc_kwh == HFC_OUTPUT_KWH
    assert p0.steps[0].ess_emergency_kwh == 0
    assert p1.steps[0].ess_emergency_kwh > 0
    assert p1.steps[0].unserved_kwh < p0.steps[0].unserved_kwh
    assert p2.steps[0].ess_emergency_kwh == 0
    assert p2.steps[0].soc_end == 0.4
    for run in (p0, p1, p2):
        validate_run(run)


def test_finite_hydrogen_inventory_limits_repeated_emergencies() -> None:
    # Given consecutive spikes with no opportunity to refill until later.
    hours = [hour(index, 3000.0) for index in range(20)] + [
        hour(index, 0.0) for index in range(20, 100)
    ]

    # When one HFC truck responds without ESS emergency backup.
    run = run_scenario(hours, Scenario(1.3, 1, Strategy.P0))

    # Then its onboard hydrogen and hourly output constrain all deliveries.
    assert run.steps[0].hfc_kwh == HFC_OUTPUT_KWH
    assert run.steps[19].hfc_kwh == 0
    assert run.steps[19].unserved_kwh > 0
    assert all(step.hfc_kwh <= HFC_OUTPUT_KWH for step in run.steps)
    assert all(step.h2_end_kg >= -1e-9 for step in run.steps)
    validate_run(run)


def test_external_refill_is_costed_once_and_soc_respects_minimum() -> None:
    # Given high initial emergency demand followed by cheap off-event hours.
    hours = [hour(0, 3000.0)] + [hour(index, 0.0) for index in range(1, 12)]

    # When P1 supplies HFC and ESS energy, then replenishes hydrogen.
    run = run_scenario(hours, Scenario(1.3, 1, Strategy.P1))

    # Then purchase expense follows only external refill, and inventory stays valid.
    assert all(
        math.isclose(step.h2_purchase_krw, step.external_h2_kg * 1000.0)
        for step in run.steps
    )
    assert any(
        step.consumed_h2_kg > 0 and step.h2_purchase_krw == 0 for step in run.steps
    )
    assert any(step.external_h2_kg > 0 for step in run.steps)
    assert all(step.soc_end >= ESS_MIN_SOC - 1e-9 for step in run.steps)
    assert all(step.h2_end_kg <= H2_CAPACITY_KG + 1e-9 for step in run.steps)
    assert run.steps[0].ess_emergency_kwh <= (0.4 - ESS_MIN_SOC) * ESS_CAPACITY * 0.95
    validate_run(run)
